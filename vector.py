"""
Vector Database Management - Chroma + Ollama Embeddings
Chunking thông minh theo cấu trúc Điều/Khoản cho văn bản pháp quy VN

Bugs đã fix (test với QĐ 2786/QĐ-HVNH):
  #1 - Regex tên văn bản: ưu tiên "Về việc ban hành", fallback "QUY ĐỊNH\n"
  #2 - Ngày ban hành: tìm trong body text, fallback docx core properties
  #3 - Điều 9 bị thiếu: phát hiện và cảnh báo khi file không đầy đủ
  #4 - Ngưỡng "có bảng" 2000 ký tự quá thấp → nâng lên 3500
  #5 - _RE_KHOAN bỏ sót khoản a./b./c. → thêm pattern đầy đủ
  #6 - File đầy đủ có 2 phần QUYẾT ĐỊNH (Điều 1-3) + QUY ĐỊNH (Điều 1-9)
       → tự động tách, chỉ chunk phần QUY ĐỊNH, lấy metadata từ QUYẾT ĐỊNH
"""
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_community.document_loaders import DirectoryLoader, Docx2txtLoader
from langchain_core.documents import Document
import os
import re
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


# ==========================================
# CẤU HÌNH
# ==========================================
EMBEDDINGS = OllamaEmbeddings(model="nomic-embed-text")   # bge-m3 tốt hơn nomic cho tiếng Việt
DB_LOCATION = "./chroma_langchain_db"
WORD_FOLDER = "./data/processed"
COLLECTION_NAME = "quy_dinh_hvnh"

# Điều dài hơn ngưỡng này → coi là CÓ BẢNG (không tách khoản)
# FIX #4: 2000 quá thấp, Điều 2 (giải thích từ ngữ) bị gắn nhầm
TABLE_THRESHOLD = 3500

# FIX #7: Context window của embedding model
# bge-m3 / nomic-embed-text tối đa ~8192 tokens ≈ 6000 ký tự tiếng Việt
# Đặt an toàn 3000 để trừ context header (~200 ký tự) và có margin
MAX_EMBED_CHARS = 3000


# ==========================================
# SMART CHUNKING - THEO CẤU TRÚC ĐIỀU/KHOẢN
# ==========================================

# Pattern nhận diện Điều - phần tử gốc của phân cấp
_RE_DIEU = re.compile(
    r"(Điều\s+\d+[\.:].*?)(?=Điều\s+\d+[\.:]|$)",
    re.DOTALL
)

# FIX #5: Bắt cả khoản số (1. 2. 3.) lẫn khoản chữ (a. b. c.)
# Khoản chữ trong pandoc output thường có dạng "a\." hoặc "a."
_RE_KHOAN_SO  = re.compile(r"(?:^|\n)(\d+\.\s.+?)(?=\n\d+\.\s|\n[a-z]\\?\.\s|\Z)", re.DOTALL)
_RE_KHOAN_CHU = re.compile(r"(?:^|\n)([a-z]\\?\.\s.+?)(?=\n[a-z]\\?\.\s|\n\d+\.\s|\Z)", re.DOTALL)

# Metadata extraction
_RE_SO_HIEU = re.compile(r"Số[:\s]*([\w/\-]+(?:QĐ|NQ|TB|CV)[^\s]*)")
_RE_NGAY    = re.compile(r"(?:ngày|Hà Nội,\s*ngày)\s+(\d+\s+tháng\s+\d+\s+năm\s+\d{4})")

# Header/footer thừa cần loại bỏ
_NOISE_PATTERNS = [
    r"NGÂN HÀNG NHÀ NƯỚC VIỆT NAM\s*\n.*?HỌC VIỆN NGÂN HÀNG\s*\n",
    r"CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\s*\nĐộc lập.*?Hạnh phúc\s*\n",
    r"KT\.\s*GIÁM ĐỐC.*?(?:\n.*?){0,3}(?=Điều|\Z)",
    r"Nơi nhận:.*?Lưu:.*?\n",
    r"\(Đã ký\)",
    r"\*\*\s*\*\*",          # bold rỗng từ pandoc markdown
    r"\\$",                  # dấu \ cuối dòng từ pandoc
]


