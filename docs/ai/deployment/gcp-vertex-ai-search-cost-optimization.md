# GCP Vertex AI Search - Setup Rẻ Nhất (2026)

> **Cập nhật:** 2026-03-08  
> **Nguồn:** MCP Tavily Research - Vertex AI Search cost optimization 2026  
> **Mục tiêu:** Setup Vertex AI Search với chi phí thấp nhất cho dự án educational game nhỏ

## 🎯 Tóm Tắt Nhanh

**Setup FREE cho development/testing:**

- ✅ **10,000 queries/tháng MIỄN PHÍ** (free trial)
- ✅ **$300 credit** cho tài khoản GCP mới
- ✅ Chi phí thực tế: **$0** trong giai đoạn dev/test
- ✅ Sau khi hết credit: **$30-60/tháng** (với Standard Edition)

**Không cần App ngay từ đầu:**

- Chỉ cần tạo Data Store với documents
- Không cần tạo App trong console
- Dùng API trực tiếp qua code

---

## 📊 So Sánh Chi Phí

### Standard vs Enterprise Edition

| Tính năng                       | Standard           | Enterprise          |
| ------------------------------- | ------------------ | ------------------- |
| **Query pricing**               | $1.50 / 1K queries | $4.00 / 1K queries  |
| **Unstructured search**         | ✅                 | ✅                  |
| **Structured search**           | ✅                 | ✅                  |
| **Core Generative Answers**     | ❌                 | ✅ (included)       |
| **Advanced Generative Answers** | ❌                 | +$4.00 / 1K queries |
| **Website search**              | ❌                 | ✅                  |
| **Extractive answers**          | ✅ (cần toggle)    | ✅ (cần toggle)     |

### Semantic Add-on (Tùy chọn)

| Tính năng             | Chi phí                         |
| --------------------- | ------------------------------- |
| **Per-query charge**  | +$0.75 / 1K queries             |
| **Embedding storage** | +$1.50 / GB / tháng             |
| **Khi nào cần**       | Hybrid search, Core/Advanced GA |

### Web Grounding (RẤT ĐẮT - Tránh)

| Tính năng                    | Chi phí              |
| ---------------------------- | -------------------- |
| **Web grounding**            | $45 / 1K requests ⚠️ |
| **Grounding with your data** | $2.50 / 1K requests  |

---

## 🏆 Setup Rẻ Nhất - Checklist Chi Tiết

### Bước 1: Tận Dụng Free Tier

```bash
# 1. Tạo tài khoản GCP MỚI (nếu chưa có)
# → Nhận $300 credit (valid 90 ngày)
# → Link: https://cloud.google.com/free

# 2. Tạo project mới
gcloud projects create YOUR-PROJECT-ID --name="AIServices"
gcloud config set project YOUR-PROJECT-ID

# 3. Enable APIs (bắt buộc để kích hoạt free trial)
gcloud services enable \
    discoveryengine.googleapis.com \
    aiplatform.googleapis.com \
    storage.googleapis.com
```

**🎁 Free Benefits Breakdown:**

- ✅ **10,000 search queries/month FREE** (recurring)
- ✅ **$300 credit** (one-time, 90 days)
- ⚠️ Advanced Generative Answers **KHÔNG** được tính vào 10K free queries

### Bước 2: Chọn Standard Edition (RẺ hơn)

```bash
# Khi tạo data store, KHÔNG chọn Enterprise features:
# - Uncheck "Advanced website indexing"
# - Uncheck "Advanced generative answers"
# - Use "Generic" industry vertical (free)

# Tạo data store (Standard)
gcloud alpha discovery-engine data-stores create \
    aiservice-datastore-m1 \
    --location=asia-southeast1 \
    --industry-vertical=GENERIC \
    --solution-type=SOLUTION_TYPE_SEARCH \
    --config=unstructured
```

**Cost Impact:**

- Standard: $1.50 / 1K queries ($0.0015 per query)
- Enterprise: $4.00 / 1K queries ($0.004 per query)
- **Tiết kiệm 62.5%** khi dùng Standard

### Bước 3: TRÁNH Semantic Add-on Ban Đầu

