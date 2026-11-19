"""BƯỚC 2/4 — Sửa tự động những lỗi bắt buộc mà máy sửa được AN TOÀN.   ★★

Test:  pytest tests/test_autofix.py -q

`fix(ds, issues, cfg) -> list[dict]`: duyệt `issues` (chỉ lỗi severity ERROR), sửa thẳng vào thư mục `ds`,
và trả về danh sách thay đổi; mỗi phần tử có khoá: image, line, action, before, after
(đây chính là file `03_fixes.csv` — bằng chứng pipeline đã làm gì, người có thể kiểm lại).

| code lỗi                                       | cách sửa                                    | action           |
|------------------------------------------------|---------------------------------------------|------------------|
| BAD_FORMAT, BAD_CLASS_ID, BOX_ZERO, DUP_BOX    | xoá dòng đó khỏi file nhãn                  | "drop_line"      |
| BOX_OUT_OF_IMAGE                               | cắt box về trong [0,1] (giữ nguyên lớp)     | "clip_box"       |
| MISSING_LABEL_FILE                             | KHÔNG sửa file (máy không thể bịa nhãn): ghi 1 dòng fix, before="(không có file)", after="chuyển người gán" | "needs_label" |
| BAD_CLASS_NAME                                 | ghi lại `names` trong data.yaml đúng `cfg["classes"]` | "rename_classes" |
| DUP_IMAGE_*, LEAK_TEST, CORRUPT_IMAGE, BAD_SIZE| xoá ảnh + nhãn khỏi `ds`                    | "remove_image"   |

Bẫy cần nghĩ tới (có test cho từng cái)
- Một file có NHIỀU dòng lỗi: số dòng trong `issues` là số dòng GỐC. Nếu xoá từng dòng một thì số dòng lệch.
  Gom theo file, rồi ghi lại MỘT lần.
- Sau khi cắt, box có thể không còn diện tích (nằm hẳn ngoài ảnh): lúc đó xoá dòng thay vì ghi box rỗng.
- Một dòng có 2 lỗi (vd. BOX_OUT_OF_IMAGE + DUP_BOX): xoá dòng thắng, chỉ ghi 1 fix `drop_line`, không ghi thêm `clip_box`. Dòng trống ở giữa file vẫn đếm vào số dòng gốc.
- Ảnh vừa bị xoá (DUP_IMAGE_*...) mà còn issue dòng của chính nó: bỏ qua êm, không được báo lỗi/chết.
- Không động tới lỗi WARN (cảnh báo là việc của người). Không sửa file ở `data/raw/` — chỉ sửa `ds`.
- Chạy lần 2 trên dữ liệu đã sửa phải không làm gì thêm (idempotent) — NGOẠI LỆ duy nhất: `needs_label` được ghi lại mỗi lần còn lỗi `MISSING_LABEL_FILE` (vì ảnh vẫn chưa có nhãn).

- `needs_label` KHÔNG tạo file nhãn rỗng (rỗng = "ảnh nền", khác với "chưa gán"). `review_queue` sẽ đẩy ảnh này lên đầu hàng đợi cho người.

Gợi ý: `yaml.safe_load / safe_dump`.
"""
from collections import defaultdict  # noqa: F401

import yaml  # noqa: F401

from ..common import ERROR, parse_yolo_line  # noqa: F401


def fix(ds, issues, cfg):
    changes = []
    errors = [issue for issue in issues if issue.severity == ERROR]
    remove_codes = {"LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}

    removed_images = set()
    for issue in errors:
        is_duplicate = issue.code.startswith("DUP_IMAGE_")
        if (not is_duplicate and issue.code not in remove_codes) or issue.image in removed_images:
            continue

        image_path = ds.image_path(issue.image)
        label_path = ds.label_path(issue.image)
        if image_path is None and not label_path.exists():
            continue
        if image_path is not None and image_path.exists():
            image_path.unlink()
        if label_path.exists():
            label_path.unlink()
        changes.append({
            "image": issue.image,
            "line": "",
            "action": "remove_image",
            "before": "ảnh và nhãn",
            "after": "đã xoá",
        })
        removed_images.add(issue.image)

    if any(issue.code == "BAD_CLASS_NAME" for issue in errors):
        names = {index: name for index, name in enumerate(cfg["classes"])}
        current_names = ds.yaml_names()
        if current_names != names:
            data = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) if ds.yaml_path.exists() else {}
            data = data or {}
            before = data.get("names")
            data["names"] = list(cfg["classes"]) if isinstance(before, list) else names
            ds.yaml_path.write_text(
                yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            changes.append({
                "image": "data.yaml",
                "line": "",
                "action": "rename_classes",
                "before": str(before),
                "after": str(data["names"]),
            })

    missing_label_images = set()
    line_errors = defaultdict(lambda: defaultdict(list))
    for issue in errors:
        if issue.image in removed_images:
            continue
        if issue.code == "MISSING_LABEL_FILE":
            if issue.image not in missing_label_images:
                changes.append({
                    "image": issue.image,
                    "line": "",
                    "action": "needs_label",
                    "before": "(không có file)",
                    "after": "chuyển người gán",
                })
                missing_label_images.add(issue.image)
        elif issue.line is not None and issue.code in {
            "BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX", "BOX_OUT_OF_IMAGE",
        }:
            line_errors[issue.image][issue.line].append(issue)

    drop_codes = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
    for stem, issues_by_line in line_errors.items():
        label_path = ds.label_path(stem)
        if not label_path.exists():
            continue

        original = label_path.read_text(encoding="utf-8", errors="replace")
        lines = original.splitlines()
        changed = False
        for line_no, line_issues in issues_by_line.items():
            index = line_no - 1
            if index < 0 or index >= len(lines):
                continue

            before = lines[index]
            if any(issue.code in drop_codes for issue in line_issues):
                lines[index] = None
                changes.append({
                    "image": stem, "line": line_no, "action": "drop_line",
                    "before": before, "after": "",
                })
                changed = True
                continue

            if not any(issue.code == "BOX_OUT_OF_IMAGE" for issue in line_issues):
                continue
            try:
                cls, x, y, width, height = parse_yolo_line(before)
            except (ValueError, OverflowError):
                lines[index] = None
                changes.append({
                    "image": stem, "line": line_no, "action": "drop_line",
                    "before": before, "after": "",
                })
                changed = True
                continue

            left = max(0.0, x - width / 2)
            top = max(0.0, y - height / 2)
            right = min(1.0, x + width / 2)
            bottom = min(1.0, y + height / 2)
            if right <= left or bottom <= top:
                lines[index] = None
                action, after = "drop_line", ""
            else:
                clipped = (cls, (left + right) / 2, (top + bottom) / 2, right - left, bottom - top)
                after = f"{cls} " + " ".join(f"{value:.6f}" for value in clipped[1:])
                if after == before:
                    continue
                lines[index] = after
                action = "clip_box"
            changes.append({
                "image": stem, "line": line_no, "action": action,
                "before": before, "after": after,
            })
            changed = True

        if changed:
            remaining = [line for line in lines if line is not None]
            text = "\n".join(remaining)
            if original.endswith(("\n", "\r")) and remaining:
                text += "\n"
            label_path.write_text(text, encoding="utf-8")

    return changes