def _clean_text(text: str) -> str:
    """Loại bỏ header/footer lặp và chuẩn hóa khoảng trắng."""
    for p in _NOISE_PATTERNS:
        text = re.sub(p, "", text, flags=re.DOTALL | re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)   # bỏ bold markdown
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _read_docx_properties(docx_path: str) -> dict:
    """
    FIX #2: Đọc metadata từ docx core properties khi không thấy trong body text.
    docProps/core.xml chứa: title, created, modified, creator...
    """
    props = {}
    try:
        with zipfile.ZipFile(docx_path) as z:
            if "docProps/core.xml" not in z.namelist():
                return props
            tree = ET.fromstring(z.read("docProps/core.xml"))
            ns = {
                "dc":      "http://purl.org/dc/elements/1.1/",
                "cp":      "http://schemas.openxmlformats.org/package/2006/metadata/core-properties",
                "dcterms": "http://purl.org/dc/terms/",
            }
            title   = tree.find(".//dc:title", ns)
            created = tree.find(".//dcterms:created", ns)
            subject = tree.find(".//dc:subject", ns)

            if title   is not None and title.text:
                props["title"]   = title.text.strip()
            if subject is not None and subject.text:
                props["subject"] = subject.text.strip()
            if created is not None and created.text:
                # ISO format: 2023-09-22T00:00:00Z → "22/09/2023"
                dt = created.text[:10]   # "2023-09-22"
                parts = dt.split("-")
                if len(parts) == 3:
                    props["created"] = f"{parts[2]}/{parts[1]}/{parts[0]}"
    except Exception:
        pass
    return props


def _extract_doc_metadata(text: str, source_path: str = "") -> dict:
    """
    Trích xuất metadata từ body text + docx properties.
    FIX #1: Regex tên văn bản lấy đúng dòng sau "QUY ĐỊNH"
    FIX #2: Fallback ngày từ docx core properties
    """
    so_hieu_m = _RE_SO_HIEU.search(text)
    ngay_m    = _RE_NGAY.search(text)

    # FIX #1 + #6: Ưu tiên "Về việc ban hành" (có trong file đầy đủ)
    # Fallback: dòng sau "QUY ĐỊNH\n" (file chỉ có phần phụ lục)
    ten_vb_m = re.search(r"Về việc ban hành (.+?)(?:\n|$)", text, re.IGNORECASE)
    if not ten_vb_m:
        ten_vb_m = re.search(r"QUY ĐỊNH\s*\n+(.+?)(?:\n|\\|$)", text, re.IGNORECASE)

    ten_van_ban = ten_vb_m.group(1).strip().rstrip("\\") if ten_vb_m else ""

    # Làm sạch tên (bỏ ký tự thừa từ pandoc)
    ten_van_ban = re.sub(r"\s+", " ", ten_van_ban).strip()

    # FIX #2: Nếu không tìm thấy ngày trong text → đọc từ docx properties
    ngay_str = ngay_m.group(1).strip() if ngay_m else ""
    if not ngay_str and source_path:
        props = _read_docx_properties(source_path)
        ngay_str = props.get("created", "Không rõ")
        if not ten_van_ban:
            ten_van_ban = props.get("title", "") or props.get("subject", "")

    if not ten_van_ban:
        ten_van_ban = Path(source_path).stem.replace("_", " ") if source_path else "Không rõ"

    return {
        "source":         source_path,
        "so_hieu":        so_hieu_m.group(1).strip() if so_hieu_m else Path(source_path).stem,
        "ngay_ban_hanh":  ngay_str or "Không rõ",
        "co_quan":        "Học viện Ngân hàng",
        "ten_van_ban":    ten_van_ban,
        "hieu_luc":       "true",
    }


def _validate_document(text: str, source_name: str) -> list[str]:
    """
    FIX #3: Kiểm tra tính đầy đủ của văn bản trước khi chunk.
    Trả về danh sách cảnh báo nếu phát hiện bất thường.
    """
    warnings = []

    dieus_found = re.findall(r"Điều\s+(\d+)[\.:]", text)
    if not dieus_found:
        warnings.append(f"⚠️  [{source_name}] Không tìm thấy cấu trúc Điều/Khoản nào!")
        return warnings

    nums = sorted(set(int(d) for d in dieus_found))

    # Kiểm tra thiếu Điều (gap trong dãy số)
    expected = list(range(nums[0], nums[-1] + 1))
    missing  = [n for n in expected if n not in nums]
    if missing:
        warnings.append(
            f"⚠️  [{source_name}] Thiếu Điều: {missing} "
            f"(tìm thấy {nums[0]}→{nums[-1]}). "
            f"File có thể là bản phụ lục không đầy đủ!"
        )

    # Cảnh báo nếu kết thúc đột ngột (không có Điều khoản thi hành)
    last_dieu = nums[-1] if nums else 0
    last_text = text[text.rfind(f"Điều {last_dieu}"):]
    if len(last_text.strip()) < 100:
        warnings.append(f"⚠️  [{source_name}] Điều cuối (Điều {last_dieu}) có nội dung quá ngắn!")

    return warnings


