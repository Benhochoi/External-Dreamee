import warnings
warnings.filterwarnings("ignore")

import re
import math
from collections import Counter
from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from vector import vector_store, get_smart_retriever
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn


# ============================================================
# BM25 THUẦN PYTHON — không cần cài thêm thư viện
# ============================================================

def _tokenize_vi(text: str) -> list[str]:
    """
    Tokenize tiếng Việt đơn giản nhưng hiệu quả:
    - Giữ nguyên từ ghép tiếng Việt (2-3 âm tiết)
    - Lowercase, bỏ dấu câu
    - Sinh thêm bigram để bắt cụm từ quan trọng
      VD: "tín chỉ" → ["tín", "chỉ", "tín_chỉ"]
    """
    text = text.lower()
    text = re.sub(r"[^\w\sàáâãèéêìíòóôõùúýăđơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]", " ", text)
    tokens = [t for t in text.split() if len(t) > 1]
    # Bigram để bắt cụm từ quan trọng: "tín chỉ", "học phần", "điều kiện"...
    bigrams = [f"{tokens[i]}_{tokens[i+1]}" for i in range(len(tokens) - 1)]
    return tokens + bigrams


class BM25:
    """
    BM25 (Okapi BM25) — thuật toán tìm kiếm từ khoá chuẩn.
    Tốt hơn TF-IDF ở chỗ: normalize độ dài doc, saturate term frequency.
    k1=1.5, b=0.75 là tham số chuẩn cho văn bản pháp quy.
    """
    def __init__(self, docs: list[Document], k1: float = 1.5, b: float = 0.75):
        self.docs    = docs
        self.k1      = k1
        self.b       = b
        self.corpus  = [_tokenize_vi(d.page_content) for d in docs]
        self.n       = len(self.corpus)
        self.avgdl   = sum(len(d) for d in self.corpus) / max(self.n, 1)
        self.df      = self._build_df()
        self.idf     = self._build_idf()

    def _build_df(self) -> dict[str, int]:
        df: dict[str, int] = {}
        for doc_tokens in self.corpus:
            for t in set(doc_tokens):
                df[t] = df.get(t, 0) + 1
        return df

    def _build_idf(self) -> dict[str, float]:
        idf: dict[str, float] = {}
        for term, freq in self.df.items():
            # BM25 IDF formula (Robertson-Sparck Jones)
            idf[term] = math.log((self.n - freq + 0.5) / (freq + 0.5) + 1)
        return idf

    def score(self, query: str, doc_idx: int) -> float:
        q_tokens  = _tokenize_vi(query)
        doc_tokens = self.corpus[doc_idx]
        tf_map    = Counter(doc_tokens)
        dl        = len(doc_tokens)
        score     = 0.0
        for term in q_tokens:
            if term not in self.idf:
                continue
            tf = tf_map.get(term, 0)
            # BM25 scoring formula
            num   = tf * (self.k1 + 1)
            denom = tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            score += self.idf[term] * (num / denom)
        return score

    def retrieve(self, query: str, k: int = 10) -> list[tuple[Document, float]]:
        scores = [(i, self.score(query, i)) for i in range(self.n)]
        scores.sort(key=lambda x: x[1], reverse=True)
        return [(self.docs[i], s) for i, s in scores[:k] if s > 0]


# ============================================================
# HYBRID RETRIEVER: BM25 + VECTOR với RRF fusion
# ============================================================

def _rrf_score(rank: int, k: int = 60) -> float:
    """
    Reciprocal Rank Fusion — cách kết hợp nhiều ranking chuẩn nhất.
    Công thức: 1 / (k + rank)  →  rank càng cao, điểm càng lớn.
    k=60 là giá trị chuẩn được chứng minh empirically.
    """
    return 1.0 / (k + rank)


