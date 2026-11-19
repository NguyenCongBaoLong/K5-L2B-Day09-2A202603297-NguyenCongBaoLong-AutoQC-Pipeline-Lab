# Báo cáo Day 09 — Nguyễn Công Bảo Long, 2A202603297

## 1. Kết luận trước
Pipeline kết luận **Hold**: nhận 193/224 ảnh, loại 31 ảnh và xuất 193 ảnh ở trạng thái bản nháp (không phải bản phát hành). Sau 80 lượt duyệt mô phỏng, 34/193 ảnh còn cảnh báo chưa được xử lý (17,62%), vượt ngưỡng Hold 10%. Hàng đợi có 121 ảnh, nhiều hơn ngân sách 41 ảnh.

## 2. Lỗi và phân việc
Ở cửa vào, 31/224 ảnh bị loại: `BAD_SIZE` 3, `CORRUPT_IMAGE` 2, `DUP_IMAGE_EXACT` 8, `DUP_IMAGE_NEAR` 7, `LEAK_TEST` 11. QC trên 193 ảnh ghi nhận 36 lỗi bắt buộc và 145 cảnh báo (số issue; mẫu số dữ liệu là 193 ảnh).

| Lỗi bắt buộc trong QC | Số issue / mẫu số | Xử lý |
|---|---:|---|
| `BAD_CLASS_ID` | 6 / 193 ảnh | Máy bỏ dòng sai |
| `BAD_CLASS_NAME` | 2 tên / 1 `data.yaml` | Máy chuẩn hóa tên lớp |
| `BAD_FORMAT` | 3 / 193 ảnh | Máy bỏ dòng sai định dạng |
| `BOX_OUT_OF_IMAGE` | 8 / 193 ảnh | Máy cắt box vào ảnh |
| `BOX_ZERO` | 4 / 193 ảnh | Máy bỏ dòng |
| `DUP_BOX` | 7 / 193 ảnh | Máy bỏ dòng lặp |
| `MISSING_LABEL_FILE` | 6 / 193 ảnh | Máy chuyển người gán, không tự tạo nhãn |

145 cảnh báo ban đầu gồm `POSSIBLE_MISSING` 53, `POSSIBLE_LOOSE_BOX` 27, `POSSIBLE_FALSE_POS` 24, `POSSIBLE_WRONG_CLASS` 17, `EMPTY_LABEL` 11, `BOX_TINY` 6, `CLASS_RARE` 4 và `BOX_HUGE` 3. Máy ghi 35 thay đổi vào `03_fixes.csv`. Hàng đợi ưu tiên `img_0020` đầu tiên (11.524; đã sửa dòng lỗi nhưng còn nghi ngờ thiếu/sai lớp), sau đó là sáu ảnh thiếu nhãn (priority 10), rồi các ảnh có cảnh báo ngữ nghĩa. Mô phỏng xử lý 80/121 ảnh; 41 ảnh vượt ngân sách. Đây là mô phỏng bằng script, không phải 80 ảnh do người thật xác nhận.

Sau mô phỏng, còn cảnh báo trên 34 ảnh: `POSSIBLE_MISSING` 12, `POSSIBLE_LOOSE_BOX` 18, `POSSIBLE_FALSE_POS` 20, `POSSIBLE_WRONG_CLASS` 3, `EMPTY_LABEL` 3, `BOX_TINY` 7 và `BOX_HUGE` 3. Số issue có thể nhiều hơn số ảnh vì một ảnh có thể có nhiều cảnh báo.

## 3. Calibration
| Tham số | Khởi đầu | Chọn | Precision / Recall trước → sau | Lý do |
|---|---:|---:|---|---|
| `duplicates.phash_dist` | 2 | 16 | Near duplicate: 1.00/0.50 → 1.00/0.83; exact: 1.00/1.00 → 1.00/1.00 | Sweep tăng recall near trên calib. Tuy nhiên, kiểm tra ảnh raw cho thấy ngưỡng này có thể xóa nhầm ảnh khác cảnh; rủi ro được nêu rõ bên dưới. |
| `second_opinion.conf` | 0.25 | 0.6 | Wrong class: 0.56/0.83 → 0.62/0.83; missing: 0.50/1.00 → 0.57/1.00; loose box: 0.29/0.40 → 0.20/0.20; false positive: 0.36/1.00 → 0.36/1.00 | Tăng precision wrong-class và giữ recall missing; loose-box recall thấp nên không coi cảnh báo model là đáp án, vẫn cần người xem. |

Calib chỉ có 39 ảnh, trong đó 6 lỗi near duplicate nên mỗi ca làm recall thay đổi khoảng 0.17. Dù calib cho precision 1.00 ở ngưỡng 16, kiểm tra ảnh raw cho thấy hai cặp bị nhận nhầm (`img_0011`/`img_0008` và `img_0177`/`img_0113` là khác cảnh); cặp `img_0084`/`img_0074` là cùng cảnh ở khoảng cách 16. Pipeline với ngưỡng 16 đánh dấu 7 near duplicate. Vì vậy precision trên calib không bảo đảm an toàn trên raw; ngưỡng này có nguy cơ loại nhầm ảnh.

## 4. Cửa chặn và điểm mù
Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb` cho kết luận **Rework**, mã thoát **20**; sáu ảnh thiếu file nhãn còn lỗi bắt buộc và không có bản export. Với ngân sách mặc định, không còn lỗi bắt buộc nhưng gate trả Hold do 34/193 ảnh còn cảnh báo (17,62%).

Đã xem 10 ảnh có nhãn trong `work/viz/`; `img_0010` bị hỏng nên script bỏ qua. Khi xem thêm ảnh lỗi, box ở `img_0030` tràn khỏi mép trái, phù hợp với lỗi `BOX_OUT_OF_IMAGE` và log `clip_box`. Điểm mù: (1) pHash có thể nhầm hai cảnh khác nhau như các cặp ở mục 3, hoặc bỏ sót cặp gần trùng thật; (2) model ý kiến thứ hai không phải đáp án, nên cảnh báo thiếu/sai lớp/box lỏng có thể là false positive hoặc bỏ sót; (3) `EMPTY_LABEL` không tự phân biệt ảnh nền hợp lệ với thiếu nhãn.

## 5. Train: raw vs clean
Chưa chạy train; phần này tùy chọn và cần GPU/Colab. Không có số liệu mAP để kết luận raw hay clean tốt hơn.

## 6. Quyết định và ghi chú AI
Quyết định hiện tại là **Hold**, không Release: 34/193 ảnh còn cảnh báo chưa duyệt, vượt ngưỡng 10%. Để đánh giá lại, cần người thật xử lý phần hàng đợi vượt ngân sách, kiểm tra các cảnh báo còn lại rồi chạy lại pipeline; không đổi ngân sách hay ngưỡng gate để ép Release.

- Prompt chính: triển khai bốn module còn stub theo docstring/test và hướng dẫn TDD của lab.
- Cách kiểm: chạy toàn bộ suite (79 test), calibration trên calib, xem preview/cặp trùng raw, chạy pipeline và thử gate với ngân sách 0. Đã thêm cảnh báo tùy chọn `BOX_EXTREME_ASPECT` theo đoạn yêu cầu và kiểm tra trên ảnh thử.
- AI sai: trong bản nháp trước khi discard, AI unpack sai cấu trúc nhãn ở nhánh `POSSIBLE_FALSE_POS`; test phát hiện. Bản làm lại hiện tại đã được chạy lại và 79 test đều qua.