def _build_context_header(meta: dict, dieu_so: str, dieu_title: str) -> str:
    """
    Prepend context vào mỗi chunk trước khi embed.
    Contextual Retrieval — giúp model hiểu ngữ cảnh khi tìm kiếm.
    """
    return (
        f"Văn bản: {meta['ten_van_ban']}\n"
        f"Số hiệu: {meta['so_hieu']} | Ngày: {meta['ngay_ban_hanh']}\n"
        f"Điều {dieu_so}: {dieu_title}\n"
        f"{'─' * 40}\n"
    )


def _split_khoan(dieu_text: str) -> list[str]:
    """
    FIX #5: Tách khoản, bắt cả hai loại:
    - Khoản số: "1. ...", "2. ...", "3. ..."
    - Khoản chữ: "a. ...", "b. ...", "c. ..."  (dạng pandoc: "a\\. ...")
    Ưu tiên tách theo khoản số (cấp 1), rồi mới đến khoản chữ (cấp 2).
    """
    # Thử tách theo khoản số trước
    khoans = _RE_KHOAN_SO.findall(dieu_text)
    if khoans and len(khoans) >= 2:
        return [k.strip() for k in khoans if len(k.strip()) >= 40]

    # Không có khoản số → thử khoản chữ
    khoans = _RE_KHOAN_CHU.findall(dieu_text)
    if khoans and len(khoans) >= 2:
        return [k.strip() for k in khoans if len(k.strip()) >= 40]

    return []


def _split_sections(text: str) -> tuple[str, str]:
    """
    FIX #6: File đầy đủ có 2 phần riêng biệt:
    ┌─ PHẦN 1: QUYẾT ĐỊNH (Điều 1-3)
    │   → Chứa metadata: số hiệu, ngày ký, căn cứ pháp lý
    │   → KHÔNG chunk — chỉ dùng để trích metadata
    └─ PHẦN 2: QUY ĐỊNH (Điều 1-9)
        → Nội dung thực tế cần chunk
        → Bắt đầu từ "QUY ĐỊNH\n..." hoặc "Điều 1. Phạm vi"

    File chỉ có phụ lục (không có QUYẾT ĐỊNH) → trả về ("", toàn bộ text)
    """
    # Tìm ranh giới: QUY ĐỊNH kèm theo nội dung Điều 1 Phạm vi
    quy_dinh_m = re.search(
        r"\nQUY ĐỊNH\s*\n.{0,300}?(?:Ban hành kèm|Điều 1\.\s*Phạm vi)",
        text, re.DOTALL
    )
    if quy_dinh_m:
        return text[:quy_dinh_m.start()].strip(), text[quy_dinh_m.start():].strip()

    # Fallback: tách tại "Điều 1. Phạm vi"
    m = re.search(r"(?:^|\n)(Điều 1\.\s*Phạm vi)", text, re.MULTILINE)
    if m:
        return text[:m.start()].strip(), text[m.start():].strip()

    # Không tìm thấy ranh giới → coi toàn bộ là QUY ĐỊNH
    return "", text


def _has_real_table(text: str) -> bool:
    """Phát hiện bảng thực sự (có ký tự | hoặc pattern cột)."""
    return bool(re.search(r"\|.+\|", text))