class HybridRetriever:
    """
    Kết hợp BM25 (keyword) + Vector (semantic) bằng Reciprocal Rank Fusion.

    Ưu điểm lai:
    ┌─ BM25:   giỏi tìm số điều khoản cụ thể ("Điều 5", "IELTS 6.5")
    │           và từ khoá chính xác ("lệ phí", "kỷ luật")
    └─ Vector: giỏi tìm ngữ nghĩa ("cần điều kiện gì?" → Điều 3)
               và câu hỏi diễn đạt khác từ trong tài liệu

    Cách dùng:
        retriever = HybridRetriever(vector_store, bm25_docs, k=5)
        docs = retriever.invoke("điều kiện chuyển đổi tín chỉ IELTS?")
    """

    def __init__(self,
                 vs,           # Chroma vector store
                 bm25_docs: list[Document],
                 k: int = 5,
                 vector_weight: float = 0.6,
                 bm25_weight:   float = 0.4):

        self._vs     = vs
        self._bm25   = BM25(bm25_docs)
        self._k      = k
        self._vw     = vector_weight
        self._bw     = bm25_weight

        # Base vector retriever (parent-child strategy từ vector.py)
        self._vec_retriever = get_smart_retriever(vs, k=k * 3)

        print(f"    BM25 index: {len(bm25_docs)} docs")
        print(f"    Vector store: ready")
        print(f"    Hybrid weights: vector={vector_weight}, BM25={bm25_weight}")

    def invoke(self, query: str) -> list[Document]:
        # ── 1. Vector search ──────────────────────────────────
        vec_results = self._vec_retriever.invoke(query)

        # ── 2. BM25 search ────────────────────────────────────
        bm25_results = self._bm25.retrieve(query, k=self._k * 3)

        # ── 3. RRF Fusion ─────────────────────────────────────
        # Key = chunk_id để dedup chính xác
        rrf_scores: dict[str, float] = {}
        doc_map:    dict[str, Document] = {}

        for rank, doc in enumerate(vec_results):
            key = doc.metadata.get("chunk_id", doc.page_content[:80])
            rrf_scores[key]  = rrf_scores.get(key, 0) + self._vw * _rrf_score(rank)
            doc_map[key]     = doc

        for rank, (doc, _bm25_score) in enumerate(bm25_results):
            key = doc.metadata.get("chunk_id", doc.page_content[:80])
            rrf_scores[key]  = rrf_scores.get(key, 0) + self._bw * _rrf_score(rank)
            if key not in doc_map:
                doc_map[key] = doc

        # ── 4. Sort và trả về top-k ───────────────────────────
        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return [doc_map[key] for key, _ in ranked[:self._k]]

    def invoke_with_scores(self, query: str) -> list[tuple[Document, float, str]]:
        """Debug mode: trả về (doc, rrf_score, source) để xem BM25 vs Vector contribute."""
        vec_results  = self._vec_retriever.invoke(query)
        bm25_results = self._bm25.retrieve(query, k=self._k * 3)

        rrf_scores: dict[str, float] = {}
        sources:    dict[str, list[str]] = {}
        doc_map:    dict[str, Document] = {}

        for rank, doc in enumerate(vec_results):
            key = doc.metadata.get("chunk_id", doc.page_content[:80])
            s   = self._vw * _rrf_score(rank)
            rrf_scores[key] = rrf_scores.get(key, 0) + s
            sources.setdefault(key, []).append(f"vector(rank={rank+1}, +{s:.3f})")
            doc_map[key] = doc

        for rank, (doc, bm25_s) in enumerate(bm25_results):
            key = doc.metadata.get("chunk_id", doc.page_content[:80])
            s   = self._bw * _rrf_score(rank)
            rrf_scores[key] = rrf_scores.get(key, 0) + s
            sources.setdefault(key, []).append(f"bm25(rank={rank+1}, score={bm25_s:.2f}, +{s:.3f})")
            if key not in doc_map:
                doc_map[key] = doc

        ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        return [
            (doc_map[key], score, " | ".join(sources.get(key, [])))
            for key, score in ranked[:self._k]
        ]

    # Tương thích với LangChain chain
    def get_relevant_documents(self, query: str) -> list[Document]:
        return self.invoke(query)


# ============================================================
# KHỞI TẠO HỆ THỐNG
# ============================================================

