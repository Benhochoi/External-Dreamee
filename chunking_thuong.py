import re
from pathlib import Path
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


# -------------------------------------------------------------------------------
# HANG SO CAU HINH
# -------------------------------------------------------------------------------

# Section ngan hon nguong nay -> giu nguyen, khong tach them
MIN_SECTION_CHARS = 80

# Section dai hon nguong nay -> tach tiep thanh paragraph chunks
MAX_SECTION_CHARS = 800

# Overlap khi tach paragraph
PARAGRAPH_CHUNK_OVERLAP = 80


# -------------------------------------------------------------------------------
# REGEX NHAN DIEN CAU TRUC
# -------------------------------------------------------------------------------

# Section header dang ALL CAPS hoac co danh so
_RE_SECTION_HEADER = re.compile(
    r"(?:^|\n)"
    r"("
    # ALL CAPS tieng Viet >= 4 ky tu
    r"(?:[A-ZĐÁÀẢÃẠĂẮẶẲẴÂẤẦẨẪẬÊẾỀỂỄỆÍÌỈĨỊ"
    r"ÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÚÙỦŨỤƯỨỪỬỮỰÝỲỶỸỴ]{4,}[^\n]{0,60})"
    r"|(?:[IVX]+\.\s+[^\n]{5,60})"           # La ma: I. II. III.
    r"|(?:\d+\.\s+[A-ZĐÁÀẢÃ][^\n]{5,60})"    # So:    1. Tieu de viet hoa
    r"|(?:\*\*[^\*\n]{5,60}\*\*)"            # Bold markdown
    r")"
    r"(?=\n)",
    re.MULTILINE
)

# Noise can loai bo truoc khi xu ly
_NOISE_PATTERNS = [
    r"\*\*\s*\*\*",     # bold rong
    r"\\$",             # dau \ cuoi dong (pandoc)
    r"^\s*-{3,}\s*$",   # dong toan dau ---
]


# -------------------------------------------------------------------------------
# TIEN XU LY
# -------------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    """Chuan hoa khoang trang va loai bo noise."""
    for p in _NOISE_PATTERNS:
        text = re.sub(p, "", text, flags=re.DOTALL | re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)  # bo bold markdown
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _extract_title(text: str, source_path: str = "") -> str:
    """
    Lay tieu de tu dong dau tien co noi dung y nghia.
    Fallback ve ten file neu khong tim thay.
    """
    for line in text.split("\n"):
        line = line.strip()
        if len(line) > 10 and not re.match(r"^\d+$", line):
            title = re.sub(r"[*#_]", "", line).strip()
            if len(title) > 5:
                return title
    return Path(source_path).stem.replace("_", " ") if source_path else "Khong ro"


def _extract_metadata(text: str, source_path: str = "") -> dict:
    """
    Trich metadata toi gian cho van ban thuong.
    Chi can: ten tai lieu, ngay (neu co), nguon.
    """
    title = _extract_title(text, source_path)

    ngay_m = re.search(
        r"(?:ngày|Ngày)\s+(\d+\s+tháng\s+\d+\s+năm\s+\d{4})"
        r"|(\d{1,2}/\d{1,2}/\d{4})",
        text
    )
    ngay_str = ""
    if ngay_m:
        ngay_str = (ngay_m.group(1) or ngay_m.group(2) or "").strip()

    return {
        "source":       source_path,
        "loai_van_ban": "thuong",
        "ten_van_ban":  title,
        "ngay":         ngay_str or "Khong ro",
        "co_quan":      "Hoc vien Ngan hang",
    }


# -------------------------------------------------------------------------------
# PHAT HIEN SECTIONS
# -------------------------------------------------------------------------------

def _detect_sections(text: str) -> list[tuple[str, str]]:

    # Thu ALL CAPS / Numbered headers
    header_matches = list(_RE_SECTION_HEADER.finditer(text))
    if len(header_matches) >= 2:
        return _split_by_matches(text, header_matches)

    # Khong co cau truc ro rang -> 1 section
    return [("", text)]


def _split_by_matches(text: str, matches: list) -> list[tuple[str, str]]:
    """
    Tach text thanh list (header, content) dua tren danh sach regex matches.
    Phan text truoc match dau tien duoc coi la phan "Gioi thieu".
    """
    sections: list[tuple[str, str]] = []

    # Phan intro truoc header dau tien
    first_start = matches[0].start()
    if first_start > 0:
        intro = text[:first_start].strip()
        if len(intro) >= MIN_SECTION_CHARS:
            sections.append(("Gioi thieu", intro))

    for i, m in enumerate(matches):
        header  = m.group(1).strip() if m.lastindex and m.group(1) else m.group(0).strip()
        start   = m.end()
        end     = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if len(content) >= MIN_SECTION_CHARS:
            sections.append((header, content))

    return sections if sections else [("", text)]


