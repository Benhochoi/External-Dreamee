print(">>> 1. ĐANG KHỞI ĐỘNG HỆ THỐNG... <<<")
import warnings
warnings.filterwarnings("ignore")

from langchain_ollama.llms import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate

print(">>> 2. ĐANG NẠP TÀI LIỆU TỪ VECTOR.PY... <<<")
from vector import retriever

print(">>> 3. ĐANG GỌI NÃO AI (QWEN 3B)... <<<")
# Đã thêm :3b để máy chạy nhẹ nhàng, không bị văng
model = OllamaLLM(model="qwen2.5")

template = """
Bạn là chuyên gia trong lĩnh vực tư vấn các quy chế, quy định của trường Học Viện Ngân Hàng.
Chỉ trả lời dựa trên thông tin được cung cấp dưới đây. Nếu không có thông tin, hãy nói "Tôi không tìm thấy nội dung này".

Tài liệu quy chế liên quan:
{reviews}

Câu hỏi cần trả lời: {question}
"""

prompt = ChatPromptTemplate.from_template(template)
chain = prompt | model

# Hàm chuyển đổi danh sách tài liệu thành chữ bình thường
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

def main():
    print("\n" + "=" * 60)
    print(" TRỢ LÝ QUY CHẾ HVNH ĐÃ SẴN SÀNG!")
    print("=" * 60)
    
    while True:
        question = input("\n Tôi có thể giúp gì cho bạn (gõ 'kết thúc' để thoát): ")
        
        if question.lower() == "kết thúc":
            print("Tạm biệt!")
            break
        if not question.strip():
            continue
            
        print("Đang lục tìm tài liệu nội bộ...")
        # Lấy tài liệu thô
        raw_docs = retriever.invoke(question)
        
        # Lọc tài liệu thành chữ
        reviews_text = format_docs(raw_docs)
        # CHÈN THÊM DÒNG NÀY ĐỂ DEBUG (KIỂM TRA):
        print("\n[DEBUG] KHO TÀI LIỆU VỪA BỐC RA ĐƯỢC:\n", reviews_text)
        print("-" * 50)
        print(" AI đang đọc tài liệu và suy nghĩ...")
        # Đưa chữ vào cho Qwen đọc
        result = chain.invoke({"reviews": reviews_text, "question": question})
    
        print("\n TRẢ LỜI:")
        print(result)

if __name__ == "__main__":
    main()