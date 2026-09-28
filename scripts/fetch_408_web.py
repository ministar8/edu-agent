"""从 csgraduates 408 真题页抽取选择题选项，回填知识库 / 生成新卷。"""

from __future__ import annotations

import json
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

KB = Path(r"C:\Users\26452\Desktop\edu-agent\knowledge\questions")
OUT = Path(r"C:\Users\26452\Desktop\edu-agent\_exam_src")
OPT = "（选项缺失）"
UA = {"User-Agent": "Mozilla/5.0 (compatible; edu-agent/1.0)"}

BASE = "https://www.csgraduates.com/study_methods/408quiz/{year}/"
YEARS = [2019, 2020, 2021, 2022, 2023, 2024, 2025]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"}:
            self.chunks.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.chunks.append(data)


def fetch(year: int) -> str:
    url = BASE.format(year=year)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    html = raw.decode("utf-8", errors="replace")
    (OUT / f"web_{year}.html").write_text(html, encoding="utf-8")
    parser = TextExtractor()
    parser.feed(html)
    text = "".join(parser.chunks)
    text = re.sub(r"\n{3,}", "\n\n", text)
    (OUT / f"web_{year}.txt").write_text(text, encoding="utf-8")
    return text


def parse_mcq(text: str) -> dict[int, dict]:
    """从页面文本解析 题号 → {stem, options, answer}。

    形态：##### N  ... A. xxx B. xxx ... 正确答案：X
    """
    # 定位「##### 1」到「解答题」之间的选择题区
    start = text.find("##### 1")
    end = text.find("解答题")
    if start < 0:
        return {}
    body = text[start:end] if end > start else text[start:]

    # 按 ##### N 切分
    parts = re.split(r"(?m)^#{5}\s+(\d{1,2})\s*$", body)
    result: dict[int, dict] = {}
    # parts: [pre, num, chunk, num, chunk, ...]
    for i in range(1, len(parts) - 1, 2):
        qnum = int(parts[i])
        chunk = parts[i + 1]
        # stem：到第一个 A. 之前
        m_opt = re.search(r"(?m)^\s*([ABCD])\s*[\.、．]\s*", chunk)
        if not m_opt:
            m_opt = re.search(r"\s([ABCD])\s*[\.、．]\s*", chunk)
        if not m_opt:
            continue
        stem = chunk[: m_opt.start()].strip()
        stem = re.sub(r"\[.*?\]\([^)]*\)", "", stem)  # 去链接
        stem = re.sub(r"!\[.*?\]\([^)]*\)", "", stem)
        stem = re.sub(r"\s+", " ", stem).strip()

        # 选项：A. ... B. ... C. ... D. ...
        opt_region = chunk[m_opt.start() :]
        # 在「正确答案」或「查看答案」前截断
        opt_region = re.split(r"正确答案|查看答案|收藏", opt_region)[0]
        marks = list(re.finditer(r"(?<![A-Za-z])([ABCD])\s*[\.、．]\s*", opt_region))
        opts: dict[str, str] = {}
        for k, m in enumerate(marks):
            letter = m.group(1)
            if letter in opts:
                continue
            stop = marks[k + 1].start() if k + 1 < len(marks) else len(opt_region)
            body_txt = opt_region[m.end() : stop]
            body_txt = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", body_txt)
            body_txt = re.sub(r"!\[.*?\]\([^)]*\)", "", body_txt)
            body_txt = re.sub(r"\s+", " ", body_txt).strip()
            opts[letter] = body_txt
        if set(opts) != {"A", "B", "C", "D"}:
            continue

        ans_m = re.search(r"正确答案[:：]\s*\**([A-D])", chunk)
        answer = ans_m.group(1) if ans_m else ""
        result[qnum] = {"stem": stem, "options": opts, "answer": answer}
    return result


def fill_kb(year: int, parsed: dict[int, dict]) -> tuple[int, int]:
    path = KB / f"{year}_408_exam.md"
    if not path.exists():
        return 0, 0
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    starts = [
        (i, int(m.group(1)))
        for i, ln in enumerate(lines)
        if (m := re.match(r"###\s*第(\d+)题", ln))
    ]
    filled = skipped = 0
    out = list(lines)
    for idx, (i, qn) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        block = "\n".join(out[i:end])
        if OPT not in block:
            continue
        info = parsed.get(qn)
        if not info:
            skipped += 1
            continue
        slots = [
            j
            for j in range(i, end)
            if OPT in out[j] and re.match(r"^[ \t]*[-*+]?\s*\*{0,2}[A-E]", out[j])
        ]
        if len(slots) != 4:
            skipped += 1
            continue
        for j in slots:
            m = re.match(
                r"^([ \t]*[-*+]?\s*)(\*{0,2})([A-E])([.、)．])([ \t]*)(\*{0,2})(（选项缺失）)(\*{0,2})(.*)$",
                out[j],
            )
            if not m:
                skipped += 1
                continue
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
        filled += 1
    if out != lines:
        path.write_text("\n".join(out) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
    return filled, skipped


def write_new_year(year: int, parsed: dict[int, dict]) -> str:
    path = KB / f"{year}_408_exam.md"
    if path.exists():
        return f"{path.name} already exists, skip create"
    lines = [
        f"# {year} 年全国硕士研究生招生考试 计算机学科专业基础综合（408）",
        "",
        "> 来源：csgraduates.com 408 历年真题（整理入库）",
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
            mark = (
                f"**{letter}. {item['options'][letter]}**"
                if item["answer"] == letter
                else f"{letter}. {item['options'][letter]}"
            )
            suf = " ✅" if item["answer"] == letter else ""
            lines.append(f"- {mark}{suf}")
        lines.append("")
        lines.append("**解析**：")
        lines.append("")
        if item["answer"]:
            lines.append(f"正确答案：{item['answer']}。（详细解析见来源站）")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return f"created {path.name} with {len(parsed)} mcq"


def main() -> int:
    OUT.mkdir(exist_ok=True)
    summary = []
    for year in YEARS:
        print(f"== fetch {year} ==")
        try:
            text = fetch(year)
        except Exception as e:
            print("  fetch fail", e)
            continue
        parsed = parse_mcq(text)
        print(f"  parsed {len(parsed)} mcq, sample keys {list(parsed)[:5]}")
        (OUT / f"web_{year}_parsed.json").write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if not parsed:
            continue
        if (KB / f"{year}_408_exam.md").exists():
            f, s = fill_kb(year, parsed)
            print(f"  fill_kb filled={f} skipped={s}")
            summary.append((year, "fill", f, s))
        else:
            msg = write_new_year(year, parsed)
            print(" ", msg)
            summary.append((year, "create", len(parsed), 0))
    print("\nSUMMARY", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
