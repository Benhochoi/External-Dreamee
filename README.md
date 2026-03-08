# [TODO: Tên dự án]

![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-[MIT]-lightgrey)
![Version](https://img.shields.io/badge/version-1.0.0-orange)
![LangChain](https://img.shields.io/badge/LangChain-0.3-purple)
![Ollama](https://img.shields.io/badge/Ollama-local-black)

> 🤖 Chatbot RAG hỏi đáp quy chế, quy định nội bộ Học viện Ngân hàng — hoạt động hoàn toàn offline với mô hình ngôn ngữ cục bộ.

---

## 📋 Mục lục

- [Giới thiệu dự án](#-giới-thiệu-dự-án)
- [Tính năng chính](#-tính-năng-chính)
- [Kiến trúc hệ thống](#-kiến-trúc-hệ-thống)
- [Tech stack](#-tech-stack)
- [Thách thức & Hướng phát triển](#-thách-thức--hướng-phát-triển)
- [Cài đặt & Cấu hình](#-cài-đặt--cấu-hình)
- [Hướng dẫn sử dụng](#-hướng-dẫn-sử-dụng)
- [Đóng góp](#-đóng-góp)
- [Credits](#-credits)
- [Giấy phép](#-giấy-phép)

---

## 📖 Giới thiệu dự án

Dự án xây dựng một hệ thống **RAG (Retrieval-Augmented Generation)** để hỏi đáp tự động về quy chế, quy định nội bộ của **Học viện Ngân hàng (HVNH)**. Thay vì phải tra cứu thủ công trong hàng chục file Word, người dùng có thể đặt câu hỏi bằng ngôn ngữ tự nhiên và nhận câu trả lời được trích dẫn rõ ràng từ văn bản gốc.

Hệ thống hoạt động **hoàn toàn offline** — không gửi dữ liệu ra ngoài — nhờ sử dụng mô hình ngôn ngữ cục bộ qua Ollama, phù hợp với môi trường nội bộ yêu cầu bảo mật thông tin.

---

## ✨ Tính năng chính

- 🔍 **Hybrid search (BM25 + Vector)** — kết hợp tìm kiếm từ khóa chính xác và tìm kiếm ngữ nghĩa, hợp nhất kết quả bằng Reciprocal Rank Fusion (RRF)
- 📄 **Chunking thông minh 2 loại văn bản:**
  - *Văn bản pháp quy* (quyết định, nghị quyết): chunking theo cấu trúc Điều → Khoản (hierarchical parent-child)
  - *Văn bản thường* (thông báo, công văn): chunking theo section/paragraph
- 🧠 **Parent-child retrieval** — khi tìm thấy khoản con, tự động fetch điều cha để LLM có đủ ngữ cảnh
- 📝 **Trích dẫn nguồn rõ ràng** — câu trả lời luôn kèm số điều, tên quyết định
- 🌐 **Giao diện web** — chat trực tiếp qua trình duyệt, không cần cài thêm phần mềm
- 🔄 **Quản lý vector database** — hỗ trợ nạp lại, bổ sung hoặc giữ nguyên database
- 🕷️ **Crawler nội dung** — thu thập văn bản từ website HVNH

---

## 🏗️ Kiến trúc hệ thống

```
Câu hỏi người dùng
        │
        ▼
┌───────────────────┐
│  HybridRetriever  │
│  ┌─────────────┐  │
│  │   BM25      │  │  ← Tìm kiếm từ khóa (số điều, mã số...)
│  │   (40%)     │  │
│  └─────────────┘  │
│  ┌─────────────┐  │
│  │  Vector     │  │  ← Tìm kiếm ngữ nghĩa (nomic-embed-text)
│  │  (60%)      │  │
│  └─────────────┘  │
│       RRF Fusion  │
└────────┬──────────┘
         │  Top-k chunks (parent fetching nếu cần)
         ▼
┌───────────────────┐
│   Ollama LLM      │  ← qwen2.5 (chạy cục bộ)
│   + Prompt RAG    │
└────────┬──────────┘
         │
         ▼
    Câu trả lời có trích dẫn
```

---

## 🛠️ Tech stack

| Thành phần | Công nghệ |
|---|---|
| Mô hình ngôn ngữ | `Ollama` + `qwen2.5` |
| Embedding | `nomic-embed-text` (via Ollama) |
| Vector database | `ChromaDB` |
| Framework AI | `LangChain` |
| Backend API | `FastAPI` + `Uvicorn` |
| Chunking | Tùy chỉnh (regex + `RecursiveCharacterTextSplitter`) |
| Đọc file Word | `docx2txt` |
| Giao diện | HTML/CSS/JavaScript thuần |
| Ngôn ngữ | `Python 3.10+` |

> **Lý do chọn stack này:** Toàn bộ pipeline chạy offline, không phụ thuộc API bên ngoài, chi phí vận hành bằng 0 sau khi triển khai. Ollama giúp quản lý model cục bộ đơn giản; ChromaDB nhẹ, không cần server riêng; LangChain cung cấp abstraction linh hoạt để nâng cấp từng thành phần độc lập.

---

## ⚡ Thách thức & Hướng phát triển

### Thách thức đã gặp

- **Cấu trúc văn bản pháp quy phức tạp** — văn bản tiếng Việt có header/footer lặp, pandoc xuất markdown không nhất quán; cần viết pipeline tiền xử lý và regex chuyên biệt
- **Context window embedding** — văn bản điều khoản dài vượt giới hạn token của model embedding; giải quyết bằng `_safe_embed_text()` tách sub-chunk với overlap
- **Chất lượng retrieval tiếng Việt** — tokenizer mặc định không hiểu từ ghép tiếng Việt; bổ sung bigram tokenization vào BM25 để bắt cụm "tín chỉ", "học phần"
- **Tìm đúng ngữ cảnh** — child chunk chính xác nhưng thiếu context → parent-child retrieval tự động fetch điều cha

### Hướng phát triển tương lai

- [ ] Hỗ trợ nhiều collection (phân tách theo năm học, loại quy chế)
- [ ] Thêm reranker (cross-encoder) để tăng độ chính xác sau retrieval
- [ ] Giao diện admin để upload văn bản mới không cần dùng CLI
- [ ] Đánh giá tự động chất lượng RAG bằng RAGAS framework
- [ ] Hỗ trợ câu hỏi đa lượt (multi-turn conversation với memory)
- [ ] Đóng gói Docker để triển khai dễ dàng hơn

---

## 🚀 Cài đặt & Cấu hình

### Yêu cầu hệ thống

- Python 3.10+
- [Ollama](https://ollama.com/) đã cài đặt và đang chạy
- RAM tối thiểu 8GB (khuyến nghị 16GB cho qwen2.5)

### 1. Clone repository

```bash
git clone https://github.com/[TODO]/[TODO].git
cd [TODO]
```

### 2. Cài đặt dependencies Python

```bash
pip install -r requirements.txt
```

### 3. Tải model Ollama

```bash
# Mô hình ngôn ngữ
ollama pull qwen2.5

# Mô hình embedding
ollama pull nomic-embed-text
```

### 4. Chuẩn bị dữ liệu

```
data/
└── processed/        ← Đặt tất cả file .docx vào đây
```

```bash
# Tạo thư mục nếu chưa có
mkdir -p data/processed

# Sao chép các file văn bản Word vào thư mục
cp /path/to/your/*.docx data/processed/
```

### 5. Xây dựng vector database

```bash
python vector.py
```

Chương trình sẽ hiện menu tương tác:
```
  [1] Dùng database hiện tại (không thay đổi)
  [2] Xóa và nạp lại toàn bộ từ đầu
  [3] Thêm file mới vào database hiện tại
  [0] Thoát
```

Chọn `[2]` để nạp lần đầu. Quá trình embedding có thể mất **vài phút** tùy số lượng văn bản.

---

## 📌 Hướng dẫn sử dụng

### Khởi động server API

```bash
python maintest.py
```

Kết quả:
```
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  MÁY CHỦ AI ĐANG CHẠY...
  ĐỊA CHỈ API: http://localhost:5000/api/chat
  HÃY MỞ FILE HTML ĐỂ BẮT ĐẦU CHAT!
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

### Mở giao diện web

Mở file `web.html` trực tiếp trong trình duyệt (Chrome/Firefox/Edge).

> ⚠️ **Lưu ý:** Phải khởi động `maintest.py` **trước** rồi mới mở file HTML.

### Gọi API trực tiếp (tùy chọn)

```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Điều kiện để được học vượt tín chỉ là gì?"}'
```

Kết quả mẫu:
```json
{
  "reply": "Theo Điều 5 của Quyết định 3337/QĐ-HVNH, sinh viên muốn học vượt cần đáp ứng..."
}
```

### Xây dựng lại vector database (khi có file mới)

```bash
python vector.py
# Chọn [2] để nạp lại hoàn toàn
# Hoặc [3] để bổ sung file mới
```

### Kiểm tra chunking độc lập

```bash
# Test chunking văn bản pháp quy
python chunking_NQ.py data/processed/ten_file.docx

# Test chunking văn bản thường
python chunking_thuong.py data/processed/ten_file.docx
```

---

## 🤝 Đóng góp

Mọi đóng góp đều được chào đón! Vui lòng làm theo các bước:

1. Fork repository này
2. Tạo branch mới: `git checkout -b feature/ten-tinh-nang`
3. Commit thay đổi: `git commit -m "feat: mô tả ngắn gọn"`
4. Push lên branch: `git push origin feature/ten-tinh-nang`
5. Tạo Pull Request và mô tả rõ thay đổi

### Quy ước commit

```
feat:     Tính năng mới
fix:      Sửa lỗi
docs:     Cập nhật tài liệu
refactor: Cải thiện code không ảnh hưởng logic
chore:    Việc vặt (cấu hình, dependencies...)
```

---

## 🏆 Credits

### Nhóm phát triển

| Tên | Vai trò | GitHub |
|---|---|---|
| [Đào Nguyên Chiến] | [Leader] | [@Benhocchoi](https://github.com/Benhochoi) |
| [Nguyễn Viết Việt Quốc] | [dev] | [@](https://github.com/TODO) |
| [Lê Thị Phượng] | [dev] | [@](https://github.com/TODO) |
| [Ngô Thuý Hạnh] | [dev] | [@](https://github.com/TODO) |
| [Lê Minh Tiểu Phượng] | [dev] | [@](https://github.com/TODO) |

### Thư viện & Tài liệu tham khảo

- [LangChain](https://python.langchain.com/) — Framework orchestration cho LLM
- [Ollama](https://ollama.com/) — Chạy LLM cục bộ
- [ChromaDB](https://www.trychroma.com/) — Vector database nhúng
- [FastAPI](https://fastapi.tiangolo.com/) — Backend API hiệu suất cao
- [BM25 (Robertson & Sparck Jones)](https://en.wikipedia.org/wiki/Okapi_BM25) — Thuật toán xếp hạng tài liệu
- [Reciprocal Rank Fusion](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf) — Cormack et al., 2009

---

## 📄 Giấy phép

Dự án này được phân phối theo giấy phép **[MIT]**.

Xem chi tiết tại file [`LICENSE`](./LICENSE).

---

<p align="center">Được xây dựng với ❤️ bởi nhóm phát triển External Dreamee — Học viện Ngân hàng</p>