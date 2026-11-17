# M1/M3 — Trace case và regression test

**Case chủ đạo:** `seeded_regression / C-002@11`, đối chứng `fixed / C-002@11`.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11
python -m pytest -q -m student -o addopts= tests/test_lab9_integration_regression.py
```

| Trường | Bằng chứng và cách đối chiếu |
|---|---|
| Expected | C-002 trong public matrix: `status=denied`, `proposal_amount=0`, `refund_vnd=0` |
| Injection | Ticket khai 5 ngày trễ, khác DB. `seeded_regression` kích hoạt công tắc `ticket_trust` |
| Bước sai đầu tiên | **Event số 3 `model_override`** thay `delay_days` của DB bằng số từ ticket; thứ tự đã được replay và ghi trong [trace_evidence.md](trace_evidence.md) |
| Vì sao là bước đầu | Các event `handoff` và `investigator` phía trước chỉ đọc và hiển thị dữ kiện; `model_override` là lúc dữ kiện DB bị ghi đè trong trạng thái reasoning |
| Grader bắt lỗi | `DbFactKept=False`; `TrialPass` và/hoặc `RefundAmountCorrect` bắt sai outcomes tiếp theo |
| Đối chứng | `fixed` kích hoạt `no_override`, không có event `model_override` khi dữ kiện ticket khác DB |
| Regression test | `tests/test_lab9_integration_regression.py::test_ticket_override_detected` chạy hai shape và đối chiếu grader |
| Bằng chứng chạy thật | [trace_evidence.md](trace_evidence.md) ghi event index, ledger, status và graders của 12 replay/control; các report tổng hợp có run ID trong eval_results.md |

**Bổ sung FM-08:** `tests/test_lab9_integration_regression.py::test_reply_amount_matches_committed_ledger`. Tạo một shape bằng `make_shape(..., {"no_override", "misreport"})` *chỉ trong test*; C-008 có proposal 35.000đ nhưng ledger cho phép 20.000đ. Grader mới phải báo sai ở variant và pass trên `fixed`.

## FM-05: proposal sai khi ledger không đổi

`tests/test_lab9_proposal_regression.py` replay C-013 trên đủ 5 seed, đối chiếu seeded_regression với fixed. Ledger vẫn bằng 0 ở cả hai; pre_deducted đổi proposal từ nhãn nguồn 35.000 xuống 0. ProposalAmountCorrect bắt sai invariant này mà không dùng outcome pass_rate để tự giải thích lỗi. Trước sửa: 5 fail; sau sửa: 5 pass.
