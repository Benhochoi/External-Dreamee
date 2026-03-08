# 🎓 HVBot — Chatbot tư vấn học tập cho sinh viên Học viện Ngân hàng

![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-lightgrey)
![Version](https://img.shields.io/badge/version-1.0.0-orange)
![LangChain](https://img.shields.io/badge/LangChain-0.3-purple)
![Ollama](https://img.shields.io/badge/Ollama-local-black)

> 🤖 Hệ thống chatbot RAG (Retrieval-Augmented Generation) hoạt động hoàn toàn offline, giúp sinh viên Học viện Ngân hàng tra cứu quy chế, quy định nội bộ nhanh chóng và chính xác bằng ngôn ngữ tự nhiên.

---

## 📋 Mục lục

- [Giới thiệu dự án](#-giới-thiệu-dự-án)
- [Tính năng chính](#-tính-năng-chính)
- [Kiến trúc hệ thống](#-kiến-trúc-hệ-thống)
- [Tech stack](#-tech-stack)
- [Thách thức & hướng phát triển](#-thách-thức--hướng-phát-triển)
- [Cài đặt & cấu hình](#-cài-đặt--cấu-hình)
- [Hướng dẫn sử dụng](#-hướng-dẫn-sử-dụng)
- [Đóng góp](#-đóng-góp)
- [Credits](#-credits)
- [Giấy phép](#-giấy-phép)

---

## 📖 Giới thiệu dự án

**HVBot** là hệ thống hỏi-đáp thông minh được xây dựng theo kiến trúc RAG, cho phép sinh viên Học viện Ngân hàng (HVNH) đặt câu hỏi bằng ngôn ngữ tự nhiên và nhận câu trả lời được **trích dẫn điều khoản cụ thể** từ văn bản gốc — thay vì phải đọc thủ công hàng chục file Word dài hàng trăm trang.

Hệ thống chạy **hoàn toàn offline** nhờ sử dụng mô hình ngôn ngữ cục bộ qua Ollama, không gửi bất kỳ dữ liệu nào ra ngoài, phù hợp với môi trường nội bộ yêu cầu bảo mật thông tin.

---

## ✨ Tính năng chính

- 🔍 **Hybrid search (BM25 + Vector + RRF)** — kết hợp tìm kiếm từ khóa chính xác (số điều, mã số) và tìm kiếm ngữ nghĩa, hợp nhất kết quả bằng Reciprocal Rank Fusion
- 📄 **Chunking thông minh theo loại văn bản:**
  - *Văn bản pháp quy* (quyết định, nghị quyết): phân tách theo cấu trúc Điều → Khoản (hierarchical parent-child chunking)
  - *Văn bản thường* (thông báo, công văn, hướng dẫn): phân tách theo section và paragraph
- 🧠 **Parent-child retrieval** — khi tìm thấy khoản con, tự động fetch điều cha để LLM có đủ ngữ cảnh trả lời
- 📝 **Trích dẫn nguồn rõ ràng** — mọi câu trả lời đều kèm số điều và tên quyết định cụ thể
- 🌐 **Giao diện web chat** — trò chuyện trực tiếp qua trình duyệt, không cần cài thêm phần mềm
- 🗄️ **Quản lý vector database tương tác** — hỗ trợ nạp mới, bổ sung hoặc giữ nguyên database qua menu CLI
- 🕷️ **Crawler thu thập văn bản** — hỗ trợ crawl tài liệu từ website HVNH

---

## 🏗️ Kiến trúc hệ thống

```
File .docx (data/processed/)
         │
         ▼
┌─────────────────────────┐
│   Phân loại văn bản     │
│  ┌──────────────────┐   │
│  │  Pháp quy (QĐ)   │──►│ chunking_NQ.py     → Điều / Khoản
│  │  Thường (TB/CV)  │──►│ chunking_thuong.py → Section / Paragraph
│  └──────────────────┘   │
└────────────┬────────────┘
             │  Chunks có metadata đầy đủ
             ▼
┌─────────────────────────┐
│  Embedding              │
│  nomic-embed-text       │
│  (via Ollama)           │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  ChromaDB               │
│  (vector store local)   │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│           HybridRetriever               │
│  ┌──────────────┐  ┌─────────────────┐  │
│  │  BM25 (40%)  │  │  Vector (60%)   │  │
│  └──────────────┘  └─────────────────┘  │
│          RRF Fusion + Parent fetch       │
└────────────────────┬────────────────────┘
                     │  Top-k chunks có ngữ cảnh đầy đủ
                     ▼
         ┌────────────────────────┐
         │  Ollama LLM (qwen2.5)  │
         │  + Prompt RAG          │
         └───────────┬────────────┘
                     │
                     ▼
         ┌────────────────────────┐
         │  FastAPI Backend       │◄──► Web Frontend (web.html)
         │  http://localhost:5000 │
         └────────────────────────┘
```

---

## 🛠️ Tech stack

| Thành phần | Công nghệ | Ghi chú |
|---|---|---|
| Mô hình ngôn ngữ | [TODO] | Chạy local qua Ollama |
| Embedding | [TODO] | Hỗ trợ đa ngôn ngữ |
| Vector database | [TODO] | Nhẹ, không cần server riêng |
| Framework AI | [TODO] | Orchestration cho pipeline RAG |
| Backend API | [TODO] | Async, tự sinh OpenAPI docs |
| Giao diện | [TODO] | Chat trực tiếp qua trình duyệt |
| Đọc file Word | [TODO] | Parse `.docx` thuần Python |
| Ngôn ngữ lập trình | [TODO] | — |

---

## ⚡ Thách thức & hướng phát triển

### Thách thức đã gặp

- **Cấu trúc văn bản pháp quy phức tạp** — văn bản tiếng Việt có header/footer lặp lại, pandoc xuất markdown không nhất quán giữa các phiên bản. Giải pháp: viết pipeline tiền xử lý regex chuyên biệt trong `chunking_NQ.py`
- **Giới hạn context window embedding** — điều khoản dài vượt token limit của model embedding. Giải pháp: hàm `_safe_embed_text()` tách sub-chunk thông minh theo đoạn văn, có overlap tại ranh giới
- **Tokenization tiếng Việt** — tokenizer mặc định không hiểu từ ghép ("tín chỉ", "học phần"). Giải pháp: BM25 tự xây với bigram tokenizer để bắt cụm từ quan trọng
- **Thiếu ngữ cảnh khi retrieval** — child chunk tìm đúng khoản nhưng LLM thiếu toàn bộ điều để trả lời đầy đủ. Giải pháp: parent-child retrieval tự động fetch điều cha từ ChromaDB

### Hướng phát triển tương lai

- [ ] Tích hợp reranker (cross-encoder) để cải thiện độ chính xác sau bước retrieval
- [ ] Hỗ trợ hội thoại đa lượt (multi-turn conversation với memory)
- [ ] Giao diện admin để upload và quản lý văn bản mới không cần dùng CLI
- [ ] Đánh giá tự động chất lượng RAG bằng RAGAS framework
- [ ] Đóng gói Docker để triển khai lên server dễ dàng hơn
- [ ] Cập nhật dữ liệu realtime từ website HVNH qua crawler tự động theo lịch

---

## 🚀 Cài đặt & cấu hình

### Yêu cầu hệ thống

- Python 3.10+
- [Ollama](https://ollama.com/) đã cài đặt và đang chạy
- RAM tối thiểu 8 GB (khuyến nghị 16 GB)

### 1. Clone repository

```bash
git clone https://github.com/[TODO]/[TODO].git
cd [TODO]
```

### 2. Cài đặt dependencies

```bash
pip install -r requirements.txt
```

### 3. Tải model Ollama về máy

```bash
# Mô hình ngôn ngữ (LLM)
ollama pull qwen2.5

# Mô hình embedding
ollama pull nomic-embed-text
```

### 4. Chuẩn bị dữ liệu

Đặt tất cả file văn bản `.docx` vào thư mục `data/processed/`:

```bash
mkdir -p data/processed

# Sao chép file Word vào thư mục
cp /path/to/your/documents/*.docx data/processed/
```

Cấu trúc thư mục sau khi chuẩn bị:

```
data/
├── processed/     ← Đặt file .docx vào đây
├── raw/           ← File nguồn chưa xử lý (tuỳ chọn)
└── pdf/           ← File PDF gốc (tuỳ chọn)
```

### 5. Xây dựng vector database

```bash
python vector.py
```

Chương trình hiển thị menu tương tác — chọn `[2]` để nạp lần đầu:

```
=================================================================
  VECTOR DATABASE MANAGER
=================================================================
  [1] Dùng database hiện tại (không thay đổi)
  [2] Xóa và nạp lại toàn bộ từ đầu
  [3] Thêm file mới vào database hiện tại
  [0] Thoát
```

> ⏱️ Quá trình embedding có thể mất **5–15 phút** tuỳ số lượng văn bản và cấu hình máy.

---

## 📌 Hướng dẫn sử dụng

### Khởi động server

```bash
python maintest.py
```

Kết quả mong đợi:

```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  MÁY CHỦ AI ĐANG CHẠY...
  ĐỊA CHỈ API: http://localhost:5000/api/chat
  HÃY MỞ FILE HTML ĐỂ BẮT ĐẦU CHAT!
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

### Mở giao diện web

Mở file `web.html` trực tiếp trong trình duyệt (Chrome / Firefox / Edge).

> ⚠️ **Quan trọng:** Phải khởi động `maintest.py` **trước**, sau đó mới mở file HTML.

### Ví dụ gọi API trực tiếp

```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Điều kiện để được học vượt tín chỉ là gì?"}'
```

Kết quả mẫu:

```json
{
  "reply": "Theo Điều 5 của Quyết định 3337/QĐ-HVNH, sinh viên muốn học vượt cần đáp ứng các điều kiện: điểm trung bình tích lũy từ 2.5 trở lên và không có môn nào bị điểm F trong học kỳ liền trước..."
}
```

### Cập nhật database khi có văn bản mới

```bash
python vector.py
# Chọn [3] để bổ sung file mới mà không xoá data cũ
# Hoặc chọn [2] để nạp lại hoàn toàn
```

### Kiểm tra chunking độc lập

```bash
# Kiểm tra chunking văn bản pháp quy (quyết định, nghị quyết)
python chunking_NQ.py data/processed/ten_quyet_dinh.docx

# Kiểm tra chunking văn bản thường (thông báo, công văn)
python chunking_thuong.py data/processed/ten_thong_bao.docx
```

---

## 🤝 Đóng góp

Mọi đóng góp đều được chào đón! Vui lòng làm theo các bước:

1. Fork repository này
2. Tạo branch mới: `git checkout -b feature/ten-tinh-nang`
3. Commit thay đổi: `git commit -m "feat: mô tả ngắn gọn"`
4. Push lên branch: `git push origin feature/ten-tinh-nang`
5. Tạo Pull Request và mô tả rõ những thay đổi đã thực hiện

### Quy ước commit message

```
feat:      Tính năng mới
fix:       Sửa lỗi
docs:      Cập nhật tài liệu
refactor:  Cải thiện cấu trúc code, không thay đổi logic
test:      Thêm hoặc sửa test
chore:     Cấu hình, dependencies, việc vặt khác
```

### Báo lỗi

Nếu phát hiện lỗi, vui lòng [mở issue](https://github.com/[TODO]/[TODO]/issues) với thông tin đầy đủ: mô tả lỗi, các bước tái hiện và log từ terminal.

---

## 🏆 Credits

### Nhóm phát triển

| Tên | Vai trò | GitHub |
|---|---|---|
| Đào Nguyên Chiến | Leader | [@Benhocchoi](https://github.com/Benhochoi) |
| Nguyễn Viết Việt Quốc | Developer | [@TODO](https://github.com/TODO) |
| Lê Thị Phượng | Developer | [@TODO](https://github.com/TODO) |
| Ngô Thuý Hạnh | Developer | [@TODO](https://github.com/TODO) |
| Lê Minh Tiểu Phượng | Developer | [@TODO](https://github.com/TODO) |

### Thư viện & tài liệu tham khảo

- [LangChain](https://python.langchain.com/) — Framework orchestration cho LLM pipeline
- [Ollama](https://ollama.com/) — Chạy mô hình ngôn ngữ cục bộ
- [ChromaDB](https://www.trychroma.com/) — Vector database nhẹ, nhúng trực tiếp vào ứng dụng
- [FastAPI](https://fastapi.tiangolo.com/) — Backend API hiệu suất cao, hỗ trợ async
- [Okapi BM25](https://en.wikipedia.org/wiki/Okapi_BM25) — Robertson & Sparck Jones, thuật toán xếp hạng tài liệu chuẩn
- [Reciprocal Rank Fusion](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) — Cormack et al., SIGIR 2009

---

## 📄 Giấy phép

Dự án này được phân phối theo giấy phép **MIT**. Xem chi tiết tại file [`LICENSE`](./LICENSE).

---

<p align="center">Được xây dựng với ❤️ bởi nhóm External Dreamee · Học viện Ngân hàng · 2026</p>