**Không nên enable:**

- ❌ Semantic Retrieval
- ❌ Hybrid Search (requires Semantic)
- ❌ Core Generative Answers (requires Semantic)
- ❌ Advanced Generative Answers

**Chỉ dùng:**

- ✅ Basic unstructured search
- ✅ Keyword search
- ✅ Extractive answers (toggle trong console)

**Cost Impact:**

- WITHOUT Semantic: $1.50 / 1K queries
- WITH Semantic: $1.50 + $0.75 = $2.25 / 1K queries (+50%)
- Plus: $1.50/GB/month cho embedding storage

### Bước 4: Scale-to-Zero Configuration (Tiết Kiệm Node Hours)

**Không áp dụng cho Search:**

- Vertex AI Search **KHÔNG** có node hours billing
- Chỉ tính theo per-query pricing
- Không cần lo autoscaling/replicas

**Áp dụng cho Gemini LLM (trong pipeline):**

```python
# src/graph/nodes/*.py
# Sử dụng Gemini với caching để giảm token costs

llm = ChatVertexAI(
    model_name="gemini-1.5-flash",  # Cheaper than Pro
    temperature=0.7,
    # Vertex implicit caching: 90% discount on cached tokens
    # Tự động áp dụng cho repeated prompts
)
```

**LLM Cost Impact:**

- Gemini 1.5 Flash: Cheaper than Pro
- Implicit caching: 90% discount on cached input tokens
- Explicit caching: Similar discount + storage cost

### Bước 5: Limit Document Retention

```python
# Chỉ index documents quan trọng
# Xóa documents cũ/không cần thiết

from google.cloud import discoveryengine_v1

# Purge old documents để giảm storage cost
client.purge_documents(
    parent=f"projects/{project}/locations/{location}/dataStores/{datastore_id}/branches/default_branch",
    filter="update_time < \"2026-01-01T00:00:00Z\""  # Example
)
```

**Storage Cost:**

- Document storage: Included in query pricing
- Embedding storage: $1.50/GB/month (only if Semantic enabled)

### Bước 6: Monitor Query Usage

```bash
# Setup billing alerts để tránh surprise charges
gcloud alpha billing budgets create \
    --billing-account=BILLING_ACCOUNT_ID \
    --display-name="Vertex AI Search Budget" \
    --budget-amount=50USD \
    --threshold-rule=percent=50 \
    --threshold-rule=percent=80 \
    --threshold-rule=percent=100
```

**Daily Tracking:**

- Theo dõi query count trong Cloud Console
- Giữ < 10K queries/month để ở trong free tier
- Sau khi hết free tier: mục tiêu < 30K queries/month ($45/month)

---

## 💰 Ước Tính Chi Phí Thực Tế

### Profile A: Development/Testing (HIỆN TẠI)

**Assumptions:**

- 1,000 queries/day = 30K queries/month
- < 10K documents
- Standard Edition
- No Semantic add-on
- Using free tier

**Chi phí:**

```
Query cost:
- 30K queries/month
- First 10K FREE (trial)
- Remaining 20K × $1.50 / 1K = $30/month

Offset by new account credit:
- $300 credit covers 10 months ($30/mo)

TOTAL: $0 for first 10 months
After credits: $30/month
```

### Profile B: Light Production (Vài Trăm Users)

**Assumptions:**

- 3,000 queries/day = 90K queries/month
- 10K-50K documents
- Standard Edition
- Optional: Semantic add-on enabled

**Chi phí:**

```
Base cost (Standard):
90K queries × $1.50 / 1K = $135/month

If Semantic add-on enabled:
90K × $0.75 / 1K = $67.50/month
+ Embedding storage (1-5 GB) = $1.50-7.50/month
Subtotal: $204-210/month

TOTAL:
- Without Semantic: $135/month
- With Semantic: $204-210/month
```

### Profile C: Modest Production (1-5K Daily Users)

**Assumptions:**

- 50,000 queries/day = 1.5M queries/month
- 50K-100K documents
- Standard Edition recommended

**Chi phí:**

