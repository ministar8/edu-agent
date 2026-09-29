"""gap 回填：KP 人工锚定 + 答案键二次抽取；定点更新 items 与 gap_inventory。

用法：
    uv run python scripts/fill_gaps.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_exams_year import (  # noqa: E402
    infer_answer_from_text,
    parse_answer_booklet,
    parse_questions,
)

# 2009–2025 KP 缺口人工锚定（question_id → (subject, kp_ids)）
# 时间复杂度等无 KP 单元的题保持空，继续记 gap
KP_BACKFILL: dict[str, tuple[str, list[str]]] = {
    "2009-Q7": ("ds", ["ds.graph"]),
    "2009-Q35": ("cn", ["cn.datalink.flow_control"]),
    "2010-Q5": ("ds", ["ds.tree"]),
    "2010-Q7": ("ds", ["ds.graph"]),
    "2010-Q15": ("co", ["co.storage.main_memory"]),
    "2011-Q22": ("co", ["co.io.interface"]),
    "2011-Q34": ("cn", ["cn.physical.bandwidth"]),
    "2012-Q9": ("ds", ["ds.search.b_tree"]),
    "2012-Q12": ("co", ["co.overview.performance"]),
    "2012-Q16": ("co", ["co.storage.main_memory"]),
    "2012-Q29": ("os", ["os.process.schedule"]),
    "2012-Q34": ("cn", ["cn.physical.channel"]),
    "2013-Q4": ("ds", ["ds.tree.huffman"]),
    "2013-Q19": ("co", ["co.io.interface"]),
    "2013-Q24": ("os", ["os.file.alloc"]),
    "2013-Q29": ("os", ["os.overview"]),
    "2013-Q34": ("cn", ["cn.datalink.ethernet"]),
    "2013-Q37": ("cn", ["cn.datalink.framing"]),
    "2014-Q6": ("ds", ["ds.tree.huffman"]),
    "2014-Q18": ("co", ["co.cpu.controller"]),
    "2014-Q27": ("os", ["os.file.disk_free_space"]),
    "2014-Q35": ("cn", ["cn.physical.bandwidth"]),
    "2015-Q31": ("os", ["os.file.disk_free_space"]),
    "2015-Q34": ("cn", ["cn.physical.channel"]),
    "2016-Q3": ("ds", ["ds.stack_queue.stack"]),
    "2016-Q4": ("ds", ["ds.array.compressed"]),
    "2016-Q12": ("co", ["co.instruction.isa"]),
    "2016-Q35": ("cn", ["cn.datalink.ethernet"]),
    "2017-Q7": ("ds", ["ds.graph"]),
    "2017-Q14": ("co", ["co.representation.ieee754"]),
    "2017-Q26": ("os", ["os.file.alloc"]),
    "2017-Q28": ("os", ["os.overview.feature"]),
    "2017-Q34": ("cn", ["cn.physical.bandwidth"]),
    "2018-Q16": ("co", ["co.representation.integer_op"]),
    "2018-Q23": ("os", ["os.overview.feature"]),
    "2018-Q34": ("cn", ["cn.physical.channel"]),
    "2022-Q4": ("ds", ["ds.tree.binary_tree"]),
    "2022-Q6": ("ds", ["ds.graph"]),
    "2023-Q1": ("ds", ["ds.search.seq"]),
    "2023-Q13": ("co", ["co.representation.complement"]),
    "2023-Q23": ("os", ["os.overview.feature"]),
    "2023-Q25": ("os", ["os.memory.allocate"]),
    "2023-Q30": ("os", ["os.memory.paging"]),
    "2021-Q3": ("ds", ["ds.array.compressed"]),
    "2021-Q10": ("ds", ["ds.sort.radix"]),
    "2021-Q34": ("cn", ["cn.physical.channel"]),
    "2024-Q2": ("ds", ["ds.stack_queue.stack"]),
    "2024-Q4": ("ds", ["ds.graph.storage"]),
    "2024-Q7": ("ds", ["ds.tree.bst"]),
    "2024-Q34": ("cn", ["cn.physical.channel"]),
    "2025-Q7": ("ds", ["ds.search.block"]),
    "2025-Q24": ("os", ["os.overview.feature"]),
    "2025-Q30": ("os", ["os.memory.virtual"]),
    # 2009-Q7 图性质已标；无「时间复杂度」KP 的题保持 gap：
    # 2011-Q1 / 2012-Q1 / 2014-Q1 / 2017-Q1 / 2019-Q1 / 2022-Q1 / 2025-Q1
}

# 更宽的答案键抽取（在 build 规则之外补）
ANSWER_EXTRA_PATS = [
    r"选\s*[（(]?([A-D])[）)]?\s*(?:[。．.、]|$)",
    r"故\s*[（(]?([A-D])[）)]?\s*(?:[。．.、]|$)",
    r"选项\s*[（(]?([A-D])[）)]?\s*(?:正确|错误)",
]


def extract_more_answer(text: str) -> str | None:
    if not text:
        return None
    a = infer_answer_from_text(text)
    if a:
        return a
    for pat in ANSWER_EXTRA_PATS:
        ms = re.findall(pat, text)
        if len(ms) == 1:
            return ms[0]
    # 「正确的是 A」类
    m = re.search(r"(?:正确|错误)的(?:是|选项)[^A-D]{0,6}([A-D])", text)
    if m:
        return m.group(1)
    return None


def load_kp_ids() -> set[str]:
    ids = set()
    for p in (ROOT / "knowledge/knowledge_points").glob("*.jsonl"):
        if p.name == "links.jsonl":
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                ids.add(json.loads(line)["id"])
    return ids


def update_items_file(year: int, updates: dict[str, dict]) -> int:
    """updates: qid -> {kp_ids?, subject?, answer_key?}"""
    path = ROOT / "knowledge/exams" / str(year) / "items.md"
    text = path.read_text(encoding="utf-8")
    n = 0
    for qid, upd in updates.items():
        m = re.search(rf"(?m)^## {re.escape(qid)}\s*$\n\n(.*?)(?=\n---|\n## |\Z)", text, re.S)
        if not m:
            continue
        block = m.group(1)
        new = block
        if "kp_ids" in upd:
            kps = upd["kp_ids"]
            new = re.sub(
                r"> kp_ids: \[[^\]]*\]",
                f"> kp_ids: [{', '.join(kps)}]",
                new,
            )
        if "subject" in upd:
            new = re.sub(r"> subject: \S+", f"> subject: {upd['subject']}", new)
        if "answer_key" in upd:
            ak = upd["answer_key"] or "null"
            new = re.sub(r"> answer_key: \S+", f"> answer_key: {ak}", new)
            # 有答案则 completeness 可升
            if ak != "null" and "answer" not in (
                re.search(r"> gap_fields: \[([^\]]*)\]", new).group(1)
                if re.search(r"> gap_fields: \[([^\]]*)\]", new)
                else ""
            ):
                pass
            # 同步 gap_fields / completeness
            gf_m = re.search(r"> gap_fields: \[([^\]]*)\]", new)
            if gf_m and ak != "null":
                fields = [
                    x.strip()
                    for x in gf_m.group(1).split(",")
                    if x.strip() and x.strip() != "answer"
                ]
                new = re.sub(
                    r"> gap_fields: \[[^\]]*\]", f"> gap_fields: [{', '.join(fields)}]", new
                )
                if not fields:
                    new = re.sub(r"> completeness: \S+", "> completeness: complete", new)
                    new = re.sub(r"> gap_status: \S+", "> gap_status: none", new)
                else:
                    new = re.sub(r"> completeness: \S+", "> completeness: partial", new)
                    new = re.sub(r"> gap_status: \S+", "> gap_status: partial", new)
        if new != block:
            text = text[: m.start(1)] + new + text[m.end(1) :]
            n += 1
    if n:
        path.write_text(text, encoding="utf-8")
    return n


def main() -> int:  # noqa: C901
    kp_ids = load_kp_ids()
    # 1) KP 回填
    by_year: dict[int, dict[str, dict]] = {}
    for qid, (subj, kps) in KP_BACKFILL.items():
        bad = [k for k in kps if k not in kp_ids]
        if bad:
            print("SKIP bad kp", qid, bad)
            continue
        year = int(qid.split("-")[0])
        by_year.setdefault(year, {})[qid] = {"kp_ids": kps, "subject": subj}

    # 2) 答案键二次抽取（仅对仍缺答案的题）
    for year_dir in sorted((ROOT / "knowledge/exams").iterdir()):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        year = int(year_dir.name)
        qsrc = ROOT / "knowledge/questions" / f"{year}_408_exam.md"
        if not qsrc.exists():
            continue
        qs = {
            q["num"]: q for q in parse_questions(qsrc.read_text(encoding="utf-8", errors="replace"))
        }
        exps, table_ans = parse_answer_booklet(ROOT / "knowledge" / "answers" / f"{year}-answer.md")
        items_text = (year_dir / "items.md").read_text(encoding="utf-8")
        for n, q in qs.items():
            qid = f"{year}-Q{n}"
            if "> answer_key: null" not in items_text.split(f"## {qid}")[-1][:800]:
                continue
            cand = q.get("answer_key") or table_ans.get(n) or ""
            if not cand:
                cand = (
                    extract_more_answer((q.get("inline_exp") or "") + "\n" + (exps.get(n) or ""))
                    or ""
                )
            if cand:
                by_year.setdefault(year, {}).setdefault(qid, {})["answer_key"] = cand

    for year, upd in by_year.items():
        n = update_items_file(year, upd)
        print(f"year={year} updated_sections={n}")

    # 3) 重建 gap_inventory：按 items 现状重算 open/filled
    inv_path = ROOT / "knowledge/exams" / "gap_inventory.jsonl"
    old = [json.loads(x) for x in inv_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    old_by_key = {
        (e.get("asset"), e.get("gap_type"), tuple(e.get("gap_fields") or [])): e for e in old
    }

    new_rows: list[dict] = []
    for year_dir in sorted((ROOT / "knowledge/exams").iterdir()):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        year = int(year_dir.name)
        items_text = (year_dir / "items.md").read_text(encoding="utf-8")
        for m in re.finditer(
            r"(?m)^## (\d{4}-Q\d+)\s*$\n\n(.*?)(?=\n---|\n## |\Z)", items_text, re.S
        ):
            qid, body = m.group(1), m.group(2)
            asset = f"question:{qid}"
            ak_m = re.search(r"> answer_key: (\S+)", body)
            ak = ak_m.group(1) if ak_m else "null"
            kps_m = re.search(r"> kp_ids: \[([^\]]*)\]", body)
            kps = [x.strip() for x in (kps_m.group(1) if kps_m else "").split(",") if x.strip()]
            gf_m = re.search(r"> gap_fields: \[([^\]]*)\]", body)
            gfs = [x.strip() for x in (gf_m.group(1) if gf_m else "").split(",") if x.strip()]

            def emit(gtype, fields, note=""):
                key = (asset, gtype, tuple(fields))
                old_e = old_by_key.get(key)
                status = "open"
                filled_at = ""
                if old_e and old_e.get("status") == "filled":
                    status = "filled"
                    filled_at = old_e.get("filled_at") or ""
                # 若字段已不在 gap_fields，视为可关闭
                if gtype == "answer" and ak != "null":
                    status = "filled"
                    filled_at = "2026-09-28"
                if gtype == "knowledge_points" and kps:
                    status = "filled"
                    filled_at = "2026-09-28"
                if gtype == "figure" and "figure" not in gfs:
                    status = "filled"
                    filled_at = "2026-09-28"
                if gtype == "question_body" and not any(
                    x in gfs for x in ("stem", "options", "sub_questions")
                ):
                    status = "filled"
                    filled_at = "2026-09-28"
                row = {
                    "asset": asset,
                    "year": year,
                    "gap_type": gtype,
                    "gap_fields": fields,
                    "completeness": "partial" if status == "open" else "complete",
                    "source": f"knowledge/exams/{year}/items.md",
                    "note": note,
                    "status": status,
                }
                if filled_at:
                    row["filled_at"] = filled_at
                new_rows.append(row)

            if ak == "null":
                emit("answer", ["answer"])
            else:
                if qid in KP_BACKFILL or (asset, "answer", ("answer",)) in old_by_key:
                    pass
                # 答案已有时：若此前 open 则补 filled（用 KP_BACKFILL/二次抽取）
                key = (asset, "answer", ("answer",))
                if key in old_by_key and old_by_key[key].get("status") == "open":
                    new_rows.append(
                        {
                            **old_by_key[key],
                            "status": "filled",
                            "filled_at": "2026-09-28",
                            "filled_source": "fill_gaps",
                        }
                    )
            if not kps:
                emit("knowledge_points", ["kp_ids"], "无法锚定或无 KP 单元（如时间复杂度）")
            else:
                if qid in KP_BACKFILL:
                    new_rows.append(
                        {
                            "asset": asset,
                            "year": year,
                            "gap_type": "knowledge_points",
                            "gap_fields": ["kp_ids"],
                            "completeness": "complete",
                            "source": f"knowledge/exams/{year}/items.md",
                            "note": "KP 锚定回填",
                            "status": "filled",
                            "filled_at": "2026-09-28",
                            "filled_source": "fill_gaps",
                        }
                    )
                key = (asset, "knowledge_points", ("kp_ids",))
                if key in old_by_key and old_by_key[key].get("status") == "open":
                    new_rows.append(
                        {
                            **old_by_key[key],
                            "status": "filled",
                            "filled_at": "2026-09-28",
                            "filled_source": "fill_gaps",
                        }
                    )
            for gf in gfs:
                gt = "question_body" if gf in ("stem", "options", "sub_questions") else gf
                emit(gt, [gf])
        # comprehensive 年卷缺口
        for e in old:
            if e.get("year") == year and e.get("gap_type") == "comprehensive":
                new_rows.append(e)

    # 去重
    uniq = {}
    for r in new_rows:
        uniq[(r["asset"], r["gap_type"], tuple(r.get("gap_fields") or []))] = r
    out = list(uniq.values())
    inv_path.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in out) + "\n",
        encoding="utf-8",
    )
    from collections import Counter

    print("inventory", len(out), Counter(r["status"] for r in out))
    print("open types", Counter(r["gap_type"] for r in out if r["status"] == "open"))
    print("filled types", Counter(r["gap_type"] for r in out if r["status"] == "filled"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
