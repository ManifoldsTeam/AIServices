---
phase: design
title: Tối ưu Đồng thời & Hiệu năng (v2)
description: Kiến trúc xử lý yêu cầu đồng thời và giảm độ trễ mỗi request
created: 2026-03-22
updated: 2026-03-24
status: Đề xuất Cập nhật — Dựa trên Nghiên cứu
research_sources: Tavily Pro research (2026-03-24), Vertex AI docs, LangGraph docs, asyncio best practices
---

# Tối ưu Đồng thời & Hiệu năng (v2)

> **Cập nhật:** 2026-03-24
> **Nghiên cứu:** Tavily Pro deep research về các mẫu đồng thời pipeline LLM (33 nguồn)
> **Phạm vi:** Song song hóa trong pipeline, mở rộng xuyên request, rate limiting, batch processing

---

## 1. Hiệu năng Hiện tại (Sau tối ưu M3)

### Kết quả Kiểm tra Pipeline (M3 accuracy test — 368 items)

| Test                  | Items | Pass%   | Thời gian | Ghi chú                           |
| --------------------- | ----- | ------- | --------- | --------------------------------- |
| smoke_5q              | 5     | 100%    | 64.2s     |                                   |
| medium_15q            | 15    | 100%    | 92.8s     |                                   |
| large_30q             | 25    | 64.1%   | 125.0s    | **Gặp lỗi 429 rate limit**        |
| multi_type (3 games)  | 45    | 100%    | 70.9s     | Song song hóa Formatter hoạt động |
| diff_application      | 7     | 100%    | 163.5s    |                                   |
| diff_high_application | 1     | 7.1%    | 434.9s    | Hỏng — KB thiếu bài tập mẫu       |
| **TỔNG**              | 368   | **89%** | 1700.2s   | 28.3 phút cho toàn bộ test suite  |

### Chuỗi Gọi LLM Mỗi Pipeline Run (10Q chỉ quiz)

| Node             | Số lần gọi | Model                         | Mục đích         | Ước tính Thời gian |
| ---------------- | ---------- | ----------------------------- | ---------------- | ------------------ |
| Supervisor       | 1          | gemini-3.1-flash-lite         | Phân loại        | ~2s                |
| Math Agent Gen   | 1          | gemini-2.5-flash (code_exec)  | Sinh nội dung    | ~30-60s            |
| Math Agent Parse | 1-2        | gemini-2.5-flash (structured) | Parse batch 7+6  | ~15-30s            |
| Reviewer         | 1          | gemini-3.1-flash-lite         | Review batch     | ~5-10s             |
| Formatter (quiz) | 1-2        | gemini-2.5-flash (structured) | Format batch 7+3 | ~10-20s            |
| **Tổng**         | **~7**     |                               |                  | **~60-120s**       |

Với retry iterations: nhân ×2-3 cho trường hợp xấu nhất.

### Vấn đề Chính: Không có Rate Limiting cho LLM Calls

**Lỗi 429 trong test `large_30q`** — batch parsing song song phát ra 4+ lệnh gọi LLM đồng thời mà không có kiểm soát tốc độ. Với quota 60 RPM mặc định (asia-southeast1), mẫu burst vượt quá giới hạn.

---

## 2. Các Tối ưu Đã Triển khai (M3 — Hoàn thành)

| Tối ưu                                      | Vị trí                                    | Tác động                                       |
| ------------------------------------------- | ----------------------------------------- | ---------------------------------------------- |
| Formatter `asyncio.gather()` cho game types | `formatter.py`                            | Tăng tốc 2-3× cho yêu cầu multi-game           |
| Batch parse retry với backoff               | `math_agent.py` `_parse_batch()`          | Ít retry toàn pipeline hơn                     |
| Parse song song qua `asyncio.gather()`      | `math_agent.py` `_parse_raw_content()`    | Tốc độ parse 2×                                |
| Cắt ngắn code trace (8000 ký tự)            | `math_agent.py` `_truncate_code_traces()` | Tỷ lệ parse thành công cao hơn                 |
| Retry nội bộ generation (2 lần thử)         | `math_agent.py` `math_agent_node()`       | Tránh restart toàn pipeline khi parse thất bại |
| Dừng sớm khi output rỗng                    | `math_agent.py`                           | Bỏ qua parse vô ích                            |

