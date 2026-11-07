"""memory.privacy.redact_pii 的单测（脱敏语义 + 正则边界 + 计数）。

安全语义断言要点：
- 命中的 PII 必须被替换为占位符，且**占位符内不得残留原数字**；
- 更长的数字串**不应**误命中（lookaround 防回归）；
- 空串与无 PII 文本返回原样且 hits == 0。
"""

from __future__ import annotations

from memory.privacy import redact_pii

REDACTED = {
    "phone": "[手机已脱敏]",
    "id": "[身份证已脱敏]",
    "email": "[邮箱已脱敏]",
}


def test_redacts_contiguous_phone() -> None:
    out, hits = redact_pii("老师我的手机是15812345678谢谢")
    assert out == f"老师我的手机是{REDACTED['phone']}谢谢"
    assert hits == 1


def test_redacts_separated_phone_with_space_and_dash() -> None:
    for raw in ("158 1234 5678", "158-1234-5678"):
        out, hits = redact_pii(f"号码{raw}备用")
        assert out == f"号码{REDACTED['phone']}备用", raw
        assert hits == 1, raw


def test_phone_inside_longer_digit_run_not_matched() -> None:
    # 11 位手机号被更长数字串包住时，lookaround 必须把它压掉（旧行为回归护栏）
    long_run = "1" + "15812345678" + "9"  # 13 位连续数字，中间含手机号形
    out, hits = redact_pii(f"编号{long_run}结尾")
    assert hits == 0, f"误命中：{out}"

def test_redacts_id_card_with_x_suffix() -> None:
    for id_card in ("11010119900307457X", "11010119900307457x", "110101199003074577"):
        out, hits = redact_pii(f"身份证号{id_card}已登记")
        assert out == f"身份证号{REDACTED['id']}已登记", id_card
        assert hits == 1, id_card


def test_redacts_email() -> None:
    out, hits = redact_pii("发邮件到a.b-test@example.com.cn收")
    assert out == f"发邮件到{REDACTED['email']}收"
    assert hits == 1


def test_redacts_multiple_pii_and_counts_hits() -> None:
    raw = "手机15812345678，邮箱x@y.com，身份证11010119900307457X"
    out, hits = redact_pii(raw)
    assert hits == 3
    assert "15812345678" not in out
    assert "x@y.com" not in out
    assert "11010119900307457X" not in out


def test_empty_text_returns_empty_with_zero_hits() -> None:
    assert redact_pii("") == ("", 0)


def test_clean_text_unchanged_with_zero_hits() -> None:
    raw = "avl树的旋转有四种情况，分别是LL、RR、LR、RL。"
    out, hits = redact_pii(raw)
    assert out == raw
    assert hits == 0
