"""
=============================================================
HVNH Regulations Page Crawler + PaddleOCR Vietnamese Extractor
=============================================================
Chức năng:
  1. Crawl trang https://hvnh.edu.vn để lấy danh sách văn bản
  2. Parse HTML hoặc dùng dữ liệu tĩnh đã cung cấp
  3. Download tất cả file PDF (từ hvnh.edu.vn và Google Drive)
  4. Dùng PaddleOCR nhận dạng văn bản Tiếng Việt
  5. Lưu kết quả vào file .txt và .json cho mỗi PDF

Yêu cầu cài đặt:
  pip install requests beautifulsoup4 paddlepaddle paddleocr
  pip install pdf2image Pillow gdown tqdm
  sudo apt-get install poppler-utils  # để dùng pdf2image
=============================================================
"""

import os
import re
import json
import time
import logging
import requests
import gdown
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from tqdm import tqdm

# PDF → image
from pdf2image import convert_from_path
from PIL import Image

# PaddleOCR
from paddleocr import PaddleOCR

# ── Cấu hình logging ────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("hvnh_crawler.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)

# ── Thư mục đầu ra ──────────────────────────────────────────
BASE_DIR   = Path("hvnh_output")
PDF_DIR    = BASE_DIR / "pdfs"
OCR_DIR    = BASE_DIR / "ocr_results"
JSON_DIR   = BASE_DIR / "json"
for d in [PDF_DIR, OCR_DIR, JSON_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Khởi tạo PaddleOCR (tiếng Việt) ─────────────────────────
log.info("Đang khởi tạo PaddleOCR (Tiếng Việt)…")
ocr_engine = PaddleOCR(
    use_angle_cls=True,   # xoay ảnh tự động
    lang="vi",            # ngôn ngữ Tiếng Việt
    show_log=False,
)
log.info("PaddleOCR sẵn sàng.")

# ════════════════════════════════════════════════════════════
# 1. DỮ LIỆU TĨNH (fallback nếu không crawl được trang)
# ════════════════════════════════════════════════════════════

STATIC_DOCUMENTS = [
    {
        "stt": 1,
        "title": "QĐ v/v Công nhận các chứng chỉ nghề nghiệp đủ điều kiện chuyển đổi KQHT, chuyển đổi TC đối với CTĐT trình độ ĐH tại HVNH",
        "so_qd": "309/QĐ-HVNH",
        "ngay_ban_hanh": "10/01/2024",
        "ap_dung": "Từ K26 trở đi",
        "url": "https://hvnh.edu.vn/pdt/vn/qdhvnh/qd-vv-cong-nhan-cac-chung-chi-nghe-nghiep-du-dieu-kien-chuyen-doi-kqht-chuyen-doi-tc-doi-voi-ctdt-trinh-do-dh-tai-hvnh-346.html",
    },
    {
        "stt": 2,
        "title": "Quy định chuẩn đầu ra năng lực ngoại ngữ và kỹ năng sử dụng CNTT trình độ ĐH tại HVNH",
        "so_qd": "3337/QĐ-HVNH",
        "ngay_ban_hanh": "07/11/2023",
        "ap_dung": "Từ K26 trở đi",
        "url": "https://hvnh.edu.vn/pdt/vn/qdhvnh/quy-dinh-chuan-dau-ra-nang-luc-ngoai-ngu-va-ky-nang-su-dung-cong-nghe-thong-tin-trinh-do-dai-hoc-tai-hoc-vien-ngan-hang-345.html",
    },
    {
        "stt": 3,
        "title": "QĐ v/v Ban hành Quy định đăng ký và huỷ đăng ký học phần trong đào tạo đại học chính quy tại HVNH",
        "so_qd": "2833/QĐ-HVNH",
        "ngay_ban_hanh": "27/9/2023",
        "ap_dung": "Sinh viên ĐH chính quy theo hệ thống tín chỉ tại HVNH",
        "url": "https://hvnh.edu.vn/pdt/vn/qdhvnh/quy-dinh-dang-ky-va-huy-dang-ky-hoc-phan-trong-dao-tao-dai-hoc-chinh-quy-tai-hoc-vien-ngan-hang-344.html",
    },
    {
        "stt": 4,
        "title": "Quy định công nhận kết quả học tập, chuyển đổi tín chỉ đối với chương trình đào tạo trình độ ĐH tại HVNH",
        "so_qd": "2786/QĐ-HVNH",
        "ngay_ban_hanh": "22/9/2023",
        "ap_dung": "Sinh viên ĐH chính quy theo hệ thống tín chỉ tại HVNH",
        "url": "https://hvnh.edu.vn/pdt/vn/qdhvnh/quy-dinh-cong-nhan-ket-qua-hoc-tap-chuyen-doi-tin-chi-doi-voi-chuong-trinh-dao-tao-trinh-do-dai-hoc-tai-hoc-vien-ngan-hang-308.html",
    },
    {
        "stt": 5,
        "title": "Quyết định v/v ban hành hướng dẫn quy chế đào tạo trình độ ĐH tại HVNH",
        "so_qd": "2216/QĐ-HVNH",
        "ngay_ban_hanh": "24/9/2021",
        "ap_dung": "Từ K24 trở đi",
        "url": "https://hvnh.edu.vn/pdt/vn/qdhvnh/quy-che-dao-tao-dai-hoc-ap-dung-cho-cac-khoa-tuyen-sinh-tu-nam-2021-288.html",
    },
    {
        "stt": 9,
        "title": "Quy định Yêu cầu năng lực NNA và kỹ năng sử dụng CNTT",
        "so_qd": "282/QĐ-HVNH",
        "ngay_ban_hanh": "01/12/2015",
        "ap_dung": "Từ K25 trở về trước",
        "url": "https://hvnh.edu.vn/medias/pdt/vi/04.2019/system/archivedate/Noi%20dung%20quy%20dinh-%20Chuan%20dau%20ra%20TA%20va%20CNTT.pdf",
    },
    {
        "stt": 14,
        "title": "QD v/v Ban hành hướng dẫn quy đổi tín chỉ HVNH",
        "so_qd": "2862/QĐ-HVNH",
        "ngay_ban_hanh": "01/7/2024",
        "ap_dung": "Sinh viên ĐH chính quy theo hệ thống tín chỉ tại HVNH",
        "url": "https://drive.google.com/file/d/1W1nuCnJk5siUC8Rjjs_gndjofXrwoSLd/view?usp=sharing",
    },
    {
        "stt": 15,
        "title": "Quy chế đào tạo đại học chính quy Học viện Ngân hàng",
        "so_qd": "269/NQ-HVNH",
        "ngay_ban_hanh": "04/12/2024",
        "ap_dung": "Khoá tuyển sinh từ năm 2024 trở đi",
        "url": "https://drive.google.com/file/d/1T6ON_gjDVcDuCSYlx9dPmfylY3zk-JDB/view?usp=sharing",
    },
    {
        "stt": 16,
        "title": "Quyết định về việc ban hành Quy định công nhận KQHT, chuyển đổi tín chỉ đối với CTĐT Trình độ ĐH tại HVNH",
        "so_qd": "4272/QĐ-HVNH",
        "ngay_ban_hanh": "05/9/2025",
        "ap_dung": "Sinh viên ĐH chính quy theo hệ thống tín chỉ tại HVNH",
        "url": "https://drive.google.com/file/d/1EmyE3fXAFRtXGExDIDz7NJCIMKhimfoT/view?usp=sharing",
    },
]

# ════════════════════════════════════════════════════════════
# 2. CRAWL TRANG CHỦ để lấy URL PDF
# ════════════════════════════════════════════════════════════

TARGET_URL = "https://hvnh.edu.vn/pdt/vn/qdhvnh/tong-hop-cac-van-ban-quy-dinh-quy-che-350.html"
HEADERS    = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}