```
Standard Edition:
1.5M queries × $1.50 / 1K = $2,250/month

Enterprise Edition (nếu cần GA features):
1.5M queries × $4.00 / 1K = $6,000/month
+ Advanced GA: 1.5M × $4.00 / 1K = $6,000/month
TOTAL Enterprise: $12,000/month ⚠️

RECOMMENDATION:
- Dùng Standard ($2,250/mo)
- Tránh Enterprise cho đến khi THỰC SỰ cần
```

---

## 🎓 Top 8 Best Practices Tiết Kiệm Chi Phí

### 1. ✅ Dùng Standard Edition (Ưu tiên #1)

**Impact:** Tiết kiệm 62.5% per query  
**When:** Chỉ cần basic search, không cần generative answers

### 2. ✅ Tránh Semantic Add-on Ban Đầu

**Impact:** Tiết kiệm $0.75 / 1K queries + $1.50/GB storage  
**When:** Keyword search đủ tốt, không cần semantic/hybrid

### 3. ✅ Tận Dụng Free Tier & Credits

**Impact:** $0 cost cho 10-12 tháng đầu  
**How:** 10K free queries/month + $300 new account credit

### 4. ✅ Cache LLM Prompts (Gemini)

**Impact:** Giảm 90% token cost cho cached inputs  
**How:** Vertex implicit caching tự động apply

### 5. ✅ Batch Document Updates

**Impact:** Giảm build costs (nếu có)  
**How:** Import documents 1 lần/tuần thay vì real-time

### 6. ✅ Limit Document Retention

**Impact:** Giảm storage & potential build costs  
**How:** Purge old/unused documents định kỳ

### 7. ✅ Monitor & Alert on Usage

**Impact:** Tránh surprise billing  
**How:** Cloud billing alerts tại $50, $100, $200

### 8. ✅ Chọn Region Rẻ Hơn (Nếu Flexible)

**Impact:** Varies by region  
**Note:** `asia-southeast1` OK, nhưng US regions có thể rẻ hơn cho một số services

---

## 🚫 Tránh Các Chi Phí "Bẫy"

### ⚠️ TRÁNH: Web Grounding ($45 / 1K requests)

```python
# KHÔNG dùng feature này cho small projects
# Cost: $45 per 1,000 = $0.045 per request (30x đắt hơn base search)

# Thay vào đó: dùng grounding with your own data ($2.50 / 1K)
```

### ⚠️ TRÁNH: Advanced Generative Answers ($4 / 1K queries)

```python
# Chỉ enable khi THỰC SỰ cần AI-generated comprehensive answers
# Standard search + extractive answers thường đủ

# Standard extractive: Included
# Advanced GA: +$4 / 1K queries (chưa tính Semantic add-on)
```

### ⚠️ TRÁNH: Enterprise Edition (Khi Chưa Cần)

```python
# Enterprise cost: $4 / 1K queries
# Standard cost: $1.50 / 1K queries
# Difference: $2.50 / 1K = 166% markup

# Chỉ upgrade khi cần:
# - Website crawling
# - Core Generative Answers
# - Advanced GA
```

### ⚠️ TRÁNH: Quá Nhiều Embeddings Storage

```python
# Semantic add-on: $1.50 / GB / month
# 1M vectors (768-dim) ≈ 3-5 GB ≈ $4.50-7.50/month

# Optimize:
# - Reduce vector dimensions nếu có thể
# - Chỉ embed documents quan trọng
# - Purge old embeddings
```

---

## 📈 Quotas & Limits (Cần Biết)

### Default Quotas (Per Project, Per Region)

| Resource                    | Quota      | Notes                       |
| --------------------------- | ---------- | --------------------------- |
| **Complete query requests** | 300/min    | Đủ cho dev/light production |
| **Document write requests** | 12,000/min | Đủ cho bulk imports         |
| **Async import operations** | 5/min      | Batch imports               |
| **Total data stores**       | 100        | Per project                 |
| **Total engines**           | 150        | Per project                 |
| **Regional documents**      | 10M        | Per location                |

### Quota Increase Needed When:

- Expected QPS > 5 queries/second (300/min)
- Bulk imports > 200/min
- Multiple data stores > 100

**How to Request:**

