"""Verify / Memory 的行为层判据（从 metrics.py 拆出，行为等价）。"""

from __future__ import annotations

import re
from typing import Any

from evaluation.task_eval._metrics_common import _as_difficulty, _norm  # noqa: F401

# ── Verify 的行为层判据（D14，2026-10-08 机械化）────────────────────────
#
# 为什么必须有：`EFFECT_PLAN §3.1` 给 Verify 冻结的头号指标 `question_id_recall@k`
# **在当前语料上不可计算**（#20：ingest 时没把 `question_id` 写进 metadata，D7 已裁决走披露），
# 而 §6 的占位门槛「≥80% `final_quality≥4`」在 verify 上是**指标效度错**：
# 实测 0B 与 Phase 1 都是 **0/15**，因为未达成的 case 全是 `exam_hit=False`
# （检索层没给真题证据），而那种情况下 agent **诚实说明"无法确认"是正确行为**
# ⇒ `final_quality` 在这里测的是**检索覆盖**，不是回答质量。
# ⇒ Verify 这一行改由下面两个可机械复现的断言把门（`fabricated` 是硬条件）。
#
# ★ 与历史人工读数的关系（必须一起披露，别装作一致）：`PHASE1_VERIFY.md` 记的
#   「仍出题 6/15→0/15」被 `verify_fabricated` **逐条复现**（case_id 完全相同）；
#   但「有真题信息 3/15→9/15」是**混级计数**（给出题干/题号 与 只列了年份来源文件
#   被数在一起），且人工件没留 case_id ⇒ 无法逐条对账。本判据改为**分两级**：
#   `exam_item_cited`（给出可核对的真题条目）与 `exam_year_only`（只报年份来源）。

_V_YEAR_RE = re.compile(r"(?:19|20)\d{2}\s*年")
_V_ITEM_RE = re.compile(r"第\s*\d+\s*题|\bQ\d{1,3}\b")
_V_EXAM_WORD_RE = re.compile(r"真题")
_V_TOPIC_RE = re.compile(r"考点|考查|涉及|归纳|变式|题型")
# 自我否定句：年份只是「来源文件 / 被列出的等年份」，**不算**给出真题条目。
# ★ 少了这层过滤，「未包含任何真题的年份、题号」这种句子会反过来制造假命中。
_V_DENIAL_RE = re.compile(
    r"仅作为|来源文件|来源列表|来源[:：]|等年份|未检索到|无法确认|并未给出|未给出"
)
_V_STEM_RE = re.compile(r"题干[：:]")
_V_ANSWER_KEY_RE = re.compile(r"(标准答案|参考答案)[：:]")
_V_GEN_ITEM_RE = re.compile(r"(\*\*题目\s*1\*\*|练习题|模拟题)")
# 表格式清单：`| 2021 | Q14 | 题干… |` —— 年份那一格**没有"年"字**，所以年份正则盖不到，
# 必须单独认（实测归档里 `ver-006` 就是这种形态，漏了它 L1 会假阴）。
_V_TABLE_ROW_RE = re.compile(r"^\|\s*(?:19|20)\d{2}\s*\|\s*Q?\d{1,3}\s*\|")


def verify_fabricated(reply: str) -> bool:
    """**仍出题**：在「问历年真题」的意图下生成了新练习题（题干 + 答案键 + 出题标题三者同现）。

    这是 §6 Verify 行的**硬条件**（必须为 0）—— 它测的正是 Verify 存在的意义：
    用户要历史真题时不得编新题。实测 0B 命中 6/15、Phase 1 命中 **0/15**，case_id 与
    `PHASE1_VERIFY.md` 的人工记录逐条一致。
    """
    text = str(reply or "")
    return bool(
        _V_STEM_RE.search(text) and _V_ANSWER_KEY_RE.search(text) and _V_GEN_ITEM_RE.search(text)
    )


def verify_exam_item_cited(reply: str) -> bool:
    """**L1**：给出可核对的真题条目 —— 同一行里既有年份、又有题号或题目描述。

    两种真实形态都要认（都是从归档里长出来的，不是设想）：
    散文式 `- 2010 年 第 33 题：…`、表格式 `| 2021 | Q14 | …`。
    ★ 判定是**逐行**的：跨行拼出来的"年份 + 题号"不算（否则整篇回复里随便两处凑成命中）。
    """
    for ln in str(reply or "").splitlines():
        s = ln.strip()
        if _V_TABLE_ROW_RE.match(s):
            return True
        if not s or not _V_YEAR_RE.search(s):
            continue
        if _V_ITEM_RE.search(s):
            return True
        if _V_EXAM_WORD_RE.search(s) and not _V_DENIAL_RE.search(s) and len(s) >= 25:
            return True
    return False