def _safe_embed_text(full_text: str, max_chars: int = MAX_EMBED_CHARS) -> list[str]:
    """
    FIX #7: Chia text dài thành các đoạn embed an toàn.

    Vấn đề: bge-m3 có context limit ~8192 tokens. Điều 5 (bảng IELTS/TOEFL)
    dài 5731 ký tự → vượt limit → lỗi ResponseError 400.

    Chiến lược:
    - Text <= max_chars → trả về nguyên 1 đoạn
    - Text > max_chars → tách theo đoạn (\n\n), giữ overlap 1 đoạn
      để không mất ngữ cảnh ranh giới giữa 2 sub-chunk.
    """
    if len(full_text) <= max_chars:
        return [full_text]

    parts = full_text.split("\n\n")
    sub_chunks = []
    current = ""

    for part in parts:
        candidate = (current + "\n\n" + part).strip() if current else part
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                sub_chunks.append(current.strip())
            # Nếu 1 đoạn đơn vẫn > max_chars (bảng rất dài) → cắt cứng
            if len(part) > max_chars:
                for i in range(0, len(part), max_chars - 100):
                    sub_chunks.append(part[i: i + max_chars].strip())
                current = ""
            else:
                current = part

    if current:
        sub_chunks.append(current.strip())

    return sub_chunks if sub_chunks else [full_text[:max_chars]]


def _split_by_dieu(full_text: str, doc_meta: dict) -> list[Document]:
    """
    Chiến lược Parent-Child chunking:

    ┌─ PARENT (dieu)    → Toàn bộ 1 Điều → LLM đọc để trả lời
    │   └─ CHILD (khoan) → Từng Khoản nhỏ → tìm kiếm chính xác
    │
    └─ Điều có bảng thực sự → không tách (giữ nguyên làm parent)

    FIX #4: Ngưỡng TABLE_THRESHOLD = 3500 (thay vì 2000 cũ)
    FIX #5: _split_khoan xử lý cả khoản số lẫn khoản chữ
    """
    chunks: list[Document] = []

    # Tìm phần nội dung QUY ĐỊNH
    qd_start = re.search(r"QUY ĐỊNH\b|(?:^|\n)Điều\s+1[\.:]", full_text, re.MULTILINE)
    body = full_text[qd_start.start():] if qd_start else full_text

    for match in _RE_DIEU.finditer(body):
        dieu_text = match.group(1).strip()
        if len(dieu_text) < 20:
            continue

        hm = re.match(r"Điều\s+(\d+)[\.:]?\s*(.*?)(?:\n|$)", dieu_text)
        if not hm:
            continue

        dieu_so    = hm.group(1)
        dieu_title = hm.group(2).strip().rstrip("\\").strip()
        ctx_header = _build_context_header(doc_meta, dieu_so, dieu_title)
        parent_id  = f"{doc_meta['so_hieu']}__dieu_{dieu_so}"

        # ── PARENT CHUNK ──────────────────────────────────────
        # FIX #7: Chunk quá dài → tách thành nhiều sub-chunk để embed
        # Mỗi sub-chunk đều mang đủ context header + lưu full_text trong metadata
        full_embed_text = ctx_header + dieu_text
        sub_embed_list  = _safe_embed_text(full_embed_text)
        is_big          = len(sub_embed_list) > 1
        has_tbl         = _has_real_table(dieu_text)

        for si, sub_text in enumerate(sub_embed_list):
            sub_id = parent_id if not is_big else f"{parent_id}_p{si+1}"
            chunks.append(Document(
                page_content=sub_text,
                metadata={
                    **doc_meta,
                    "chunk_id":    sub_id,
                    "chunk_type":  "dieu",
                    "dieu_so":     dieu_so,
                    "dieu_title":  dieu_title,
                    "level":       "parent",
                    "parent_id":   "",
                    "char_count":  str(len(dieu_text)),
                    "has_table":   str(has_tbl),
                    "sub_total":   str(len(sub_embed_list)),
                    "sub_index":   str(si + 1),
                    # Lưu full text để retriever trả về đủ nội dung
                    "full_text":   dieu_text[:2000],
                }
            ))

        # Điều có bảng thực sự hoặc cực dài → KHÔNG tách khoản
        if has_tbl or len(dieu_text) > TABLE_THRESHOLD:
            continue

        # ── CHILD CHUNKS (Khoản) ──────────────────────────────
        khoans = _split_khoan(dieu_text)
        for j, khoan_text in enumerate(khoans):
            chunks.append(Document(
                page_content=(
                    ctx_header
                    + f"[Khoản {j+1} của Điều {dieu_so}]\n"
                    + khoan_text
                ),
                metadata={
                    **doc_meta,
                    "chunk_id":   f"{parent_id}__khoan_{j+1}",
                    "chunk_type": "khoan",
                    "dieu_so":    dieu_so,
                    "dieu_title": dieu_title,
                    "khoan_so":   str(j + 1),
                    "level":      "child",
                    "parent_id":  parent_id,
                    "char_count": str(len(khoan_text)),
                    "has_table":  "false",
                }
            ))

    return chunks


