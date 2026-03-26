# Đề xuất Công nghệ Web Game và Schema — Contract do AI Service quyết định

> Cập nhật: 2026-03-20
> Trạng thái: **GameService ủy quyền toàn bộ quyết định API contract cho AI Service**
> Mục tiêu: Contract chính thức giữa AI Service ↔ GameService

## 1. Phạm vi

Tài liệu này đề xuất:

- Lựa chọn công nghệ làm game web cho phía client.
- Chiến lược contract/schema giữa AI Service và GameService.
- Cách versioning để tránh vỡ tích hợp khi mở rộng.

## 2. Tổng hợp công nghệ game web

## 2.1 Phaser (đề xuất ưu tiên cho phạm vi hiện tại)

Lý do:

- Framework game 2D đã trưởng thành.
- Hỗ trợ TypeScript tốt, hệ sinh thái lớn.
- Phù hợp mini-game giáo dục dạng quiz/flashcard/fill-blank.
- Chạy tốt desktop/mobile web với WebGL + Canvas fallback.

Tham khảo chính thống:

- https://github.com/phaserjs/phaser
- https://phaser.io

## 2.2 PixiJS (renderer hiệu năng cao, không phải full game framework)

Lý do:

- Hiệu năng render 2D rất tốt.
- Hỗ trợ WebGL/WebGPU (WebGPU vẫn đang hoàn thiện trên trình duyệt).
- Phù hợp khi GameService muốn tự xây kiến trúc game và tự quản lý game loop/physics.

Tham khảo chính thống:

- https://pixijs.com/8.x/guides/components/renderers
- https://pixijs.download/dev/docs/rendering.html

## 2.3 Babylon.js 8 (cho roadmap 3D-first)

Lý do:

- Năng lực 3D mạnh, đầu tư nhiều vào WebGPU/WGSL.
- Phù hợp hướng 3D trong tương lai, chưa cần cho V1 hiện tại.

Tham khảo chính thống:

- https://blogs.windows.com/windowsdeveloper/2025/03/27/announcing-babylon-js-8-0/

## 2.4 Lựa chọn multiplayer/realtime (nếu cần về sau)

Colyseus phù hợp khi cần mô hình room realtime authoritative server.
Tham khảo:

- https://colyseus.io
- https://github.com/colyseus/colyseus

## 2.5 Khuyến nghị

Với mục tiêu Week 3 và loại game hiện tại:

- Khuyến nghị chính: Phaser + TypeScript.
- Giữ schema ở mức engine-agnostic để sau này đổi engine/renderer không phải đổi API.

## 3. Khoảng trống contract hiện tại (AI Service)

~~Quan sát từ schema hiện có:~~

- ~~Các trường content trong response còn lỏng kiểu (`dict[str, list[dict]]`), giảm độ an toàn khi codegen client.~~
- ~~Chưa có `contract_version` rõ ràng trong payload generation.~~
- ~~Chưa có discriminated union cho game items đa hình.~~

> **✅ Đã xử lý (2026-03-20):**
>
> - `GameContentResponse.content` đã chuyển từ `dict[str, list[dict]]` → `GameContentMap` (typed model, mỗi game type 1 field riêng).
> - Thêm `contract_version: str = "1.0.0"` vào `GameContentResponse`.
> - Formatter đã trả về Pydantic model (`list[QuizQuestion]`, `list[Flashcard]`, `list[FillBlankQuestion]`) thay vì `list[dict]`.
> - Toàn bộ pipeline sử dụng typed model end-to-end.

## 4. Đề xuất chiến lược contract

Sử dụng OpenAPI `oneOf` + discriminator cho các game item.

Lý do:

- Biểu diễn đa hình rõ ràng cho code generation.
- Tăng khả năng tương thích và parse an toàn ở frontend.
- Dễ mở rộng game type trong tương lai.

Lưu ý:

- Hạn chế dùng `anyOf` cho payload cấu trúc trừ khi thật sự cần thiết.
- Ưu tiên discriminator rõ ràng như `type` hoặc `game_type`.

## 5. Đề xuất hình dạng response V1

