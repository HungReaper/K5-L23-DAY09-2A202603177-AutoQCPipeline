# Báo cáo Day 09 — Trịnh Đức Hưng, 2A202603177

## 1. Kết luận trước

Pipeline kết luận **Hold** (mã thoát 10). Vào 224 ảnh; cửa vào loại 22 ảnh (2 hỏng, 3 quá nhỏ, 8 trùng từng byte, 4 trùng gần đúng, 5 rò rỉ test), còn **202 ảnh** đi tiếp và được xuất ra `submission/export/clean_v1` (202 file nhãn) dưới dạng **bản nháp, chưa phát hành**. Lý do Hold: không còn lỗi bắt buộc nào (0), nhưng **38/202 ảnh (18.81%)** vẫn còn cảnh báo chưa được người duyệt, vượt ngưỡng 10%. Hàng đợi có 125 ảnh mà ngân sách duyệt chỉ 80 ảnh.

## 2. Lỗi và phân việc

| Mã lỗi | Số dòng / ảnh | Ai sửa (máy/người) | Vì sao |
| --- | ---: | --- | --- |
| `CORRUPT_IMAGE` · `BAD_SIZE` | 2 · 3 ảnh | máy (loại ở cửa vào) | Ảnh không mở được hoặc cạnh ngắn < 250px thì không dùng được, không có gì để sửa. |
| `DUP_IMAGE_EXACT` · `DUP_IMAGE_NEAR` | 8 · 4 ảnh | máy (loại ở cửa vào) | Giữ 1 bản, bỏ bản trùng để không thổi phồng dữ liệu. NEAR dùng `phash_dist = 12` (mục 3). |
| `LEAK_TEST` | 5 ảnh | máy (loại ở cửa vào) | Trùng ảnh kho test: giữ lại sẽ làm mAP test bị đẩy lên giả. |
| `BAD_FORMAT` · `BAD_CLASS_ID` · `BOX_ZERO` · `DUP_BOX` | 3 · 6 · 4 · 7 dòng | máy (`drop_line`, 20 dòng) | Dòng hỏng không có cách đoán lại giá trị đúng, xoá dòng là an toàn. Ảnh có dòng bị xoá được cộng điểm ưu tiên vào hàng đợi (`FIXED_DROP_LINE`) để người kiểm lại. |
| `BOX_OUT_OF_IMAGE` | 8 dòng | máy (`clip_box`, 8 dòng) | Phần tràn ra ngoài ảnh chắc chắn sai; cắt về biên ảnh, giữ phần trong ảnh. |
| `BAD_CLASS_NAME` | 2 tên trong `data.yaml` | máy (`rename_classes`) | `Person` / `Bus` chỉ sai chữ hoa, đổi về `person` / `bus` theo `configs`. |
| `MISSING_LABEL_FILE` | 6 ảnh | người (`needs_label`) | Máy không được bịa nhãn; ảnh vào đầu hàng đợi (trọng số 10). |
| `POSSIBLE_MISSING` | 53 dòng / 52 ảnh | người | Model lớn thấy vật mà nhãn không có; có thể model sai (precision trên calib 0.57). |
| `POSSIBLE_WRONG_CLASS` | 18 dòng / 18 ảnh | người | Đổi lớp tự động nguy hiểm vì model cũng nhầm car / truck / bus. |
| `POSSIBLE_LOOSE_BOX` | 28 dòng / 24 ảnh | người | Không biết box đúng nằm đâu, chỉ người vẽ lại được. |
| `POSSIBLE_FALSE_POS` | 29 dòng / 27 ảnh | người | Box nhãn không khớp vật nào model thấy; precision thấp (0.31 trên calib), không dám xoá tự động. |
| `EMPTY_LABEL` · `BOX_TINY` · `BOX_HUGE` | 12 ảnh · 6 dòng / 4 ảnh · 3 dòng | người (cảnh báo nhẹ) | Ảnh nền hay thiếu nhãn? Vật quá nhỏ / quá to? Cần mắt người; trọng số thấp (1 / 0.3 / 0.5). |
| `CLASS_RARE` | 4 dòng (`<dataset>`) | máy (gián tiếp) | Là lớp −1, 4, 7, 93: hệ quả của `BAD_CLASS_ID`, hết sau `drop_line`. |

(Số lấy từ `02_error_list_v1`, mẫu số 202 ảnh sau cửa vào; 5 dòng mã ở cửa vào được liệt kê lại cho đủ. `03_fixes.csv` có 35 thay đổi: 20 `drop_line` + 8 `clip_box` + 6 `needs_label` + 1 `rename_classes`. Sau sửa tự động, `04_error_list_v2` còn đúng 6 lỗi bắt buộc, đều là `MISSING_LABEL_FILE`.)

