"""CHECK 6 — Ý kiến thứ hai: so nhãn với một model LỚN HƠN (yolo26l).   ★★★ (khó nhất, đáng điểm nhất)

Test:  pytest tests/test_second_opinion.py -q

Máy kiểm quy tắc, người kiểm ý nghĩa (slide). Các lỗi như thiếu nhãn / gán nhầm lớp hợp lệ / box lỏng
KHÔNG bắt được bằng quy tắc cú pháp. Ta nhờ một model mạnh hơn "nhìn lại" và CHỈ CẢNH BÁO (model cũng có thể sai):
những ảnh bị cờ sẽ vào hàng đợi cho NGƯỜI duyệt.

`preds[stem]` = list `[id_lớp, conf, cx, cy, w, h]` của model (lấy qua `get_preds(ds, cfg, "checker")` nếu preds=None).
`L = ds.valid_boxes(stem)` = list `(id_lớp, cx, cy, w, h)` của nhãn (đã bỏ dòng hỏng).
Ngưỡng ở `cfg["second_opinion"]`: conf, min_area_px, fp_conf, iou_missing, iou_match, iou_loose.

Thuật toán gợi ý, với từng ảnh (bỏ qua ảnh không có trong preds hoặc không có file nhãn):
  P = dự đoán có conf >= conf  VÀ diện tích px (w*W * h*H) >= min_area_px
  Với mỗi dự đoán r trong P: lấy các nhãn có IoU(r, nhãn) >= iou_missing  (cands)
   - không có cands                            -> POSSIBLE_MISSING     (model thấy vật mà nhãn không có box)
   - có cands cùng lớp, tốt nhất IoU < iou_loose -> POSSIBLE_LOOSE_BOX  (đúng vật, box lỏng/lệch)
   - không có cands cùng lớp, nhưng cands tốt nhất IoU >= iou_match (khác lớp) -> POSSIBLE_WRONG_CLASS
  Với mỗi dòng nhãn hợp lệ: nếu IoU với MỌI dự đoán (conf >= fp_conf, không lọc diện tích) đều < iou_missing
                                             -> POSSIBLE_FALSE_POS  (box nhãn không khớp vật nào model thấy; Issue.line = số dòng)

Chi tiết các ca biên (test kiểm đúng các ca này)
- `cands` gồm nhãn MỌI lớp có IoU >= iou_missing; "tốt nhất cùng lớp" = cands cùng lớp có IoU lớn nhất; "tốt nhất khác lớp" tương tự với cands khác lớp.
- Thứ tự quyết định cho mỗi dự đoán: (1) cands rỗng -> MISSING. (2) có cands cùng lớp: IoU tốt nhất < iou_loose -> LOOSE_BOX, ngược lại KHÔNG cờ
  (nhãn đúng lớp đã phủ vật này, kể cả khi còn nhãn khác lớp chồng lên). (3) không có cands cùng lớp: nếu IoU tốt nhất khác lớp >= iou_match -> WRONG_CLASS;
  nếu chỉ có khác lớp với IoU trong [iou_missing, iou_match) -> không cờ gì (mơ hồ: để cho FALSE_POS / lần duyệt khác).
- Một dự đoán sinh tối đa MỘT issue (MISSING / LOOSE_BOX / WRONG_CLASS); một ảnh có thể có nhiều issue.
- Thứ tự issue: theo `ds.image_files()` rồi theo thứ tự dự đoán trong `preds[stem]`, cuối cùng là các FALSE_POS theo số dòng; `Issue.image` = stem, `Issue.line` chỉ đặt cho FALSE_POS.

Lưu ý số dòng: dùng `ds.read_label_lines(stem)` (giữ số dòng gốc, kể cả dòng hỏng/trống) để lấy `Issue.line`; `valid_boxes` KHÔNG giữ số dòng.

Tất cả severity WARN; `Issue.extra` nên có {"conf": ...} hoặc {"iou": ...} (hàng đợi duyệt dùng conf để xếp ưu tiên).

Gợi ý
- `iou_xywh` có sẵn. Dòng nhãn hỏng không được làm script chết (dùng `ds.valid_boxes` và `parse_yolo_line` trong try).
- Kết quả phụ thuộc mạnh vào ngưỡng: calibrate chúng ở Bước 3 thay vì đoán.
"""
from ..common import WARN, Issue, iou_xywh, parse_yolo_line  # noqa: F401
from ..model_cache import get_preds  # noqa: F401


