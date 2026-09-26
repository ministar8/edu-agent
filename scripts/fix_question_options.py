"""把 knowledge/questions/*.md 里「（选项缺失）」占位符补回真实选项文本。

★ 这是**纯本地数据搬运**：只把同一题块内、位于标记行上方的裸选项行搬进标记行，
  不引入任何外部内容，不做任何推测性补全。

★ 为什么必须保守分层（而不是尽量多补）：
  裸选项行与**图片 OCR 残留**混在同一区域（`123456`、`中断IO`、`DMA`、
  `a=3b=4c=8d=7f=10h=9g=6e=6关键路径`、`删除 0调整` …）。把噪声当成选项写进语料
  是**不可逆污染**，代价远高于「少补几题」。故护栏宁可误拒，不可误收。

★ 关键观察（决定了取哪一截）：**OCR 噪声通常排在选项之前**——
  图片 dump 紧跟题干，选项在其后。所以候选一律取「紧邻标记行上方的最后 N 行」，
  而不是「区域内任意 N 行」。

用法:
    python scripts/fix_question_options.py --preview   # 只出审阅表，不写盘
    python scripts/fix_question_options.py --apply     # 写盘（先自动备份）
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_DIR = ROOT / "knowledge" / "questions"

PLACEHOLDER = "（选项缺失）"
BLOCK_HEAD = re.compile(r"^###\s+第\s*\d+\s*题")
MARKER = re.compile(r"^\s*[-*+]\s*(\*{0,2})([A-E])([.、)．])")
MAX_OPT_LEN = 80

# 噪声特征：命中任一即整块拒收
NOISE_PATTERNS = (
    re.compile(r"```"),  # 代码围栏
    re.compile(r"[：:；;]\s*$"),  # 以冒号/分号收尾（多为引导句）
    re.compile(r"^(考虑以下|如下图所示|如下表|见图|如图所示)"),
    re.compile(r"^\*{0,2}解析\*{0,2}\s*[：:]"),
    re.compile(r"·{3,}"),  # OCR 表格/连线残留：`024H0······180H1018H1…页表`
)


@dataclass
class Block:
    file: str
    head: str
    start: int
    marker_rows: list[int] = field(default_factory=list)
    consumed: list[int] = field(default_factory=list)
    pairs: list[tuple[str, str]] = field(default_factory=list)  # (占位原文, 补后文本)
    verdict: str = ""
    reason: str = ""
    before: str = ""
    after: str = ""


def _is_noise(line: str) -> str:
    """返回噪声原因；空串表示通过。"""
    if len(line) > MAX_OPT_LEN:
        return f"超长({len(line)}字)"
    for pat in NOISE_PATTERNS:
        if pat.search(line):
            return f"噪声特征({pat.pattern[:12]})"
    return ""


def _char_type(line: str) -> str:
    """行的字符构成类型，用于一致性校验。

    N = 数字为主（1.25% / 25ms / F000FF12H / -32768）
    C = 汉字为主（仅Ⅰ、Ⅱ / 程序的功能都通过…）
    M = 混合
    """
    n = len(line)
    if n == 0:
        return "M"
    digit = sum(1 for c in line if c.isdigit() or c in "%.")
    cjk = sum(1 for c in line if "\u4e00" <= c <= "\u9fff")
    latin = sum(1 for c in line if c.isascii() and c.isalpha())
    if digit / n >= 0.25 and cjk / n <= 0.25:
        return "N"
    if cjk / n >= 0.35:
        return "C"
    if latin / n >= 0.5:
        return "L"
    return "M"


def _is_stem(line: str) -> bool:
    """题干特征：以问号/括号空位收尾，或明显长于选项。"""
    return bool(re.search(r"[（(]\s*[）)]\s*[。.？?]?\s*$", line)) or line.endswith("？")


def parse_blocks(path: Path) -> list[Block]:
    lines = path.read_text(encoding="utf-8").split("\n")
    blocks: list[Block] = []
    cur: Block | None = None
    for i, raw in enumerate(lines):
        if BLOCK_HEAD.match(raw):
            if cur:
                blocks.append(cur)
            cur = Block(file=path.name, head=raw.strip(), start=i)
        if cur is None:
            continue
        if PLACEHOLDER in raw and MARKER.match(raw):
            cur.marker_rows.append(i)
    if cur:
        blocks.append(cur)
    for b in blocks:
        b.marker_rows = [i for i in b.marker_rows if PLACEHOLDER in lines[i]]
    return blocks, lines  # type: ignore[return-value]


def resolve(block: Block, lines: list[str]) -> None:
    """就地把 block 判定为 accept / reject，并填 pairs / consumed。"""
    if not block.marker_rows:
        block.verdict = "skip"
        block.reason = "无占位符"
        return
    n = len(block.marker_rows)
    first = block.marker_rows[0]

    # 候选区：块内、首个标记行之前的非空非标记行
    cand: list[tuple[int, str]] = []
    for i in range(block.start + 1, first):
        s = lines[i].strip()
        if not s or MARKER.match(s):
            continue
        cand.append((i, s))
    # 去掉题干（最长且含括号空位/问号的那条；若无则去掉最长一条）
    stems = [k for k, (_, s) in enumerate(cand) if _is_stem(s)]
    if stems:
        drop = max(stems, key=lambda k: len(cand[k][1]))
    elif cand:
        drop = max(range(len(cand)), key=lambda k: len(cand[k][1]))
    else:
        block.verdict, block.reason = "reject", "候选区为空"
        return
    cand.pop(drop)

    if len(cand) < n:
        block.verdict = "reject"
        block.reason = f"候选不足(需{n}得{len(cand)})"
        return

    tail = cand[-n:]
    for idx, s in tail:
        why = _is_noise(s)
        if why:
            block.verdict = "reject"
            block.reason = why
            return

    # 一致性：n 条候选的字符构成类型必须相同（防 OCR 噪声混入）
    types = {_char_type(s) for _, s in tail}
    if len(types) > 1:
        block.verdict = "reject"
        block.reason = "类型不一致:" + "/".join(sorted(types))
        return

    # ★ 重复项护栏：选择题选项不会雷同。出现相同文本几乎必然是 OCR 丢字符
    #   （实测 2021 第12题 `9.3×10^13 / 9.3×10^15 / 9.3 / 9.3` —— 后两条丢了指数）。
    #   补两个一样的选项比不补更糟（会让人以为题目本身如此）。
    texts = [s for _, s in tail]
    if len(set(texts)) < len(texts):
        block.verdict = "reject"
        block.reason = "选项重复:" + "|".join(sorted({t for t in texts if texts.count(t) > 1})[:2])
        return

    block.consumed = [i for i, _ in tail]
    block.pairs = [
        (lines[mi], lines[mi].replace(PLACEHOLDER, s))
        for mi, (_, s) in zip(block.marker_rows, tail)
    ]
    block.verdict = "accept"


# 枚举子项（`Ⅰ.I/O 结束` / `I.若 v 是…`）：题干自带的罗列，**不是选项**。
# 它们常紧跟题干排在真选项之前，若参与"取最后 N 条"会挤掉真选项
# （实测 2019 第4题、第24题都被它挤歪）。只在**建议**里排除，仍展示在候选列。
ENUM_ITEM = re.compile(r"^[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVXivx]{1,4}\s*[.、．]")


def _suggest_pool(cand: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """建议映射的取值池：候选里剔掉噪声行与枚举子项。"""
    return [(i, t) for i, t in cand if not ENUM_ITEM.match(t) and not _is_noise(t)]


def _candidates(block: Block, lines: list[str]) -> list[tuple[int, str]]:
    """重算候选裸行（题干之外、首标记行之上的非空非标记行），返回 (行号, 文本)。"""
    first = block.marker_rows[0]
    pre = [
        (i, lines[i].strip())
        for i in range(block.start + 1, first)
        if lines[i].strip() and not MARKER.match(lines[i])
    ]
    if not pre:
        return []
    stems = [k for k, (_, s) in enumerate(pre) if _is_stem(s)]
    drop = (
        max(stems, key=lambda k: len(pre[k][1]))
        if stems
        else max(range(len(pre)), key=lambda k: len(pre[k][1]))
    )
    pre.pop(drop)
    return pre


def render_manual(blocks: list[Block], per_file: dict) -> str:
    """人工补表：只列被拒收的块，给出裸行候选 + 建议映射，由人确认后再写盘。

    ★ 为什么这些块不能自动补：护栏拒收说明「按位置取最后 N 行」不可靠
      （噪声混入 / 类型不一致 / 数量不足）。但**文本就在原位**，人一眼能判读，
      所以交给人工而不是继续放宽护栏 —— 放宽护栏会把噪声写进语料。
    """
    rows = []
    order = {"候选不足": 0, "噪声特征": 1, "类型不一致": 2, "选项重复": 3}
    todo = sorted(
        [b for b in blocks if b.verdict == "reject"],
        key=lambda b: (order.get(b.reason.split("(")[0].split(":")[0], 9), b.file, b.head),
    )
    for b in todo:
        lines = per_file[b.file][1]
        cand = [t for _, t in _candidates(b, lines)]
        n = len(b.marker_rows)
        stem = ""
        for i in range(b.start + 1, b.marker_rows[0]):
            s = lines[i].strip()
            if s and _is_stem(s):
                stem = s
                break
        if not stem:
            pre = [
                lines[i].strip() for i in range(b.start + 1, b.marker_rows[0]) if lines[i].strip()
            ]
            stem = max(pre, key=len) if pre else ""

        cand_html = (
            "<br>".join(
                f'<span class="k">{i + 1}.</span> {c.replace("<", "&lt;")}'
                for i, c in enumerate(cand)
            )
            or '<span class="none">（无）</span>'
        )
        mark_html = "<br>".join(lines[i].strip().replace("<", "&lt;") for i in b.marker_rows)

        pool = [t for _, t in _suggest_pool(_candidates(b, lines))]
        if len(pool) == n:
            sug = "<br>".join(
                f"{chr(65 + i)} ← {t.replace('<', '&lt;')[:36]}" for i, t in enumerate(pool)
            )
            cls = "y"
        elif len(pool) > n:
            tail = pool[-n:]
            sug = (
                f'<span class="warn">有效候选 {len(pool)} 条（已剔除噪声/枚举），'
                f"建议取最后 {n} 条：</span><br>"
                + "<br>".join(
                    f"{chr(65 + i)} ← {t.replace('<', '&lt;')[:36]}" for i, t in enumerate(tail)
                )
            )
            cls = "p"
        else:
            sug = (
                f'<span class="none">有效候选仅 {len(pool)} 条，缺 {n - len(pool)} 条 —— '
                "源文件没抄全，本地补不了</span>"
            )
            cls = "n"

        rows.append(
            f'<tr class="{cls}"><td class="f">{b.file.replace("_408_exam.md", "")}</td>'
            f"<td>{b.head.replace('###', '').strip()[:22]}</td>"
            f'<td class="stem">{stem.replace("<", "&lt;")[:70]}</td>'
            f"<td>{cand_html}</td><td>{mark_html}</td><td>{b.reason}</td><td>{sug}</td></tr>"
        )
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>真题选项人工补表（拒收块）</title><style>
body{{font-family:-apple-system,"Microsoft YaHei",sans-serif;margin:20px;color:#222;background:#fff}}
h1{{font-size:17px;font-weight:600}} .meta{{color:#666;font-size:13px;margin:6px 0 14px}}
table{{border-collapse:collapse;width:100%;font-size:12.5px}}
th,td{{border:1px solid #ddd;padding:6px 7px;vertical-align:top;text-align:left}}
th{{background:#f5f5f5;font-weight:600;position:sticky;top:0;z-index:1}}
tr.y{{background:#f2fbf5}} tr.p{{background:#fffbf0}} tr.n{{background:#fdf6f5}}
.k{{color:#888;font-weight:600}} .none{{color:#b3261e}} .warn{{color:#a06000}}
.f{{color:#555;white-space:nowrap}} .stem{{color:#444;max-width:230px}}
</style></head><body>
<h1>真题选项人工补表</h1>
<div class="meta">拒收块 {len(todo)} 个 ｜ 绿=有效候选正好可直接填 ｜ 黄=有效候选偏多需挑 ｜ 红=源文件没抄全 ｜ 生成于 {datetime.now():%Y-%m-%d %H:%M}</div>
<div class="warn" style="margin-bottom:12px;font-size:13px">⚠️ 「建议」列是启发式（在剔除噪声行与枚举子项后取最后 N 条），<b>仅供参考，必须逐块人工确认</b>。之所以不自动写入，就是因为这些块按位置取行已被证明不可靠。</div>
<table><thead><tr><th>卷</th><th>题</th><th>题干</th><th>裸行候选</th><th>当前标记行</th><th>拒收理由</th><th>建议</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></body></html>"""