**Thứ tự hàng đợi:** điểm ưu tiên = tổng trọng số của các cảnh báo × (1 + conf của model), cộng thêm điểm cho ảnh đã bị máy sửa (`FIXED_DROP_LINE` 2, `FIXED_CLIP_BOX` 1) và 10 điểm cho ảnh chưa có nhãn. Vì vậy đầu hàng là img_0020 (11.52: vừa bị xoá dòng `BAD_CLASS_ID`, vừa có MISSING và WRONG_CLASS với conf cao), tiếp theo là 6 ảnh `NEEDS_LABEL` (10.0), rồi tới các ảnh có WRONG_CLASS (trọng số 3) hoặc MISSING (2) với conf cao. **Với ngân sách 80 ảnh** (cắt ở điểm 3.343), người xem được **74/103 ảnh** có cảnh báo ngữ nghĩa, tức **94/123 dòng** (76%): 51/53 MISSING, 18/18 WRONG_CLASS, 13/24 FALSE_POS, 12/28 LOOSE_BOX (mẫu số theo `04_error_list_v2`). LOOSE_BOX bị bỏ lại nhiều nhất vì trọng số thấp nhất (1.5).

## 3. Calibration (2 ngưỡng)

| Tham số | Khởi đầu | Đã chọn | Precision / Recall (trước → sau, trên calib) | Lý do (đánh đổi) |
| --- | --- | --- | --- | --- |
| `duplicates.phash_dist` | 2 | **12** | DUP_IMAGE_NEAR: 1.00 / 0.50 → 1.00 / 0.67 (EXACT giữ 1.00 / 1.00) | Ngưỡng này **tự xoá ảnh**, nên ưu tiên precision. Từ 4 đến 14 cho kết quả như nhau trên calib; trên raw, 12 bắt thêm 2 cặp trùng thật (img_0223/img_0077 dist 6, chỉ khác màu; img_0186/img_0061 dist 10, cắt nhẹ), số ảnh loại ở intake tăng từ 19 lên 22. Không chọn 16 dù F1 trên calib cao nhất (0.91), lý do ở dưới. |
| `second_opinion.conf` | 0.25 | **0.6** | MISSING: 0.50 / 1.00 → 0.57 / 1.00 · WRONG_CLASS: 0.56 / 0.83 → 0.62 / 0.83 · LOOSE_BOX: 0.29 / 0.40 → 0.20 / 0.20 | Đây là cảnh báo cho người nên ưu tiên recall. 0.6 là mức conf cao nhất còn giữ recall MISSING bằng 1.00, và tốt hơn hẳn 0.5. Lên 0.8 thì ra Release (7.9% ảnh còn cảnh báo) nhưng recall MISSING giảm còn 0.75 và cờ MISSING trên raw giảm từ 53 xuống 32. Đó là Release giả, vì hàng đợi nhỏ đi là do checker mù hơn. Chấp nhận **Hold** (18.8%), vì hàng đợi 125 ảnh vượt ngân sách duyệt 80 ảnh. Đánh đổi: LOOSE_BOX recall giảm (0.40 → 0.20). |

**Chỗ calibration đánh lừa:** trên calib, `phash_dist = 16` có precision 1.00 và F1 của DUP_IMAGE_NEAR cao nhất (0.91), nên nhìn bảng thì 16 trông tốt nhất. Chạy trên raw, số ảnh bị loại ở intake tăng từ 22 lên 31. Mở xem 3 cặp mới ở dist 16 thì có **2 cặp là ảnh khác hẳn nhau**: img_0011 (tennis) với img_0008 (trượt tuyết), img_0177 (lướt sóng) với img_0113 (người ngồi bàn); thêm 6 ảnh bị gắn LEAK_TEST. Calib chỉ có 39 ảnh nên không có cặp ảnh khác nhau nào có khoảng cách ≤ 16, vì vậy precision 1.00 trên calib không đại diện cho raw khoảng 224 ảnh. Tương tự, WRONG_CLASS đạt precision 1.00 ở conf 0.8 trên calib, nhưng lỗi chèn trong calib chủ yếu là person→car, còn raw hay nhầm giữa car, truck và bus.

## 4. Cửa chặn và điều pipeline KHÔNG bắt được

