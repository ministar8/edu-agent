"""memory_step4fix_gate 判据组：㉘㉙㉚

从原单文件 `memory_step4fix_gate.py` 按判据边界原样搬出，逻辑一字未改。
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from _m4f_core import ROOT, check, section, skip


def check_28() -> None:
    """㉘ Generate 的「答案键自相矛盾」修在**真源**上（§22 唯一不达行 + #33）。

    实测缺陷（§6 整轮 `gen-003`/`007`/`009`/`010`，judge 判低分**可举证**）：
    `standard_answer` 与 `explanation` 是**两个字段各写各的** —— 答案说「能聚合为 /22」、
    解析说「三者不能合并为单个 CIDR 块」；或答案里留着「=602？」「→实际为 8」的自我改口。
    ⇒ 修在 schema 字段描述（模型填这个字段的瞬间看得到）+ `[规则]` 里一条。

    ★ 三项各挡一种「绿而路径不可达」：
      ㉘a 只改 prompt 不改 schema（或反之）⇒ 两条真源都要有；
      ㉘b 只改 `_QUESTION_AGENT_RULES` 这个源常量、组合进最终 prompt 的那步被改掉 ⇒ 断言**最终**字符串；
      ㉘c prompt 与 schema 都对，但 `question_core` 构造 agent 时换了实参 ⇒ AST 锁 wiring。
    """
    section("㉘ Generate 答案键与解析同结论（#33）")

    from prompts import QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT
    from schema.questions import GeneratedQuestion

    f_sa = str(GeneratedQuestion.model_fields["standard_answer"].description or "")
    f_ex = str(GeneratedQuestion.model_fields["explanation"].description or "")
    check(
        "㉘a schema 两个字段描述都带约束（同结论 + 不改口）⇒ 驱动的是真 Pydantic 字段，不是文本 grep",
        "同结论" in f_sa and "改口" in f_ex,
        f"standard_answer={f_sa[:26]!r} explanation={f_ex[:26]!r}",
    )
    check(
        "㉘b 约束进了 question_gen_agent **实际使用的那条** system prompt（不是只待在源常量里）",
        "同结论" in QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT
        and "算不清" in QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT,
        f"len={len(QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT)}",
    )

    tree = ast.parse((ROOT / "src" / "agents" / "question_core.py").read_text(encoding="utf-8"))
    wired = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "build_agent"
        ):
            kw = {k.arg: getattr(k.value, "id", "") for k in node.keywords}
            if (
                kw.get("system_prompt") == "QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT"
                and kw.get("response_format") == "GeneratedQuestionSet"
            ):
                wired = True
    check(
        "㉘c `question_core` 确实把这条 prompt + 这个 schema 交给 build_agent（换实参就红）",
        wired,
        ""
        if wired
        else "AST 里没找到 system_prompt=QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT "
        "且 response_format=GeneratedQuestionSet 的 build_agent 调用",
    )


def check_29() -> None:
    """㉙ 审核表重跑**不许冲掉人工标注**（#37，`export_review_sheets`）。

    原状态：`export_calibration` 无条件写 `"human_score": None`，而 `calibration_30.jsonl`
    的 30 条 human_score 是**人工标注** —— judge 校准的 exact / within_1 / mae / spearman
    四个数全从它算。⇒ 照文档里那句默认命令重跑一次就把论文依据清空了，而工具照旧打印成功。
    """
    section("㉙ 审核表的防覆写（#37：重跑导出不得吃掉人工标注）")
    _c29_merge()
    _c29_calibration()


def check_30() -> None:
    """㉚ `gold_review_apply` 的不变量 —— 它改的是 **gold**，错了就污染锚点归属。

    gold 一改 ⇒ record 的 `golden_sha256` / `gold_status` 跟着变 ⇒ 之前的效果数字降级成
    「draft gold 下的读数」。所以这个执行器必须被钉住「只动那一个字段」。
    本组全部跑在 `tempfile` 的副本上，**不碰仓库里真实的 demo 文件**。
    """
    section("㉚ gold_status 翻转器（只改 gold_status / 拒绝未知 id / 换行与注释不变）")
    _c30_body()


def _c29_merge() -> None:

    from lib.export_review_sheets import merge_preserving_human

    merged, dropped = merge_preserving_human(
        {"qa-001": {"case_id": "qa-001", "human_score": 4}},
        [{"case_id": "qa-001", "human_score": None, "llm_score": 1}],
        ["human_score"],
    )
    check(
        "㉙a 旧表的人工值优先：新值是 None 也不留空（#37 的原始事故形状）",
        merged[0]["human_score"] == 4 and dropped == [],
        str(merged[0]),
    )
    # ★ 比 ㉙a 更狠的一例：grade 的 human_score 是**机械预填**的非空值，
    #   而审核人改的正是这个字段 —— 若只在「新值为空」时保留，人的修改会被预填值冲回去
    merged2, _ = merge_preserving_human(
        {"grd-001": {"case_id": "grd-001", "review_fields": {"human_score": 0}}},
        [{"case_id": "grd-001", "review_fields": {"human_score": 100}}],
        ["review_fields.human_score"],
    )
    check(
        "㉙b 表里值赢过派生值（100 是预填、0 是人改的 ⇒ 保留 0）",
        merged2[0]["review_fields"]["human_score"] == 0,
        str(merged2[0]["review_fields"]),
    )
    _, dropped3 = merge_preserving_human(
        {"zz-999": {"case_id": "zz-999", "human_score": 3}},
        [{"case_id": "qa-001", "human_score": None}],
        ["human_score"],
    )
    check(
        "㉙c 本次集合之外的行会被报出来（不静默丢）",
        dropped3 == ["zz-999"],
        str(dropped3),
    )


def _c29_calibration() -> None:
    from lib.export_review_sheets import merge_preserving_human

    cal_path = ROOT / "evals" / "datasets" / "demo" / "calibration_30.jsonl"
    if not cal_path.exists():
        skip("㉙d", "calibration_30.jsonl 不在本机")
        return
    rows = [
        json.loads(ln)
        for ln in cal_path.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    human = [r for r in rows if r.get("human_score") is not None]
    m5, _ = merge_preserving_human(
        {"qa-001": {"case_id": "qa-001", "llm_score": 4}},
        [{"case_id": "qa-001", "llm_score": None}, {"case_id": "qa-001", "llm_score": 2}],
        ["human_score"],
        fill_if_missing=["llm_score"],
    )
    check(
        "㉙e 派生列走另一条规则：本次拿不到就沿用旧值（不清空已发表的 llm_score），拿得到就刷新",
        m5[0]["llm_score"] == 4 and m5[1]["llm_score"] == 2,
        f"{m5[0]['llm_score']} / {m5[1]['llm_score']}",
    )
    check(
        "㉙d 已发表的那份表仍是满标注（30 行 / human_score 全非空）⇒ 校准四个数有数据可算",
        len(rows) == 30 and len(human) == 30,
        f"rows={len(rows)} human={len(human)}",
    )


def _c30_body() -> None:
    import tempfile

    row1 = '{"case_id": "qa-001", "task": "qa", "gold_status": "draft", "gold": {"reference": "x"}}'
    row2 = '{"case_id": "qa-002", "task": "qa", "gold_status": "draft"}'
    sample = ("# 注释行不许被重排\n" + row1 + "\n" + row2 + "\n").encode("utf-8")

    with tempfile.TemporaryDirectory() as td:
        after_fp = _c30_main(td, sample)
        _c30_crossfile(td, after_fp)
        _c30_crlf(td, sample)


def _c30_main(td, sample):
    import json

    from lib.gold_review_apply import apply_file

    f = Path(td) / "qa_cases.jsonl"
    f.write_bytes(sample)
    changed, seen1, before_fp, after_fp = apply_file(f, {"qa-001"}, "reviewed", write=True)
    got = [
        json.loads(ln) for ln in f.read_bytes().decode("utf-8").splitlines() if ln.startswith("{")
    ]
    check(
        "㉚a 只有 gold_status 变了（gold 子对象逐键相等），且指纹确实变了",
        changed == ["qa-001"]
        and got[0]["gold_status"] == "reviewed"
        and got[0]["gold"] == {"reference": "x"}
        and before_fp != after_fp,
        f"{got[0]} seen={sorted(seen1)}",
    )
    check(
        "㉚b 不在列表里的 case 一个字没动（qa-002 仍是 draft）",
        got[1]["gold_status"] == "draft",
        str(got[1]),
    )
    _, r2, _, _ = apply_file(f, {"nope-404"}, "reviewed", write=False)
    check(
        "㉚c demo 集合里没有的 id ⇒ 本文件的 seen 为空（refused 由调用方全局算）",
        r2 == set(),
        str(r2),
    )
    return after_fp


def _c30_crossfile(td, after_fp) -> None:

    from lib.gold_review_apply import apply_file

    # ★ ㉚d 钉住刚修的那个 bug：refused 按单文件算会把别的文件的 id 报成「找不到」，
    #   于是同一次运行既说「拟写 2 条」又说「全部拒绝」
    f = Path(td) / "qa_cases.jsonl"
    f3 = Path(td) / "grade_cases.jsonl"
    g_row = '{"case_id": "grd-001", "task": "grade", "gold_status": "draft"}'
    f3.write_bytes((g_row + "\n").encode("utf-8"))
    c1, seen_qa, _, _ = apply_file(f, {"grd-001"}, "reviewed", write=False)
    c2, seen_grd, _, _ = apply_file(f3, {"grd-001"}, "reviewed", write=True)
    check(
        "㉚d 跨文件不误报：qa 文件对 grd-001 的 seen 为空，但 grade 文件认得它 ⇒ 全局 refused 应为空",
        c1 == [] and seen_qa == set() and c2 == ["grd-001"] and seen_grd == {"grd-001"},
        f"qa_changed={c1} grade_changed={c2} grade_seen={seen_grd}",
    )
    c3, _, _, fp3 = apply_file(f, {"qa-001"}, "reviewed", write=False)
    check(
        "㉚e 幂等：已是目标状态就 0 改动、指纹不变（重复跑不会二次写盘）",
        c3 == [] and fp3 == after_fp,
        f"changed={c3}",
    )


def _c30_crlf(td, sample) -> None:

    from lib.gold_review_apply import apply_file, assert_only_status_changed

    f2 = Path(td) / "grade_cases.jsonl"
    crlf_sample = sample.replace(b"\n", b"\r\n")
    f2.write_bytes(crlf_sample)
    apply_file(f2, {"qa-001"}, "reviewed", write=True)
    raw2 = f2.read_bytes()
    crlf = raw2.count(b"\r\n")
    check(
        "㉚f CRLF 文件跑完仍是纯 CRLF（无 CR CR、无裸 LF），注释行逐字节不变",
        raw2.count(b"\r\r") == 0
        and raw2.count(b"\n") == crlf
        and raw2.split(b"\r\n")[0] == crlf_sample.split(b"\r\n")[0],
        f"CRLF={crlf} 裸LF={raw2.count(chr(10).encode()) - crlf} CRCR={raw2.count(b'\r\r')}",
    )
    try:
        assert_only_status_changed(sample, sample)
        same_input_rejected = False
    except AssertionError:
        same_input_rejected = True
    check(
        "㉚g 自检：拿同一份内容做「只改了 gold_status」断言必须报错（不变量不是摆设）",
        same_input_rejected,
    )
