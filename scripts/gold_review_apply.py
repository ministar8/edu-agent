"""把**你确认过的** case 的 `gold_status` 从 draft 翻成 reviewed（或 frozen）。

★ 这个工具**不是签名**。签名是你「逐条看过 gold」这件事本身；它只是把你给出的
  case_id 列表机械地写进 5 个 demo 文件，省掉手改 66 行时改错一个字符的风险。

用法::

    # 先看要改什么（不写盘）
    PYTHONPATH=src uv run python scripts/gold_review_apply.py --ids grd-001,grd-002 --status reviewed
    # 确认无误再落地
    PYTHONPATH=src uv run python scripts/gold_review_apply.py --ids-file confirmed.txt --status reviewed --apply

三条硬不变量（`memory_step4fix_gate.py` 的 ㉚ 直接测它们）：

1. **除 `gold_status` 外逐字段相等** —— 改完重新解析，与改前逐键比对；
2. **行数与注释行逐字节不变** —— `#` 开头行原样写回，schema 说明不会被顺手重排；
3. **换行风格不变** —— demo 文件是 CRLF，这里全程按字节处理，绝不产出 `\r\r\n` 或裸 `\\n`。

★ 改完**必须**更新 `docs/EXPERIMENTS.md` §20.0 的效果集指纹（工具会把新值印成一行可直接粘的文本）：
   gold 一改，归档 record 里的 `golden_sha256` 与 `gold_status` 就跟着变 ⇒ 之前的效果数字
   属「draft gold 下的读数」，不能与 reviewed 混在一张表里（#27/#3 同一条纪律）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "evals" / "datasets" / "demo"
DEMO_FILES = (
    "qa_cases.jsonl",
    "generate_cases.jsonl",
    "grade_cases.jsonl",
    "verify_cases.jsonl",
    "memory_cases.jsonl",
)
ALLOWED_STATUS = ("draft", "reviewed", "frozen")


def _fp(raw: bytes) -> str:
    """与 §20.0 同一口径：整个文件字节的 sha256 前 16 位。"""
    return hashlib.sha256(raw).hexdigest()[:16]


def flip_text(raw: str, ids: set[str], status: str) -> tuple[str, list[str], set[str]]:
    """在**已把换行统一成 LF 的文本**上做翻转，返回 (新文本, 改动的 case_id, 本文件出现过的 case_id)。

    行尾风格由调用方负责，本函数只管内容。
    ★ 第三个返回值是 **seen 而不是 refused**：refused 只能在**全部文件跑完之后**算。
      按单文件算 `ids - seen` 会让 qa 文件把 `grd-001` 报成「找不到」，而 grade 文件明明匹配了它
      —— dry-run 里同一次运行既说「拟写 2 条」又说「全部拒绝」，就是这个原因。
    """
    changed: list[str] = []
    lines = raw.split("\n")
    out: list[str] = []
    seen: set[str] = set()
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            out.append(line)
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            out.append(line)
            continue
        if not isinstance(obj, dict):
            out.append(line)
            continue
        cid = str(obj.get("case_id") or "")
        if cid not in ids:
            out.append(line)
            continue
        seen.add(cid)
        if obj.get("gold_status") == status:
            out.append(line)  # 幂等：已是目标值就不动
            continue
        obj["gold_status"] = status
        out.append(json.dumps(obj, ensure_ascii=False))
        changed.append(cid)
    return "\n".join(out), changed, seen


def apply_file(
    path: Path, ids: set[str], status: str, *, write: bool
) -> tuple[list[str], set[str], str, str]:
    """处理一个 demo 文件。返回 (改动的 case_id, 本文件出现过的 case_id, 改前指纹, 改后指纹)。

    ★ 全程按字节判换行：`splitlines()` 会在 `\r` 上再切一刀（这正是历史上那次
      「join 回去却静默失败」的成因），所以这里只认文件自己那一种换行。
    """
    data = path.read_bytes()
    if b"\r\r" in data:
        raise ValueError(f"{path.name} 里有 \\r\\r —— 先修数据再翻 gold_status，别在坏文件上叠写")
    newline = "\r\n" if b"\r\n" in data else "\n"
    body = data.decode("utf-8").replace("\r\n", "\n")
    new_body, changed, seen = flip_text(body, ids, status)
    before_fp = _fp(data)
    if changed:
        out_bytes = new_body.replace("\n", newline).encode("utf-8")
        assert_only_status_changed(data, out_bytes)
        after_fp = _fp(out_bytes)
        if write:
            path.write_bytes(out_bytes)
    else:
        after_fp = before_fp
    return changed, seen, before_fp, after_fp


def assert_only_status_changed(before: bytes, after: bytes) -> None:
    """核心不变量：逐行看 —— **要么逐字节相同，要么只差 `gold_status` 一个字段**。

    ★ 原先写成「每一行都必须只差 gold_status」，于是没被选中的行（本来就该逐字节不动）
      反过来触发了断言 ⇒ 是护栏 ㉚a 第一次跑就把这个 bug 抓出来的。
    """
    a_rows = [ln for ln in before.decode("utf-8").replace("\r\n", "\n").split("\n") if ln.strip()]
    b_rows = [ln for ln in after.decode("utf-8").replace("\r\n", "\n").split("\n") if ln.strip()]
    if len(a_rows) != len(b_rows):
        raise AssertionError(f"行数变了：{len(a_rows)} → {len(b_rows)}")
    n_changed = 0
    for x, y in zip(a_rows, b_rows, strict=True):
        if x.lstrip().startswith("#"):
            if x != y:
                raise AssertionError(f"注释行被改了：{x[:60]}")
            continue
        if x == y:
            continue  # 未被选中的行必须逐字节不动
        ox, oy = json.loads(x), json.loads(y)
        sx, sy = ox.pop("gold_status", None), oy.pop("gold_status", None)
        if ox != oy:
            raise AssertionError(f"除 gold_status 外还有字段不同：{ox.get('case_id')}")
        if sx == sy:
            raise AssertionError(f"gold_status 没变却被改写了整行：{ox.get('case_id')}")
        n_changed += 1
    if n_changed == 0:
        raise AssertionError("说好了要写回，结果一行都没差 —— 那就别写")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="翻转 gold_status（只翻你确认过的 case）")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--ids", default="", help="逗号分隔的 case_id 列表")
    src.add_argument("--ids-file", default="", help="每行一个 case_id（# 开头算注释）")
    ap.add_argument("--status", required=True, choices=ALLOWED_STATUS)
    ap.add_argument("--apply", action="store_true", help="真正写盘（不加就只打印计划）")
    ap.add_argument(
        "--all-draft",
        action="store_true",
        help="把当前所有 draft 的 case 都当作已确认（★ 只有在你逐条看过之后才许用）",
    )
    args = ap.parse_args(argv)

    ids: set[str] = set()
    if args.ids:
        ids = {s.strip() for s in args.ids.replace("，", ",").split(",") if s.strip()}
    if args.ids_file:
        p = Path(args.ids_file)
        if not p.exists():
            print(f"读不到 ids 文件：{p}", file=sys.stderr)
            return 2
        ids = {
            ln.strip()
            for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        }
    if args.all_draft:
        ids |= _draft_ids()
    if not ids:
        print(
            "没有要处理的 case_id（--ids / --ids-file / --all-draft 至少给一个）", file=sys.stderr
        )
        return 2

    mode = "写入" if args.apply else "试跑（不写盘）"
    print(f"gold_status → {args.status} · 待确认 {len(ids)} 条 · {mode}")
    total_changed: list[str] = []
    matched: set[str] = set()
    fp_lines: list[str] = []
    for name in DEMO_FILES:
        path = DEMO_DIR / name
        if not path.exists():
            print(f"  跳过（文件不存在）：{name}")
            continue
        changed, seen, before_fp, after_fp = apply_file(path, ids, args.status, write=args.apply)
        matched |= seen
        tag = "已写" if args.apply else "拟写"
        print(
            f"  {name:22s} {tag} {len(changed):2d} 条"
            f"  指纹 {before_fp}" + (f" → {after_fp}" if after_fp != before_fp else "（不变）")
        )
        total_changed += changed
        if after_fp != before_fp:
            stem = name.replace("_cases.jsonl", "")
            fp_lines.append(f"`{stem} {after_fp}`")

    if not total_changed:
        print("⇒ 没有任何行被改动（要么 id 不匹配，要么已经是目标状态）")
    all_refused = sorted(ids - matched)
    if all_refused:
        print(f"⚠️ 这些 id 在 demo 集里找不到，已拒绝：{all_refused}")
    if fp_lines and total_changed:
        print(
            "\n§20.0 效果集指纹那一行请改成（gold 一改就必须同步，否则锚点与数据对不上）：\n  "
            + " · ".join(fp_lines)
        )
    if not args.apply and total_changed:
        print("\n（这是试跑。确认无误后加 --apply 才会写盘。）")
    return 0


def _draft_ids() -> set[str]:
    """当前仍是 draft 的 case_id（给 --all-draft 用）。"""
    out: set[str] = set()
    for name in DEMO_FILES:
        path = DEMO_DIR / name
        if not path.exists():
            continue
        for ln in path.read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            obj: dict[str, Any] = json.loads(ln)
            if obj.get("gold_status") == "draft":
                out.add(str(obj.get("case_id")))
    return out


if __name__ == "__main__":
    sys.exit(main())
