"""真题选项占位符：仅在「上方裸行数 == 选项槽数」时回填。

不做「取末 N 行」启发式 —— 源文件缺选项时会静默错配（见 RETRIEVAL_ROADMAP 不做清单）。
只回填可证明安全的子集：紧邻占位选项块上方、数量对齐、且不是题干噪声的裸行。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\26452\Desktop\edu-agent\knowledge\questions")
OPT = "（选项缺失）"
OPT_SLOT = re.compile(
    r"^([ \t]*[-*+]?\s*)(\*{0,2})([A-E])([.、)．])([ \t]*)(\*{0,2})(（选项缺失）)(\*{0,2})(.*)$"
)
# 明显不是选项正文的行
NOISE = re.compile(
    r"[ⅠⅡⅢⅣⅤ]|^\s*```|^\s*#{1,6}\s|^\s*\||^\s*\*\*解析|^\s*\*\*参考|^### 第|^\s*解析[：:]|^\s*答案[：:]"
)


def is_option_text(line: str) -> bool:
    s = line.strip()
    if not s or OPT in s:
        return False
    if NOISE.search(s):
        return False
    if OPT_SLOT.match(line):
        return False
    # 题干特征：括号填空 / 问句 / 「下列…是（ ）」
    if re.search(r"[（(]\s*[）)]|（\s*）|？|\?$", s) or s.endswith("。"):
        return False
    if re.search(r"^(下列|下列选项|以下|关于|对 n|若|设 |现有|给定|某|在 |用 |由 |已知)", s):
        return False
    # OCR 图注/页表/公式残片：过长、无空格长串、含图示符号
    if len(s) > 40:
        return False
    if re.search(r"[□■▲△◇○]", s):
        return False
    if re.search(r"\d{6,}", s):  # 123456 / 2016302540 之类
        return False
    # 已知 OCR 噪声形态
    if s in {"中断IO", "KMP算法", "OSI模型", "TLB", "IO接口", "TLB 缺失", "Cache 缺失"}:
        return False
    return True


def collect_bare(
    lines: list[str], ph_start: int, n_slots: int
) -> tuple[list[str], list[int]] | None:
    """向上收集紧邻裸行；数量不等于 n_slots 则放弃。返回 (文本, 行号)。"""
    buf: list[str] = []
    idxs: list[int] = []
    i = ph_start - 1
    while i >= 0 and len(buf) < n_slots:
        ln = lines[i]
        if not ln.strip():
            if buf:
                break
            i -= 1
            continue
        if OPT_SLOT.match(ln):
            break
        if is_option_text(ln):
            buf.append(ln.strip())
            idxs.append(i)
            i -= 1
            continue
        break
    buf.reverse()
    idxs.reverse()
    if len(buf) != n_slots:
        return None
    if len(set(buf)) != len(buf):
        return None
    if any((("×" in x or "x10" in x.lower()) and "^" not in x) for x in buf):
        return None
    if any(re.match(r"^仅\s*[、,，]", x) or re.match(r"^[、,，]", x) for x in buf):
        return None
    return buf, idxs


def rebuild_slot(orig_line: str, text: str) -> str:
    """按原槽位样式重写选项行，避免 ** 重复。"""
    m = OPT_SLOT.match(orig_line)
    assert m
    pre, b1, letter, dot, sp, b2, _ph, b3, post = m.groups()
    post = (post or "").strip()
    bold = bool(b1 or b2 or b3) or "**" in orig_line
    # 列表前缀：缩进 + '- '
    prefix = re.match(r"^([ \t]*[-*+]?\s*)", orig_line)
    pfx = prefix.group(1) if prefix else "- "
    core = f"{letter}{dot} {text}"
    if bold:
        body = f"{pfx}**{core}**"
    else:
        body = f"{pfx}{core}"
    if post:
        body = f"{body} {post}"
    return body


def process_file(path: Path, *, apply: bool) -> tuple[int, int, list[str]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    # 找连续选项槽块
    i = 0
    filled = 0
    skipped = 0
    notes: list[str] = []
    out = list(lines)
    while i < len(lines):
        if OPT_SLOT.match(lines[i]) and OPT in lines[i]:
            j = i
            slots: list[int] = []
            while j < len(lines) and OPT_SLOT.match(lines[j]) and OPT in lines[j]:
                slots.append(j)
                j += 1
            n = len(slots)
            collected = collect_bare(lines, i, n)
            if collected:
                bare, bare_idxs = collected
                for idx, line_no in enumerate(slots):
                    out[line_no] = rebuild_slot(lines[line_no], bare[idx])
                # 裸行已并入选项，清掉避免正文重复
                for bi in bare_idxs:
                    out[bi] = ""
                filled += n
                notes.append(f"{path.name}:{i + 1} 回填 {n} 项 ← 裸行 {bare}")
            else:
                skipped += n
                # 记录是否「上方有裸行但数量不对」
                near = []
                k = i - 1
                while k >= 0 and len(near) < 6:
                    if lines[k].strip():
                        if is_option_text(lines[k]):
                            near.append(lines[k].strip()[:40])
                        else:
                            break
                    k -= 1
                if near:
                    notes.append(
                        f"{path.name}:{i + 1} 跳过 {n} 槽（上方裸行 {len(near)} ≠ {n}）{near[:4]}"
                    )
            i = j
            continue
        i += 1

    if apply and out != lines:
        path.write_text("\n".join(out) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
    return filled, skipped, notes


def main() -> int:
    apply = "--apply" in sys.argv
    total_f = total_s = 0
    for path in sorted(ROOT.glob("*.md")):
        if OPT not in path.read_text(encoding="utf-8"):
            continue
        f, s, notes = process_file(path, apply=apply)
        total_f += f
        total_s += s
        print(f"== {path.name}: fill={f} skip={s} ==")
        for n in notes:
            print("  ", n)
    print(f"\n合计可回填 {total_f} 处，仍缺 {total_s} 处")
    print("模式:", "APPLY" if apply else "PREVIEW（加 --apply 写盘）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
