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


CHECK = "label_format"


def run(ds, cfg):
    lf = cfg["label_format"]
    tol = lf["overflow_tol"]
    min_px = lf["min_box_px"]
    max_frac = lf["max_box_frac"]
    dup_iou = lf["dup_box_iou"]
    n_classes = len(ds.classes)

    issues = []
    for lp in ds.label_files():                       # đã sắp xếp theo tên -> kết quả ổn định
        stem = lp.stem
        size = ds.image_size(stem)                    # None nếu không có ảnh / ảnh hỏng -> bỏ qua BOX_TINY
        kept = []                                     # (id, box) các dòng hợp lệ trước đó, để bắt DUP_BOX
        for ln_no, text in ds.read_label_lines(stem) or []:   # số dòng GỐC (dòng trống đã bỏ nhưng giữ số)
            # 1) cú pháp: dòng hỏng thì báo rồi bỏ, không kiểm hình học
            try:
                c, x, y, w, h = parse_yolo_line(text)
            except ValueError as e:
                issues.append(Issue(CHECK, ERROR, "BAD_FORMAT", stem, f"dòng sai định dạng: {e}", line=ln_no))
                continue
            if not 0 <= c < n_classes:
                issues.append(Issue(CHECK, ERROR, "BAD_CLASS_ID", stem, f"id lớp {c} ngoài 0..{n_classes - 1}",
                                    line=ln_no, extra={"id": c}))
                continue
            if w <= 0 or h <= 0:
                issues.append(Issue(CHECK, ERROR, "BOX_ZERO", stem, f"box rỗng (w={w}, h={h})", line=ln_no))
                continue

            # 2) tràn ảnh: mức tràn lớn nhất trên 4 mép
            overflow = max(0.0, -(x - w / 2), (x + w / 2) - 1, -(y - h / 2), (y + h / 2) - 1)
            if overflow > tol:
                issues.append(Issue(CHECK, ERROR, "BOX_OUT_OF_IMAGE", stem, f"box tràn ảnh {overflow:.4f}",
                                    line=ln_no, extra={"overflow": round(overflow, 6)}))

            # 3) box lặp: cùng lớp với một dòng TRƯỚC ĐÓ và IoU > ngưỡng -> báo ở dòng sau
            box = (x, y, w, h)
            for c_prev, b_prev in kept:
                if c_prev == c:
                    iou = iou_xywh(box, b_prev)
                    if iou > dup_iou:
                        issues.append(Issue(CHECK, ERROR, "DUP_BOX", stem, f"box lặp (IoU {iou:.3f})",
                                            line=ln_no, extra={"iou": round(iou, 4)}))
                        break
            kept.append((c, box))

            # 4) cảnh báo kích thước
            if size is not None:
                short_px = min(w * size[0], h * size[1])
                if short_px < min_px:
                    issues.append(Issue(CHECK, WARN, "BOX_TINY", stem, f"box nhỏ: cạnh ngắn {short_px:.1f}px",
                                        line=ln_no, extra={"short_px": round(short_px, 2)}))
            if w * h > max_frac:
                issues.append(Issue(CHECK, WARN, "BOX_HUGE", stem, f"box chiếm {w * h:.2%} ảnh",
                                    line=ln_no, extra={"area_frac": round(w * h, 4)}))
    return issues
