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


DROP_CODES = {"BAD_FORMAT", "BAD_CLASS_ID", "BOX_ZERO", "DUP_BOX"}
CLIP_CODES = {"BOX_OUT_OF_IMAGE"}
REMOVE_CODES = {"DUP_IMAGE_EXACT", "DUP_IMAGE_NEAR", "LEAK_TEST", "CORRUPT_IMAGE", "BAD_SIZE"}


def _is_remove(code):
    return code in REMOVE_CODES or code.startswith("DUP_IMAGE_")


def _fx(image, line, action, before, after):
    return {"image": image, "line": line, "action": action, "before": before, "after": after}


def _clip(text):
    """Cắt box về [0,1]. Trả về dòng mới, hoặc None nếu box không còn diện tích (=> xoá dòng)."""
    try:
        c, x, y, w, h = parse_yolo_line(text)
    except ValueError:
        return None
    x1, x2 = max(0.0, x - w / 2), min(1.0, x + w / 2)
    y1, y2 = max(0.0, y - h / 2), min(1.0, y + h / 2)
    if x2 <= x1 or y2 <= y1:
        return None
    nw, nh = x2 - x1, y2 - y1
    return f"{c} {x1 + nw / 2:.6f} {y1 + nh / 2:.6f} {nw:.6f} {nh:.6f}"


def fix(ds, issues, cfg):
    errors = [i for i in issues if i.severity == ERROR]      # KHÔNG động tới WARN
    fixes = []

    # 1) Xoá ảnh (trùng / rò rỉ test / hỏng / sai cỡ): xoá ảnh + nhãn trong ds (không phải data/raw)
    removed = set()
    for i in errors:
        if not _is_remove(i.code) or i.image in removed:
            continue
        removed.add(i.image)
        img = ds.image_path(i.image)
        lab = ds.label_path(i.image)
        if img is None and not lab.exists():                 # đã xoá ở lần chạy trước -> idempotent
            continue
        names = []
        if img is not None:
            names.append(img.name)
            img.unlink()
        if lab.exists():
            names.append(lab.name)
            lab.unlink()
        fixes.append(_fx(i.image, None, "remove_image", " + ".join(names), f"(đã xoá: {i.code})"))

    # 2) data.yaml: ghi lại names đúng cfg["classes"] (giữ các khoá khác)
    if any(i.code == "BAD_CLASS_NAME" for i in errors):
        want = list(cfg["classes"])
        old = ds.yaml_names()
        if [old.get(k) for k in range(len(old))] != want or len(old) != len(want):
            d = {}
            if ds.yaml_path.exists():
                d = yaml.safe_load(ds.yaml_path.read_text(encoding="utf-8")) or {}
            d["names"] = {k: n for k, n in enumerate(want)}
            ds.yaml_path.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
            fixes.append(_fx("data.yaml", None, "rename_classes", str(old), str(d["names"])))

    # 3) Ảnh chưa có file nhãn: máy KHÔNG bịa nhãn, không tạo file rỗng -> chuyển người gán
    seen = set()
    for i in errors:
        if i.code != "MISSING_LABEL_FILE" or i.image in removed or i.image in seen:
            continue
        seen.add(i.image)
        if ds.label_path(i.image).exists():
            continue
        fixes.append(_fx(i.image, None, "needs_label", "(không có file)", "chuyển người gán"))

    # 4) Lỗi theo dòng: gom theo file, quyết định cho từng dòng GỐC, rồi ghi file MỘT lần
    by_file = defaultdict(lambda: defaultdict(set))         # stem -> số dòng -> {code}
    for i in errors:
        if i.line is not None and (i.code in DROP_CODES or i.code in CLIP_CODES):
            by_file[i.image][i.line].add(i.code)

    for stem in sorted(by_file):
        lab = ds.label_path(stem)
        if stem in removed or not lab.exists():              # ảnh vừa bị xoá: bỏ qua êm
            continue
        raw = lab.read_text(encoding="utf-8", errors="replace").splitlines()   # giữ cả dòng trống -> số dòng gốc
        out = list(raw)
        changed = False
        for ln_no in sorted(by_file[stem]):
            if not 1 <= ln_no <= len(raw):                   # issue cũ, dòng không còn -> bỏ qua
                continue
            before = raw[ln_no - 1]
            codes = by_file[stem][ln_no]
            if codes & DROP_CODES:                           # xoá dòng thắng clip
                new = None
            else:
                new = _clip(before)
                if new is not None:
                    out[ln_no - 1] = new
                    fixes.append(_fx(stem, ln_no, "clip_box", before, new))
                    changed = True
                    continue
            out[ln_no - 1] = None
            fixes.append(_fx(stem, ln_no, "drop_line", before, ""))
            changed = True
        if changed:
            kept = [ln for ln in out if ln is not None]
            lab.write_text("".join(ln + "\n" for ln in kept), encoding="utf-8")
    return fixes
