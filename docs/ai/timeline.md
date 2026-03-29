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

| Ngày       | Giờ   | Tiêu đề                                       | Kết quả                                                                                      | Chi tiết                                      |
| ---------- | ----- | --------------------------------------------- | -------------------------------------------------------------------------------------------- | --------------------------------------------- |
| 2026-03-26 | 14:00 | Refactor bucket + 798 PDFs                    | ✅ 798 PDFs uploaded, Vertex import triggered                                                | [chi tiết](../../docs/timeline/26-03-2026.md) |
| 2026-03-26 | 18:00 | Client-Side Rate Limiting                     | ✅ 8/8 call sites wrapped, rate_limiter.py created                                           | [chi tiết](../../docs/timeline/26-03-2026.md) |
| 2026-03-27 | 10:00 | Singleton/Cache + ChatVertexAI Migration      | ✅ 7/7 singleton checks passed, zero ChatVertexAI                                            | [chi tiết](../../docs/timeline/27-03-2026.md) |
| 2026-03-27 | 14:30 | Fix notebook async execution                  | ✅ asyncio.run → await, patch target fixed                                                   | [chi tiết](../../docs/timeline/27-03-2026.md) |
| 2026-03-27 | 19:22 | Verify Vertex indexing + re-benchmark         | ✅ 798/798 indexed, 84.6% pass rate (13 tests)                                               | [chi tiết](../../docs/timeline/27-03-2026.md) |
| 2026-03-27 | 19:44 | Refactor timeline + pass rate analysis        | ✅ Timeline → summary+daily, 5 root causes identified                                        | [chi tiết](../../docs/timeline/27-03-2026.md) |
| 2026-03-29 | 09:30 | Implement P0–P4 pipeline fixes                | ✅ 5 root causes fixed, 31 unit tests pass                                                   | [chi tiết](../../docs/timeline/29-03-2026.md) |
| 2026-03-29 | 12:20 | Tối ưu high_application + auto suspicious RCA | ✅ Thêm exemplar theo domain, lọc feedback theo difficulty, rerun high_application đạt 10.0% | [chi tiết](../../docs/timeline/29-03-2026.md) |
