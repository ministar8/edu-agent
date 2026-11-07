"""runner 的归档 IO：写入 / 续跑 / 读取已完成 case（从 _runner_support.py 拆出，行为等价）。

与机械判据（is_env_error / generation_ok / mechanical_failures 等）分离，
使 IO 层可独立复用。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from evaluation.task_eval._runner_record import CaseRecord
from evaluation.task_eval._runner_support import is_env_error

logger = logging.getLogger(__name__)


def write_jsonl(path: str | Path, rows: list[dict]) -> Path:
    """整体重写 jsonl（dict 行）。**每行都以 `\\n` 结尾，包括最后一行。**

    ★ 为什么收成一处（2026-10-07）：`cli.py` 的三处写出原先各自用
      `write_text("\\n".join(...))` —— 该写法**不留尾换行**，而 `append_record`
      是 `"a"` 模式追加 `json + "\\n"`。两者相遇时新记录会**粘在末行尾部**，
      拼成一条解析失败的坏行 ⇒ **上一条与这一条同时丢失**（实测：3 条只剩 1 条可读）。
      后果不只丢数据：`load_done_ids` 读不到被粘住的 case_id ⇒ 续跑会**重做**它，
      而那条已经烧过的 token 无从追溯。
      行格式现在只有一份实现，新调用方不可能再漏掉尾换行。
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return out


def _needs_newline_pad(path: Path) -> bool:
    """文件存在、非空、且末字节不是 `\\n` ⇒ True（需要补分隔符才能安全追加）。"""
    try:
        size = path.stat().st_size
        if not size:
            return False
        with open(path, "rb") as f:
            f.seek(-1, os.SEEK_END)
            return f.read(1) != b"\n"
    except OSError:
        return False


def dump_records(records: list[CaseRecord], path: str | Path) -> Path:
    """把 record 列表落盘为 jsonl（供报告与论文复算）。"""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
    return out


def append_record(record: CaseRecord, path: str | Path) -> None:
    """**逐条追加**一条 record 并立即 flush。

    ★ 为什么必须有（2026-10-05 实测教训）：原实现只在整轮结束时 `dump_records`，
      于是一次跑满 15 分钟、发出 **165 次 LLM 调用**的 run 被中止后，
      **一条记录都没落盘** —— 配额全白烧。逐条追加让「跑一半被中止」不再丢数据，
      配合 `load_done_ids` 可**续跑**。
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if _needs_newline_pad(out):
        # 见 `write_jsonl` 的说明：末行缺尾换行时直接 append 会把两条粘成一条坏行。
        logger.warning("目标 jsonl 末行无换行，追加前先补一个 —— %s", out)
        with open(out, "a", encoding="utf-8") as f:
            f.write("\n")
    with open(out, "a", encoding="utf-8") as f:
        f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        f.flush()


def load_done_ids(path: str | Path) -> set[str]:
    """读出**真正完成**的 case_id（用于续跑时跳过）。

    ★ 环境错误的记录**不算完成**（2026-10-05 修）：欠费/额度耗尽时写下的 record
      是「没跑成」，若也计入 done，续跑会把它**永久跳过** —— 实测 mem-006
      因欠费失败后被误判「已完成」，补跑时被跳过。
      故这里只认「非环境错误」的记录，让环境恢复后能自动补跑。
    """
    out = Path(path)
    if not out.exists():
        return set()
    done: set[str] = set()
    for line in out.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue  # 被中断写坏的最后一行：忽略即可，续跑会重做该 case
        text = " ".join(obj.get("hard_fails") or []) + " " + str(obj.get("retrieval_error") or "")
        if is_env_error(text):
            continue  # 环境错误 → 视为未完成，允许重试
        case_id = str(obj.get("case_id") or "")
        if case_id:
            done.add(case_id)
    return done