def verify_exam_year_only(reply: str) -> bool:
    """**L2**：只报出年份/来源文件与考点归属，没给到可核对的题目条目。

    与 L1 **互斥**（L1 成立就不算 L2）—— 否则一个回复同时命中两级，两个率就没法相加解读。
    L2 高、L1 低 的含义是"说得出发过什么方向、但给不出具体题" ⇒ 属检索覆盖不足，
    不是回答质量问题（这正是 #20 的那条链）。
    """
    if verify_exam_item_cited(reply):
        return False
    for ln in str(reply or "").splitlines():
        s = ln.strip()
        if _V_YEAR_RE.search(s) and (_V_TOPIC_RE.search(s) or _V_DENIAL_RE.search(s)):
            return True
    return False


# ── Memory 的可测性 / 配对对照（D15，2026-10-08）───────────────────────
#
# 为什么 §6 的 Memory 行**不写百分数门槛**：
#   * 0B 那批的 `gold` 里根本没有 `expected_memory` ⇒ 四率**全 N/A**（#9），
#     所以「≥80% correct-use」**无法按 Phase 0 回填** —— 回填不出一个当时没测的量。
#   * 新口径下可测正样本只有 **n=1**（§20.8.6）。n=1 上任何百分数都没有统计意义，
#     答辩被问「你这个 100% 是几条？」就崩（与 §9「硬上统计指标」的禁令同向）。
#   ⇒ 改为**三条结构断言**：① 配对成立（`paired_control_verdict`）
#     ② 每条被计入的正样本可追溯（`memory_traceable`）③ 报「可测率」作为披露量。


def memory_traceable(rec: dict[str, Any]) -> bool:
    """**断言 2**：这条 Memory record 的结论是不是**有证据支撑**的。

    要求四样都在：逐轮日志（能指出"哪一轮没调工具"）、记忆卡捕获通道、
    episodes 字段（OFF 臂**可以**是空列表，但字段必须在 ⇒ 区分「没写」与「没读」）、
    `store_enabled`（paired control 的自证）。
    ★ 不看 `memory_cards` 是否为空 —— 空卡是**合法结果**（负样本就该空）。
    """
    return bool(
        rec.get("turn_log")
        and "memory_cards" in rec
        and "episodes" in rec
        and isinstance(rec.get("store_enabled"), bool)
    )


def paired_control_verdict(
    on_records: list[dict[str, Any]], off_records: list[dict[str, Any]]
) -> dict[str, Any]:
    """**断言 1**：Store ON/OFF 是不是真的**只差 Store** 这一个变量。

    只统计「两臂都 `validity_valid is True` 的正样本」= **交集** ——
    一条臂前置条件没凑成的 case 不参与配对（否则结论会被 case 有效性污染，#5/#18 都是这类）。
    对交集里每条 case 要求：ON 侧实际召回为真、OFF 侧为假；
    并额外报 OFF 侧**出现记忆卡**的条数 —— 那正是 **#24** 的机械探测器
    （旧实现只置 `agent.store=None`、进程级 store 还活着 ⇒ OFF 侧照样有卡，
    当时的「OFF 0 卡」其实是 #22 造成的假象，两个缺陷互相掩盖）。
    """

    def positives(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for r in records:
            em = (r.get("gold") or {}).get("expected_memory") or {}
            if em.get("should_be_recalled") is not True:
                continue
            if r.get("validity_valid") is not True:
                continue
            out[str(r.get("case_id"))] = r
        return out

    on, off = positives(on_records), positives(off_records)
    common = sorted(set(on) & set(off))
    ok: list[str] = []
    bad: list[str] = []
    off_has_card: list[str] = []
    for cid in common:
        a, b = on[cid], off[cid]
        if bool(a.get("memory_recalled_actual")) and not bool(b.get("memory_recalled_actual")):
            ok.append(cid)
        else:
            bad.append(cid)
        if b.get("memory_cards"):
            off_has_card.append(cid)
    return {
        "n_pairs": len(common),
        "n_ok": len(ok),
        "failed": bad,
        "off_has_card": off_has_card,
        # ★ 通过条件：至少一对、且**一对都不许有反例**；OFF 侧出现卡一律判失败
        "passed": bool(common) and not bad and not off_has_card,
        "note": "只统计两臂都满足前置条件的正样本；OFF 侧有卡即失败（#24 探测器）",
    }
