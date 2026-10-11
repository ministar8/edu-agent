"""memory_step4fix_gate 判据组：⑫ 词表同源 / ⑬ 重判归因 / ⑭

从原单文件 `memory_step4fix_gate.py` 按判据边界原样搬出，逻辑一字未改。
"""

from __future__ import annotations

import json
from pathlib import Path

from _m4f_core import ROOT, check, section, skip


def _vocab_tokens(system_text: str) -> set[str]:
    """从批改 system 文本里抽出「按学科分组注入」的考点名集合。

    ★ 为什么按 `【学科】a、b、c` 的行结构抽，而不是全文散搜：
    只有**词表块**里的名字才是「模型可选的取值」；规则尾部的反例（如「数据结构」太粗）
    也存在于文本中，全文散搜会把反例当成合法值，护栏就失去意义。
    """
    import re

    return {
        name
        for line in re.findall(r"【[^】]*】([^\n]+)", system_text)
        for name in line.split("、")
        if name
    }


def _independent_scan() -> tuple[set[str], set[str]]:
    """**绕开 `kp_vocab`**，直接解析 kp_index，返回 `(全部 name, subject 根节点 name)`。

    ★ 为什么必须独立扫一遍：⑫a~⑫c 的两侧集合都来自 `core.kp_vocab` ⇒ 属同义反复，
    `kp_vocab` 自己解析漂移时全绿无感知（⑫i 即为此而设）。本轮 #8 又加了一层过滤
    （剔掉 `node_kind == "subject"`），所以**期望集本身也要由独立扫描算出**，
    否则「过滤是否正确」这件事没有外部判据。
    """
    import json

    names: set[str] = set()
    roots: set[str] = set()
    for p in sorted((Path(ROOT) / "knowledge" / "knowledge_points").glob("*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            name = str(obj.get("name") or "").strip()
            if not name:
                continue
            names.add(name)
            if str(obj.get("node_kind") or "") == "subject":
                roots.add(name)
    return names, roots


def check_12() -> None:
    """⑫ GRADE_PROMPT 的词表必须与 `kp_index` **同源**（2026-10-07 缺陷 E · 方案 A）。

    缺陷 E 的机制：批改产出的 `knowledge_points` 是 LLM 自造自由文本 ⇒ 归一化不命中
    ⇒ 每个自造词各成一个 1-hit 桶 ⇒ `MEMORY_WEAK_MIN_HITS` 永不满足 ⇒ `weak_topics` 恒空。
    修法是在 prompt 里注入候选 canonical 词表，从**上游**约束输出。

    本组护栏锁的是「注入这件事真的生效了、且注入的就是 kp_index 那一份」：
      ⑫a 词表确实进了 prompt（接线，不是只写了函数）
      ⑫b 无遗漏（canonical ⊆ prompt 词表；只注入半个学科 ⇒ 模型被迫自造）
      ⑫c 无多余（prompt 词表 ⊆ canonical；混入自造词会重新制造不同源）
      ⑫d **不注入别名**（别名会让模型输出 `AVL` 而非 `平衡二叉树`）
      ⑫e 降级：词表为空 ⇒ 退回 8 个示例且全 canonical（服务不得起不来）
      ⑫f prompt 不含花括号（否则 `ChatPromptTemplate` 在 import 期直接炸）
      ⑫g 成本上界：批改 system 不超 2000 字符（每次批改都付这个钱）
      ⑫h ★ **反向验证**：探测器对篡改文本必须报红（证明 ⑫b/⑫c 不是恒绿）
    """
    section("⑫ GRADE_PROMPT 词表与 kp_index 同源（缺陷 E · 方案 A）")
    from core.kp_vocab import canonical_names
    from prompts import GRADE_PROMPT
    from prompts.service import _knowledge_points_block

    system_text = GRADE_PROMPT.messages[0].prompt.template
    canonical = set(canonical_names())
    injected = _vocab_tokens(system_text)

    direct_names, subject_roots = _independent_scan()
    # #8 之后，prompt 该提供的是「canonical − 课程根节点」—— 期望集由独立扫描算出。
    expected = direct_names - subject_roots

    check(
        "⑫a 词表块确实进了 prompt（接线生效，非只定义函数）",
        len(injected) > 100,
        f"prompt 内 {len(injected)} 个 / canonical {len(canonical)} 个 / 应提供 {len(expected)} 个",
    )
    missing = sorted(expected - injected)
    check("⑫b 无遗漏（应提供的考点全部可选）", not missing, f"缺失 {len(missing)}: {missing[:3]}")
    extra = sorted(injected - canonical)
    check("⑫c 无多余（prompt 内全部 ∈ canonical）", not extra, f"多余 {len(extra)}: {extra[:3]}")

    # ⑫d 别名不得出现在取值表里。别名表的键是「非 canonical 的同义写法」，
    #   一旦出现就说明词表注入了 aliases 而不是 canonical。
    from memory.topics import _TOPIC_ALIASES

    aliased = sorted(set(_TOPIC_ALIASES) & injected)
    check(
        "⑫d 未注入别名（只给 canonical，防模型输出 AVL 而非平衡二叉树）",
        not aliased,
        f"混入别名: {aliased}" if aliased else f"别名表 {len(_TOPIC_ALIASES)} 条均未出现",
    )

    # ⑫e 降级分支
    import re as _re

    fallback = _knowledge_points_block({})
    fb_names = {
        n.strip("「」")
        for n in _re.split(r"[、]", _re.findall(r"例如[：:]\s*([^。]+)", fallback)[0])
    }
    check(
        "⑫e 降级：词表为空 ⇒ 退回 8 示例且全 canonical（服务不起不来）",
        _vocab_tokens(fallback) == set()
        and len(fb_names) == 8
        and fb_names <= canonical
        and bool(fallback),
        f"示例 {len(fb_names)} 个，非规范 {sorted(fb_names - canonical)}",
    )

    check(
        "⑫f prompt 不含花括号（不破坏 ChatPromptTemplate import 期校验）",
        "{" not in system_text and "}" not in system_text,
    )
    check(
        "⑫g 批改 system 长度在上界内（每次批改调用都付这个词表钱）",
        len(system_text) <= 2000,
        f"{len(system_text)} 字符",
    )

    # ⑫h 反向验证：探测器必须能抓到「删一个 + 造一个」的篡改。
    #   篡改样例取自缺陷 E 的**真实产出**（`图的基本性质`），不是随手编的串。
    tampered = system_text.replace("【数据结构】", "【数据结构】图的基本性质、", 1)
    if "平衡二叉树" in tampered:
        tampered = tampered.replace("平衡二叉树", "", 1)
    t_injected = _vocab_tokens(tampered)
    detector_caught = (
        "图的基本性质" in t_injected - canonical  # ⑫c 会红
        and "平衡二叉树" in canonical - t_injected  # ⑫b 会红
    )
    check(
        "⑫h **反向验证**：篡改文本被探测器抓出（证明 ⑫b/⑫c 非恒绿）",
        detector_caught,
        f"抓到 自造={sorted(t_injected - canonical)[:1]} 遗漏={sorted(canonical - t_injected)[:1]}",
    )

    # ⑫i ★ 双读校验：⑫a~⑫c 与 ⑫k 的期望集**都**要能脱离 `kp_vocab` 独立算出 ——
    #   否则 kp_vocab 自身解析漂移（漏学科、把 links.jsonl 当 name、去重并掉考点、
    #   过滤过头/不足）时，护栏会跟着一起绿。
    check(
        "⑫i kp_vocab 解析结果 == 独立解析 jsonl（防同源双份都漂）",
        direct_names == canonical,
        f"独立解析 {len(direct_names)} 个 / kp_vocab {len(canonical)} 个；"
        f"差异 {sorted(direct_names ^ canonical)[:3]}",
    )

    # ⑫k 缺陷 #8：课程根节点**不得被提供给模型**，但**不得过滤过头**。
    #   规则尾自己写着「不是学科名（如「数据结构」太粗）」—— 若把它列进可选取值，
    #   模型选它就能轻易凑满 `MIN_HITS=2`，聚成「整门课 = 一个薄弱点」的桶，
    #   且因为是 canonical 而**比自造词更难发现**。
    offered_roots = sorted(subject_roots & injected)
    check(
        "⑫k·1 未把课程根节点提供给模型（`node_kind=subject` 已全部剔除）",
        not offered_roots and len(subject_roots) == 4,
        f"根节点={sorted(subject_roots)} 混入={offered_roots}",
    )
    #   反向：domain 层（408 大纲章名）必须**保留** —— 它们是合法薄弱点标签，
    #   E-5 的可接受集里就用到 `图` 与 `堆排序`。过滤过头会把这些一起杀掉。
    domains_kept = sorted(n for n in ("图", "排序", "内存管理", "树与二叉树") if n in injected)
    check(
        "⑫k·2 domain 章名仍保留（过滤没有过头把合法薄弱点也剔掉）",
        len(domains_kept) == 4,
        f"保留 {domains_kept}",
    )


def check_13() -> None:
    """⑬ B 组四条 review 结论的落地（2026-10-07，全部零 LLM）。

    先说清楚**验真伪**的结果，再锁修复：
      B1 **确认** —— 重判（`--rejudge`）走 `mechanical_reasons_from_record`，
         它照抄 `runner.mechanical_failures`，而 `case_invalid` / `memory_miss`
         是 runner 另两处分头写的 ⇒ 重判把它们**整个清掉**。实测归档里 4 条
         `case_invalid` 的 reasons 恰为 `["case_invalid"]` ⇒ 重判后变 `[]`、
         `primary_failure` 翻成 `none`（看起来像通过）。
      B2 **确认（潜伏）** —— `cli.py` 三处 `write_text("\\n".join(...))` 不留尾换行，
         与 `append_record` 的 `"a"` 模式相遇会把两条粘成一条坏行（实测 3 条只剩 1 条可读）。
         全盘扫过现存 12 份归档：末字节**都是** `\\n` ⇒ 尚未真的烧到过数据，属潜伏。
      B3 **一半被推翻** —— 「显式 config 只写一半会丢 `user_id`」成立，但仓内无此类调用方
         （`service.py` 两把键一起给）⇒ 不改行为，只把契约写进 docstring；
         「并发下回落会算到别人头上」**被实测推翻**：`get_config()` 读 contextvar，
         asyncio 每个 Task 各持副本，4 个交错任务仍各自取到自己的 uid（见 ⑩e）。
      B4 **大部分被推翻，剩一条真的** —— `forbidden_values` 是**回复文本里的自由词**，
         不是 KP 名，要求它 canonical 是错的规则（且 gold_sanity 已在查 `None` 与
         「与期望值重叠」）；`min_grade_calls` 改成 0 也**没放松** mem-001 的约束
         （真正兜底的是 `grade_score_bands`）。但 **mem-005 的前置条件确实是空标**：
         它只声明 `min_grade_calls: 0`，而 `len(calls) < 0` 永不成立 ⇒ 这条负样本对照
         从来没校验过「A 段真的没写入」。⇒ 新增 `max_grade_calls` 上限把它变成真约束。
    """
    section("⑬ 重判归因 / jsonl 落盘 / 负样本前置条件（B 组修复）")

    import tempfile
    from pathlib import Path as _P

    from evaluation.task_eval import memory_scorer as _ms
    from evaluation.task_eval.cases import SetupConditions, load_cases
    from evaluation.task_eval.gold_sanity import run_sanity
    from evaluation.task_eval.judge import mechanical_reasons_from_record
    from evaluation.task_eval.runner import CaseRecord, append_record, write_jsonl

    # —— B1：重判保留 runner 写的归因 ——
    rec_ci = {
        "case_id": "mem-001",
        "task": "memory",
        "validity_valid": False,
        "failure_reason": ["case_invalid"],
        "reply": "参考答案：略",
        "hard_fails": [],
    }
    got = mechanical_reasons_from_record(rec_ci)
    check("⑬a 重判保留 `case_invalid`（不再洗成『通过』）", got == ["case_invalid"], str(got))

    rec_mm = {
        "case_id": "mem-009",
        "task": "memory",
        "failure_reason": ["memory_miss"],
        "reply": "x",
    }
    got = mechanical_reasons_from_record(rec_mm)
    check(
        "⑬b 重判保留 `memory_miss`（标注缺口记号，非 judge 意见）", got == ["memory_miss"], str(got)
    )

    # 兜底路径：上一轮已被误清（reasons=[]）但 `validity_valid=False` 仍在 ⇒ 能恢复
    rec_wiped = {"case_id": "mem-002", "task": "memory", "validity_valid": False, "reply": "x"}
    got = mechanical_reasons_from_record(rec_wiped)
    check("⑬c reasons 已被洗空时按 `validity_valid` 重建", got == ["case_invalid"], str(got))

    # ★ 反向：保留面不能过宽 —— judge -only 的 reason 必须被清掉（否则新旧 judge 混在一起）
    rec_judge = {
        "case_id": "qa-001",
        "task": "qa",
        "pack_nonempty": True,
        "reply": "答案",
        "failure_reason": ["generation_wrong", "hallucination"],
    }
    got = mechanical_reasons_from_record(rec_judge)
    check(
        "⑬d 反向：judge-only reasons 仍被清除（保留面只有两项）",
        got == [],
        str(got),
    )

    # —— B2：行写出格式 ——
    tmp = _P(tempfile.mkdtemp()) / "b13.jsonl"
    rows = [{"case_id": f"a-{i}", "task": "qa"} for i in (1, 2)]
    write_jsonl(tmp, rows)
    raw = tmp.read_bytes()
    check(
        "⑬e write_jsonl 末行带换行（append 前置条件成立）",
        raw.endswith(b"\n") and len(raw.splitlines()) == 2,
        f"末字节={raw[-1:]} 行数={len(raw.splitlines())}",
    )
    append_record(CaseRecord(case_id="a-3", task="qa", task_mode="learn", query="q"), tmp)
    append_record(CaseRecord(case_id="a-4", task="qa", task_mode="learn", query="q"), tmp)
    ids = []
    bad = 0
    for ln in tmp.read_text(encoding="utf-8").splitlines():
        try:
            ids.append(json.loads(ln)["case_id"])
        except Exception:
            bad += 1
    check(
        "⑬f 追加到 write_jsonl 产物后 4 条全可解析",
        ids == ["a-1", "a-2", "a-3", "a-4"] and bad == 0,
        f"可解析={ids} 坏行={bad}",
    )

    # ★ 自愈路径：手写一份**没有**尾换行的文件（模拟旧 cli 产物 / 外部编辑）
    legacy = tmp.parent / "legacy.jsonl"
    legacy.write_text(
        "\n".join(json.dumps({"case_id": f"L-{i}", "task": "qa"}) for i in (1, 2)),
        encoding="utf-8",
    )
    append_record(CaseRecord(case_id="L-3", task="qa", task_mode="learn", query="q"), legacy)
    append_record(CaseRecord(case_id="L-4", task="qa", task_mode="learn", query="q"), legacy)
    got, bad = [], 0
    for ln in legacy.read_text(encoding="utf-8").splitlines():
        try:
            got.append(json.loads(ln)["case_id"])
        except Exception:
            bad += 1
    check(
        "⑬g 无尾换行的旧文件：append 前自动补分隔，4 条不丢（且幂等不多补）",
        got == ["L-1", "L-2", "L-3", "L-4"] and bad == 0,
        f"可解析={got} 坏行={bad} 物理行={len(legacy.read_text(encoding='utf-8').splitlines())}",
    )

    # —— B4：负样本对照的前置条件 ——
    cases = load_cases(ROOT / "evals" / "datasets" / "demo" / "memory_cases.jsonl")
    m5 = next((c for c in cases if c.case_id == "mem-005"), None)
    if m5 is None:
        check("⑬h mem-005 存在", False, "载入 0 条")
    else:
        sc = m5.gold.setup_conditions
        check(
            "⑬h mem-005 现声明「恰好 0 次批改」（min=0 且 max=0）",
            sc is not None and sc.min_grade_calls == 0 and sc.max_grade_calls == 0,
            f"min={getattr(sc, 'min_grade_calls', None)} max={getattr(sc, 'max_grade_calls', None)}",
        )
        v0 = _ms.check_case_validity(setup=sc, grade_scores=[], session_scope=0)
        v1 = _ms.check_case_validity(
            setup=sc, grade_scores=[{"session": 0, "score": 40.0}], session_scope=0
        )
        check(
            "⑬i 上限真生效：0 次⇒有效；A 段多出 1 次批改⇒case_invalid",
            v0.valid is True and v1.valid is False,
            f"0次={v0.valid} 1次={v1.valid} ({v1.reason})",
        )
        # ★ 反向：退回「只写 min:0」时空标 lint 必须变红
        m5_copy = load_cases(ROOT / "evals" / "datasets" / "demo" / "memory_cases.jsonl")
        target = next(c for c in m5_copy if c.case_id == "mem-005")
        target.gold.setup_conditions = SetupConditions(min_grade_calls=0)
        rep = run_sanity([target])
        check(
            "⑬j 反向：改回只写 `min: 0` ⇒ gold_sanity 必须报 ERROR（空标 lint 可红）",
            len(rep.errors) == 1 and rep.errors[0].field_name.endswith("min_grade_calls"),
            f"ERROR={[(i.field_name, i.message[:22]) for i in rep.errors]}",
        )
        check(
            "⑬k 真实 6 条 memory gold 体检仍全绿（新字段没制造假红灯）",
            not run_sanity(cases).errors,
            "",
        )

    # ★ 已发表的数字不许因为改 gold 而变动：逐条比对两份归档的 validity
    for fname in ("phase1_memory_step5_store_off.jsonl", "phase1_memory_step5_store_on.jsonl"):
        fp = ROOT / "evals" / "results" / "task_eval" / fname
        if not fp.exists():
            skip(f"⑬l {fname}", "本机归档未入库（D11 裁决 `*.jsonl` 不入库）⇒ 该项未执行", count=1)
            continue
        by_id = {c.case_id: c for c in cases}
        changed = []
        n = 0
        for ln in fp.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            r = json.loads(ln)
            if r.get("task") != "memory":
                continue
            n += 1
            c = by_id.get(r["case_id"])
            if c is None:
                changed.append(f"{r['case_id']}(gold 缺失)")
                continue
            new_v = _ms.check_case_validity(
                setup=c.gold.setup_conditions,
                grade_scores=r.get("grade_scores") or [],
                session_scope=0,
            ).valid
            if new_v != r.get("validity_valid"):
                changed.append(f"{r['case_id']}:{r.get('validity_valid')}→{new_v}")
        check(
            f"⑬l 新 gold 下 {fname} 的 validity 逐条不变（不动已发表数字）",
            n == 6 and not changed,
            f"{n} 条；变动={changed}",
        )

    tmp.unlink(missing_ok=True)
    legacy.unlink(missing_ok=True)


def check_14() -> None:
    """⑭ Generate 主指标（Task 4 registry 化后）：主指标 = registry 逐题复合（四态）。

    背景：`EFFECT_PLAN §3.1` 冻结的是**逐题 AND**；§4.2 事故 —— 旧布尔合取把
    None 剔出分母，0.733 被读成 1.000。Task 4 起布尔合取/池化的本地副本已删
    （`metrics.every_item_passes` / `metrics.delivery_rate`），判据只在
    `predicates.registry` 一处，复合走 `pc.composite`：fail 优先 → required 项
    missing_premise 毒化（rate=None，**不冒充通过率**）→ not_applicable 有权缺席。
    checkpoint 5 裁定 A：老归档缺 `top_items` 键（证据不存在）⇒ `missing_premise`，
    **不得**记成 fail；键存在但列表为空 ⇒ 仍是 fail（查了且没覆盖 ≠ 没证据）。
    """
    section("⑭ Generate 主指标：registry 逐题复合（四态，Task 4 起）")

    from evaluation.task_eval.predicates import common as pc
    from evaluation.task_eval.report import build_report, render_markdown

    keys = ("gen_structure", "gen_answerability", "gen_coverage", "gen_correctness")

    # ⑭a 整题测不到 ⇒ 复合 missing_premise ⇒ rate=None、n=0（**绝不能算通过**，
    #    否则「测不到」被洗成满分/合格 —— 规则①）
    all_mp: dict[str, pc.Verdict] = {k: "missing_premise" for k in keys}
    r_a = pc.rate([pc.composite(all_mp)])
    check(
        "⑭a 全 missing_premise ⇒ 复合 missing_premise（rate=None、n=0），不是 pass",
        pc.composite(all_mp) == "missing_premise" and r_a["rate"] is None and r_a["n"] == 0,
        str(r_a),
    )
    # ⑭b 逐题 AND：fail 优先；not_applicable 有权缺席、不拉低该题
    one_fail = {**{k: "pass" for k in keys}, "gen_coverage": "fail"}
    one_na = {**{k: "pass" for k in keys}, "gen_coverage": "not_applicable"}
    check(
        "⑭b 一题有 fail ⇒ 复合 fail；not_applicable 不毒化该题",
        pc.composite(one_fail) == "fail" and pc.composite(one_na) == "pass",
    )

    # ⑭c ★ 方向性：池化**系统性偏乐观** —— 一道题崩得越集中、其他题可测项越多，
    #    稀释越狠。同构样本锁这个方向（旧归档的 0.9423 vs 0.80 已随旧口径退役，见 ⑭d）。
    diluted = [{k: "fail" for k in keys[:2]}] + [{k: "pass" for k in keys}] * 13
    pooled = pc.rate([v for r in diluted for v in r.values()])["rate"]
    per_case = pc.rate([pc.composite(r) for r in diluted])["rate"]
    check(
        "⑭c 同一样本两口径必须分叉，且池化**偏高**（证明逐题复合有信息量）",
        isinstance(pooled, float) and isinstance(per_case, float) and pooled - per_case > 0.02,
        f"池化={pooled} vs 逐题={per_case}（崩掉的题只算 1 题，却被 54 个好项摊薄）",
    )

    # ⑭d 真实归档锁定形态（checkpoint 5 裁定 A 后）：phase1_baseline_v2 的 15 条
    #    generate **全部没有 `top_items` 键**（老归档，检索探针未落盘）⇒ coverage
    #    missing_premise（测不到，不记 fail）；无 gold ⇒ answerability/correctness
    #    同为 missing_premise ⇒ 逐题复合全部 missing_premise ⇒ rate=None、n=0、
    #    n_a_missing_premise=15。（旧读数 0.80/0.9423 是「归档字段 + 旧布尔口径」的
    #    历史值，随 registry 化退役 —— 语义修正，须随改动披露，非回归。）
    import json as _json

    fp = ROOT / "evals" / "results" / "task_eval" / "phase1_baseline_v2.jsonl"
    if not fp.exists():
        skip(
            "⑭d~⑭f",
            "phase1_baseline_v2.jsonl 不在本机（未入库）⇒ 三项判据未执行",
            count=3,
        )
        return
    gen = [
        _json.loads(ln)
        for ln in fp.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    gen = [r for r in gen if r.get("task") == "generate"]
    rep = build_report(gen)
    g = rep["tasks"]["generate"]
    cp = g["gen_case_pass"]
    check(
        "⑭d 归档 15 条缺 top_items ⇒ 复合全测不到：rate=None、n=0、n_a_missing_premise=15",
        cp["rate"] is None and cp["n"] == 0 and cp["n_a_missing_premise"] == len(gen) == 15,
        f"n={len(gen)} gen_case_pass={cp}",
    )
    # ⑭e 报告文案：主指标必须是逐题复合，池化数必须自标「非主指标」，旧名必须消失
    md = render_markdown(rep)
    check(
        "⑭e 报告：逐题数挂「主指标」、池化数挂「诊断，非主指标」、旧名「交付完整率（主指标）」已消失",
        "适用项全过率（主指标）" in md
        and "诊断，非主指标" in md
        and "交付完整率（主指标）" not in md,
    )
    # ⑭f 整题测不到的题必须**显式露出**，不许静默进分母（夹具：结构完整 + 无 gold）
    full_reply = (
        "题干：设 Cache 采用 2-Way 组相联，主存 64 块，Cache 8 行，问组号需要几位。\n"
        "A. 2\nB. 3\nC. 4\nD. 6\n"
        "标准答案：B\n"
        "解析：8 行分 2 路，8/2=4 组，组号需 2 位，因此选 B。"
    )
    all_mp_recs = [
        {
            "task": "generate",
            "reply": full_reply,
            "top_items": [{"kp": ["co.overview"]}],
            "gold": {},
        }
        for _ in range(3)
    ]
    st = build_report(all_mp_recs)["tasks"]["generate"]["gen_case_pass"]
    check(
        "⑭f 3 题全测不到 ⇒ 主指标 n=0、n_a_missing_premise=3（分母不会假装是 3）",
        st["n"] == 0 and st["n_a_missing_premise"] == 3,
        str(st),
    )