```json
{
  "contract_version": "1.0.0",
  "request_id": "uuid",
  "user_id": "user_123",
  "generated_at": "2026-03-13T10:00:00Z",
  "locale": "vi-VN",
  "packs": [
    {
      "game_type": "quiz",
      "schema_version": "quiz.v1",
      "rules": {
        "time_limit_sec": 45,
        "shuffle_options": true
      },
      "items": [
        {
          "id": "q1",
          "type": "quiz",
          "prompt": "Đạo hàm của x^2 là gì?",
          "options": ["x", "2x", "x^2", "2"],
          "correct_answer_index": 1,
          "answer": "2x",
          "explanation": "d/dx x^2 = 2x",
          "difficulty": "easy",
          "topic": "đạo-hàm",
          "provenance": {
            "source_scope": "system",
            "chunk_ref": "docA#p12"
          }
        }
      ]
    }
  ],
  "metadata": {
    "generation_time_seconds": 8.2,
    "model_used": "gemini",
    "cost_estimate_usd": 0.02
  }
}
```

## 6. Mẫu mô hình OpenAPI (minh họa)

```yaml
components:
  schemas:
    GameItem:
      oneOf:
        - $ref: "#/components/schemas/QuizItem"
        - $ref: "#/components/schemas/FlashcardItem"
        - $ref: "#/components/schemas/FillBlankItem"
      discriminator:
        propertyName: type
        mapping:
          quiz: "#/components/schemas/QuizItem"
          flashcard: "#/components/schemas/FlashcardItem"
          fill_blank: "#/components/schemas/FillBlankItem"
```

## 7. Chính sách versioning và tương thích

Quy tắc:

- Thay đổi cộng thêm (thêm field optional): tăng minor version.
- Thay đổi phá vỡ tương thích (xóa/đổi tên/đổi nghĩa field): tăng major version.
- Giữ version riêng theo từng game type (`quiz.v1`, `flashcard.v1`) để tiến hóa độc lập.

Field khuyến nghị:

- Top-level `contract_version` (version contract payload API).
- Theo từng pack `schema_version` (version schema game type).

## 8. Checklist thảo luận với GameService

> **Lưu ý**: GameService đã ủy quyền AI Service toàn quyền quyết định contract.
> Các mục dưới đây chuyển thành quyết định nội bộ AI Service.

1. ~~Chốt engine cho frontend V1:~~

- Khuyến nghị Phaser, nhưng là quyết định của GameService.

2. [x] Chốt tên discriminator:

- Sử dụng tên field của `GameContentMap` (`quiz`, `flashcard`, `fill_blank`). Không cần discriminator ở cấp item vì mỗi game type là 1 list riêng biệt.

3. [x] Chốt field bắt buộc và field optional cho từng game type.

- Xem `GameContentMap`, `QuizQuestion`, `Flashcard`, `FillBlankQuestion` trong `src/api/schemas/game_content.py`.

4. Chốt error contract:

- `code`, `message`, `request_id`, `retryable`, `details`.

5. [x] Chốt chính sách version/deprecation.

- `contract_version` ở top-level response (semver).

6. Chốt endpoint capability:

- `GET /api/v1/game-types` trả về danh sách type + schema version + ràng buộc.

## 9. Quy tắc code — tránh triển khai pattern dễ break

> **Rule bắt buộc** — áp dụng cho toàn bộ codebase AI Service.

1. **Không dùng `dict[str, Any]`, `dict[str, list[dict]]`, hoặc `Any`** trong request/response model.
   - Mọi API payload phải có Pydantic model cụ thể.
   - Vi phạm → reject PR.

2. **Không trả về `.model_dump()` sớm** khi data còn flow trong pipeline.
   - Giữ Pydantic model cho đến khi serialize ra API/Firestore.
   - Chỉ gọi `.model_dump(mode="json")` ở boundary cuối cùng (API response, Firestore write).

3. **Mọi game type mới phải có model riêng** + thêm field vào `GameContentMap`.
   - Không mở rộng bằng cách nhét vào dict.

4. **`contract_version` phải tăng** khi thêm/sửa field trong response.
   - Minor: thêm field optional.
   - Major: đổi/xóa field, đổi cấu trúc.

## 10. Bước tiếp theo

- AI Service:
  - ✅ Đã siết chặt typing response + formatter (2026-03-20).
  - Generate OpenAPI spec từ Pydantic models.
  - Triển khai error contract chuẩn.
- GameService:
  - Validate payload có phù hợp runtime/rendering phía game không.
  - Chốt nhu cầu dữ liệu UI cho từng game type.
- Hai bên:
  - Đóng băng schema V1 và thống nhất chiến lược nâng cấp V1.1.