def resolve_pass2(block: Block, lines: list[str]) -> bool:
    """第二轮：只对第一轮被拒的块生效，放宽「位置」约束、收紧「形态」约束。

    ★ 为什么要有第二轮：第一轮要求「紧邻标记行上方的最后 N 行」逐条通过噪声与
      类型校验，这会被紧跟题干的**枚举子项**（`Ⅰ.`/`I.`）和代码围栏挤掉真选项 ——
      2019 第4题有效候选正好 4 条却被误拒。第二轮先剔除噪声行与枚举子项再取。

    ★ 为什么不能把第一轮的**类型一致性**照搬过来：字符构成比例在短选项上不稳定
      （`仅I` 判 M、`仅II` 判 L，于是 4 条真选项被判「类型不一致」）。
      改用**形态同源**判据：同首字符，或全部含数字；外加长度齐性与去重。

    ★ 实测踩到的坑（护栏即由此而来）：2022 第15题候选含
      `024H0······180H1018H1实页号（页框号）存在位虚页号82129130···页表`
      —— 它**含数字**，靠「全含数字」混过了。故补两条：`·{3,}` 判噪声、
      长度齐性 max/min ≤ 4。

    返回 True 表示本轮接受。
    """
    if not block.marker_rows:
        return False
    n = len(block.marker_rows)
    pool = _suggest_pool(_candidates(block, lines))
    if len(pool) != n:  # ★ 必须**正好** n 条：多一条说明还有噪声没剔干净
        block.reason = f"二轮候选≠{n}(得{len(pool)})"
        return False

    texts = [t for _, t in pool]
    if len(set(texts)) < n:
        block.reason = "二轮重复项"
        return False

    lengths = [len(t) for t in texts]
    if max(lengths) / max(1, min(lengths)) > 4:
        block.reason = f"二轮长度不齐({min(lengths)}~{max(lengths)})"
        return False

    firsts = {t[0] for t in texts}
    all_digit = all(any(c.isdigit() for c in t) for t in texts)
    if len(firsts) != 1 and not all_digit:
        block.reason = "二轮形态不同源"
        return False

    block.consumed = [i for i, _ in pool]
    block.pairs = [
        (lines[mi], lines[mi].replace(PLACEHOLDER, t))
        for mi, (_, t) in zip(block.marker_rows, pool)
    ]
    block.verdict = "accept2"
    block.reason = "二轮:同首字符" if len(firsts) == 1 else "二轮:全含数字"
    return True


