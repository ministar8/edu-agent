"""E-5 · 缺陷 E **效果探针**（配对对照：词表版 prompt vs 8 示例版 prompt）。

要回答的问题
------------
E-3 把 162 个 canonical 考点名注入了 `GRADE_PROMPT`。⑫ 组护栏只证明
「**注入生效且与 kp_index 同源**」，**不证明模型跟随**。本探针补上这一环：
批改产出的 `knowledge_points` 是否真的只用表里的规范名。

★ 为什么是配对而不是单臂
------------------------
单臂（只跑新 prompt）无法归因 —— 跟随率高时，分不清是「词表起的作用」
还是「这个模型本来就这么输出」。配对**只差一个变量**：

    臂 A = 现 `GRADE_PROMPT`（注入 162 词表）
    臂 B = 同一 prompt，只把词表块换成 `_knowledge_points_block({})`
           —— 该降级分支逐字等于 **E-3 之前**的 8 示例文案，故臂 B 就是修复前口径。

两臂题面、模型、温度、schema、超时全部相同 ⇒ 差值只归因到词表注入。

判据（测量，不判定）
--------------------
* `all_canonical`  : 该题产出的 KP **全部** ∈ canonical（题级）
* `follow_rate`    : canonical 词数 / 总产出词数（词级，跨题求和）
* `kp_normalized`  : `normalize_topics(raw)` —— **真正决定聚合结果**的值；
                     自造词归一后仍是自造词 ⇒ 各成 1-hit 桶、`MIN_HITS` 永不满足
* `expected_hit`   : 归一结果里是否含该题的期望 canonical KP（能否进对桶）

★ 这不是门禁：模型输出有随机性，做成硬门禁会偶发红灯（交接纪律 #5
「1 条 probe 的差异不要外推」）。故**只打印 + 落盘，退出码恒 0**。

用法::

    PYTHONPATH=src PYTHONIOENCODING=utf-8 uv run python scripts/memory_e5_probe.py
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from langchain_core.prompts import ChatPromptTemplate  # noqa: E402

from agents.temperature import TEMPERATURE_GRADING  # noqa: E402
from core import settings  # noqa: E402
from core.kp_vocab import canonical_names, prompt_names_by_subject  # noqa: E402
from evaluation.provenance import code_version  # noqa: E402
from memory.topics import normalize_topics  # noqa: E402
from prompts import GRADE_PROMPT, PROMPT_SET_VERSION  # noqa: E402
from prompts.service import _knowledge_points_block  # noqa: E402
from rag.llm_calls import call_structured  # noqa: E402
from schema.grading import GradingResult  # noqa: E402

# ★ 默认落盘路径**不许默默覆写既有证据**：E-5 跑过一次（prompt hash `f09c75642029`），
#   #8 剔根节点后 hash 变成 `2f485d2d7ef7` ⇒ 复测必须写到**新文件**，旧那份是「中间态」证据。
#   用 `E5_OUT=<路径>` 指定输出（Step 9 就是这么跑的）。
#   ★ `E5_OUT` 允许**相对仓库根**的路径：不 resolve 会在收尾的 `OUT.relative_to(ROOT)` 处抛
#     `ValueError`（实测踩过：12 次调用已跑完并已落盘，只是最后打印崩 ⇒ 退出码 1 但数据没丢）。
_out_env = os.environ.get("E5_OUT", "")
OUT = (
    Path(_out_env)
    if Path(_out_env).is_absolute()
    else (
        ROOT / _out_env
        if _out_env
        else ROOT / "evals" / "results" / "task_eval" / "phase1_e5_prompt_following.jsonl"
    )
)

# ★ 臂名是**归档里的键**，也是统计表的行名 ⇒ 只允许在这一处定义。
#   `162` 是首跑时的词表条数，#8 之后实际为 158；名字保持不动（旧归档要能对上），
#   真实条数由 `_system_vocab_size()` 在运行时打印并写进归档头部。
ARM_A = "A_vocab162"
ARM_B = "B_examples8"

# ── 6 道题：覆盖缺陷 E 的**真实肇事考点**（平衡二叉树 / 图 / 堆与排序）──────
#   题面取自 `evals/datasets/demo/memory_cases.jsonl` 的 Session A 提问，
#   与 E-3 前 `store.db` 取证（`图的基本性质` / `堆的定义` / `完全二叉树`）同源，
#   这样两臂结果可以和那份修复前证据直接对照。
#   ★ 标准答案若有出入，两臂受同样的影响 ⇒ 不影响配对的差值解释。
#   ★ gold 必须是 `expected_any`（**可接受的规范名集合**），不是单个词 ——
#     实测 kp_index 里 `排序`（章级）与 `快速排序`（具体算法）**是两个并存节点**，
#     而 **`堆` 根本不存在**、只有 `堆排序`。取单个词会把「合法但选了另一档粒度」
#     误判成未命中（2026-10-07 首跑即因此把「堆」「排序」写成 gold ⇒ 假阴性，
#     与首跑「AVL树」那次同类的 **gold 写错**，不是链路问题）。
CASES: list[dict] = [
    {
        "qid": "2012-Q4",
        "expected_any": {"平衡二叉树"},
        "stem": (
            "若平衡二叉树的高度为 6，且所有非叶结点的平衡因子均为 1，"
            "则该平衡二叉树的结点总数为 。\nA. 10\nB. 20\nC. 32\nD. 33"
        ),
        "standard_answer": "B. 20",
        "user_answer": "我选 D（33）",
    },
    {
        "qid": "2013-Q3",
        "expected_any": {"平衡二叉树"},
        "stem": (
            "若将关键字 1, 2, 3, 4, 5, 6, 7 依次插入到初始为空的平衡二叉树 T 中，"
            "则 T 中平衡因子为 0 的分支结点的个数是 。\nA. 0\nB. 1\nC. 2\nD. 3"
        ),
        "standard_answer": "D. 3",
        "user_answer": "我选 A（0）",
    },
    {
        "qid": "mem-002-T0",
        "expected_any": {"图", "图的存储", "图的遍历"},
        "stem": (
            "下列关于无向连通图特性的叙述中，正确的是 。\n"
            "I. 所有顶点的度之和为偶数\nII. 边数大于顶点个数减 1\nIII. 至少有一个顶点的度为 1"
        ),
        "standard_answer": "仅 I",
        "user_answer": "我选 III",
    },
    {
        "qid": "mem-002-T1",
        "expected_any": {"图的存储", "图"},
        "stem": "用邻接矩阵存储一个有 6 个顶点、10 条边的无向图，该矩阵中 1 的个数是多少？",
        "standard_answer": "20",
        "user_answer": "我答 10",
    },
    {
        "qid": "mem-003-T0",
        # ★ 小根堆判定：kp_index 无 `堆`，只有 `堆排序` ⇒ 可接受集只能取 `堆排序`。
        "expected_any": {"堆排序"},
        "stem": "对于下列关键字序列 5, 8, 12, 19, 28, 20, 15, 22，请判断它是否构成小根堆。",
        "standard_answer": "构成小根堆",
        "user_answer": "我认为构成",
    },
    {
        "qid": "mem-003-T1",
        "expected_any": {"快速排序", "排序"},
        "stem": "对序列 49, 38, 65, 97, 76 进行一趟快速排序，以 49 为枢轴，得到的结果是什么？",
        "standard_answer": "38, 49, 65, 97, 76",
        "user_answer": "我写成 38, 49, 65, 97, 76",
    },
]


def _system_text(prompt: ChatPromptTemplate) -> str:
    return prompt.messages[0].prompt.template


def _system_vocab_size(prompt: ChatPromptTemplate) -> int:
    """system 里「【章名】A、B、C」行的**去重词数**（即该臂实际注入了多少个候选词）。

    ★ 为什么抽成函数（2026-10-07 Step 9）：臂名沿用的是首跑时的条数 `A_vocab162`，
      而 #8 过滤课程根节点后实际只剩 **158** ⇒ 归档头行若把「162」写死，就成了
      **与实际注入不符**的自述。运行时条数必须以代码算出来的为准，故这里只有一处实现。
    """
    import re as _re

    text = _system_text(prompt)
    return len(
        {
            tok
            for line in _re.findall(r"【[^】]*】([^\n]+)", text)
            for tok in line.split("、")
            if tok
        }
    )


def _build_arms() -> dict[str, ChatPromptTemplate]:
    """臂 A = 真实 `GRADE_PROMPT`；臂 B = 只把词表块换成降级版。"""
    system_a = _system_text(GRADE_PROMPT)
    human_tpl = GRADE_PROMPT.messages[1].prompt.template
    block_a = _knowledge_points_block(prompt_names_by_subject())
    block_b = _knowledge_points_block({})

    # 臂 B 必须「逐字只换词表块」—— 块不在 system 里就说明接线或解析变了。
    if block_a not in system_a:
        raise SystemExit("词表块不在 GRADE_PROMPT 里，无法构造对照组（⑫a 应当也是红的）")
    if block_a == block_b:
        raise SystemExit("两臂词表块相同 ⇒ 配对失效（kp_index 未读到？）")

    arms = {
        # ★ 臂名里的 `162` 是**首跑时**的词表条数（#8 过滤课程根节点后实为 158）。
        #   刻意**不改名** —— 既有归档按臂名存取，改名会让 `--reanalyse` 读旧档时取不到统计。
        #   实际条数由 `_system_vocab_size()` 在运行时打印**并写进归档头部**，以那两处为准。
        ARM_A: GRADE_PROMPT,
        ARM_B: ChatPromptTemplate.from_messages(
            [("system", system_a.replace(block_a, block_b, 1)), ("human", human_tpl)]
        ),
    }

    for name, prompt in arms.items():
        text = _system_text(prompt)
        n_vocab = _system_vocab_size(prompt)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        print(f"  臂 {name}: system {len(text)} 字符 · 词表 {n_vocab} 个 · sha256[:12]={digest}")
    return arms


async def _grade(prompt: ChatPromptTemplate, case: dict) -> tuple[list[str], int | None]:
    """走产品同一调用路径（`call_structured` + `GradingResult` + 批改温度）。

    返回 `(原始 knowledge_points, score)`；`call_structured` 返回 None ⇒ `([], None)`，
    这本身就是要暴露的失败（缺陷 A 的残留症状）。
    """
    messages = prompt.format_messages(
        stem=case["stem"],
        standard_answer=case["standard_answer"],
        user_answer=case["user_answer"],
    )
    result = await call_structured(
        messages,
        GradingResult,
        temperature=TEMPERATURE_GRADING,
        timeout=settings.LLM_TIMEOUT,
        stage="grading",
    )
    if result is None:
        return [], None
    return list(result.knowledge_points or []), result.score


async def _measure(arm: str, prompt: ChatPromptTemplate, canonical: set[str]) -> list[dict]:
    records: list[dict] = []
    for case in CASES:
        raw, score = await _grade(prompt, case)
        norm = normalize_topics(raw)
        expected = case["expected_any"]
        non_canon = [n for n in raw if n not in canonical]
        rec = {
            "arm": arm,
            "qid": case["qid"],
            "expected_any": sorted(expected),
            "kp_raw": raw,
            "kp_normalized": norm,
            "all_canonical": bool(raw) and all(n in canonical for n in raw),
            "non_canonical": non_canon,
            "expected_hit_after_normalize": bool(set(norm) & expected),
            "score": score,
        }
        records.append(rec)
        flag = "✅" if rec["all_canonical"] else "❌"
        hit = "命中" if rec["expected_hit_after_normalize"] else "未命中"
        print(f"  {flag} [{arm}] {case['qid']}  raw={raw}")
        print(f"        normalize={norm} | 可接受集{sorted(expected)} {hit} | score={score}")
        await asyncio.sleep(0.3)  # 别把同一模型的连续请求挤在一起
    return records


def _arm_stats(rs: list[dict]) -> dict:
    total_words = sum(len(r["kp_raw"]) for r in rs)
    canon_words = sum(len(r["kp_raw"]) - len(r["non_canonical"]) for r in rs)
    return {
        "cases": len(rs),
        "empty_outputs": sum(1 for r in rs if not r["kp_raw"]),
        "all_canonical_cases": sum(1 for r in rs if r["all_canonical"]),
        "total_words": total_words,
        "canonical_words": canon_words,
        "follow_rate": (canon_words / total_words) if total_words else 0.0,
        "expected_hits": sum(1 for r in rs if r["expected_hit_after_normalize"]),
        "non_canonical_words": sorted({n for r in rs for n in r["non_canonical"]}),
    }


def _summarise(records: list[dict]) -> None:
    by_arm: dict[str, list[dict]] = {}
    for r in records:
        by_arm.setdefault(r["arm"], []).append(r)

    print()
    print("=" * 72)
    print("E-5 汇总（两臂同题、同模型、同温度，唯一差别是词表注入）")
    print("=" * 72)
    header = (
        f"{'臂':14s} {'all_canonical':>14s} {'词级跟随率':>14s} {'期望入桶':>10s} {'空产出':>7s}"
    )
    print(header)
    stats: dict[str, dict] = {}
    for arm, rs in by_arm.items():
        s = _arm_stats(rs)
        stats[arm] = s
        a = f"{s['all_canonical_cases']}/{s['cases']}"
        b = f"{s['canonical_words']}/{s['total_words']}={s['follow_rate']:.3f}"
        c = f"{s['expected_hits']}/{s['cases']}"
        print(f"{arm:14s} {a:>14s} {b:>14s} {c:>10s} {s['empty_outputs']:>7d}")

    a_rate = stats.get(ARM_A, {}).get("follow_rate", 0.0)
    b_rate = stats.get(ARM_B, {}).get("follow_rate", 0.0)
    print(f"\nΔ 词级跟随率（A − B）= {a_rate - b_rate:+.3f}")
    for arm, s in stats.items():
        if s["non_canonical_words"]:
            print(f"  [{arm}] 仍自造的词：{s['non_canonical_words']}")
    print()
    print("★ 读数提醒：模型有随机性，**单条差异不要外推**（纪律 #5），结论只看聚合差值。")
    print(
        "  自造词即使只多一个，也会各成 1-hit 桶 ⇒ `MIN_HITS=2` 永不满足 —— 这才是缺陷 E 的代价。"
    )


def reanalyse(path: Path = OUT, write: bool = False) -> int:
    """用**当前** gold 重算既有归档 —— 改 gold 不该重新花 token。

    只重算 `expected_hit_after_normalize`（依赖 gold），其余字段原样沿用
    （`all_canonical` / `non_canonical` 只依赖 kp_index，与 gold 无关）。

    `write=True` 时原地重写：原始 `kp_raw` / `kp_normalized` **不变**，
    只把过期的单值 `expected` 换成 `expected_any` + 重算的入桶。
    ★ 必须能重写 —— 留一份带错误 gold 的产物，下次接手的人会被误导成「产品没入桶」。
    """
    gold_by_qid = {c["qid"]: c["expected_any"] for c in CASES}
    records: list[dict] = []
    stale: list[str] = []
    header_lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            # ★ 全部注释行都保留（**含 provenance 行**）。曾按 `provenance=` 过滤，
            #   结果 `--write` 一次就把 code_version / 两臂 system sha 全丢了。
            if "修正 gold 后重析" not in line:
                header_lines.append(line)
            continue
        rec = json.loads(line)
        expected = gold_by_qid.get(rec["qid"])
        if expected is None:
            stale.append(rec["qid"])
            continue
        rec.pop("expected", None)
        rec["expected_any"] = sorted(expected)
        rec["expected_hit_after_normalize"] = bool(set(rec["kp_normalized"]) & expected)
        records.append(rec)

    print(f"重析 {path.name}：{len(records)} 条（零 LLM 调用）")
    if stale:
        print(f"  ⚠ 归档里有 {len(stale)} 条的 qid 不在当前 CASES，已跳过：{sorted(set(stale))}")
    print(
        "  ★ 只重算了「入桶」（依赖 gold）；「全 canonical / 跟随率」只依赖 kp_index，与 gold 无关。"
    )
    _summarise(records)

    if write:
        with path.open("w", encoding="utf-8") as fh:
            for h in header_lines:
                fh.write(h + "\n")
            fh.write(
                f"# 修正 gold 后重析：单值 expected → expected_any"
                f"（`堆` 不在 kp_index、`排序`/`快速排序` 是两个并存节点）。"
                f"kp_raw / kp_normalized 未改动。{datetime.now(UTC).isoformat()}\n"
            )
            for rec in records:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"\n已原地重写：{path.relative_to(ROOT)}")
    return 0


async def main() -> int:
    canonical = set(canonical_names())
    print(
        f"模型 = {settings.LLM_MODEL} · temperature = {TEMPERATURE_GRADING}"
        f" · PROMPT_SET_VERSION = {PROMPT_SET_VERSION} · canonical = {len(canonical)}"
    )
    arms = _build_arms()
    print()

    records: list[dict] = []
    for arm, prompt in arms.items():
        records.extend(await _measure(arm, prompt, canonical))

    _summarise(records)

    provenance = {
        "probe": "memory_e5_probe",
        "code_version": code_version(),
        "prompt_set_version": PROMPT_SET_VERSION,
        "arm_system_sha256": {
            arm: hashlib.sha256(_system_text(prompt).encode("utf-8")).hexdigest()[:12]
            for arm, prompt in arms.items()
        },
        "model": settings.LLM_MODEL,
        "temperature": TEMPERATURE_GRADING,
        "n_cases": len(CASES),
        "date": datetime.now(UTC).isoformat(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        fh.write(
            "# E-5 缺陷 E 效果探针（配对：臂 A 实际注入 "
            f"{_system_vocab_size(arms[ARM_A])} 个候选词 vs 臂 B 8 条示例=E-3 前口径；"
            "臂名沿用首跑条数，实际条数以本行为准）。\n"
        )
        fh.write("# 测量，非门禁；模型有随机性，判定看两臂聚合差值。\n")
        fh.write(f"# provenance={json.dumps(provenance, ensure_ascii=False)}\n")
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"\n落盘：{OUT.relative_to(ROOT)}（{len(records)} 条 = {len(CASES)} 题 × 2 臂）")
    return 0


if __name__ == "__main__":
    # ★ `--reanalyse` 零成本（不碰 LLM）；不带参数才真跑（12 次批改调用，需授权）。
    #   `--reanalyse [路径] --write` = 用当前 gold 原地重写归档。
    if len(sys.argv) > 1 and sys.argv[1] == "--reanalyse":
        args = sys.argv[2:]
        write = "--write" in args
        paths = [a for a in args if not a.startswith("--")]
        raise SystemExit(reanalyse(Path(paths[0]) if paths else OUT, write=write))
    raise SystemExit(asyncio.run(main()))