```bash
# Contact Google Cloud Support
# Or use quota increase form in Console:
# IAM & Admin → Quotas → Vertex AI Search → Request Increase
```

---

## 🛠️ Setup Commands - Standard Edition (Rẻ Nhất)

### Step 1: Enable APIs & Create Data Store

```bash
# Set project
export PROJECT_ID="green-mercury-485016-n1"
export LOCATION="asia-southeast1"
export DATASTORE_ID="aiservice-datastore-v2"

gcloud config set project $PROJECT_ID

# Enable APIs
gcloud services enable \
    discoveryengine.googleapis.com \
    aiplatform.googleapis.com \
    storage.googleapis.com

# Create data store (STANDARD edition)
gcloud alpha discovery-engine data-stores create \
    $DATASTORE_ID \
    --location=$LOCATION \
    --industry-vertical=GENERIC \
    --solution-type=SOLUTION_TYPE_SEARCH \
    --content-config=CONTENT_REQUIRED
```

### Step 2: Upload Documents (One-time)

```bash
# Create GCS bucket
export BUCKET_NAME="${PROJECT_ID}-search-data"
gsutil mb -l $LOCATION gs://$BUCKET_NAME

# Upload sample documents
# (Prepare JSON lines format)
cat > sample_docs.jsonl << 'EOF'
{"id": "doc1", "content": {"mimeType": "text/plain", "uri": "gs://bucket/doc1.txt"}}
{"id": "doc2", "content": {"mimeType": "text/plain", "uri": "gs://bucket/doc2.txt"}}
EOF

# Import documents
gcloud alpha discovery-engine import documents \
    --data-store=$DATASTORE_ID \
    --location=$LOCATION \
    --source-gcs-uri=gs://$BUCKET_NAME/sample_docs.jsonl
```

### Step 3: Query (Via API - Không Cần App)

```python
from google.cloud import discoveryengine_v1

project_id = "green-mercury-485016-n1"
location = "asia-southeast1"
data_store_id = "aiservice-datastore-v2"

client = discoveryengine_v1.SearchServiceClient()

# Construct serving config
serving_config = f"projects/{project_id}/locations/{location}/dataStores/{data_store_id}/servingConfigs/default_config"

# Search request
request = discoveryengine_v1.SearchRequest(
    serving_config=serving_config,
    query="your search query",
    page_size=10,
    # Extractive answers (FREE on Standard)
    content_search_spec={
        "extractive_content_spec": {
            "max_extractive_answer_count": 3,
            "max_extractive_segment_count": 5
        }
    }
)

response = client.search(request)

# Count towards FREE 10K/month quota ✅
```

### Step 4: Enable Extractive Answers (Console)

**QUAN TRỌNG:** Extractive answers có sẵn trên Standard edition, KHÔNG cần Enterprise!

1. Vào Cloud Console → AI Applications → Search
2. Click vào Data Store của bạn
3. Click **"Configurations"** tab
4. Scroll xuống **"Response Settings"**
5. **KHÔNG** cần toggle "Enterprise edition features"
6. Chỉ cần set:
   - ✅ Return extractive answers: ON
   - ✅ Max extractive answers: 3
   - ✅ Max extractive segments: 5

**Lỗi 400 "Cannot use enterprise edition features":**

- Xảy ra khi code request `snippetSpec` hoặc `summarySpec` (Enterprise features)
- Chỉ dùng `extractive_content_spec` (Standard feature)

---

## 🔍 Alternatives Comparison (Cost Reference)

### Vertex AI Search vs Alternatives

| Solution                        | Cost (1M vectors/month) | Notes                           |
| ------------------------------- | ----------------------- | ------------------------------- |
| **Vertex AI Search (Standard)** | ~$50-150                | 30-100K queries + storage       |
| **Pinecone**                    | ~$50-280                | 1M-10M vectors, managed         |
| **Weaviate Cloud**              | ~$45+                   | Flex plan, serverless available |
| **Milvus (Zilliz Cloud)**       | ~$99+                   | Managed tiers                   |
| **Self-hosted Milvus**          | ~$20-50                 | Infrastructure + ops overhead   |

**Recommendation:**

