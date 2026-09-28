"""从 web_YYYY.txt 稳健解析选择题（以「查看答案」为题末边界）。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fill_from_web_txt import fill_kb, write_new_year  # noqa: E402

KB = Path(r"C:\Users\26452\Desktop\edu-agent\knowledge\questions")
OUT = Path(r"C:\Users\26452\Desktop\edu-agent\_exam_src")
OPT = "（选项缺失）"


def parse_mcq(text: str) -> dict[int, dict]:
    ans_map: dict[int, str] = {}
    m = re.search(r"选择题答案速对(.{0,500}?)数据结构", text, re.S)
    if m:
        for n, a in re.findall(r"(\d{1,2})([A-D])", m.group(1)):
            if 1 <= int(n) <= 40:
                ans_map[int(n)] = a

    start = text.find("选择题答案速对")
    end = text.find("解答题")
    body = text[start:end] if end > start else (text[start:] if start >= 0 else text)

    # 题末固定为 查看答案与解析
    chunks = re.split(r"查看答案与解析", body)
    result: dict[int, dict] = {}
    used_nums: set[int] = set()
    for chunk in chunks:
        # 题号：chunk 里第一次出现「行首 1-40」且后面像题干
        qnum = None
        for m in re.finditer(r"(?m)^(\d{1,2})\s*\n", chunk):
            n = int(m.group(1))
            if not (1 <= n <= 40) or n in used_nums:
                continue
            after = chunk[m.end() : m.end() + 80]
            if re.match(r"^\s*[一-鿿A-Za-z`（(]", after):
                qnum = n
                stem_start = m.end()
                break
        if qnum is None:
            continue
        head = chunk[stem_start:]
        mo = re.search(r"(?m)^\s*([ABCD])\s*[\.、．]", head)
        if not mo:
            continue
        stem = re.sub(r"\s+", " ", head[: mo.start()]).strip()
        rest = head[mo.start() :]
        marks = list(re.finditer(r"(?m)^\s*([ABCD])\s*[\.、．]\s*", rest))
        if len(marks) < 4:
            marks = list(re.finditer(r"(?<![A-Za-z])([ABCD])\s*[\.、．]\s*", rest))
        opts: dict[str, str] = {}
        for k, mm in enumerate(marks):
            letter = mm.group(1)
            if letter in opts:
                continue
            stop = marks[k + 1].start() if k + 1 < len(marks) else len(rest)
            opts[letter] = re.sub(r"\s+", " ", rest[mm.end() : stop]).strip()
        if set(opts) != {"A", "B", "C", "D"}:
            continue
        ans = ans_map.get(qnum, "")
        # 同 chunk 末尾可能已带 正确答案（若 split 没切到）
        am = re.search(r"正确答案[:：]\s*\**([A-D])", chunk)
        if am:
            ans = am.group(1)
        result[qnum] = {"stem": stem, "options": opts, "answer": ans}
        used_nums.add(qnum)
    return result


def main() -> int:
    # 重新填充所有年份
    from fill_from_web_txt import parse_mcq as _old  # noqa: F401

    summary = []
    for year in range(2019, 2026):
        src = OUT / f"web_{year}.txt"
        if not src.exists():
            continue
        text = src.read_text(encoding="utf-8", errors="replace")
        parsed = parse_mcq(text)
        print(f"== {year}: parsed {len(parsed)} == {sorted(parsed)}")
        (OUT / f"web_{year}_parsed.json").write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if not parsed:
            continue
        if (KB / f"{year}_408_exam.md").exists():
            f, s, notes = fill_kb(year, parsed)
            for n in notes:
                print(n)
            print(f"  -> filled={f} skipped={s}")
            summary.append((year, f, s))
        else:
            print(" ", write_new_year(year, parsed))
    print("SUMMARY", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
