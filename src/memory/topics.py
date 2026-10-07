"""topic 规范化：闭环（episode 关联 / weak_topics / 记忆卡）的唯一入口。

自由文本 topic 不能直接当关联键：空格、全半角、同义词会导致同一知识点裂成多条。
所有写入与派生计算必须先 `normalize_topic`。

★ 2026-10-06（Step 5 实测缺陷 D）：**canonical name 必须原样保留**。

本模块此前的实现有两个会**主动改坏** canonical name 的行为：

1. ``_WS.sub("", text)`` **删掉全部空白** —— 而 kp_index 里 **21 个** canonical name
   本身**含空格**（``TCP 流量控制`` / ``Cache 替换算法`` / ``B+ 树`` / ``KMP 算法`` …）。
   删空格后它们立刻**不再是 canonical** ⇒ 与 gold / kp_index 对不上
   ⇒ ``recalled`` / ``used`` 恒 False，``weak_topics`` 全是漂移值。
2. ``_TOPIC_ALIASES`` 的**目标值不是 canonical** ⇒ 归一后落到**不可达值**。共两例：
   ``"页面置换算法" → "页面置换"``（把 canonical 改成非 canonical）、
   ``"deadlock" → "进程死锁"``（kp_index 里根本没有「进程死锁」⇒ 目标不可达）。

根因是「凭硬编码别名表**猜**什么是规范名」。正确做法是**以 kp_index 为权威**：
输入若已是 canonical，原样返回；只有非 canonical 的别名才走归一。

故本模块的 canonical 词表**取自 `core.kp_vocab`**（惰性加载 + 缓存，
读 `knowledge/knowledge_points/*.jsonl`），并把顺序定为：

    ① 已是 canonical          → 原样返回（**不做任何改写**，保空格、保大小写）
    ② 命中本模块别名表        → 用目标值（★ 目标值必须 ∈ canonical，由 gate `⑪f` 全表断言）
    ③ 命中 rag 同义词表        → **仅当目标值 ∈ canonical 才采纳**（否则视为无映射）
    ④ 其余                    → 压缩空白作为稳定化（稳定即可）

★ 关于 ③ 的**实际覆盖面**（勿夸大）：`rag.synonyms.SYNONYM_MAP` 共 338 条，
  其中 **269 条目标值非 canonical**（约 80%）⇒ 只有 **69 条**可安全采纳。
  它是**薄覆盖补充**，不是主力；`'AVL树' → '平衡二叉树'` 属**本步骤命中**，
  而非别名表覆盖 —— 不要据此高估本函数的确定性。

★ 2026-10-06（缺陷 E 收敛）：词表解析**已迁至 `core.kp_vocab`**。
  本模块**不再自行解析 jsonl** —— 因为 `prompts.service.GRADE_PROMPT` 需要同一份
  词表去约束模型输出；两处各读各的会重新制造「产出词表 ≠ 归一化词表」的错配
  （即缺陷 E：模型产出 `图的基本性质`，而 canonical 只有 `图`）。

**为什么惰性加载**：`memory` 会被 API 进程 import，而 kp_index 只在仓库里；
惰性 + 失败静默降级，保证**文件缺失时不影响服务启动**（退化为旧行为，不抛错）。
该保证现由 `core.kp_vocab` 承担。
"""

from __future__ import annotations

import re
import unicodedata

# canonical 词表的**唯一事实源**在 `core.kp_vocab`（2026-10-06 缺陷 E 收敛）。
# ★ 不要在本模块重新解析 `knowledge/knowledge_points/*.jsonl` ——
#   `prompts.service.GRADE_PROMPT` 也从同一模块取词表，两处一旦各读各的，
#   就会出现「模型产出词表 ≠ 归一化词表」的错配（缺陷 E 的成因）。
from core.kp_vocab import canonical_names as _kp_canonical_names

# 教学场景常见**别名/同义词** → 规范名。
#
# ★★ 硬纪律：**每一条的「目标值」都必须 ∈ kp_index 的 canonical name 集合** ★★
#
#   否则等于造出一个**永远不可能命中**的归一目标 —— 归一后仍不是 canonical，
#   聚合时照样对不上，且**不报错、不丢数据**，是最难查的一类病灶。
#   历史 bug 有一例，正是这条纪律被破坏：
#
#     · `"deadlock": "进程死锁"`  —— kp_index 里**根本没有**「进程死锁」这个考点
#                                    （只有「死锁」），归一后落到**不可达值**。
#     · `"页面置换算法": "页面置换"` —— canonical 恰恰是 `页面置换算法`，
#                                    属于把**对的改错**。
#
#   该纪律已由 gate `⑪f` **全表断言**（遍历本表所有 target，逐个核验 ∈ canonical）。
#   新增别名时若写错目标值，gate 立即变红。
_TOPIC_ALIASES: dict[str, str] = {
    # 键是别名（非 canonical）、目标必须是 canonical
    "deadlock": "死锁",
    "belady": "页面置换算法",
    "虚存": "虚拟内存",
    "信号量": "进程同步",
}
# 说明：已删除三条**恒等自映射**（`"死锁": "死锁"` / `"虚拟内存": "虚拟内存"`
#   / `"进程同步": "进程同步"`）。它们在 `normalize_topic` 的顺序 ① 之后
#   **永不触发**（键本身已是 canonical ⇒ ① 已原样返回），属死代码。

