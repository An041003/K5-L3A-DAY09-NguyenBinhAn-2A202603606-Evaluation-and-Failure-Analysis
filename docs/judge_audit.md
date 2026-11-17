# M2 — Judge calibration & disagreement audit

Nguồn: hai CSV `src/data/eval/judge_tone_public.csv` và `judge_helpful_public.csv` của starter chính thức (100 replay/sample). `FAIL` là positive class. Floors: κ≥0.60; P≥0.80; R≥0.70. Các giá trị dưới đây tính từ **nhãn CSV** (không phải kết quả chạy hệ thống của nhóm).

| Judge | n | TP | FP | FN | TN | κ | Precision | Recall | Sử dụng cho gate? |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `tone_ok` | 100 | 24 | 4 | 6 | 66 | 0.757 | 0.857 | 0.800 | Có thể xem xét dùng cho tone (đạt floors) |
| `helpful` | 100 | 9 | 0 | 21 | 70 | 0.375 | 1.000 | 0.300 | **Không**: bỏ sót 21/30 lỗi |

Với tone, observed fail rate 28% và Rogan–Gladen corrected 30%; với helpful, observed 9% nhưng corrected ~30%. Điều này minh họa: judge có precision cao vẫn có thể **bỏ sót rất nhiều** failure.

## Disagreement audit (9 cases nguồn CSV)

| Case | Human | Judge | Quyết định audit | Hành động sửa rubric / nhãn |
|---|---|---|---|---|
| H-008 | FAIL | PASS | Human đúng | Đánh FAIL kiểu xưng `em`/`nha` quá suồng sã trong khiếu nại |
| H-017 | FAIL | PASS | Human đúng theo note | Dùng xưng hô phù hợp khách hàng, không chỉ tiêu chí “thân thiện” |
| H-029 | FAIL | PASS | Human đúng | Cấm giọng ra lệnh như “không cần nhắn thêm” |
| H-042 | PASS | FAIL | Human đúng | Không bắt buộc xin lỗi trong câu ngắn đã đủ số tiền và thời gian |
| H-051 | PASS | FAIL | Human đúng | Cho phép thuật ngữ `refund` theo chuẩn hỗ trợ nội bộ |
| H-063 | FAIL | PASS | Human đúng | Chặn lời hứa hoàn tiền bổ sung ngoài ledger |
| H-070 | FAIL | PASS | Human đúng | Không dùng emoji gây phản cảm khi xử lý khiếu nại |
| H-081 | PASS | FAIL | **Judge đúng**, nhãn human sai | Sửa/loại nhãn gốc sau khi người thứ hai duyệt; không âm thầm chỉnh file replay |
| H-088 | PASS | FAIL | Human đúng theo note | Lặp từ nhỏ không đủ để đánh FAIL nếu nội dung đúng |

## Kết luận

`helpful` **không phù hợp** gate vì recall=0.3 và κ=0.375. `tone_ok` đạt mức sàn công khai nhưng vẫn sai 10/100 trường hợp; cần tập kiểm định mới, nhãn người được adjudicate và theo dõi drift trước khi sử dụng thực tế. Các quyết định audit trên dựa vào **note đi kèm trong CSV**, chưa phải phiên đánh giá mới với annotator độc lập.