def smart_chunk_documents(documents: list[Document]) -> list[Document]:
    """
    Xử lý toàn bộ documents:
    - Văn bản có cấu trúc Điều/Khoản → hierarchical chunking
    - Văn bản khác → fallback RecursiveCharacterTextSplitter
    """
    all_chunks:   list[Document] = []
    fallback_docs: list[Document] = []

    for doc in documents:
        source = doc.metadata.get("source", "")
        text   = _clean_text(doc.page_content)

        # FIX #6: Tách QUYẾT ĐỊNH (metadata) vs QUY ĐỊNH (content)
        phan_quyet_dinh, phan_quy_dinh = _split_sections(text)
        # Trích metadata từ toàn bộ text (để lấy ngày, số hiệu từ phần QUYẾT ĐỊNH)
        meta = _extract_doc_metadata(text, source)

        if phan_quyet_dinh:
            print(f"   📋 {Path(source).name}: phát hiện file đầy đủ "
                  f"(QUYẾT ĐỊNH {len(phan_quyet_dinh)} ký tự + QUY ĐỊNH {len(phan_quy_dinh)} ký tự)")
        
        content_to_chunk = phan_quy_dinh if phan_quy_dinh else text

        # FIX #3: Kiểm tra tính đầy đủ
        warnings = _validate_document(content_to_chunk, Path(source).name)
        for w in warnings:
            print(w)

        if re.search(r"Điều\s+\d+[\.:]", content_to_chunk):
            dieu_chunks = _split_by_dieu(content_to_chunk, meta)
            all_chunks.extend(dieu_chunks)

            parents  = sum(1 for c in dieu_chunks if c.metadata.get("level") == "parent")
            children = sum(1 for c in dieu_chunks if c.metadata.get("level") == "child")
            print(f"   📌 {Path(source).name}: "
                  f"{parents} điều + {children} khoản = {len(dieu_chunks)} chunks")
        else:
            doc.page_content = content_to_chunk
            doc.metadata.update(meta)
            doc.metadata.update({"chunk_type": "paragraph", "level": "flat"})
            fallback_docs.append(doc)
            print(f"   📄 {Path(source).name}: fallback mode")

    if fallback_docs:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=150,
            separators=["\n\n", "\n", ".", " "],
        )
        fb_chunks = splitter.split_documents(fallback_docs)
        all_chunks.extend(fb_chunks)
        print(f"   📄 Fallback: {len(fb_chunks)} chunks")

    return all_chunks


# ==========================================
# HELPER FUNCTIONS (giữ nguyên API cũ)
# ==========================================

def delete_database():
    """Xóa hoàn toàn database cũ."""
    if os.path.exists(DB_LOCATION):
        try:
            shutil.rmtree(DB_LOCATION)
            print(f"✅ Đã xóa database cũ tại: {DB_LOCATION}")
            return True
        except Exception as e:
            print(f"❌ Lỗi khi xóa database: {e}")
            return False
    else:
        print(f"ℹ️ Database chưa tồn tại tại: {DB_LOCATION}")
        return True


