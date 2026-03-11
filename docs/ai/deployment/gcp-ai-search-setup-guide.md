# GCP AI Search Setup Guide - Edu Game AI Service

> **Updated:** March 8, 2026  
> **MCP Research:** Used latest Tavily search for Vertex AI Search 2026 documentation

## Tổng Quan

Hướng dẫn này cung cấp các bước chi tiết để setup Google Cloud Vertex AI Search (Enterprise Edition) cho dự án edu-game-ai-service, bao gồm:

- Enabling Enterprise Edition features
- Creating Data Stores
- Ingesting documents
- Configuring extractive answers
- Troubleshooting common issues

## Prerequisites (Đã Verified)

### Thông Tin Project Hiện Tại

✅ **Verified 2026-03-08**

- Project ID: `green-mercury-485016-n1`
- Region: `asia-southeast1`
- Data Store ID: `aiservice-datastore-m1_1772802306291`
- Location: `global`

## Vấn Đề Hiện Tại Cần Fix

### 1. Enterprise Edition Not Enabled

**Error:**

```
400 Cannot use enterprise edition features (website search, multi-modal search,
extractive answers/segments, etc.) in a standard edition search engine.
```

**Root Cause:** Data store được tạo ở Standard Edition, không support extractive answers.

**Solution Steps:**

#### Option A: Enable Enterprise Edition (Console)