---

## 3. Kiến trúc Đề xuất: Kiểm soát Đồng thời Nhiều Lớp

Dựa trên nghiên cứu hệ thống LLM production, best practices của Vertex AI, và các mẫu asyncio.

### 3.1 Tổng quan Kiến trúc

```
┌──────────────────────────────────────────────────────────────────────┐
│                      Lớp 1: API Gateway                              │
│   POST /api/v1/generate → Firestore job → queue dispatch            │
│   Chia request: 100Q → 10×10Q sub-jobs                              │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────┐
│                  Lớp 2: Bộ Điều phối Job                             │
│   Cloud Tasks queue (rate: 5/s, max concurrent: 10)                  │
│   HOẶC local asyncio.Queue + worker pool (chế độ dev)                │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────┐
│              Lớp 3: Rate Limiter Mỗi Instance                        │
│   AsyncTokenBucket (capacity=5, refill=1.0/s mỗi 60RPM)             │
│   + asyncio.Semaphore(10) giới hạn đồng thời mỗi process            │
│   Mỗi LLM call → bucket.wait_and_consume() → sema acquire           │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────┐
│            Lớp 4: Thực thi Pipeline LangGraph                        │
│   supervisor → math_agent → reviewer → formatter → END              │
│   Nội bộ: parse batch song song, format game-type song song          │
│   Retry từng node với backoff (không retry toàn graph)               │
└──────────────────────┬───────────────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────────────┐
│          Lớp 5: Circuit Breaker + Quan sát                           │
│   Trip sau 5 lỗi 429 liên tiếp → cooldown 60s                      │
│   Metrics: latency p95, tỷ lệ 429, queue depth, bucket fill level  │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2 Chi tiết Lớp 3: AsyncTokenBucket + Semaphore

**Mục đích:** Ngăn lỗi 429 bằng cách kiểm soát tốc độ gọi LLM phía client theo quota Vertex AI.

```python
# src/services/rate_limiter.py

import asyncio
import time
from dataclasses import dataclass, field

@dataclass
class AsyncTokenBucket:
    """Token bucket async-safe cho rate limiting LLM calls.

    capacity: kích thước burst tối đa (requests)
    refill_rate: tokens/giây (ví dụ: 1.0 cho 60 RPM)
    """
    capacity: float
    refill_rate: float
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)
    _lock: asyncio.Lock = field(init=False)

    def __post_init__(self):
        self._tokens = self.capacity
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
        self._last_refill = now

    async def wait_and_consume(self, amount: float = 1.0):
        """Chặn cho đến khi có token sẵn sàng, sau đó tiêu thụ."""
        while True:
            async with self._lock:
                await self._refill()
                if self._tokens >= amount:
                    self._tokens -= amount
                    return
                needed = amount - self._tokens
                wait_time = needed / self.refill_rate if self.refill_rate > 0 else 1.0
            await asyncio.sleep(wait_time)


# Singleton module-level (tạo một lần mỗi process)
# 60 RPM = 1 req/giây trung bình, cho phép burst 5
_llm_bucket = AsyncTokenBucket(capacity=5.0, refill_rate=1.0)
_llm_semaphore = asyncio.Semaphore(10)  # tối đa 10 LLM calls đồng thời

async def rate_limited_llm_call(coro):
    """Bọc bất kỳ LLM call nào với rate limiting + giới hạn đồng thời.

    Cách dùng:
        result = await rate_limited_llm_call(llm.ainvoke(messages))
    """
    await _llm_bucket.wait_and_consume()
    async with _llm_semaphore:
        return await coro