- **Development/Small scale (< 1M vectors):** Vertex AI Search Standard với free tier
- **Cost-sensitive production:** Self-hosted Milvus hoặc Weaviate
- **Need GCP integration + LLM features:** Vertex AI Search (best integration)

---

## 📚 Known Issues & Workarounds

### Issue 1: Default API Quota Thấp

**Problem:** Community reports default quota = 5 requests/min  
**Solution:** Request quota increase qua Support early  
**Impact:** Can limit development testing

### Issue 2: Build/Hosting Cost Ambiguity

**Problem:** Community reports conflicting info về index build costs  
**Workaround:** Budget conservatively, contact Google Sales for quote  
**Impact:** Hard to estimate exact costs for large imports

### Issue 3: Embedding Storage Calculation

**Problem:** Không có official bytes-per-vector documentation  
**Workaround:** Measure empirically (test với sample vectors)  
**Formula:** ~768-dim vector ≈ 3-4 KB per vector

---

## ✅ Action Plan - Setup Rẻ Nhất Cho Project Này

### Immediate Steps (Today)

```bash
# 1. Verify free tier status
gcloud alpha billing accounts list
# Check if $300 credit still available

# 2. Create NEW data store (Standard, no apps needed)
gcloud alpha discovery-engine data-stores create \
    aiservice-datastore-standard \
    --location=asia-southeast1 \
    --industry-vertical=GENERIC \
    --solution-type=SOLUTION_TYPE_SEARCH \
    --content-config=CONTENT_REQUIRED

# 3. Update .env.develop
# DATA_STORE_ID=aiservice-datastore-standard

# 4. Test with <100 queries to verify
```

### Update Code (Using Standard Features Only)

```python
# src/services/vertex_search.py
# ONLY use extractive_content_spec (Standard feature)

content_search_spec = discoveryengine.SearchRequest.ContentSearchSpec(
    extractive_content_spec=discoveryengine.SearchRequest.ContentSearchSpec.ExtractiveContentSpec(
        max_extractive_answer_count=3,  # FREE on Standard
        max_extractive_segment_count=5,
    ),
    # Remove snippetSpec (Enterprise only)
    # Remove summarySpec (Enterprise only)
)
```

### Monitor Costs Weekly

```bash
# Check current month usage
gcloud alpha discovery-engine operations list \
    --location=asia-southeast1 \
    --filter="done=true"

# Check billing
gcloud billing accounts get-iam-policy BILLING_ACCOUNT_ID
```

### Expected Costs

| Period               | Queries/Month | Cost                        |
| -------------------- | ------------- | --------------------------- |
| **Month 1-10**       | 30K           | $0 (10K free + $300 credit) |
| **Month 11+**        | 30K           | $30/month                   |
| **Light production** | 90K           | $135/month                  |

---

## 📞 Get Help / Clarifications

### Contact Google For:

1. ✅ Production pricing quote (if scaling > 100K queries/month)
2. ✅ Quota increase requests
3. ✅ Enterprise features evaluation (if really needed)
4. ✅ Build/hosting cost clarification

### Self-Service Resources:

- Pricing Calculator: https://cloud.google.com/products/calculator
- Vertex AI Search Pricing: https://cloud.google.com/generative-ai-app-builder/pricing
- Quotas Documentation: https://cloud.google.com/generative-ai-app-builder/quotas

---

## 🎯 Summary: Setup RẺ NHẤT

1. ✅ **Dùng Standard Edition** ($1.50 / 1K queries)
2. ✅ **KHÔNG enable Semantic add-on** (save $0.75 / 1K + storage)
3. ✅ **Tận dụng 10K free queries/month** (recurring)
4. ✅ **Dùng $300 new account credit** (10 months coverage)
5. ✅ **Chỉ dùng extractive answers** (FREE trên Standard)
6. ✅ **TRÁNH Enterprise features** (cho đến khi thực sự cần)
7. ✅ **Monitor usage weekly** (billing alerts)
8. ✅ **Không cần tạo App** trong console (query trực tiếp qua API)

**Chi phí thực tế:** $0 trong 10 tháng đầu, $30-60/month sau đó.