def render_preview(blocks: list[Block]) -> str:
    acc = [b for b in blocks if b.verdict == "accept"]
    rej = [b for b in blocks if b.verdict == "reject"]
    rows = []
    for b in blocks:
        if b.verdict == "skip":
            continue
        cls = "ok" if b.verdict == "accept" else "no"
        badge = "补" if b.verdict == "accept" else "拒"
        before = "<br>".join(x.replace("<", "&lt;") for x in [p[0] for p in b.pairs]) or "—"
        after = "<br>".join(x.replace("<", "&lt;") for x in [p[1] for p in b.pairs]) or "—"
        rows.append(
            f'<tr class="{cls}"><td>{b.file}</td><td>{b.head[:28]}</td>'
            f"<td>{badge}</td><td>{before}</td><td>{after}</td><td>{b.reason}</td></tr>"
        )
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>真题选项补全审阅表</title><style>
body{{font-family:-apple-system,"Microsoft YaHei",sans-serif;margin:24px;color:#222;background:#fff}}
h1{{font-size:18px;font-weight:600}} .meta{{color:#666;font-size:13px;margin-bottom:16px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{border:1px solid #ddd;padding:6px 8px;vertical-align:top;text-align:left}}
th{{background:#f5f5f5;font-weight:600;position:sticky;top:0}}
tr.ok td:nth-child(3){{color:#0a7d34;font-weight:600}}
tr.no td:nth-child(3){{color:#b3261e;font-weight:600}}
tr.no{{background:#fdf6f5}} td:nth-child(6){{color:#888}}
</style></head><body>
<h1>真题选项补全审阅表</h1>
<div class="meta">共 {len(acc) + len(rej)} 块含占位符 ｜ 通过护栏 {len(acc)} ｜ 拒收 {len(rej)} ｜ 生成于 {datetime.now():%Y-%m-%d %H:%M}</div>
<table><thead><tr><th>文件</th><th>题</th><th>判定</th><th>改前</th><th>改后</th><th>理由</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--preview", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--manual", action="store_true", help="只出拒收块的人工补表")
    ap.add_argument("--out", default="docs/真题选项补全审阅表.html")
    a = ap.parse_args()

    all_blocks: list[Block] = []
    per_file: dict[str, tuple[Path, list[str]]] = {}
    for path in sorted(QUESTIONS_DIR.glob("*.md")):
        blocks, lines = parse_blocks(path)  # type: ignore[misc]
        per_file[path.name] = (path, lines)
        for b in blocks:
            resolve(b, lines)
            if b.verdict == "reject":
                resolve_pass2(b, lines)
        all_blocks.extend(blocks)

    acc = [b for b in all_blocks if b.verdict.startswith("accept")]
    rej = [b for b in all_blocks if b.verdict == "reject"]

    if a.manual:
        out = ROOT / "docs/真题选项人工补表.html"
        out.write_text(render_manual(all_blocks, per_file), encoding="utf-8")
        print(f"人工补表（拒收 {len(rej)} 块）: {out}")
        return 0

    out = ROOT / a.out
    out.write_text(render_preview(all_blocks), encoding="utf-8")
    print(f"含占位符块 {len(acc) + len(rej)} ｜ 通过 {len(acc)} ｜ 拒收 {len(rej)}")
    print(f"审阅表: {out}")

    if not a.apply:
        return 0

    # ★ 先算清要改多少，**为 0 就直接返回、不建备份**。
    #   踩过的坑：脚本无条件 copytree + 时间戳命名，结果跑一次多一个目录；
    #   有一次因为 `verdict` 匹配 bug 实际写入 0 处，却仍在桌面留下一份无用备份。
    plan = [
        (n, b)
        for n, (_, _) in per_file.items()
        for b in [x for x in all_blocks if x.file == n and x.verdict.startswith("accept")]
    ]
    todo = sum(len(b.pairs) for _, b in plan)
    if todo == 0:
        print("无可补块，未写盘、未建备份")
        return 0

    # 备份放**仓库外**（放仓库内会污染 `git status`），且**固定路径覆盖**，
    # 不再每次生成新目录 —— 语料本身受 git 保护，备份只是双保险。
    bak = ROOT.parent / "edu-agent-questions-backup"
    if bak.exists():
        shutil.rmtree(bak)
    shutil.copytree(QUESTIONS_DIR, bak)
    print(f"已备份（覆盖式）: {bak}")

    filled = 0
    for name, (path, lines) in per_file.items():
        blocks = [b for b in all_blocks if b.file == name and b.verdict.startswith("accept")]
        if not blocks:
            continue
        drop = {i for b in blocks for i in b.consumed}
        repl = {}
        for b in blocks:
            for mi, (old, new) in zip(b.marker_rows, b.pairs):
                repl[mi] = new
                filled += 1
        new_lines = [repl.get(i, ln) for i, ln in enumerate(lines) if i not in drop]
        path.write_text("\n".join(new_lines), encoding="utf-8")
    print(f"已写入 {len(per_file)} 个文件，补全 {filled} 处占位符")
    return 0


if __name__ == "__main__":
    sys.exit(main())