def crawl_main_page(url: str) -> list[dict]:
    """Crawl trang tổng hợp văn bản, trả về danh sách dict."""
    log.info(f"Crawling: {url}")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        resp.encoding = "utf-8"
    except requests.RequestException as e:
        log.warning(f"Không crawl được trang chính: {e}. Dùng dữ liệu tĩnh.")
        return STATIC_DOCUMENTS

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table")
    if not table:
        log.warning("Không tìm thấy bảng. Dùng dữ liệu tĩnh.")
        return STATIC_DOCUMENTS

    docs = []
    rows = table.find_all("tr")[1:]  # bỏ header
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 6:
            continue
        link_tag = cols[5].find("a")
        if not link_tag:
            continue
        href = link_tag.get("href", "").strip()
        if not href:
            continue
        if href.startswith("/"):
            href = urljoin("https://hvnh.edu.vn", href)
        docs.append({
            "stt":            cols[0].get_text(strip=True),
            "title":          cols[1].get_text(strip=True),
            "so_qd":          cols[2].get_text(strip=True),
            "ngay_ban_hanh":  cols[3].get_text(strip=True),
            "ap_dung":        cols[4].get_text(strip=True),
            "url":            href,
        })
    log.info(f"Tìm thấy {len(docs)} văn bản trên trang.")
    return docs if docs else STATIC_DOCUMENTS