**(a) Gate chặn đúng.** Chạy `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`: vẫn nhận 202/224 ảnh, sửa tự động 35 thay đổi, nhưng không có người gán nên 6 ảnh thiếu file nhãn còn nguyên. Kết luận **REWORK** ("còn 6 lỗi bắt buộc (MISSING_LABEL_FILE: 6)"), **mã thoát 20**, log in "KHÔNG xuất: còn lỗi bắt buộc (Rework)", và thư mục `work/exp_nb` **không được tạo**. So với lần chạy chính (ngân sách 80): người gán đủ 6 ảnh đó nên lỗi bắt buộc về 0, kết luận chuyển sang Hold.

**(b) Điểm mù (bằng chứng trên calib, nơi biết đáp án):**

1. **Box lỏng vừa phải gần như không bị bắt.** 5 box chèn lỏng (phóng to ×1.45–1.58) thì `POSSIBLE_LOOSE_BOX` chỉ bắt 1 (calib_023, IoU 0.42), recall 0.20. Với calib_002, 006, 012, box lỏng có IoU với dự đoán của model < 0.5, nên bị báo nhầm thành `POSSIBLE_FALSE_POS` (vẫn tới tay người nhưng sai lý do). Riêng **calib_024 không có cảnh báo nào**, lọt hẳn. Trên raw, LOOSE_BOX lại có trọng số thấp nhất nên chỉ 12/28 dòng được duyệt.
2. **Nhầm lớp mà model lớn cũng nhầm.** Lỗi chèn truck→bus ở **calib_009** không có cảnh báo `POSSIBLE_*` nào: yolo26l cũng nhìn chiếc xe đó là bus nên "xác nhận" nhãn sai. Đây là 1 FN duy nhất của WRONG_CLASS (5/6). Cả 5 ca bắt được đều là person→car, cặp lớp dễ phân biệt.
3. **Ảnh trùng biến đổi mạnh.** Ở `phash_dist = 12`, 2/6 ảnh trùng gần đúng bị lọt: calib_037 (mức biến đổi 3, phash 16) và calib_038 (mức 4, phash 18). Muốn bắt thì phải nâng ngưỡng lên ≥ 16 hoặc 18, nhưng ở 16 trên raw đã gộp nhầm ảnh khác nhau (mục 3). Một ngưỡng phash không tách được hai trường hợp này.

## 5. Train: raw vs clean (tùy chọn, chấm riêng)

**Chưa chạy.** Phần train làm trên Colab (T4, yolo26n, 20 epoch × 2 seed × 2 biến thể, khoảng 20 phút) sau khi push `submission/export` lên repo public. Trong buổi này mới hoàn thành phần lõi (pipeline QC, calibration, gate), chưa có `submission/results/` nên không có số mAP để so sánh.

## 6. Quyết định và ghi chú AI

**(a) Quyết định cuối: Hold.** Không còn lỗi bắt buộc nào, nhưng 38/202 ảnh (18.81%) còn cảnh báo chưa được người duyệt, vượt ngưỡng 10%. Dataset `clean_v1` chỉ là bản nháp để thử nghiệm. Để chuyển sang **Release**: tỉ lệ đó phải < 10%, tức còn **≤ 20 ảnh** chưa duyệt, nên cần người duyệt thêm **ít nhất 18 ảnh** nữa theo thứ tự `05_review_queue.csv` (ước tính bằng phép tính; pipeline giới hạn `--budget` tối đa 80 nên không chạy thử được), hoặc tăng ngân sách duyệt của dự án lên khoảng 98 ảnh. **Không** đạt Release bằng cách nâng `second_opinion.conf` lên 0.8: cách đó chỉ làm checker mù hơn (mục 3).

**(b) Ghi chú AI** (có dùng AI viết 4 module ở Bước 2):

- **Prompt chính:** dán docstring kèm file test của từng module (`label_format`, `gate`, `autofix`, `second_opinion`), yêu cầu viết đúng đặc tả, không sửa test.
- **Cách kiểm:** chạy `pytest tests/test_<tên>.py -q` cho từng file rồi cả bộ (79/79 xanh); chạy `python -m pipeline.run` trên dữ liệu thật; tự thử thêm 3 ca biên: một dòng dính 2 lỗi (tràn + lặp → chỉ 1 `drop_line`), file có dòng trống ở giữa (số dòng gốc giữ đúng), một ảnh nhiều dự đoán (ra đúng MISSING / WRONG_CLASS / FALSE_POS dòng 3).
- **Một lần AI sai:** trong test ca biên "ảnh nhiều dự đoán", AI viết `assert got == [...] or got`, tức là test không bao giờ fail khi `got` khác rỗng. Mình phát hiện khi đọc lại code: kết quả đúng là nhờ in ra và tự so bằng mắt, không phải nhờ assert. Bài học: test xanh chưa chắc đúng, phải đọc cả điều kiện assert.