def load_documents_from_folder(folder_path: str) -> list[Document] | None:
    """
    Load tất cả file .docx từ thư mục.
    Tự động bỏ qua:
      - ~$*.docx  : file tạm của Word (đang mở) → BadZipFile
      - ~*.docx   : file tạm khác của Office
      - file rỗng : 0 bytes
    """
    from pathlib import Path
    import zipfile

    folder = Path(folder_path)
    print(f"⏳ Đang tải file Word từ: {folder_path}")

    # Tìm tất cả .docx, loại ngay file tạm theo tên
    all_files  = list(folder.glob("**/*.docx"))
    skip_temp  = [f for f in all_files if f.name.startswith("~$") or f.name.startswith("~")]
    valid_files = [f for f in all_files if f not in skip_temp]

    if skip_temp:
        print(f"⚠️  Bỏ qua {len(skip_temp)} file tạm của Word:")
        for f in skip_temp:
            print(f"    ✗ {f.name}")

    # Kiểm tra từng file có phải docx hợp lệ không (zip archive)
    good_files, bad_files = [], []
    for f in valid_files:
        if f.stat().st_size == 0:
            bad_files.append((f, "file rỗng (0 bytes)"))
            continue
        try:
            with zipfile.ZipFile(f):
                pass
            good_files.append(f)
        except zipfile.BadZipFile:
            bad_files.append((f, "không phải file docx hợp lệ"))

    if bad_files:
        print(f"⚠️  Bỏ qua {len(bad_files)} file lỗi:")
        for f, reason in bad_files:
            print(f"    ✗ {f.name} → {reason}")

    if not good_files:
        print(f"❌ Không tìm thấy file .docx hợp lệ nào trong '{folder_path}'")
        return None

    print(f"📂 Đang load {len(good_files)} file hợp lệ...")
    documents = []
    for f in good_files:
        try:
            doc = Docx2txtLoader(str(f)).load()
            documents.extend(doc)
            print(f"   ✅ {f.name}")
        except Exception as e:
            print(f"   ❌ {f.name} → lỗi khi load: {e}")

    if not documents:
        print(f"❌ Không load được nội dung từ file nào!")
        return None

    print(f"\n✅ Đã tải {len(documents)} file Word thành công")
    return documents


def split_documents(documents: list[Document]) -> list[Document]:
    """Chia nhỏ documents bằng smart chunking."""
    print("✂️  Đang chunking thông minh theo cấu trúc Điều/Khoản...")
    chunks = smart_chunk_documents(documents)

    type_counts: dict[str, int] = {}
    for c in chunks:
        t = c.metadata.get("chunk_type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    print(f"\n✅ Tổng cộng: {len(chunks)} chunks")
    for t, n in type_counts.items():
        icon = {"dieu": "📌", "khoan": "  └─", "paragraph": "📄"}.get(t, "📄")
        print(f"   {icon} {t}: {n}")
    return chunks


def create_vector_store(chunks: list[Document] | None = None,
                        reset: bool = False) -> Chroma:
    """Tạo hoặc load vector store."""
    if reset:
        print("\n🔄 RESET MODE: Xóa database cũ...")
        delete_database()

    print("📦 Đang khởi tạo Vector Store...")
    vector_store = Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=DB_LOCATION,
        embedding_function=EMBEDDINGS,
    )

    if chunks:
        print(f"💾 Đang embed và lưu {len(chunks)} chunks... (có thể mất vài phút)")
        batch_size = 50
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i: i + batch_size]
            vector_store.add_documents(documents=batch)
            done = min(i + batch_size, len(chunks))
            print(f"   ✓ {done}/{len(chunks)}", end="\r")
        print(f"\n✅ Đã lưu xong {len(chunks)} chunks!")

    return vector_store


def get_database_stats(vector_store: Chroma) -> dict | None:
    """Lấy thống kê về database."""
    try:
        count = vector_store._collection.count()
        return {
            "total_chunks":    count,
            "collection_name": COLLECTION_NAME,
            "location":        DB_LOCATION,
        }
    except Exception as e:
        print(f"⚠️ Không thể lấy stats: {e}")
        return None


def get_smart_retriever(vector_store: Chroma, k: int = 5):
    """
    Retriever với Parent-Child strategy:
    - Tìm child chunk nhỏ → chính xác
    - Tự động fetch parent (Điều đầy đủ) → LLM có đủ context
    """
    base_retriever = vector_store.as_retriever(
        search_type="similarity",
        search_kwargs={"k": k * 2},
    )

    class ParentChildRetriever:
        def __init__(self, base, store, top_k):
            self._base  = base
            self._store = store
            self._k     = top_k

        def invoke(self, query: str) -> list[Document]:
            results      = self._base.invoke(query)
            seen_parents = set()
            final        = []

            for doc in results:
                parent_id = doc.metadata.get("parent_id", "")
                chunk_id  = doc.metadata.get("chunk_id", "")

                if parent_id:
                    # Child → fetch parent để LLM đọc đầy đủ
                    if parent_id not in seen_parents:
                        fetched = self._store.get(where={"chunk_id": parent_id})
                        if fetched and fetched["documents"]:
                            seen_parents.add(parent_id)
                            final.append(Document(
                                page_content=fetched["documents"][0],
                                metadata=fetched["metadatas"][0],
                            ))
                else:
                    if chunk_id not in seen_parents:
                        seen_parents.add(chunk_id)
                        final.append(doc)

                if len(final) >= self._k:
                    break

            return final

        def get_relevant_documents(self, query: str) -> list[Document]:
            return self.invoke(query)

    return ParentChildRetriever(base_retriever, vector_store, k)


