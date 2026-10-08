"""四态判据与复合语义（EVIDENCE_CHAIN.md §1.3/§1.6）。"""

from __future__ import annotations

from typing import Literal

Verdict = Literal["pass", "fail", "not_applicable", "missing_premise"]
PREDICATE_VERDICTS: tuple[Verdict, ...] = ("pass", "fail", "not_applicable", "missing_premise")
_MEASURED: frozenset[Verdict] = frozenset({"pass", "fail"})


def to_record_value(verdict: Verdict) -> bool | None:
    """落盘仍是三态布尔；`item_reasons` 另存原因。二者合起来才无损（§1.3 四态）。"""
    return {"pass": True, "fail": False}.get(verdict)


def from_record_value(value: object, reason: str) -> Verdict:
    """从归档还原四态：True/False 直接映射，None 时**必须**看 reason。

    ★ reason 缺失或非法 ⇒ 按 `missing_premise` 处理（保守侧）：老归档的 `None` 无法证明
      当时是「不适用」还是「测不到」，而把它当「不适用」正是 §4.2 事故的形状。
    """
    if value is True:
        return "pass"
    if value is False:
        return "fail"
    return "not_applicable" if reason == "not_applicable" else "missing_premise"


def composite(
    verdicts: dict[str, Verdict],
    *,
    optional: frozenset[str] = frozenset(),
) -> Verdict:
    """合取复合。`optional`（契约不要求的项）连 missing_premise 都不毒化。

    ★ 规则表见 §1.6：fail 优先 → 再 missing_premise → 有一个 pass 即 pass →
      什么都没测成 ⇒ missing_premise。`not_applicable` 有权缺席。
    """
    judged = {k: v for k, v in verdicts.items() if k not in optional}
    if not judged:
        return "not_applicable"
    if "fail" in judged.values():
        return "fail"
    if "missing_premise" in judged.values():
        return "missing_premise"
    return "pass" if "pass" in judged.values() else "not_applicable"


def rate(verdicts: list[Verdict]) -> dict[str, object]:
    measured = [v for v in verdicts if v in _MEASURED]
    return {
        "rate": (sum(1 for v in measured if v == "pass") / len(measured)) if measured else None,
        "n": len(measured),
        "n_a_missing_premise": sum(1 for v in verdicts if v == "missing_premise"),
        "n_a_not_applicable": sum(1 for v in verdicts if v == "not_applicable"),
    }


def is_reply_part(address: str) -> bool:
    """`reply#stem` 这类地址指向 reply 文本内部的语义片段。

    ★ 它**不是** record 的键，所以 V0 的键存在性检查必须跳过它 —— 它由 Task 5 的
      R1-A 覆盖检查负责。两边共用这一套地址语法，但各管各的那一类。
    """
    return address.startswith("reply#")


def has_path(rec: object, dotted: str) -> bool:
    """点分路径的**键存在性**检查。

    `top_items[].kp` = `rec["top_items"]` 是**列表**，逐元素须含 `kp`，任一可达即算存在。
    ★ 实测修正（Task 3 标定）：原稿把 `x[]` 当「属性 x 已在上一层取到」处理，
      导致 `x[]` 出现在**首段**时（rec 本身是 dict）恒返回 False ——
      而 `top_items[].kp` 恰恰就是首段形式，V0 会对它永远报缺键。
    """
    parts = dotted.split(".")
    cur = rec
    for i, part in enumerate(parts):
        if part.endswith("[]"):
            name = part[:-2]
            if not isinstance(cur, dict) or name not in cur:
                return False
            items = cur[name]
            if not isinstance(items, list):
                return False
            tail = ".".join(parts[i + 1 :])
            if not tail:
                return bool(items)
            return any(has_path(item, tail) for item in items)
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


def drop_path(rec: dict, dotted: str) -> None:
    """按点分路径删键（falsify 的 `drop_path` op 用）。路径不存在时静默返回。

    列表段（`x[]`）⇒ 对**每个**元素删除剩余路径的键（取证要的是「该证据在整条列表上缺席」）。
    ★ 实测修正（Task 3 fix round 1）：brief 稿在循环里把**末段**也走下去再对末值 pop，
      导致叶子键永远删不掉（demo 断言 7 失败）；这里改为只走前 n-1 段、对**父 dict** pop 末段。
    """
    parts = dotted.split(".")
    cur = rec
    for i, part in enumerate(parts[:-1]):
        if part.endswith("[]"):
            name = part[:-2]
            if not isinstance(cur, dict) or name not in cur:
                return
            items = cur[name]
            tail = ".".join(parts[i + 1 :])
            if isinstance(items, list):
                for item in items:
                    if tail:
                        drop_path(item, tail)
                    elif isinstance(item, dict):
                        item.pop(name, None)
            return
        if not isinstance(cur, dict) or part not in cur:
            return
        cur = cur[part]
    last = parts[-1]
    name = last[:-2] if last.endswith("[]") else last
    if isinstance(cur, dict):
        cur.pop(name, None)