```

**Tại sao thiết kế này:**

- **Token bucket** kiểm soát tốc độ trung bình (1 req/s = 60 RPM) trong khi cho phép burst ngắn (capacity=5)
- **Semaphore** giới hạn kết nối HTTP đồng thời để ngăn cạn kiệt tài nguyên
- **Singleton module-level** đảm bảo tất cả node pipeline dùng chung một limiter
- Không cần dependencies bên ngoài (Redis không cần cho single-instance local/Cloud Run)

**Điều chỉnh theo quota:**

| Quota (RPM)   | `refill_rate` | `capacity` | `semaphore` | Max Concurrent Instances |
| ------------- | ------------- | ---------- | ----------- | ------------------------ |
| 60 (mặc định) | 1.0           | 5          | 10          | 1 (margin an toàn)       |
| 200 (yêu cầu) | 3.0           | 10         | 15          | 3-5                      |
| 500 (cao)     | 8.0           | 15         | 20          | 8-10                     |

### 3.3 Các Điểm Tích hợp trong Codebase Hiện tại

Nơi kết nối `rate_limited_llm_call()`:

| File            | Hàm                     | LLM Calls                  | Thay đổi             |
| --------------- | ----------------------- | -------------------------- | -------------------- |
| `math_agent.py` | `math_agent_node()`     | `code_exec_llm.ainvoke()`  | Bọc với rate limiter |
| `math_agent.py` | `_parse_batch()`        | `structured_llm.ainvoke()` | Bọc với rate limiter |
| `formatter.py`  | `_format_quizzes()`     | `chain.ainvoke()`          | Bọc với rate limiter |
| `formatter.py`  | `_format_flashcards()`  | `chain.ainvoke()`          | Bọc với rate limiter |
| `formatter.py`  | `_format_fill_blanks()` | `chain.ainvoke()`          | Bọc với rate limiter |
| `reviewer.py`   | `reviewer_node()`       | `review_llm.ainvoke()`     | Bọc với rate limiter |
| `supervisor.py` | `supervisor_node()`     | `llm.ainvoke()`            | Bọc với rate limiter |

**Thay đổi code tối thiểu cho mỗi call site:**

```python
# Trước:
result = await structured_llm.ainvoke(messages)

# Sau:
from src.services.rate_limiter import rate_limited_llm_call
result = await rate_limited_llm_call(structured_llm.ainvoke(messages))
```

### 3.4 Chi tiết Lớp 5: Circuit Breaker

**Mục đích:** Ngừng retry khi provider liên tục thất bại (quota cạn, sự cố).

```python
# Thêm vào src/services/rate_limiter.py

@dataclass
class CircuitBreaker:
    """Circuit breaker đơn giản cho lỗi provider LLM."""
    failure_threshold: int = 5
    cooldown_seconds: float = 60.0
    _consecutive_failures: int = field(init=False, default=0)
    _tripped_at: float | None = field(init=False, default=None)

    def record_success(self):
        self._consecutive_failures = 0
        self._tripped_at = None

    def record_failure(self):
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._tripped_at = time.monotonic()

    @property
    def is_open(self) -> bool:
        if self._tripped_at is None:
            return False
        elapsed = time.monotonic() - self._tripped_at
        if elapsed > self.cooldown_seconds:
            # Nửa mở: cho phép thử một lần
            self._tripped_at = None
            self._consecutive_failures = 0
            return False
        return True
```

---

## 4. Các Tối ưu Đề xuất: Triển khai theo Ưu tiên

### P0 — Song song hóa Trong Pipeline (HOÀN THÀNH)

| Tối ưu                                      | Trạng thái | File            |
| ------------------------------------------- | ---------- | --------------- |
| Formatter `asyncio.gather()` cho game types | Xong       | `formatter.py`  |
| Batch parse retry với backoff               | Xong       | `math_agent.py` |
| Parse song song qua `asyncio.gather()`      | Xong       | `math_agent.py` |
| Cắt ngắn code trace (8000 ký tự)            | Xong       | `math_agent.py` |
| Retry nội bộ generation (2 lần thử)         | Xong       | `math_agent.py` |

### P1 — Rate Limiting Phía Client (QUAN TRỌNG — Chặn mọi mở rộng)

**Vấn đề:** Lỗi 429 trong test `large_30q`. Không có kiểm soát tốc độ cho bất kỳ LLM call nào.

**Giải pháp:** `AsyncTokenBucket` + `asyncio.Semaphore` (Phần 3.2 ở trên)

**Các bước triển khai:**

1. Tạo `src/services/rate_limiter.py` với `AsyncTokenBucket`, `CircuitBreaker`, và `rate_limited_llm_call()`
2. Kết nối vào tất cả 7 điểm gọi LLM (bảng trong Phần 3.3)
3. Thêm cấu hình rate limiter vào `Settings` (env-configurable: `LLM_RATE_LIMIT_RPM`, `LLM_MAX_CONCURRENT`)
4. Test với `large_30q` — kỳ vọng lỗi 429 biến mất

**Nỗ lực:** Thấp-Trung bình (1 file mới + 7 wrapper một dòng)
**Tác động:** Loại bỏ lỗi 429, cho phép song song an toàn, điều kiện tiên quyết cho mọi mở rộng

### P2 — Song song Format Batches Trong Mỗi Game Type

**Vấn đề:** Mỗi formatter game type chạy batch tuần tự trong `_format_quizzes()`, `_format_flashcards()`, `_format_fill_blanks()`.

**Mẫu hiện tại:**

```python
for batch_start in range(0, len(items), FORMATTER_BATCH_SIZE):
    result = await chain.ainvoke(...)  # Tuần tự!
