# ShelfCash

ShelfCash là backend hỗ trợ chủ quán F&B quyết định mua nguyên liệu: cần mua gì,
bao nhiêu và phương án nào phù hợp với ngân sách, tồn kho và hạn dùng đã ghi nhận.
Hệ thống dùng dữ liệu bán hàng, công thức và điều kiện nhà cung cấp để dự báo nhu
cầu, tính toán và giải thích các phương án. Chủ quán quyết định việc mua hàng.

## Từ dữ liệu đến phương án mua

Nhập và duyệt dữ liệu → kiểm tra khả năng tính → dự báo → tính nhu cầu nguyên
liệu và tồn kho có thể dùng → so sánh phương án mua → xem giải thích hoặc tải PDF.

## Khả năng hiện có trong source

| Khả năng | Giúp người dùng làm gì |
| --- | --- |
| Import / Inventory | Duyệt cách hiểu dữ liệu trước khi nhập; theo dõi nguyên liệu, lô hàng, tồn kho và hạn dùng. |
| Forecast | Dự báo nhu cầu sản phẩm từ lịch sử bán hàng, với các mức phân vị nhu cầu. |
| Planning | Tính nhu cầu nguyên liệu và so sánh phương án mua theo dữ liệu, ngân sách và điều kiện đã khai báo. |
| Summary | Đọc bản tóm tắt của một kết quả Planning đã lưu. |
| Chat | Hỏi và nhận giải thích theo bằng chứng của kết quả đang xem. |
| PDF | Xuất báo cáo từ kết quả đã lưu để tải xuống. |

Summary và Chat hỗ trợ đọc kết quả; backend vẫn sở hữu dữ liệu và phép tính.

## Bắt đầu và tìm tài liệu

- **Clone mới:** [cài đặt và cấu hình lần đầu](docs/GETTING_STARTED.md#first-time-setup).
- **Máy đã setup:** [start / status / stop](docs/GETTING_STARTED.md#daily-use).
- **Đăng ký và tạo quán:** [signup → xác minh email → tạo Store](docs/GETTING_STARTED.md#onboarding).
- **FE:** [bắt đầu từ handoff](docs/handoff/010_BE_CAPABILITY_RESPONSE_VI.md), rồi đọc OpenAPI và contract theo chức năng.
- **Developer:** [testing](docs/TESTING.md), [runbook kiểm chứng](docs/runbooks/FULL_TEST_FLOW.md) và [engineering rules](AGENTS.md).
- **Hiểu hệ thống:** [kiến trúc](docs/ARCHITECTURE.md), [nghiệp vụ](docs/DOMAIN_MODEL.md) và [các quyết định kiến trúc](docs/DECISIONS.md).
- **Theo dõi tiến độ:** [trạng thái hiện tại](docs/CURRENT_STATE.md) và [roadmap](docs/ROADMAP.md).

## Giới hạn hiện tại

Chất lượng dự báo trên dữ liệu thực chưa được đánh giá; forecast challenger chỉ
dành cho kiểm chứng có opt-in, chưa được bật cho production. Toàn bộ browser flow
và deployment của source hiện tại chưa được xác nhận. FE chạy riêng với backend.

Email thật cần SMTP và callback FE phù hợp; LLM là tùy chọn, cấu hình riêng cho
Import, Summary và Chat. Có đường tính toán và giải thích xác định không cần LLM.
Store mới cần dữ liệu và cấu hình đủ điều kiện trước khi Planning có thể tính.
ShelfCash không tự đặt hàng hay biến phương án mua thành tồn kho thực tế.
