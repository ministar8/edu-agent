"""把 papers-rebuild + answers 重排版真题转成知识库 markdown。

产出：knowledge/questions/YYYY_408_exam.md
- 选项来自重排版试卷（文字层干净）
- 答案字母 + 解析 来自 answers/（有文字层时）
- 文首标注可信度口径（见 408-exam-paper README）
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\26452\Desktop\edu-agent")
sys.path.insert(0, str(ROOT / "src"))

PAPERS = ROOT / "knowledge" / "papers-rebuild"
ANSWERS = ROOT / "knowledge" / "answers"
OUT_DIR = ROOT / "knowledge" / "questions"

# 可信度口径（README）：大纲真题 > 第三方原题 > 回忆版
# 本仓库 papers-rebuild 为第三方重排的原题整理版；答案册单独标注文字/扫描。
CRED_PAPER = "第三方重排版原题（图像→文字重排，约 5 错/100KB）"
CRED_ANSWER_TEXT = "第三方参考答案（含文字解析）"
CRED_ANSWER_SCAN = "第三方参考答案（扫描件，无文字解析）"


def load_pdf_text(path: Path) -> str:
    if not path.exists():
        return ""
    import subprocess

    dump = (
        r"C:\Users\26452\.local\share\mimocode\builtin_skills"
        r"\desktop-1579e7d\skills\pdf-official\scripts\text_dump.py"
    )
    out = ROOT / "_exam_src" / f"{path.stem}_conv.txt"
    out.parent.mkdir(exist_ok=True)
    subprocess.run(
        [sys.executable, dump, str(path), "--out", str(out)],
        capture_output=True,
        text=True,
    )
    return out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""


def parse_answer_key(text: str) -> dict[int, str]:
    key: dict[int, str] = {}
    t = text

    # 1) 紧凑成对：1. B / 01. C / 1.C
    for m in re.finditer(r"(?<![\d.])(\d{1,2})\s*[\.、:：]\s*\**([A-D])\b", t):
        n = int(m.group(1))
        if 1 <= n <= 40:
            key.setdefault(n, m.group(2))

    # 2) 参考答案：1.【参考答案】D
    for m in re.finditer(r"(\d{1,2})\s*[\.、]?\s*【参考答案】\s*\**([A-D])", t):
        n = int(m.group(1))
        if 1 <= n <= 40:
            key[n] = m.group(2)

    # 3) 网格 + 字母串：DAAAB BCDBD DACDC ...（5 字母一组，共 8 组）
    #    出现在 一、单项选择题 之后
    section = t
    m_sec = re.search(r"单项选择题", t)
    if m_sec:
        section = t[m_sec.end() : m_sec.end() + 2500]
    for m in re.finditer(r"\b((?:[A-D]{5}\s+){3,7}[A-D]{5})\b", section):
        letters = re.sub(r"\s+", "", m.group(1))
        if 35 <= len(letters) <= 40 and set(letters) <= set("ABCD"):
            # 与已有冲突时不覆盖更明确的成对结果
            for i, ch in enumerate(letters[:40], 1):
                if i not in key:
                    key[i] = ch
    return {k: v for k, v in key.items() if 1 <= k <= 40}


def parse_explanations(text: str) -> dict[int, str]:
    out: dict[int, str] = {}
    t = text.replace("•", ".")
    patterns = [
        r"(?m)^\s*0?(\d{1,2})\s*[\.、]?\s*【解析】",
        r"(?m)^\s*0?(\d{1,2})\s*[\.、]?\s*【参考答案】\s*[A-D]\s*\**【解析】",
        r"(?m)^\s*0?(\d{1,2})\s*[\.、]\s*解析[:：]",
        r"(?m)^\s*0?(\d{1,2})\s*【解析】",
    ]
    starts: list[tuple[int, int]] = []
    for pat in patterns:
        for m in re.finditer(pat, t):
            starts.append((m.start(), int(m.group(1))))
    starts.sort()
    seen: set[int] = set()
    for i, (pos, n) in enumerate(starts):
        if n in seen or not (1 <= n <= 40):
            continue
        end = starts[i + 1][0] if i + 1 < len(starts) else min(len(t), pos + 1200)
        body = t[pos:end]
        # 去掉题号/标记头
        body = re.sub(r"^\s*0?\d{1,2}\s*[\.、]?\s*【解析】\s*", "", body)
        body = re.sub(r"^\s*0?\d{1,2}\s*[\.、]?\s*【参考答案】\s*[A-D]\s*\**【解析】\s*", "", body)
        body = re.sub(r"^\s*0?\d{1,2}\s*[\.、]\s*解析[:：]\s*", "", body)
        body = re.sub(r"第\s*\d+\s*页.*", "", body)
        body = re.sub(r"[•·]\s*\d{3}\s*[•·].*", "", body)
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        if len(body) > 20:
            out[n] = body[:800]
            seen.add(n)
    return out


def parse_paper_mcq(text: str) -> dict[int, dict]:
    """从重排版试卷抽 1-40 选择题。"""
    # 清理 <u> 标记
    t = re.sub(r"</?u>", "", text)
    t = t.replace(" ", " ")
    start = re.search(r"单项选择题", t)
    end = re.search(r"(综合应用题|解答题|二、)", t[start.end() :] if start else t)
    body = t[start.end() : start.end() + end.start()] if start and end else t

    result: dict[int, dict] = {}
    # 题号：行首 1. 或 1．
    marks = list(re.finditer(r"(?m)^\s*(\d{1,2})\s*[\.．]\s*", body))
    for i, m in enumerate(marks):
        qn = int(m.group(1))
        if not (1 <= qn <= 40) or qn in result:
            continue
        stop = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        chunk = body[m.end() : stop]
        # 选项 A. B. C. D.
        om = re.search(r"(?<![A-Za-z])A\s*[\.．]\s*", chunk)
        if not om:
            continue
        stem = re.sub(r"\s+", " ", chunk[: om.start()]).strip()
        rest = chunk[om.start() :]
        opt_marks = list(re.finditer(r"(?<![A-Za-z])([A-D])\s*[\.．]\s*", rest))
        opts: dict[str, str] = {}
        for k, omk in enumerate(opt_marks):
            letter = omk.group(1)
            if letter in opts:
                continue
            endk = opt_marks[k + 1].start() if k + 1 < len(opt_marks) else len(rest)
            opts[letter] = re.sub(r"\s+", " ", rest[omk.end() : endk]).strip()
        if set(opts) == {"A", "B", "C", "D"} and stem:
            result[qn] = {"stem": stem, "options": opts}
    return result


def build_md(year: int, mcq: dict[int, dict], answers: dict[int, str], expl: dict[int, str]) -> str:
    ans_cred = CRED_ANSWER_TEXT if expl or answers else CRED_ANSWER_SCAN
    lines = [
        f"# {year} 年全国硕士研究生招生考试 计算机学科专业基础综合（408）",
        "",
        "## 材料可信度",
        "",
        f"- 试卷：{CRED_PAPER}（`knowledge/papers-rebuild/{year}.pdf`）",
        f"- 答案：{ans_cred}",
        "- 可信度排序约定：大纲原题 > 第三方原题 > 回忆版；本卷为第三方重排原题，**非回忆版**。",
        "- 入库用途：RAG 题干/选项检索与出题批改；以选项文本为准，解析以答案册文字为准。",
        "",
        "## 一、单项选择题",
        "",
    ]
    for qn in sorted(mcq):
        item = mcq[qn]
        ans = answers.get(qn, "")
        lines.append(f"### 第{qn}题")
        lines.append("")
        lines.append(item["stem"])
        lines.append("")
        for letter in "ABCD":
            txt = item["options"][letter]
            if ans == letter:
                lines.append(f"- **{letter}. {txt}** ✅")
            else:
                lines.append(f"- {letter}. {txt}")
        lines.append("")
        lines.append("**解析**：")
        lines.append("")
        body = expl.get(qn, "")
        if body:
            lines.append(body)
        elif ans:
            lines.append(f"正确答案：{ans}。（详见 `knowledge/answers/{year}-answer.pdf`）")
        else:
            lines.append("（本卷答案册为扫描件，无文字解析；正确答案未标注。）")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for year in range(2009, 2026):
        paper = PAPERS / f"{year}.pdf"
        if not paper.exists():
            print(f"== {year}: no paper ==")
            continue
        ptxt = load_pdf_text(paper)
        mcq = parse_paper_mcq(ptxt)
        atxt = load_pdf_text(ANSWERS / f"{year}-answer.pdf")
        answers = parse_answer_key(atxt) if len(atxt) > 400 else {}
        expl = parse_explanations(atxt) if len(atxt) > 400 else {}
        md = build_md(year, mcq, answers, expl)
        out = OUT_DIR / f"{year}_408_exam.md"
        out.write_text(md, encoding="utf-8")
        print(f"== {year}: mcq={len(mcq)} answers={len(answers)} expl={len(expl)} -> {out.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