CHECK = "second_opinion"


def _label_boxes(ds, stem):
    """[(số dòng gốc, id, (cx, cy, w, h))] của các dòng hợp lệ; dòng hỏng / id lạ bị bỏ qua (label_format sẽ báo)."""
    out = []
    for ln_no, text in ds.read_label_lines(stem) or []:
        try:
            c, x, y, w, h = parse_yolo_line(text)
        except ValueError:
            continue
        if 0 <= c < len(ds.classes):
            out.append((ln_no, c, (x, y, w, h)))
    return out


def run(ds, cfg, preds=None):
    so = cfg["second_opinion"]
    conf_min, min_area = so["conf"], so["min_area_px"]
    fp_conf = so["fp_conf"]
    iou_missing, iou_match, iou_loose = so["iou_missing"], so["iou_match"], so["iou_loose"]
    if preds is None:
        preds = get_preds(ds, cfg, "checker")

    issues = []
    for img in ds.image_files():
        stem = img.stem
        if stem not in preds or not ds.label_path(stem).exists():
            continue
        labels = _label_boxes(ds, stem)
        size = ds.image_size(stem)
        rows = preds[stem] or []

        # --- A. Từng dự đoán tin cậy, đủ lớn: model thấy vật -> nhãn có phủ đúng không?
        for r in rows:
            p_cls, p_conf, p_box = int(r[0]), float(r[1]), tuple(r[2:6])
            if p_conf < conf_min:
                continue
            if size is not None and p_box[2] * size[0] * p_box[3] * size[1] < min_area:
                continue
            cands = [(iou_xywh(p_box, box), c) for _, c, box in labels]
            cands = [(iou, c) for iou, c in cands if iou >= iou_missing]
            if not cands:
                issues.append(Issue(CHECK, WARN, "POSSIBLE_MISSING", stem,
                                    f"model thấy {ds.classes[p_cls] if 0 <= p_cls < len(ds.classes) else p_cls} "
                                    f"(conf {p_conf:.2f}) nhưng nhãn không có box",
                                    extra={"conf": p_conf, "pred_cls": p_cls, "box": list(p_box)}))
                continue
            same = [iou for iou, c in cands if c == p_cls]
            if same:
                best = max(same)
                if best < iou_loose:
                    issues.append(Issue(CHECK, WARN, "POSSIBLE_LOOSE_BOX", stem,
                                        f"đúng lớp nhưng box lệch/lỏng (IoU {best:.2f} < {iou_loose})",
                                        extra={"conf": p_conf, "iou": round(best, 4), "pred_cls": p_cls}))
                continue                                    # nhãn đúng lớp đã phủ vật này
            best_iou, best_cls = max(cands)                 # chỉ còn ứng viên khác lớp
            if best_iou >= iou_match:
                issues.append(Issue(CHECK, WARN, "POSSIBLE_WRONG_CLASS", stem,
                                    f"nhãn lớp {best_cls} nhưng model nói lớp {p_cls} (IoU {best_iou:.2f}, conf {p_conf:.2f})",
                                    extra={"conf": p_conf, "iou": round(best_iou, 4),
                                           "label_cls": best_cls, "pred_cls": p_cls}))
            # IoU khác lớp trong [iou_missing, iou_match): mơ hồ -> không cờ

        # --- B. Từng box nhãn: có dự đoán nào (conf >= fp_conf, không lọc diện tích) khớp không?
        fp_boxes = [tuple(r[2:6]) for r in rows if float(r[1]) >= fp_conf]
        for ln_no, c, box in labels:
            best = max((iou_xywh(box, pb) for pb in fp_boxes), default=0.0)
            if best < iou_missing:
                issues.append(Issue(CHECK, WARN, "POSSIBLE_FALSE_POS", stem,
                                    f"box nhãn lớp {c} không khớp vật nào model thấy (IoU tốt nhất {best:.2f})",
                                    line=ln_no, extra={"iou": round(best, 4), "label_cls": c}))
    return issues