def _load_all_docs_for_bm25(vs) -> list[Document]:
    """
    Load toàn bộ chunks từ ChromaDB để build BM25 index.
    BM25 cần đọc tất cả docs, không chỉ top-k như vector search.
    """
    try:
        result = vs.get(include=["documents", "metadatas"])
        docs = []
        for text, meta in zip(result["documents"], result["metadatas"]):
            docs.append(Document(page_content=text, metadata=meta or {}))
        print(f"    Loaded {len(docs)} docs từ ChromaDB cho BM25 index")
        return docs
    except Exception as e:
        print(f"   Không load được docs cho BM25: {e}")
        return []


# Build hybrid retriever
_all_docs = _load_all_docs_for_bm25(vector_store)
retriever = HybridRetriever(
    vs=vector_store,
    bm25_docs=_all_docs,
    k=5,
    vector_weight=0.6,   # Vector giỏi ngữ nghĩa → weight cao hơn
    bm25_weight=0.4,     # BM25 giỏi từ khoá → hỗ trợ thêm
)


# ============================================================
# LLM + PROMPT
# ============================================================

print(">>> 4. ĐANG GỌI NÃO AI (QWEN 2.5)... <<<")
model = OllamaLLM(model="qwen2.5")

template = """
Bạn là chuyên gia tư vấn quy chế, quy định của Học viện Ngân hàng (HVNH).

## Nguyên tắc:
- CHỈ trả lời dựa trên [TÀI LIỆU] được cung cấp bên dưới
- Trích dẫn rõ: "Theo Điều X của Quyết định 2786/QĐ-HVNH..."
- Nếu không tìm thấy → trả lời: "Tôi không tìm thấy nội dung này trong quy chế hiện hành"
- Không bịa đặt, không suy diễn ngoài tài liệu
- Chỉ trả lời bằng tiếng Việt, tuyệt đối không sử dụng ngôn ngữ khác hoặc thêm các thẻ phân loại không liên quan.
[TÀI LIỆU QUY CHẾ LIÊN QUAN]
{reviews}

[CÂU HỎI]
{question}

[TRẢ LỜI]
"""

prompt = ChatPromptTemplate.from_template(template)
chain  = prompt | model


def format_docs(docs: list[Document]) -> str:
    parts = []
    for doc in docs:
        meta    = doc.metadata
        dieu    = meta.get("dieu_so", "")
        title   = meta.get("dieu_title", "")
        so_hieu = meta.get("so_hieu", "")
        header  = f"[Điều {dieu} - {title} | {so_hieu}]" if dieu else f"[{so_hieu}]"
        parts.append(f"{header}\n{doc.page_content}")
    return "\n\n" + "─"*50 + "\n\n".join(parts)

# ============================================================
# PHẦN MỚI: TẠO MÁY CHỦ KẾT NỐI VỚI WEB (FASTAPI)
# ============================================================

app = FastAPI(title="HVBot RAG API")

# Cho phép Web (HTML) có thể gửi tin nhắn qua Python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    userId: str = None

@app.post("/api/chat")
async def chat_api(request: ChatRequest):
    try:
        question = request.message
        print(f"\n[WEB GỬI CÂU HỎI]: {question}")
        
        # 1. Tìm kiếm quy chế bằng Hybrid Search
        raw_docs = retriever.invoke(question)
        reviews_text = format_docs(raw_docs)
        
        # 2. Đưa vào AI (Ollama) xử lý
        print("AI đang đọc quy chế và suy nghĩ...")
        result = chain.invoke({"reviews": reviews_text, "question": question})
        
        print(f"[XONG] Đã gửi câu trả lời về giao diện Web")
        return {"reply": result}
        
    except Exception as e:
        print(f"[LỖI RỒI]: {e}")
        return {"reply": f"Hệ thống gặp lỗi kỹ thuật: {str(e)}"}

# ============================================================
# LỆNH KHỞI CHẠY (BẮT BUỘC)
# ============================================================
if __name__ == "__main__":
    print("\n" + "!" * 50)
    print("  MÁY CHỦ AI ĐANG CHẠY...")
    print("  ĐỊA CHỈ API: http://localhost:5000/api/chat")
    print("  HÃY MỞ FILE HTML ĐỂ BẮT ĐẦU CHAT!")
    print("!" * 50)
    
    # Chạy máy chủ tại cổng 5000
    uvicorn.run(app, host="0.0.0.0", port=5000)