# kp_index 位置与解析已迁至 `core.kp_vocab`（单一事实源）。

_WS = re.compile(r"\s+")


def _canonical_names() -> frozenset[str]:
    """kp_index 的 canonical name 集合。

    ★ 2026-10-06 缺陷 E：实现**已迁至 `core.kp_vocab`**，本函数保留为薄代理，
      以免改动 `normalize_topic` 内部的所有调用点。
      惰性加载 + 进程内缓存 + 读不到时静默降级，均由 `core.kp_vocab` 保证。
    """
    return _kp_canonical_names()


def normalize_topic(raw: str) -> str:
    """规范化知识点名：**canonical 原样保留**，别名映射到 canonical，其余稳定化。

    ★ 顺序不可换：canonical 判定必须在「删空白」和「别名表」**之前**，
      否则含空格的 canonical name 会被自己改坏（见模块 docstring）。
    """
    text = unicodedata.normalize("NFKC", raw or "").strip()
    if not text:
        return ""

    # ① canonical：**原样返回**（保空格、保大小写、不查别名表）
    canonical = _canonical_names()
    if text in canonical:
        return text

    # ② 非 canonical：先试**本模块**别名表（权威、目标值必须是 canonical）
    if text in _TOPIC_ALIASES:
        return _TOPIC_ALIASES[text]
    key = text.lower()
    if key in _TOPIC_ALIASES:
        return _TOPIC_ALIASES[key]

    # ③ 次级兜底：复用 rag 的同义词表，但**仅当其目标值本身是 canonical** 才采纳。
    #    ★ 不能无条件复用 —— `SYNONYM_MAP`（338 条）里存在**与 kp_index 方向相反**的映射，
    #      例如 `'二叉排序树' → '二叉搜索树'`，而 canonical 恰恰是 `二叉排序树`。
    #      无条件复用会把对的改错。
    #
    #    ★★ 覆盖面必须如实说明（勿夸大）★★
    #      实测：338 条中 **269 条目标值非 canonical**（约 80%），
    #            只有 **69 条**的目标值 ∈ canonical ⇒ **仅这 69 条可安全采纳**。
    #      原因是 `SYNONYM_MAP` 是**检索用**同义词表（服务于 RAG 召回），
    #      其值域与 kp_index 的 canonical 域本来就是两个不同的东西。
    #      ⇒ 本步骤是**薄覆盖补充**，不是主力；权威别名一律走上面的 ② 本模块别名表。
    #      ⇒ 故 `'AVL树' → '平衡二叉树'` 属**本兜底命中**（它不在 `_TOPIC_ALIASES` 里），
    #        不是别名表覆盖案例 —— 不要据此高估本函数的确定性。
    mapped = _rag_synonym(text, canonical)
    if mapped is not None:
        return mapped

    # ④ 其余：压缩空白作为稳定化（含空格的 canonical 已在 ① 拦下，不会走到这里）
    return _WS.sub("", text)


def _rag_synonym(text: str, canonical: frozenset[str]) -> str | None:
    """从 `rag.synonyms.SYNONYM_MAP` 取映射，**仅当目标是 canonical** 时返回。

    惰性 import + 静默降级：`rag` 依赖较重，且缺失时不影响记忆层基本功能。
    """
    try:
        from rag.synonyms import SYNONYM_MAP
    except Exception:  # pragma: no cover - 环境缺 rag 时退化
        return None
    for cand in (text, text.lower()):
        target = SYNONYM_MAP.get(cand)
        if target and target in canonical:
            return target
    return None


def normalize_topics(raws: list[str] | None) -> list[str]:
    """去重且保序规范化。"""
    seen: set[str] = set()
    out: list[str] = []
    for raw in raws or []:
        t = normalize_topic(raw)
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def canonical_names() -> frozenset[str]:
    """暴露 canonical name 集合（供 gate / 诊断用，只读）。"""
    return _canonical_names()
