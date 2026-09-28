"""从真题源文本抽取「题号 → 选项」，回填知识库占位符。

匹配键：年份 + 题号（`### 第N题`）。
只在源文本能抽出 **恰好 4 个选项** 且字母齐全时写入；否则跳过并记录。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

KB = Path(r"C:\Users\26452\Desktop\edu-agent\knowledge\questions")
SRC = Path(r"C:\Users\26452\Desktop\edu-agent\_exam_src")
OPT = "（选项缺失）"

# 源里选项分隔：A. / A． / A、 / A 锛? / A锛? 等（PDF 抽取常见变体）
LETTER = r"[ABCD]"
# 宽松字母后缀
OPT_SPLIT = re.compile(
    r"(?<![A-Za-z])([ABCD])\s*[.、．锛?锛�:：]\s*",
    re.UNICODE,
)
# 题号：1． / 1. / 01. / 1锛?
QNUM = re.compile(r"(?m)(?:^|\n)\s*(\d{1,2})\s*[.、．锛?锛�]\s*")

KB_QNUM = re.compile(r"###\s*第(\d+)题")
KB_SLOT = re.compile(
    r"^([ \t]*[-*+]?\s*)(\*{0,2})([A-E])([.、)．])([ \t]*)(\*{0,2})(（选项缺失）)(\*{0,2})(.*)$"
)


def clean_opt(s: str) -> str:
    s = s.replace("\xa0", " ").strip()
    # 去掉 PDF 二进制/控制字符噪声（2022 扫描层混入）
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", s)
    s = re.sub(r"---\s*page\s*\d+\s*---", " ", s)
    s = re.sub(r"·\s*\d+\s*·", " ", s)
    s = re.sub(r"\s+", " ", s)
    # 若清洗后出现 { 或大量 latin-1 噪声，截到正常选项边界
    s = re.split(r"\{|\\x|ÿ", s)[0]
    return s.strip(" 　;；.")


def parse_options_from_source(text: str) -> dict[int, dict[str, str]]:
    """抽取选择题选项。返回 {题号: {A:..,B:..,C:..,D:..}}。"""
    # 归一全角句点与 PDF 噪声
    t = text.replace("锛?", ":").replace("锛�", ":").replace("锛?", ":")
    t = t.replace("．", ".").replace("。", ".")
    # 找所有选项字母位置
    marks = [(m.start(), m.group(1)) for m in re.finditer(r"(?<![A-Za-z])([ABCD])\s*[.、:：]", t)]
    # 找题号位置（行首数字 + 点）
    qmarks = [(m.start(), int(m.group(1))) for m in QNUM.finditer(t)]

    result: dict[int, dict[str, str]] = {}
    for qi, (qpos, qnum) in enumerate(qmarks):
        end = qmarks[qi + 1][0] if qi + 1 < len(qmarks) else len(t)
        chunk = t[qpos:end]
        # 只看题干后的选项区：从第一次出现 A. 开始
        local = []
        for pos, letter in marks:
            if qpos < pos < end:
                local.append((pos - qpos, letter))
        if len(local) < 4:
            continue
        # 取连续 A B C D
        opts: dict[str, str] = {}
        for i in range(len(local) - 3):
            seq = [local[i + k][1] for k in range(4)]
            if seq == ["A", "B", "C", "D"]:
                for k in range(4):
                    start = local[i + k][0]
                    stop = local[i + k + 1][0] if k < 3 else (local[i + 3][0] + 200)
                    # 选项正文在字母标记之后
                    m = re.match(r"[ABCD]\s*[.、:：]\s*", chunk[start:])
                    body_start = start + (m.end() if m else 3)
                    body = chunk[body_start:stop]
                    # 截断解析/答案标记
                    body = re.split(r"【答案】|【解析】|答案[:：]|解析[:：]|知识点", body)[0]
                    opts[seq[k]] = clean_opt(body)
                break
        if len(opts) == 4 and all(opts[x] for x in "ABCD"):
            # 避免题干/过长噪声
            if all(len(opts[x]) <= 60 for x in "ABCD"):
                result[qnum] = opts
    return result


def fill_kb(
    year_file: str, src_opts: dict[int, dict[str, str]], *, apply: bool
) -> tuple[int, int, list[str]]:
    path = KB / year_file
    if not path.exists():
        return 0, 0, [f"missing kb file {year_file}"]
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    # 题块起止
    q_spans: list[tuple[int, int, int]] = []  # (qnum, start, end)
    starts = [(i, int(m.group(1))) for i, ln in enumerate(lines) if (m := KB_QNUM.match(ln))]
    for idx, (i, qn) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
        q_spans.append((qn, i, end))

    filled = skipped = 0
    notes: list[str] = []
    out = list(lines)
    for qn, qs, qe in q_spans:
        block_has_opt = any(OPT in out[j] for j in range(qs, qe))
        if not block_has_opt:
            continue
        opts = src_opts.get(qn)
        if not opts:
            skipped += 1
            notes.append(f"  第{qn}题: 源无可用选项")
            continue
        # 找槽位
        slots = [j for j in range(qs, qe) if KB_SLOT.match(out[j]) and OPT in out[j]]
        if len(slots) != 4:
            skipped += 1
            notes.append(f"  第{qn}题: 槽位数={len(slots)}≠4")
            continue
        for j in slots:
            m = KB_SLOT.match(out[j])
            assert m
            pre, b1, letter, dot, sp, b2, _ph, b3, post = m.groups()
            post = (post or "").strip()
            prefix = re.match(r"^([ \t]*[-*+]?\s*)", out[j])
            pfx = prefix.group(1) if prefix else "- "
            core = f"{letter}{dot} {opts[letter]}"
            bold = bool(b1 or b2 or b3) or "**" in out[j]
            body = f"{pfx}**{core}**" if bold else f"{pfx}{core}"
            if post:
                body = f"{body} {post}"
            out[j] = body
        filled += 1
        notes.append(f"  第{qn}题: 已填 {opts}")

    if apply and out != lines:
        path.write_text("\n".join(out) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
    return filled, skipped, notes


def main() -> int:
    apply = "--apply" in sys.argv
    # 源文本映射
    srcs = {
        "2019_408_exam.md": SRC / "2019.txt",
        "2020_408_exam.md": SRC / "2020.txt",
        "2022_408_exam.md": SRC / "2022.txt",
        "2023_408_exam.md": SRC / "2023.txt",
        "2024_408_exam.md": SRC / "2024.txt",
    }
    total_f = total_s = 0
    for kb_name, src_path in srcs.items():
        if not src_path.exists():
            print(f"== {kb_name}: no src ==")
            continue
        raw = src_path.read_text(encoding="utf-8", errors="replace")
        src_opts = parse_options_from_source(raw)
        print(f"== {kb_name}  源解析出 {len(src_opts)} 题选项 ==")
        f, s, notes = fill_kb(kb_name, src_opts, apply=apply)
        total_f += f
        total_s += s
        for n in notes[:30]:
            print(n)
        if len(notes) > 30:
            print(f"  ... +{len(notes) - 30} more")
        print(f"  -> filled={f} skipped={s}")
    print(f"\n合计 filled={total_f} skipped={total_s}  mode={'APPLY' if apply else 'PREVIEW'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
