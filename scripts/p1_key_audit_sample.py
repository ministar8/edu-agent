"""P−1 冻结前置：答案键可靠性抽查的**抽样器**（只读语料，零 LLM，零 OCR 结果读取）。

设计参数由项目所有者在 checkpoint（P−1 裁定二）冻结，**写在代码里而不是散在文档里**，
这样「预先固定随机种子/抽样单位/分层配额」可被机器复核：

  - 总体：有答案键的题（`answer_key` 为单个 A–H）；**缺键题不入分母**，单独登记。
  - 目标：零接受属性抽样 —— 若真实错键率 ≥ 5%，以 ≥95% 概率至少发现一个错键 ⇒ n = ceil(ln .05/ln .95) = 59。
  - 分层：来源文件（= 考试年份）。四个低覆盖批次 2009/2010/2013/2016 **每层至少 5 道（硬配额）**；
    其余 39 道按各层有键题数占比分配，余数按最大余数法补齐（确定性、可重跑）。
  - 抽样单位：`(question_id, answer_key)` 原子 —— 错键登记、扩查触发、审计轨迹都绑这个原子。
  - ★ **清单里故意不写源键的值**：核验者必须先独立读原始扫描页写下键、再与 `items.md` 比对；
    把源键印在清单上等于用同一份 OCR 派生文本给核验者定锚，正是规程禁止的自我验证路径。
  - ★ 本脚本**不读**任何 OCR 判定结果，也**不写** gold —— 它只产生「该查哪 59 个原子」的冻结清单。
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import random
import re
import sys
from pathlib import Path

Q_RE = re.compile(r"^## (\d{4}-Q\d+)\s*$", re.M)
KEY_RE = re.compile(r"^>\s*answer_key:\s*(.*)$", re.M)
ITEMS_DIR = Path("knowledge/exams")

N_TOTAL = 59
TARGET_ERROR_RATE = 0.05
CONFIDENCE = 0.95
FORCED_STRATA = ("2009", "2010", "2013", "2016")
FORCED_EACH = 5
SEED = 20261009  # 冻结的种子：任何改种子都等于换一次抽样，必须在裁定里写明


def _design_n() -> int:
    """由 (置信度, 目标可发现错键率) 现推 n，并校验硬编码值 —— 防「改了 p/c 而 n 还是老数」。"""
    derived = math.ceil(math.log(1 - CONFIDENCE) / math.log(1 - TARGET_ERROR_RATE))
    if derived != N_TOTAL:
        raise SystemExit(f"设计参数与样本量不一致：公式给 n={derived}，代码写死 N_TOTAL={N_TOTAL}")
    return N_TOTAL


def keyed_atoms() -> dict[str, list[str]]:
    by_year: dict[str, list[str]] = collections.defaultdict(list)
    for f in sorted(ITEMS_DIR.rglob("items.md")):
        txt = f.read_text(encoding="utf-8", errors="replace")
        spans = [(m.group(1), m.start(), m.end()) for m in Q_RE.finditer(txt)]
        for i, (qid, _st, en) in enumerate(spans):
            nxt = spans[i + 1][1] if i + 1 < len(spans) else len(txt)
            m = KEY_RE.search(txt[en:nxt].split("**题干**")[0])
            ak = m.group(1).strip() if m else ""
            if re.fullmatch(r"[A-H]", ak):
                by_year[f.parent.name].append(qid)
    return {y: sorted(v) for y, v in sorted(by_year.items())}


def allocate(keyed: dict[str, list[str]]) -> tuple[dict[str, int], list[str]]:
    notes: list[str] = []
    alloc: dict[str, int] = {}
    remaining = N_TOTAL
    for y in FORCED_STRATA:
        avail = len(keyed.get(y, []))
        if avail < FORCED_EACH:
            notes.append(
                f"{y}: 有键仅 {avail} < 配额 {FORCED_EACH} ⇒ 记录为「层内不足」，缺口不挪用"
            )
            alloc[y] = avail
            remaining -= avail
        else:
            alloc[y] = FORCED_EACH
            remaining -= FORCED_EACH
    rest = {y: len(v) for y, v in keyed.items() if y not in FORCED_STRATA}
    total_rest = sum(rest.values())
    base = {y: remaining * n // total_rest for y, n in rest.items()}
    leftover = remaining - sum(base.values())
    for y in sorted(rest, key=lambda k: (-(remaining * rest[k] % total_rest), k)):
        if leftover <= 0:
            break
        base[y] += 1
        leftover -= 1
    for y, n in sorted(base.items()):
        if n > rest[y]:
            notes.append(f"{y}: 配额 {n} 超过有键 {rest[y]} ⇒ 截断，差额重分配未实现（须人工复核）")
            n = rest[y]
        alloc[y] = n
    return alloc, notes


def draw(keyed: dict[str, list[str]], alloc: dict[str, int], seed: int) -> list[dict[str, str]]:
    rng = random.Random(seed)
    rows: list[dict[str, str]] = []
    for y in sorted(keyed):
        pool = list(keyed[y])
        rng.shuffle(pool)
        for qid in pool[: alloc.get(y, 0)]:
            # 不写 answer_key 值（防定锚）；原子身份由 question_id 承担，比对时再从 items.md 取源键
            rows.append(
                {"year": y, "question_id": qid, "verifier_reading": "", "verdict": "pending"}
            )
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="evals/claims/p1_key_audit_sample.json")
    ap.add_argument("--check", action="store_true", help="只核对已冻结清单与本脚本重算是否一致")
    args = ap.parse_args(argv)

    _design_n()
    keyed = keyed_atoms()
    alloc, notes = allocate(keyed)
    rows = draw(keyed, alloc, SEED)
    payload = {
        "design": {
            "population_keyed_items": sum(len(v) for v in keyed.values()),
            "n_target": N_TOTAL,
            "method": "zero-acceptance attribute sampling",
            "detect_error_rate_at_least": TARGET_ERROR_RATE,
            "confidence": CONFIDENCE,
            "formula": "n = ceil(ln(1-c)/ln(1-p))",
            "seed": SEED,
            "unit": "(question_id, answer_key) 原子；清单内不预填源键值以免给核验者定锚",
            "strata": "来源文件 = 考试年份",
            "forced_quotas": {y: FORCED_EACH for y in FORCED_STRATA},
            "excluded_from_denominator": "缺答案键的题（单独登记，不入错键率分母）",
            "shortfall_notes": notes,
        },
        "allocation": alloc,
        "sample": rows,
    }
    path = Path(args.out)
    if args.check:
        old = json.loads(path.read_text(encoding="utf-8"))
        same = [r["question_id"] for r in old.get("sample", [])] == [r["question_id"] for r in rows]
        print(
            "PASS 冻结清单与本脚本重算一致"
            if same
            else "FAIL 清单与重算不一致（种子或规则被改过？）"
        )
        return 0 if same else 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已写入 {path}：{len(rows)} 个原子，分层 {alloc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
