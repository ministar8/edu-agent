# analysis/ —— 历史分析工件

| 文件 | 说明 |
|---|---|
| `legacy_coverage_gap.json` | 2026-10-10 语料换代的 **legacy ↔ 新层主题覆盖对照**（`_meta` 内带 chunk 规模：legacy 2481 vs basic 123 / advanced 98 / exams 1359，另有 `thin_coverage` 等字段） |

**来历**：由 `scripts/legacy_coverage_gap.py` 生成，是换代决策（`d3813fb`：L3 收口
questions→exams）的取证工件之一。该脚本已在 `0cac1d4`（删 8 个一次性诊断脚本）中删除——
**git 历史可取回**（`git show 0cac1d4^:scripts/legacy_coverage_gap.py`）。

**现状**：全仓无代码引用（生产者已删、结论已沉淀进换代提交）。作为换代证据保留在本目录，
勿当活数据使用；要复算需先从 git 恢复脚本。
