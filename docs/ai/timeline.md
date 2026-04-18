# Project Timeline

> Nhật ký phát triển — bản **tóm tắt ngắn gọn**. Chi tiết từng ngày xem trong [`docs/timeline/`](../../docs/timeline/).  
> Agent PHẢI: (1) thêm dòng tóm tắt ở đây, (2) thêm/cập nhật file chi tiết `docs/timeline/DD-MM-YYYY.md`.

---

## Format

**File này (summary):**

```
| Ngày | Giờ | Tiêu đề | Kết quả | Chi tiết |
```

**File chi tiết** (`docs/timeline/DD-MM-YYYY.md`):

```
### HH:MM — [Tiêu đề ngắn gọn]

**Vấn đề:** ...
**Nguyên nhân:** ...
**Hành động:** ...
**Kết quả:** ...
**References:** ...
```

> Mỗi file daily chỉ cần **giờ** (HH:MM) vì ngày đã nằm trong tên file.

---

## Summary

| Ngày       | Giờ   | Tiêu đề                                       | Kết quả                                                                                                                | Chi tiết                                      |
| ---------- | ----- | --------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| 2026-03-26 | 14:00 | Refactor bucket + 798 PDFs                    | ✅ 798 PDFs uploaded, Vertex import triggered                                                                          | [chi tiết](../../docs/timeline/26-03-2026.md) |
| 2026-03-26 | 18:00 | Client-Side Rate Limiting                     | ✅ 8/8 call sites wrapped, rate_limiter.py created                                                                     | [chi tiết](../../docs/timeline/26-03-2026.md) |
| 2026-03-27 | 10:00 | Singleton/Cache + ChatVertexAI Migration      | ✅ 7/7 singleton checks passed, zero ChatVertexAI                                                                      | [chi tiết](../../docs/timeline/27-03-2026.md) |
| 2026-03-27 | 14:30 | Fix notebook async execution                  | ✅ asyncio.run → await, patch target fixed                                                                             | [chi tiết](../../docs/timeline/27-03-2026.md) |
| 2026-03-27 | 19:22 | Verify Vertex indexing + re-benchmark         | ✅ 798/798 indexed, 84.6% pass rate (13 tests)                                                                         | [chi tiết](../../docs/timeline/27-03-2026.md) |
| 2026-03-27 | 19:44 | Refactor timeline + pass rate analysis        | ✅ Timeline → summary+daily, 5 root causes identified                                                                  | [chi tiết](../../docs/timeline/27-03-2026.md) |
| 2026-03-29 | 09:30 | Implement P0–P4 pipeline fixes                | ✅ 5 root causes fixed, 31 unit tests pass                                                                             | [chi tiết](../../docs/timeline/29-03-2026.md) |
| 2026-03-29 | 12:20 | Tối ưu high_application + auto suspicious RCA | ✅ Thêm exemplar theo domain, lọc feedback theo difficulty, rerun high_application đạt 10.0%                           | [chi tiết](../../docs/timeline/29-03-2026.md) |
| 2026-03-29 | 20:49 | Pipeline 100% delivery — 5 fixes              | ✅ ALL 4 difficulty levels 100% delivery (recall/comprehension/application/high_application)                           | [chi tiết](../../docs/timeline/29-03-2026.md) |
| 2026-04-09 | 10:00 | E2E Final Verification — 100% Delivery        | ✅ 40/40 items, 115/115 tests, total 2079s (recall 125s, comprehension 123s, application 540s, high_application 1291s) | [chi tiết](../../docs/timeline/09-04-2026.md) |
| 2026-04-09 | 11:00 | Performance Optimization Plan                 | 📋 Plan created: 3 tiers, 8 tasks, target high_application ≤400s                                                       | [chi tiết](../../docs/timeline/09-04-2026.md) |
| 2026-04-09 | 13:15 | Tier 1 Performance Optimizations              | ✅ 3 optimizations implemented (parallel parse, cache search, skip supervisor), 82/82 tests pass                       | [chi tiết](../../docs/timeline/09-04-2026.md) |
| 2026-04-09 | 14:30 | Tier 1 Code Review + Commit                   | ✅ 3 findings fixed (F1-F3), 93/93 tests pass, committed as `4c1464b`                                                  | [chi tiết](../../docs/timeline/09-04-2026.md) |
| 2026-04-09 | 15:38 | Tier 2 Performance Optimizations              | ✅ T-OPT-2.1 parse-only retry + T-OPT-2.3 parallel micro-batch, T-OPT-2.2 skipped (research), 105/105 tests pass       | [chi tiết](../../docs/timeline/09-04-2026.md) |
| 2026-04-10 | 16:00 | Tier 3 Performance Optimizations              | ✅ T-OPT-3.3 deterministic supervisor + T-OPT-3.4 parallel formatter batches, 13/13 tests, 140/145 regression          | [chi tiết](../../docs/timeline/10-04-2026.md) |
| 2026-04-10 | 17:00 | Final Benchmark Notebook Created              | ✅ Comprehensive notebook for all 3 tiers, SDK verification, 4-level E2E benchmark vs 2078.5s baseline                 | [chi tiết](../../docs/timeline/10-04-2026.md) |