```

**Mẫu đề xuất:**

```python
batch_tasks = [chain.ainvoke(bd) for bd in all_batch_data]
results = await asyncio.gather(*batch_tasks, return_exceptions=True)
```

**Điều kiện tiên quyết:** P1 rate limiter (ngăn overload burst)
**Tác động:** ~1.5× cho tập lớn (20+ items mỗi game type)
**Nỗ lực:** Thấp (refactor 3 hàm formatter)

### P3 — Batch Request (100Q → N×10Q Sub-Jobs)

**Trường hợp sử dụng:** Giáo viên tạo 100 câu hỏi để ôn thi.

**Kiến trúc:**

```
POST /generate { num_questions: 100 }
  │
  ├─ Chia: 10 sub-jobs × 10Q mỗi cái
  │    ├─ sub-1: { num_questions: 10, topic: giống nhau, offset: 0 }
  │    ├─ sub-2: { num_questions: 10, topic: giống nhau, offset: 10 }
  │    └─ ...
  │
  ├─ Lên lịch: asyncio.Queue(maxsize=20) + N workers
  │    ├─ Worker 1: run_pipeline(sub-1) → checkpoint kết quả
  │    ├─ Worker 2: run_pipeline(sub-2) → checkpoint kết quả
  │    └─ ... (được giới hạn bởi rate limiter)
  │
  └─ Tổng hợp: thu thập kết quả → sắp xếp theo offset → gộp → trả về
```

**Mẫu triển khai (chế độ async local):**

```python
import asyncio
import itertools

def chunkify(items, chunk_size):
    it = iter(items)
    while True:
        chunk = list(itertools.islice(it, chunk_size))
        if not chunk:
            break
        yield chunk

async def batch_generate(request, max_workers=5):
    """Chia request lớn thành sub-jobs, xử lý với song song có giới hạn."""
    if request.num_questions <= 10:
        return await run_pipeline(request)

    chunks = list(range(0, request.num_questions, 10))
    queue = asyncio.Queue(maxsize=max_workers * 2)
    results = {}

    async def worker(worker_id):
        while True:
            try:
                offset = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            sub_req = request.model_copy()
            sub_req.num_questions = min(10, request.num_questions - offset)
            result = await run_pipeline(sub_req)
            results[offset] = result
            queue.task_done()

    for offset in chunks:
        await queue.put(offset)

    workers = [asyncio.create_task(worker(i)) for i in range(max_workers)]
    await queue.join()
    for w in workers:
        w.cancel()

    # Gộp theo thứ tự
    return merge_results(sorted(results.items()))
