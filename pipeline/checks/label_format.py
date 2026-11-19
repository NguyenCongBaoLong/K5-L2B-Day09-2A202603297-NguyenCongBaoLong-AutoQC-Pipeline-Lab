"""CHECK 2 — Dòng nhãn YOLO: sai định dạng, ID lớp lạ, box tràn ảnh, box rỗng, box lặp.   (Script 2 trong slide)   ★★

Test:  pytest tests/test_label_format.py -q

Mỗi dòng nhãn: `id cx cy w h` (5 số, toạ độ 0–1). Trả về list[Issue]; `Issue.line` = số dòng (đếm từ 1).

| code             | severity | khi nào                                                                  |
|------------------|----------|--------------------------------------------------------------------------|
| BAD_FORMAT       | ERROR    | không đúng 5 cột số (dùng `parse_yolo_line`, bắt `ValueError`)           |
| BAD_CLASS_ID     | ERROR    | id lớp ngoài 0..len(ds.classes)-1                                        |
| BOX_ZERO         | ERROR    | w <= 0 hoặc h <= 0                                                       |
| BOX_OUT_OF_IMAGE | ERROR    | mép box vượt [0,1] quá `cfg["label_format"]["overflow_tol"]`; extra={"overflow": mức tràn} |
| DUP_BOX          | ERROR    | cùng lớp với một dòng TRƯỚC ĐÓ và IoU > `dup_box_iou`; báo ở dòng SAU    |
| BOX_TINY         | WARN     | cạnh ngắn của box (px) < `min_box_px`  (cần `ds.image_size(stem)`)       |
| BOX_HUGE         | WARN     | w*h > `max_box_frac`                                                     |

Gợi ý
- Mép trái = x - w/2, mép phải = x + w/2 (xem câu hỏi "dòng YOLO nào lỗi?" trong slide).
- Một dòng hỏng (BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO) thì `continue`, đừng kiểm tiếp hình học của dòng đó.
- Dòng thiếu cột làm script của slide dừng giữa chừng: đây là lý do phải `try/except`.
- `iou_xywh(a, b)` có sẵn trong common.py.
- Ngưỡng nằm trong `cfg["label_format"]` — đừng viết cứng số vào code.
"""
from ..common import ERROR, WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401


def run(ds, cfg):
    thresholds = cfg["label_format"]
    issues = []

    for label_file in ds.label_files():
        stem = label_file.stem
        image_size = ds.image_size(stem)
        previous_boxes = []

        for line_no, text in ds.read_label_lines(stem) or []:
            try:
                cls, x, y, width, height = parse_yolo_line(text)
            except (ValueError, OverflowError):
                issues.append(Issue(
                    "label_format", ERROR, "BAD_FORMAT", stem,
                    "Dòng nhãn không đúng định dạng YOLO", line_no,
                ))
                continue

            if not 0 <= cls < len(ds.classes):
                issues.append(Issue(
                    "label_format", ERROR, "BAD_CLASS_ID", stem,
                    f"ID lớp {cls} nằm ngoài danh sách lớp", line_no,
                ))
                continue
            if width <= 0 or height <= 0:
                issues.append(Issue(
                    "label_format", ERROR, "BOX_ZERO", stem,
                    "Box có chiều rộng hoặc chiều cao không dương", line_no,
                ))
                continue

            left = x - width / 2
            top = y - height / 2
            right = x + width / 2
            bottom = y + height / 2
            overflow = max(0.0, -left, -top, right - 1.0, bottom - 1.0)
            if overflow > thresholds["overflow_tol"]:
                issues.append(Issue(
                    "label_format", ERROR, "BOX_OUT_OF_IMAGE", stem,
                    f"Box tràn khỏi ảnh {overflow:.6g}", line_no,
                    {"overflow": overflow},
                ))

            box = (x, y, width, height)
            if any(
                previous_cls == cls
                and iou_xywh(box, previous_box) > thresholds["dup_box_iou"]
                for previous_cls, previous_box in previous_boxes
            ):
                issues.append(Issue(
                    "label_format", ERROR, "DUP_BOX", stem,
                    "Box trùng với dòng nhãn trước đó", line_no,
                ))
            previous_boxes.append((cls, box))

            if image_size is not None:
                image_width, image_height = image_size
                if min(width * image_width, height * image_height) < thresholds["min_box_px"]:
                    issues.append(Issue(
                        "label_format", WARN, "BOX_TINY", stem,
                        "Cạnh ngắn của box nhỏ hơn ngưỡng pixel", line_no,
                    ))
            if width * height > thresholds["max_box_frac"]:
                issues.append(Issue(
                    "label_format", WARN, "BOX_HUGE", stem,
                    "Box chiếm phần lớn diện tích ảnh", line_no,
                ))
            if image_size is not None:
                pixel_width = width * image_size[0]
                pixel_height = height * image_size[1]
                if pixel_width > 0 and pixel_height > 0:
                    aspect_ratio = max(
                        pixel_width / pixel_height,
                        pixel_height / pixel_width,
                    )
                    if aspect_ratio > 10:
                        issues.append(Issue(
                            "label_format", WARN, "BOX_EXTREME_ASPECT", stem,
                            f"Tỷ lệ khung hình box bất thường ({aspect_ratio:.2f}:1, ngưỡng 10:1).",
                            line_no, {"aspect_ratio": round(aspect_ratio, 4)},
                        ))

    return issues
