## Tech Stack liên quan tới AI:

1. **Xử lý đầu vào:**
   1. Dạng Tường thuật & Ngữ nghĩa (Narrative & Semantic)
      - Môn: văn, sử, tiếng anh,...
      - Đặc điểm: chứa sự kiện, diễn biến, quan hệ nhân quả, ẩn dụ
      - Thách thức: Dễ bị hallucination nếu mất ngữ cảnh hoặc sai lệch thời gian/ địa điểm
      - Hướng xử lý: GraphRag
      - Game Output: visual novel ?, sắp xếp dòng thời gian, trắc nghiệm đọc hiểu
   2. Dạng Mô tả Không gian & Trực quan (Spatial & Visual)
      - Môn: Địa, sinh, kỹ thuật công nghệ (liên quan đến bản vẽ)
      - Đặc điểm: thông tin nằm trong ảnh, sơ đồ,... Văn bản chỉ có vai trò chú thích, diễn đạt lại thông tin
      - Thách thức: PDF parser không nhận ảnh -> cần viết tool hoặc dùng VLM
      - Hướng xử lý: Multimodal LLM -> caption ảnh + mô tả
      - Game output:
   3. Dạng Cấu trúc & Phân loại (Structured & Taxonomy):
      - **Môn học:** Ngữ pháp Tiếng Anh (công thức thì), Bảng tuần hoàn Hóa học, Phân loại sinh vật học.
      - **Đặc điểm:** Có quy tắc cứng, thường trình bày dưới dạng bảng (table), danh sách (list), hoặc cây phả hệ.
      - **Thách thức:** RAG thông thường khi chunking (cắt nhỏ) sẽ làm vỡ cấu trúc bảng.
      - **Hướng xử lý:** Table Parsing (LlamaParse), chuyển đổi sang JSON/CSV, lưu vào SQL database.
      - **Game Output:** Flashcard (lật thẻ), Game nối cột (Matching), Điền vào chỗ trống
   4. Dạng Ký hiệu & Tính toán (Symbolic & Computational)
      - **Môn học:** Toán, Vật lý, Hóa học (phần bài tập tính toán).
      - **Đặc điểm:** Chứa dày đặc các ký hiệu LaTeX (∫,∑,...), phương trình cân bằng. Logic của nó là logic toán học, không phải logic ngôn ngữ.
      - **Thách thức:** LLM rất dở tính toán số học, dễ giải sai dù nói đúng lý thuyết.
      - **Hướng xử lý:** Code Interpreter (dùng Python để giải), Tool Calling (Wolfram Alpha).
      - **Game Output:** Game giải đố số học, Mô phỏng thí nghiệm, Điền số liệu còn thiếu
2. **Điều phối luồng**

3. Độ chính xác tính toán:

NOTE: như trên thì llm chỉ giỏi ngôn ngữ, không giỏi tính toán -> viết tool hoặc api như trên

### Tóm lại:

Công nghệ đề xuất cụ thể

**LangGraph:** Để dựng khung (Graph, State, Nodes).

**Neo4j:** DB graph, để sau milestone 1, hiện tại chỉ dùng redis với postgres. pgvector cho rag

**LangChain Core:** Để viết Prompt Template và tạo Chain cho từng Agent

**Pydantic:** Để định nghĩa class MathQuestion, HistoryQuestion... giúp ép kiểu dữ liệu đầu ra

**LLM Model:**

- Supervisor & Reviewer: Nên dùng model thông minh nhất (GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Pro) để điều phối và chấm điểm chính xác.
- Worker Agents: Có thể dùng model nhẹ hơn, rẻ hơn (GPT-4o-mini, Gemini Flash) để tiết kiệm chi phí vì nhiệm vụ đã được chia nhỏ cụ thể.

# **Tổng quan Kiến trúc Hệ thống: AI Tạo Nội dung Game Học tập**

## **1. Mục tiêu Dự án (Project Scope)**

Xây dựng một hệ thống Backend AI tự động, có khả năng:

- **Input:** Tiếp nhận đa dạng tài liệu học tập (SGK, Slide bài giảng, Giáo trình PDF/Word) của nhiều môn học (Toán, Lý, Văn, Sử, Anh, Sinh...).
- **Processing:** Hiểu sâu nội dung, tính toán lại các bài tập, xâu chuỗi sự kiện lịch sử và phân tích hình ảnh minh họa.
- **Output:** Sinh ra bộ dữ liệu câu hỏi (JSON) chuẩn hóa để nạp vào các Game giáo dục (Quiz, Timeline, Map Labeling, Flashcard).
- **Đối tượng:** Học sinh cấp 3 (Target ban đầu), mở rộng sau này.

## **2. Thách thức cốt lõi & Giải pháp Chiến lược**

Vấn đề lớn nhất là mỗi môn học có đặc thù dữ liệu khác nhau. Chúng ta không dùng một cách xử lý cho tất cả, mà chia thành **4 Trụ cột xử lý (4-Pillar Strategy)**:

| **Nhóm Dữ liệu**            | **Môn điển hình**    | **Đặc điểm khó**                         | **Giải pháp Công nghệ (Keytech)**                                   |
| --------------------------- | -------------------- | ---------------------------------------- | ------------------------------------------------------------------- |
| **Logic & Tính toán**       | Toán, Lý, Hóa        | LLM tính toán sai, nhiều ký hiệu $LaTeX$ | **Python REPL Tool** (Code Interpreter) để tính toán chính xác.     |
| **Tường thuật & Ngữ nghĩa** | Văn, Sử, GDCD        | Dài dòng, cần ngữ cảnh, quan hệ nhân-quả | **GraphRAG (Neo4j)** để hiểu mối quan hệ thực thể & dòng thời gian. |
| **Trực quan & Không gian**  | Địa, Sinh, Công nghệ | Thông tin nằm trong Hình ảnh/Bản đồ      | **Multimodal LLM (Vision)** để trích xuất thông tin từ ảnh.         |
| **Cấu trúc & Phân loại**    | Anh văn, Hóa (bảng)  | Quy tắc cứng, dạng bảng biểu             | **Structured Extraction** (LlamaParse) chuyển về JSON/SQL.          |

## **3. Kiến trúc Hệ thống (System Architecture)**

Sử dụng mô hình **Supervisor Agent (Mô hình Giám sát)** trên nền tảng **LangGraph**.

### **Sơ đồ Luồng dữ liệu (Data Flow)**

### **Chi tiết các thành phần trong LangGraph:**

1. **Supervisor (Router):** "Tổng đài viên". Nhận đoạn văn bản, quyết định xem nó thuộc môn nào/dạng nào để giao cho nhân viên chuyên trách.
2. **Specialized Agencies (Nhân viên chuyên trách):**

- _Math Agent:_ Biết viết code Python để giải phương trình, sinh đáp án đúng/sai dựa trên tính toán số học.
- _Story Agent:_ Biết truy vấn đồ thị tri thức để tìm nguyên nhân - kết quả của sự kiện lịch sử.
- _Visual Agent:_ Biết nhìn ảnh minh họa và đặt câu hỏi về các chi tiết trong ảnh.

1. **Reviewer (KCS):** "Giáo viên chấm thi". Kiểm tra lại câu hỏi do Agent con tạo ra. Nếu thấy sai đáp án hoặc câu hỏi vô nghĩa -> Trả về yêu cầu làm lại.

## **4. Công nghệ sử dụng (Tech Stack)**

### **A. AI & Orchestration (Bộ não)**

- **LangChain:** Framework cơ bản để giao tiếp với LLM.
- **LangGraph:** Framework nâng cao để xây dựng luồng đi phức tạp (vòng lặp feedback, rẽ nhánh) cho Agent.
- **LLM Models:** GPT-4o hoặc Gemini 1.5 Pro (cho Supervisor/Reviewer), GPT-4o-mini (cho các task đơn giản).

### **B. Ingestion & Pre-processing (Xử lý đầu vào)**

- **LlamaParse / Unstructured:** Công cụ để đọc file PDF, giữ nguyên định dạng bảng biểu và công thức toán học.

### **C. Database (Bộ nhớ) - Mô hình Polyglot**

Chúng ta sử dụng chiến lược "Đa cơ sở dữ liệu" nhưng bắt đầu đơn giản:

- **PostgreSQL (Core):**
- Lưu trữ dữ liệu người dùng & App.
- Lưu trữ **Vector Embeddings** (dùng pgvector) cho tính năng RAG cơ bản.
- Lưu trữ **Kết quả câu hỏi (JSONB)** cho Game Client tải về.
- Lưu trữ **LangGraph Checkpoint** (trạng thái hoạt động của AI).
- **Neo4j (Advanced - Thêm vào sau):**
- Lưu trữ **Knowledge Graph** cho các môn Xã hội (Sử/Văn) để AI hiểu ngữ cảnh sâu hơn.

## **5. Lộ trình Triển khai (Roadmap)**

- **Giai đoạn 1 (MVP - Thái cực Logic):**
- Tập trung vào môn **Toán/Lý**.
- Xây dựng Math Agent với khả năng dùng Python Tool để giải bài tập.
- DB: Chỉ dùng PostgreSQL.
- **Giai đoạn 2 (Thái cực Ngữ nghĩa):**
- Mở rộng sang **Sử/Văn**.
- Tích hợp Story Agent và thử nghiệm GraphRAG.
- DB: Thêm Neo4j.
- **Giai đoạn 3 (Đa phương tiện & Mở rộng):**
- Xử lý hình ảnh (Sinh/Địa).
- Hoàn thiện luồng Reviewer để đảm bảo chất lượng cao.
- Tối ưu hóa API cho Game Client.