# ════════════════════════════════════════════════════════════
# 3. LẤY PDF TRỰC TIẾP TỪ TRANG CON (nếu link là HTML)
# ════════════════════════════════════════════════════════════

def extract_pdf_from_detail_page(url: str) -> Optional[str]:
    """Truy cập trang chi tiết văn bản, tìm link PDF."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        resp.encoding = "utf-8"
    except requests.RequestException as e:
        log.warning(f"  Không lấy được trang chi tiết: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith(".pdf"):
            if href.startswith("/"):
                href = urljoin("https://hvnh.edu.vn", href)
            return href
    # Tìm iframe hoặc embed PDF
    for tag in soup.find_all(["iframe", "embed"], src=True):
        src = tag.get("src", "")
        if ".pdf" in src.lower():
            if src.startswith("/"):
                src = urljoin("https://hvnh.edu.vn", src)
            return src
    return None


# ════════════════════════════════════════════════════════════
# 4. DOWNLOAD PDF
# ════════════════════════════════════════════════════════════

def safe_filename(text: str, max_len: int = 80) -> str:
    """Chuyển chuỗi thành tên file an toàn."""
    text = re.sub(r'[\\/:*?"<>|]', "_", text)
    return text[:max_len].strip()


def is_google_drive(url: str) -> bool:
    return "drive.google.com" in url


def extract_gdrive_id(url: str) -> Optional[str]:
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else None


def download_gdrive(url: str, dest: Path) -> bool:
    """Download file từ Google Drive dùng gdown."""
    file_id = extract_gdrive_id(url)
    if not file_id:
        log.warning(f"  Không parse được Google Drive ID từ: {url}")
        return False
    dl_url = f"https://drive.google.com/uc?id={file_id}"
    try:
        log.info(f"  GDrive download: {dl_url} → {dest.name}")
        gdown.download(dl_url, str(dest), quiet=False, fuzzy=True)
        return dest.exists() and dest.stat().st_size > 1000
    except Exception as e:
        log.warning(f"  gdown thất bại: {e}")
        return False


def download_direct(url: str, dest: Path) -> bool:
    """Download file PDF trực tiếp."""
    try:
        log.info(f"  Direct download: {url} → {dest.name}")
        resp = requests.get(url, headers=HEADERS, stream=True, timeout=60)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return dest.exists() and dest.stat().st_size > 1000
    except requests.RequestException as e:
        log.warning(f"  Download thất bại: {e}")
        return False


def resolve_and_download(doc: dict, index: int) -> Optional[Path]:
    """
    Quyết định cách download:
    - Nếu URL là PDF trực tiếp → download thẳng
    - Nếu là Google Drive → dùng gdown
    - Nếu là trang HTML → crawl trang con tìm PDF
    """
    url   = doc["url"]
    fname = safe_filename(f"{index:02d}_{doc.get('so_qd', 'unknown')}_{doc['title']}")
    dest  = PDF_DIR / f"{fname}.pdf"

    if dest.exists() and dest.stat().st_size > 1000:
        log.info(f"  Đã tồn tại, bỏ qua: {dest.name}")
        return dest

    # --- Google Drive ---
    if is_google_drive(url):
        ok = download_gdrive(url, dest)
        return dest if ok else None

    # --- Link trực tiếp đến PDF ---
    if url.lower().endswith(".pdf"):
        ok = download_direct(url, dest)
        return dest if ok else None

    # --- Trang HTML → tìm PDF bên trong ---
    log.info(f"  Phát hiện trang HTML, đang tìm PDF trong: {url}")
    pdf_url = extract_pdf_from_detail_page(url)
    if pdf_url:
        log.info(f"    → Tìm thấy PDF: {pdf_url}")
        ok = download_direct(pdf_url, dest)
        return dest if ok else None
    else:
        log.warning(f"    → Không tìm thấy PDF trong trang: {url}")
        return None


# ════════════════════════════════════════════════════════════
# 5. OCR VỚI PADDLEOCR
# ════════════════════════════════════════════════════════════

def ocr_pdf(pdf_path: Path) -> str:
    """
    Chuyển PDF → ảnh → PaddleOCR → văn bản Tiếng Việt.
    Trả về toàn bộ text nhận dạng được.
    """
    log.info(f"  OCR: {pdf_path.name}")
    all_text = []

    try:
        images = convert_from_path(
            str(pdf_path),
            dpi=200,           # 200 DPI đủ tốt cho văn bản tiếng Việt
            fmt="PNG",
        )
    except Exception as e:
        log.error(f"  Không chuyển PDF sang ảnh được: {e}")
        return ""

    log.info(f"  Số trang: {len(images)}")

    for page_no, img in enumerate(images, start=1):
        log.info(f"  OCR trang {page_no}/{len(images)}…")
        import numpy as np
        img_array = np.array(img)

        try:
            result = ocr_engine.ocr(img_array, cls=True)
        except Exception as e:
            log.warning(f"  OCR trang {page_no} lỗi: {e}")
            continue

        page_lines = []
        if result and result[0]:
            for line in result[0]:
                # line = [[bbox], (text, confidence)]
                text, conf = line[1]
                if conf >= 0.5:          # lọc kết quả có độ tin cậy ≥ 50%
                    page_lines.append(text)

        page_text = "\n".join(page_lines)
        all_text.append(f"{'='*60}\n--- TRANG {page_no} ---\n{'='*60}\n{page_text}")

    return "\n\n".join(all_text)


# ════════════════════════════════════════════════════════════
# 6. LƯU KẾT QUẢ
# ════════════════════════════════════════════════════════════

def save_ocr_result(doc: dict, index: int, text: str):
    fname = safe_filename(f"{index:02d}_{doc.get('so_qd', 'unknown')}_{doc['title']}")

    # Lưu .txt
    txt_path = OCR_DIR / f"{fname}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"TIÊU ĐỀ : {doc['title']}\n")
        f.write(f"SỐ QĐ   : {doc.get('so_qd','')}\n")
        f.write(f"NGÀY BH : {doc.get('ngay_ban_hanh','')}\n")
        f.write(f"ÁP DỤNG : {doc.get('ap_dung','')}\n")
        f.write(f"NGUỒN   : {doc['url']}\n")
        f.write("=" * 60 + "\n\n")
        f.write(text)
    log.info(f"  Đã lưu OCR: {txt_path}")

    # Lưu .json
    json_path = JSON_DIR / f"{fname}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "metadata": doc,
                "ocr_text": text,
                "char_count": len(text),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


# ════════════════════════════════════════════════════════════
# 7. PIPELINE CHÍNH
# ════════════════════════════════════════════════════════════

def main():
    log.info("=" * 60)
    log.info("HVNH CRAWLER + PADDLEOCR  BẮT ĐẦU")
    log.info("=" * 60)

    # Bước 1: Lấy danh sách văn bản
    docs = crawl_main_page(TARGET_URL)

    summary = []

    # Bước 2: Download + OCR từng văn bản
    for i, doc in enumerate(tqdm(docs, desc="Xử lý văn bản"), start=1):
        log.info(f"\n[{i}/{len(docs)}] {doc['title'][:60]}…")
        doc_result = {**doc, "status": "skip", "pdf_file": None, "ocr_chars": 0}

        pdf_path = resolve_and_download(doc, i)

        if pdf_path is None:
            log.warning(f"  Không download được PDF.")
            doc_result["status"] = "download_failed"
            summary.append(doc_result)
            time.sleep(1)
            continue

        doc_result["pdf_file"] = str(pdf_path)
        text = ocr_pdf(pdf_path)

        if text.strip():
            save_ocr_result(doc, i, text)
            doc_result["status"]    = "success"
            doc_result["ocr_chars"] = len(text)
            log.info(f"  ✅ Hoàn thành ({len(text):,} ký tự)")
        else:
            log.warning(f"  ⚠️  OCR không trích xuất được văn bản.")
            doc_result["status"] = "ocr_empty"

        summary.append(doc_result)
        time.sleep(1)   # tránh bị chặn

    # Bước 3: Lưu báo cáo tổng hợp
    report_path = BASE_DIR / "summary_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # In tóm tắt
    log.info("\n" + "=" * 60)
    log.info("KẾT QUẢ TỔNG HỢP")
    log.info("=" * 60)
    ok  = sum(1 for r in summary if r["status"] == "success")
    fail= sum(1 for r in summary if r["status"] != "success")
    log.info(f"  ✅ Thành công  : {ok}/{len(summary)}")
    log.info(f"  ❌ Thất bại    : {fail}/{len(summary)}")
    log.info(f"  📁 PDF         : {PDF_DIR}")
    log.info(f"  📄 OCR text    : {OCR_DIR}")
    log.info(f"  📊 JSON        : {JSON_DIR}")
    log.info(f"  📋 Báo cáo     : {report_path}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()