```

**Cho chế độ Cloud Tasks:** Mỗi sub-job = một Cloud Tasks entry riêng → Cloud Run instance riêng.

**Xử lý partial failure:**

- Mỗi sub-job checkpoint độc lập (Firestore status mỗi sub-job)
- Sub-jobs thất bại có thể retry riêng lẻ
- Parent job tổng hợp: nếu >=80% sub-jobs thành công, trả kết quả partial + báo cáo lỗi

**Tác động:** Tăng tốc 10× cho 100Q (2000s → ~200s)
**Nỗ lực:** Trung bình
**Điều kiện tiên quyết:** P1 rate limiter

### P4 — Rate Limiting Xuyên Instance (Production Multi-Instance)

**Khi nào cần:** Nhiều Cloud Run instances chia sẻ cùng quota dự án Vertex AI.

**Các phương án (tăng dần độ phức tạp):**

| Phương án                       | Khi nào       | Độ phức tạp        | Khuyến nghị                     |
| ------------------------------- | ------------- | ------------------ | ------------------------------- |
| Token bucket mỗi instance       | <=3 instances | Không (đã có ở P1) | Chia quota cho max instances    |
| Cloud Tasks dispatch rate       | Bất kỳ quy mô | Thấp (cấu hình)    | Đặt `max_dispatches_per_second` |
| Redis-backed distributed bucket | >5 instances  | Trung bình         | Dùng thư viện `self-limiters`   |

**Cho quy mô của chúng ta (<=10 instances):** Cloud Tasks rate limiting (5/s dispatch, 10 max concurrent) là đủ. Không cần Redis cho đến khi >50 RPM mỗi instance.

### P5 — Lớp Cache (Tương lai)

**Chiến lược:** Cache ở hai cấp:

1. **Kết quả Vertex AI Search** — cùng query+topic+scope → cùng context (TTL: 1h)
2. **Output pipeline** — cùng request params → cùng nội dung (TTL: 24h, với randomization)

```python
# Cache key bao gồm tất cả params ảnh hưởng output
cache_key = f"{subject}:{topic}:{difficulty}:{num_questions}:{sorted(game_types)}"
cache_hash = hashlib.sha256(cache_key.encode()).hexdigest()
```

**Tác động:** Bỏ qua toàn bộ pipeline cho request trùng lặp
**Khi nào:** Sau khi biết mẫu người dùng từ dữ liệu production

---

## 5. Ma trận Ưu tiên (Cập nhật)

| #     | Tối ưu                           | Nỗ lực        | Tác động               | Ưu tiên | Trạng thái    | Phụ thuộc    |
| ----- | -------------------------------- | ------------- | ---------------------- | ------- | ------------- | ------------ |
| 1     | Formatter `asyncio.gather()`     | Thấp          | 2-3× formatter         | P0      | Xong          | —            |
| 2     | Batch parse retry + backoff      | Thấp          | Ít retry hơn           | P0      | Xong          | —            |
| 3     | Parse song song batch            | Thấp          | Tốc độ parse 2×        | P0      | Xong          | —            |
| 4     | Cắt ngắn code trace              | Thấp          | Tỷ lệ parse cao hơn    | P0      | Xong          | —            |
| 5     | Retry nội bộ generation          | Thấp          | Không restart pipeline | P0      | Xong          | —            |
| **6** | **AsyncTokenBucket + Semaphore** | **Thấp-TB**   | **Loại bỏ lỗi 429**    | **P1**  | **Tiếp theo** | —            |
| **7** | **Circuit breaker**              | **Thấp**      | **Ngăn retry storm**   | **P1**  | **Tiếp theo** | #6           |
| 8     | Song song format batches         | Thấp          | 1.5× mỗi game type     | P2      | Chưa bắt đầu  | #6           |
| 9     | Batch request (100Q→10×10Q)      | Trung bình    | 10× request lớn        | P3      | Chưa bắt đầu  | #6           |
| 10    | Cloud Tasks rate limiting        | Thấp (config) | Bảo vệ quota           | P4      | Phase deploy  | —            |
| 11    | Cloud Run auto-scaling           | Thấp (config) | N users đồng thời      | P4      | Phase deploy  | #10          |
| 12    | Lớp cache                        | Trung bình    | Bỏ qua pipeline        | P5      | Tương lai     | Dữ liệu prod |

---

## 6. Ước tính Hiệu năng Sau Tối ưu

| Kịch bản             | Hiện tại (M3)        | +P1 (rate limit)      | +P2 (song song fmt) | +P3 (batching) | +P4/P5 (deploy)     |
| -------------------- | -------------------- | --------------------- | ------------------- | -------------- | ------------------- |
| 1 user, 10Q, quiz    | ~90s                 | ~90s                  | ~80s                | ~80s           | ~80s                |
| 1 user, 10Q, 3 games | ~70s                 | ~70s                  | ~60s                | ~60s           | ~60s                |
| 1 user, 30Q, quiz    | ~125s (**64% pass**) | ~140s (**~95% pass**) | ~120s               | ~120s          | ~120s               |
| 1 user, 100Q, quiz   | ~2000s               | ~2000s                | ~1800s              | **~200s**      | ~200s               |
| 10 đồng thời, 10Q    | Tuần tự              | Tuần tự               | Tuần tự             | Tuần tự        | **~120s song song** |

**Nhận xét quan trọng:**

1. **P1 (rate limiter) là ưu tiên #1** — sửa lỗi 429 trong `large_30q` (64% → ~95% pass rate)
2. **P3 (batch request) cho lợi ích latency lớn nhất** cho request lớn (tăng tốc 10×)
3. **P4 (Cloud Run/Tasks) cho phép multi-user đồng thời** — hoãn đến phase deploy theo yêu cầu người dùng

---

## 7. Lộ trình Triển khai

```
Phase 1 (M3 — Xong): Song song hóa trong pipeline
  ✅ asyncio.gather() trong formatter_node (game types song song)
  ✅ asyncio.gather() trong _parse_raw_content (batch parsing song song)
  ✅ Retry với backoff trong _parse_batch, math_agent_node
  ✅ Cắt ngắn code trace, dừng sớm

