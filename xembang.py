import chromadb

# 1. Trỏ đường dẫn vào đúng thư mục database của bạn
db_path = "./chroma_langchain_db"

print(f"📁 Đang mở database tại: {db_path}...")
try:
    # 2. Kết nối với ChromaDB
    client = chromadb.PersistentClient(path=db_path)
    
    # Lấy đúng tên collection bạn đã tạo trong file vector.py
    collection = client.get_collection(name="quy_dinh_hvnh")
    
    # 3. Lấy toàn bộ dữ liệu ra (không lấy vector số học cho đỡ rối mắt)
    data = collection.get(include=["documents", "metadatas"])
    
    # 4. In thống kê
    tong_so_doan = len(data['ids'])
    print("\n" + "="*50)
    print(f"✅ TỔNG SỐ ĐOẠN VĂN BẢN TRONG DATABASE: {tong_so_doan}")
    print("="*50)
    
    if tong_so_doan == 0:
        print("Database đang trống không!")
    else:
        print("\n👇 XEM THỬ 3 ĐOẠN DỮ LIỆU ĐẦU TIÊN:\n")
        # Chỉ in 3 cái đầu tiên để màn hình không bị trôi dài
        for i in range (tong_so_doan):
            print(f"🔸 [ID]: {data['ids'][i]}")
            print(f"🔸 [Nguồn file]: {data['metadatas'][i].get('source', 'Không rõ')}")
            # Cắt lấy 200 ký tự đầu của đoạn văn để xem thử
            print(f"🔸 [Nội dung]: {data['documents'][i][:200]}...") 
            print("-" * 50)

except Exception as e:
    print(f"\n❌ Lỗi: {e}")
    print("Hãy chắc chắn thư mục 'chroma_langchain_db' đang nằm cùng chỗ với file này.")