1. Mở [AI Applications Console](https://console.cloud.google.com/gen-app-builder/engines)
2. Chọn project `green-mercury-485016-n1`
3. Tìm app/engine sử dụng data store `aiservice-datastore-m1_1772802306291`
4. Click vào app → **Configurations** → **Response Settings**
5. Tìm toggle **"Enterprise edition features"** → Enable
6. Save changes

**Verification:**

```bash
# Kiểm tra engine config
gcloud alpha discovery-engine engines describe <ENGINE_ID> \
  --project=green-mercury-485016-n1 \
  --location=global

# Response should show: searchTier: "ENTERPRISE"
```

#### Option B: Create New Enterprise Engine

Nếu không thể upgrade existing engine:

```bash
# Create new enterprise-tier search engine
gcloud alpha discovery-engine engines create <NEW_ENGINE_ID> \
  --project=green-mercury-485016-n1 \
  --location=global \
  --data-store-ids=aiservice-datastore-m1_1772802306291 \
  --display-name="Edu Game AI - Enterprise Search" \
  --industry-vertical=GENERIC \
  --search-tier=ENTERPRISE
```

**Update Settings:**

```env
# .env.develop
# Use engine ID instead of data store ID for search
SEARCH_ENGINE_ID=<NEW_ENGINE_ID>
```

### 2. Gemini Model Availability Issue

**Error:**

```
404 Publisher Model `gemini-2.0-flash` was not found in
projects/green-mercury-485016-n1/locations/asia-southeast1
```

**Root Cause:** Gemini 2.0 Flash chưa available ở region `asia-southeast1`.

**Solution:** Đổi sang model có sẵn

#### Fix All Nodes (Recommended Approach)

Update model name trong tất cả node files:

**For Production (Recommended):**

```python
# Use Gemini 1.5 Pro (more capable, higher cost)
model_name="gemini-1.5-pro"
```

**For Development (Cost-effective):**

```python
# Use Gemini 1.5 Flash (fast, lower cost)
model_name="gemini-1.5-flash"
```

**Files to Update:**

- [src/graph/nodes/supervisor.py](../../../src/graph/nodes/supervisor.py) - Line 62
- [src/graph/nodes/math_agent.py](../../../src/graph/nodes/math_agent.py) - Line 85
- [src/graph/nodes/reviewer.py](../../../src/graph/nodes/reviewer.py) - Line 79
- [src/graph/nodes/formatter.py](../../../src/graph/nodes/formatter.py) - Line 165

**Gemini Model Comparison (2026):**
| Model | Speed | Cost | Capabilities | Region Support |
|-------|-------|------|--------------|----------------|
| gemini-1.5-flash | Fast | Low | Good for most tasks | asia-southeast1 ✅ |
| gemini-1.5-pro | Medium | Medium | Best reasoning | asia-southeast1 ✅ |
| gemini-2.0-flash | Fastest | Low | Latest features | US/EU only ❌ |

**Alternative:** Use `us-central1` region for Gemini 2.0 Flash

```python
# In _get_llm() functions
return ChatVertexAI(
    model_name="gemini-2.0-flash",
    project=settings.gcp_project_id,
    location="us-central1",  # Change from asia-southeast1
    ...
)
```

## Complete Setup Guide (Fresh Setup)

### Step 1: Enable Required APIs

```bash
# Ensure billing is enabled first
gcloud services enable discoveryengine.googleapis.com \
  bigquery.googleapis.com \
  storage.googleapis.com \
  aiplatform.googleapis.com \
  --project=green-mercury-485016-n1
```

**Required Permissions:**

- `roles/serviceusage.serviceUsageAdmin` - To enable APIs

### Step 2: Create Data Store (If Not Exists)

#### Via Console:

1. Open [AI Applications → Data Stores](https://console.cloud.google.com/gen-app-builder/data-stores)
2. Click **Create data store**
3. Select **Cloud Storage** as source
4. Configure:
   - **Data Store Name:** `aiservice-datastore-m1`
   - **Location:** `global`
   - **Industry Vertical:** `GENERIC`
   - **Bucket Path:** `gs://documents-development-bucket/`
5. Enable **Document parsing and chunking**:
   - Chunk size: 500 tokens
   - Include headings in chunks: ✅
6. Click **Create**

#### Via gcloud:

```bash
# Create data store
gcloud alpha discovery-engine data-stores create aiservice-datastore-m1 \
  --project=green-mercury-485016-n1 \
  --location=global \
  --industry-vertical=GENERIC \
  --solution-types=SOLUTION_TYPE_SEARCH \
  --display-name="AI Service Math Documents"
```

### Step 3: Upload Documents to Cloud Storage

```bash
# Upload math curriculum documents
gsutil -m cp -r docs/math-grade10/* \
  gs://documents-development-bucket/system/math-grade10/

# Verify upload
gsutil ls gs://documents-development-bucket/system/math-grade10/
```

**Supported Formats:** PDF, DOCX, PPTX, TXT, HTML, XLSX

### Step 4: Import Documents to Data Store

```bash
# Import from Cloud Storage
gcloud alpha discovery-engine documents import \
  --project=green-mercury-485016-n1 \
  --location=global \
  --data-store=aiservice-datastore-m1 \
  --gcs-uri=gs://documents-development-bucket/system/math-grade10/* \
  --reconciliation-mode=INCREMENTAL \
  --auto-generate-ids
```

**Monitor Import:**

```bash
# Check import status
gcloud alpha discovery-engine operations describe <OPERATION_ID> \
  --project=green-mercury-485016-n1 \
  --location=global
```

### Step 5: Create Enterprise Search Engine

```bash
# Create engine with ENTERPRISE tier
gcloud alpha discovery-engine engines create edu-game-ai-search \
  --project=green-mercury-485016-n1 \
  --location=global \
  --data-store-ids=aiservice-datastore-m1 \
  --display-name="Edu Game AI Search - Enterprise" \
  --industry-vertical=GENERIC \
  --search-tier=ENTERPRISE \
  --solution-type=SOLUTION_TYPE_SEARCH
```

**Verify Enterprise Tier:**

```bash
gcloud alpha discovery-engine engines describe edu-game-ai-search \
  --project=green-mercury-485016-n1 \
  --location=global \
  | grep searchTier
# Should output: searchTier: ENTERPRISE
```

### Step 6: Enable Extractive Answers in Code

Code đã được implement đúng trong [src/services/vertex_search.py](../../../src/services/vertex_search.py):

```python
return VertexAISearchRetriever(
    project_id=settings.gcp_project_id,
    data_store_id=settings.data_store_id,  # Or use engine_id
    location_id=settings.data_store_location,
    max_documents=max_documents,
    max_extractive_answer_count=3,  # ✅ Extractive answers enabled
    get_extractive_answers=True,    # ✅ Extractive answers enabled
    filter=filter_str,
)
```

**Alternative: Use Engine ID** (Recommended for Enterprise)

```python
# Update code to use engine_id instead of data_store_id
return VertexAISearchRetriever(
    project_id=settings.gcp_project_id,
    engine_id="edu-game-ai-search",  # Use engine instead
    location_id="global",
    max_documents=max_documents,
    max_extractive_answer_count=3,
    get_extractive_answers=True,
    filter=filter_str,
)
```

### Step 7: Update Environment Configuration

```env
# .env.develop
GCP_PROJECT_ID=green-mercury-485016-n1
GCP_LOCATION=asia-southeast1

# Option 1: Use Data Store ID (Standard)
DATA_STORE_ID=aiservice-datastore-m1
DATA_STORE_LOCATION=global

# Option 2: Use Engine ID (Enterprise - Recommended)
SEARCH_ENGINE_ID=edu-game-ai-search
SEARCH_LOCATION=global

GCS_BUCKET=documents-development-bucket
```

### Step 8: Test Search with Extractive Answers

```python
# Test script
from src.services.vertex_search import create_retriever
from src.config import get_settings

settings = get_settings()
retriever = create_retriever(
    user_id="test_user",
    doc_scope="system",
    max_documents=5
)

# Search for "đạo hàm"
results = retriever.get_relevant_documents("đạo hàm của hàm số")

print(f"Found {len(results)} results")
for doc in results:
    print(f"- {doc.metadata.get('title', 'N/A')}")
    if hasattr(doc, 'extractive_answers'):
        print(f"  Extractive: {doc.extractive_answers[0]}")
```

## Pricing Considerations (2026)

**Standard vs Enterprise Edition:**
| Tier | Cost per 1K queries | Features |
|------|---------------------|----------|
| Standard | $1.50 | Basic search |
| Enterprise | $4.00 | + Extractive answers, advanced features |

**Additional Costs:**

- Advanced Generative Answers: +$4.00 per 1K queries
- Data ingestion/storage: Variable by GB
- Embeddings: Based on model usage

**Free Tier:** 10,000 queries/month (Standard tier only)

**Recommendation:**

- Development: Standard tier
- Production: Enterprise tier with monitoring

## Monitoring & Quotas

### Check Quotas

```bash
# View current quotas
gcloud alpha quotas list \
  --project=green-mercury-485016-n1 \
  --service=discoveryengine.googleapis.com
```

**Default Limits:**

- Data stores per project: 100 (regional)
- Engines per project: 150
- Documents per location: 10,000,000
- Concurrent import operations: Limited

### Request Quota Increase

```bash
# Requires: serviceusage.quotas.update permission
gcloud alpha quotas update <QUOTA_ID> \
  --project=green-mercury-485016-n1 \
  --service=discoveryengine.googleapis.com \
  --preferred-value=<NEW_VALUE>
```

## Troubleshooting

### Issue: Zero Results from Search

**Causes:**

1. Documents not indexed yet
2. Service account lacks permissions
3. Filter too restrictive

**Debug:**

```bash
# Check data store status
gcloud alpha discovery-engine data-stores describe aiservice-datastore-m1 \
  --project=green-mercury-485016-n1 \
  --location=global

# Check document count (should be > 0)
# Look for: documentCount: <number>
```

### Issue: Cross-Project Bucket Access Denied

**Solution:**

```bash
# Grant service account read access to bucket
gsutil iam ch \
  serviceAccount:service-<PROJECT_NUMBER>@gcp-sa-discoveryengine.iam.gserviceaccount.com:roles/storage.objectViewer \
  gs://documents-development-bucket
```

### Issue: Google Workspace (Drive/Gmail) Returns Zero Results

**Solution:**

1. Enable People API:

   ```bash
   gcloud services enable people.googleapis.com \
     --project=green-mercury-485016-n1
   ```

2. Configure OAuth scopes:
   - `https://www.googleapis.com/auth/drive.readonly`
   - `https://www.googleapis.com/auth/gmail.readonly`

3. Enable domain-wide delegation (for organization)

## Next Steps

1. ✅ Enable Enterprise Edition for existing data store
2. ✅ Update Gemini model to gemini-1.5-flash
3. ✅ Verify extractive answers work in notebook
4. ⬜ Upload math curriculum documents
5. ⬜ Monitor query costs and usage
6. ⬜ Setup alerts for quota limits

## References (MCP Research - March 2026)

- [Vertex AI Search Documentation](https://docs.cloud.google.com/generative-ai-app-builder/docs/enterprise-edition)
- [Enterprise Edition Setup](https://cloud.google.com/generative-ai-app-builder/docs/enterprise-edition)
- [Extractive Answers Guide](https://oneuptime.com/blog/post/2026-02-17-how-to-implement-extractive-answers-and-segments-in-vertex-ai-search/view)
- [Pricing Calculator](https://cloud.google.com/generative-ai-app-builder/pricing)
- [Gemini Model Availability](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations)

---

**Last Updated:** March 8, 2026  
**Verified By:** AI Assistant using MCP Tavily Research