# ==========================================
# MAIN WORKFLOW
# ==========================================

def main():
    print("=" * 70)
    print("📚 VECTOR DATABASE MANAGER  (Smart Chunking - Điều/Khoản)")
    print("=" * 70)

    if not os.path.exists(WORD_FOLDER):
        os.makedirs(WORD_FOLDER)
        print(f"📁 Đã tạo thư mục: {WORD_FOLDER}")
        print("👉 Hãy đặt file Word vào thư mục này!")

    db_exists = os.path.exists(DB_LOCATION)

    if db_exists:
        print(f"\n✅ Database đã tồn tại tại: {DB_LOCATION}")
        temp_store = Chroma(
            collection_name=COLLECTION_NAME,
            persist_directory=DB_LOCATION,
            embedding_function=EMBEDDINGS,
        )
        stats = get_database_stats(temp_store)
        if stats:
            print(f"📊 Thống kê:")
            print(f"   - Collection: {stats['collection_name']}")
            print(f"   - Tổng chunks: {stats['total_chunks']}")
            print(f"   - Location:    {stats['location']}")

        print("\n" + "=" * 70)
        print("🔧 TÙY CHỌN:")
        print("=" * 70)
        print("  [1] Sử dụng database hiện tại")
        print("  [2] Xóa và nạp lại data mới")
        print("  [3] Thêm data vào database hiện tại")
        print("  [0] Thoát")
        print("=" * 70)

        choice = input("\n👉 Chọn (0-3): ").strip()

        if choice == "0":
            print("\n👋 Tạm biệt!")
            return None
        elif choice == "1":
            print("\n✅ Sử dụng database hiện tại")
            vector_store = temp_store
        elif choice == "2":
            documents = load_documents_from_folder(WORD_FOLDER)
            if not documents:
                return None
            chunks       = split_documents(documents)
            vector_store = create_vector_store(chunks, reset=True)
        elif choice == "3":
            documents = load_documents_from_folder(WORD_FOLDER)
            if not documents:
                return temp_store
            chunks = split_documents(documents)
            print(f"💾 Đang thêm {len(chunks)} chunks...")
            temp_store.add_documents(documents=chunks)
            vector_store = temp_store
        else:
            print("❌ Lựa chọn không hợp lệ!")
            return None

    else:
        print(f"\nℹ️ Database chưa tồn tại — đang tạo mới...")
        documents = load_documents_from_folder(WORD_FOLDER)
        if not documents:
            print(f"❌ Không có file Word nào trong: {WORD_FOLDER}")
            return None
        chunks       = split_documents(documents)
        vector_store = create_vector_store(chunks)

    stats = get_database_stats(vector_store)
    if stats:
        print(f"\n📊 Database: {stats['total_chunks']} chunks")

    print("\n" + "=" * 70)
    print("✨ HOÀN TẤT!")
    print("=" * 70)
    return vector_store


# ==========================================
# AUTO-INITIALIZE (khi import)
# ==========================================

if __name__ != "__main__":
    if os.path.exists(DB_LOCATION):
        print(f"✅ Loading existing database from: {DB_LOCATION}")
        vector_store = Chroma(
            collection_name=COLLECTION_NAME,
            persist_directory=DB_LOCATION,
            embedding_function=EMBEDDINGS,
        )
        stats = get_database_stats(vector_store)
        if stats:
            print(f"📊 Loaded {stats['total_chunks']} chunks")
    else:
        print("⚠️ Database không tồn tại! Chạy: python vector.py")
        vector_store = None

    retriever = (
        get_smart_retriever(vector_store, k=5)
        if vector_store else None
    )


# ==========================================
# COMMAND LINE
# ==========================================

if __name__ == "__main__":
    vector_store = main()

    if vector_store:
        retriever = get_smart_retriever(vector_store, k=5)
        print("\n🔍 Smart Retriever sẵn sàng!")
        print("👉 from vector import retriever")