Phase 2 (Sprint tiếp theo): Rate limiting phía client
  → Tạo src/services/rate_limiter.py (AsyncTokenBucket + CircuitBreaker)
  → Kết nối rate_limited_llm_call() vào tất cả 7 điểm gọi LLM
  → Thêm LLM_RATE_LIMIT_RPM và LLM_MAX_CONCURRENT vào Settings
  → Test: large_30q nên pass >90% (hiện tại 64%)
  → Song song format batches trong formatter (sau khi rate limiter ổn định)

Phase 3 (Sprint tương lai): Batch request
  → Mô hình parent/child job (Firestore hoặc local)
  → asyncio.Queue + worker pool cho chế độ local
  → Chia 100Q → 10×10Q với song song có giới hạn
  → Xử lý partial failure + tổng hợp kết quả

Phase 4 (Phase Deploy — hoãn):
  → Cloud Run auto-scaling (containerConcurrency=1, maxScale=10)
  → Cloud Tasks rate limiting (5/s dispatch, 10 concurrent)
  → Distributed rate limiter (chỉ khi cần >5 instances)
  → Lớp cache (sau khi có mẫu sử dụng production)
```

---

## 8. Tham chiếu Quota Vertex AI

| Chiều | Mặc định (asia-southeast1) | Sử dụng (1 pipeline) | 10 Đồng thời         | Hành động Cần thiết                    |
| ----- | -------------------------- | -------------------- | -------------------- | -------------------------------------- |
| RPM   | 60                         | ~7                   | ~70                  | Yêu cầu tăng lên 200 nếu >15 đồng thời |
| TPM   | 1,000,000                  | ~56,000              | ~560,000             | Trong giới hạn                         |
| RPD   | 1,500                      | ~7                   | ~700/ngày (100 runs) | Trong giới hạn                         |

**Khuyến nghị:** Cho production, yêu cầu tăng quota lên 200 RPM. Với token bucket rate limiter, ngay cả quota 60 RPM mặc định cũng hoạt động cho <=8 pipeline đồng thời.

---

## Phụ lục A: Nguồn Nghiên cứu

Thiết kế này được tham khảo từ:

- Tài liệu chiến lược retry của Vertex AI (exponential backoff + jitter cho 429/5xx)
- Tài liệu rate limits của Gemini API (đa chiều: RPM, TPM, RPD mỗi project)
- Các triển khai async token-bucket đã public cho Python/asyncio
- Mô hình thực thi superstep của LangGraph (fan-out qua Send/Command, retry từng node)
- Thư viện `asynciolimiter` và `self-limiters` cho async rate limiting
- `tenacity` cho async retry với tích hợp backoff
