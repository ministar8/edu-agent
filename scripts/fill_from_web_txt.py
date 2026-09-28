"""解析已抓取的 web_YYYY.txt，回填知识库选项或生成新年份卷。"""

from __future__ import annotations

import json
import re
from pathlib import Path

KB = Path(r"C:\Users\26452\Desktop\edu-agent\knowledge\questions")
OUT = Path(r"C:\Users\26452\Desktop\edu-agent\_exam_src")
OPT = "（选项缺失）"


def parse_mcq(text: str) -> dict[int, dict]:
    ans_map: dict[int, str] = {}
    m = re.search(r"选择题答案速对(.{0,500}?)数据结构", text, re.S)
    if m:
        for n, a in re.findall(r"(\d{1,2})([A-D])", m.group(1)):
            ans_map[int(n)] = a

    start = text.find("选择题答案速对")
    end = text.find("解答题")
    body = text[start:end] if end > start else (text[start:] if start >= 0 else text)

    parts = re.split(r"(?m)^(\d{1,2})\s*$", body)
    result: dict[int, dict] = {}
    for i in range(1, len(parts) - 1, 2):
        qnum = int(parts[i])
        if not (1 <= qnum <= 40):
            continue
        chunk = parts[i + 1]
        head = re.split(r"查看答案|正确答案", chunk)[0]
        mo = re.search(r"(?m)^\s*([ABCD])\s*[\.、．]\s*$", head)
        if not mo:
            mo = re.search(r"(?m)^\s*([ABCD])\s*[\.、．]\s*", head)
        if not mo:
            continue
        stem = re.sub(r"\s+", " ", head[: mo.start()]).strip()
        rest = head[mo.start() :]
        marks = list(re.finditer(r"(?m)^\s*([ABCD])\s*[\.、．]\s*", rest))
        if not marks:
            marks = list(re.finditer(r"(?<![A-Za-z])([ABCD])\s*[\.、．]\s*", rest))
        opts: dict[str, str] = {}
        for k, mm in enumerate(marks):
            letter = mm.group(1)
            if letter in opts:
                continue
            stop = marks[k + 1].start() if k + 1 < len(marks) else len(rest)
            body_txt = re.sub(r"\s+", " ", rest[mm.end() : stop]).strip()
            opts[letter] = body_txt
        if set(opts) != {"A", "B", "C", "D"}:
            continue
        ans = ans_map.get(qnum, "")
        am = re.search(r"正确答案[:：]\s*\**([A-D])", chunk)
        if am:
            ans = am.group(1)
        result[qnum] = {"stem": stem, "options": opts, "answer": ans}
    return result


def fill_kb(year: int, parsed: dict[int, dict]) -> tuple[int, int, list[str]]:
    path = KB / f"{year}_408_exam.md"
    if not path.exists():
        return 0, 0, ["no kb file"]
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    starts = [
        (i, int(m.group(1)))
        for i, ln in enumerate(lines)
        if (m := re.match(r"###\s*第(\d+)题", ln))
    ]
    filled = skipped = 0
    notes: list[str] = []
    out = list(lines)
    for idx, (i, qn) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        block = "\n".join(out[i:end])
        if OPT not in block:
            continue
        info = parsed.get(qn)
        if not info:
            skipped += 1
            notes.append(f"  第{qn}题: web无此题")
            continue
        slots = []
        for j in range(i, end):
            if OPT in out[j] and re.match(r"^[ \t]*[-*+]?\s*\*{0,2}[A-E]", out[j]):
                slots.append(j)
        if len(slots) != 4:
            skipped += 1
            notes.append(f"  第{qn}题: 槽位={len(slots)}")
            continue
        ok = True
        for j in slots:
            m = re.match(
                r"^([ \t]*[-*+]?\s*)(\*{0,2})([A-E])([.、)．])([ \t]*)(\*{0,2})(（选项缺失）)(\*{0,2})(.*)$",
                out[j],
            )
            if not m or m.group(3) not in info["options"]:
                ok = False
                break
            pre, b1, letter, dot, sp, b2, _ph, b3, post = m.groups()
            post = (post or "").strip()
            pfx_m = re.match(r"^([ \t]*[-*+]?\s*)", out[j])
            pfx = pfx_m.group(1) if pfx_m else "- "
            core = f"{letter}{dot} {info['options'][letter]}"
            bold = bool(b1 or b2 or b3) or "**" in out[j]
            body = f"{pfx}**{core}**" if bold else f"{pfx}{core}"
            if post:
                body = f"{body} {post}"
            out[j] = body
        if not ok:
            skipped += 1
            continue
        filled += 1
        notes.append(f"  第{qn}题: OK {info['options']}")
    if out != lines:
        path.write_text("\n".join(out) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
    return filled, skipped, notes


def write_new_year(year: int, parsed: dict[int, dict]) -> str:
    path = KB / f"{year}_408_exam.md"
    if path.exists():
        return "exists"
    lines = [
        f"# {year} 年全国硕士研究生招生考试 计算机学科专业基础综合（408）",
        "",
        "> 来源：csgraduates.com 408 历年真题（2026-09-28 整理入库）",
        "",
        "## 一、单项选择题",
        "",
    ]
    for qn in sorted(parsed):
        item = parsed[qn]
        lines.append(f"### 第{qn}题")
        lines.append("")
        lines.append(item["stem"])
        lines.append("")
        for letter in "ABCD":
            txt = item["options"][letter]
            if item.get("answer") == letter:
                lines.append(f"- **{letter}. {txt}** ✅")
            else:
                lines.append(f"- {letter}. {txt}")
        lines.append("")
        lines.append("**解析**：")
        lines.append("")
        lines.append(f"正确答案：{item.get('answer') or '?'}。")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return f"created {len(parsed)} mcq"


def main() -> int:
    summary = []
    for year in range(2019, 2026):
        src = OUT / f"web_{year}.txt"
        if not src.exists():
            print(f"== {year}: no text ==")
            continue
        text = src.read_text(encoding="utf-8", errors="replace")
        parsed = parse_mcq(text)
        print(f"== {year}: parsed {len(parsed)} mcq ==")
        (OUT / f"web_{year}_parsed.json").write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if not parsed:
            continue
        if (KB / f"{year}_408_exam.md").exists():
            f, s, notes = fill_kb(year, parsed)
            for n in notes[:20]:
                print(n)
            print(f"  -> filled={f} skipped={s}")
            summary.append((year, f, s))
        else:
            msg = write_new_year(year, parsed)
            print(" ", msg)
            summary.append((year, "create", len(parsed)))
    print("SUMMARY", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