# -------------------------------------------------------------------------------
# CHUNKING LOGIC
# -------------------------------------------------------------------------------

def _build_context_header(meta: dict, section_title: str) -> str:
    """
    Prepend contextual header vao moi chunk.
    Giup embedding model biet chunk nay den tu tai lieu nao, phan nao.
    """
    lines = [f"Tai lieu: {meta['ten_van_ban']}"]
    if section_title:
        lines.append(f"Phan: {section_title}")
    lines.append("-" * 40)
    return "\n".join(lines) + "\n"


def _chunk_one_section(
    header: str,
    content: str,
    meta: dict,
    doc_id: str,
    section_idx: int,
) -> list[Document]:
    """
    Chunk 1 section thanh 1 hoac nhieu Document:
        Ngan (< MAX_SECTION_CHARS)  -> 1 chunk, chunk_type = "section"
        Dai  (>= MAX_SECTION_CHARS) -> tach paragraph, chunk_type = "paragraph"
    """
    ctx    = _build_context_header(meta, header)
    chunks: list[Document] = []

    if len(content) < MAX_SECTION_CHARS:
        chunks.append(Document(
            page_content=ctx + content,
            metadata={
                **meta,
                "chunk_id":      f"{doc_id}__s{section_idx}",
                "chunk_type":    "section",
                "section_title": header,
                "section_idx":   str(section_idx),
                "level":         "flat",
                "char_count":    str(len(content)),
            }
        ))
    else:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=MAX_SECTION_CHARS,
            chunk_overlap=PARAGRAPH_CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " "],
        )
        paras = splitter.split_text(content)
        for pi, para in enumerate(paras):
            if len(para.strip()) < MIN_SECTION_CHARS:
                continue
            chunks.append(Document(
                page_content=ctx + para.strip(),
                metadata={
                    **meta,
                    "chunk_id":      f"{doc_id}__s{section_idx}_p{pi + 1}",
                    "chunk_type":    "paragraph",
                    "section_title": header,
                    "section_idx":   str(section_idx),
                    "para_idx":      str(pi + 1),
                    "level":         "flat",
                    "char_count":    str(len(para)),
                }
            ))

    return chunks


# -------------------------------------------------------------------------------
# PUBLIC API -- goi tu vector.py
# -------------------------------------------------------------------------------

def chunk_van_ban_thuong(documents: list[Document]) -> list[Document]:
    """
    Entry point: nhan list[Document] -> tra ve list[Document] chunks.

    Xu ly tung document theo thu tu:
        1. Lam sach noise
        2. Trich metadata (ten tai lieu, ngay)
        3. Phat hien sections tu dong
        4. Chunk tung section -> section hoac paragraph chunks
    """
    all_chunks: list[Document] = []

    for doc in documents:
        source = doc.metadata.get("source", "")
        name   = Path(source).name
        text   = _clean_text(doc.page_content)
        meta   = _extract_metadata(text, source)
        doc_id = Path(source).stem.replace(" ", "_")

        # Canh bao neu thuc ra la van ban phap quy
        if re.search(r"Điều\s+\d+[\.:]", text):
            print(f"  [WARN] {name}: phat hien cau truc Dieu/Khoan")
            print(f"         -> Hay dung chunking_NQ.py de co ket qua tot hon")

        sections   = _detect_sections(text)
        doc_chunks: list[Document] = []

        for si, (header, content) in enumerate(sections):
            sc = _chunk_one_section(header, content, meta, doc_id, si)
            doc_chunks.extend(sc)

        print(f"  [OK] {name}: {len(sections)} section(s) -> {len(doc_chunks)} chunks")
        all_chunks.extend(doc_chunks)

    print(f"\nTong chunks van ban thuong: {len(all_chunks)}")
    return all_chunks


# -------------------------------------------------------------------------------
# CHAY DOC LAP -- TEST NHANH
# python chunking_thuong.py duong/dan/file.docx
# -------------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from langchain_community.document_loaders import Docx2txtLoader

    path   = sys.argv[1] if len(sys.argv) > 1 else "test.docx"
    docs   = Docx2txtLoader(path).load()
    chunks = chunk_van_ban_thuong(docs)

    print(f"\n{'-' * 55}")
    print("Preview tat ca chunks:")
    for i, c in enumerate(chunks):
        t = c.metadata.get("chunk_type", "?")
        s = c.metadata.get("section_title", "")
        print(f"\n[Chunk {i + 1} | {t} | section: '{s}']")
        print(c.page_content[:400])
        print("-" * 55)