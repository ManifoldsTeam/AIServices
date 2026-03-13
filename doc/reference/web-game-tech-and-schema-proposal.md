# Đề xuất Công nghệ Web Game và Schema (để thống nhất với GameService)

> Cập nhật: 2026-03-13
> Mục tiêu: Bản nháp để thảo luận và chốt contract giữa AI Service và GameService

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

Quan sát từ schema hiện có:

- Các trường content trong response còn lỏng kiểu (`dict[str, list[dict]]`), giảm độ an toàn khi codegen client.
- Chưa có `contract_version` rõ ràng trong payload generation.
- Chưa có discriminated union cho game items đa hình.

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

1. Chốt engine cho frontend V1:

- Phaser (đề xuất) hoặc stack khác theo nhu cầu GameService.

2. Chốt tên discriminator:

- `type` hay `game_type` ở cấp item.

3. Chốt field bắt buộc và field optional cho từng game type.
4. Chốt error contract:

- `code`, `message`, `request_id`, `retryable`, `details`.

5. Chốt chính sách version/deprecation và quy trình rollout.
6. Chốt endpoint capability:

- `GET /api/v1/game-types` trả về danh sách type + schema version + ràng buộc.

## 9. Bước tiếp theo

- AI Service:
  - Siết chặt typing của response trong Pydantic.
  - Generate OpenAPI và công bố ví dụ schema.
- GameService:
  - Validate payload có phù hợp runtime/rendering phía game không.
  - Chốt nhu cầu dữ liệu UI cho từng game type.
- Hai bên:
  - Đóng băng schema V1 và thống nhất chiến lược nâng cấp V1.1.
