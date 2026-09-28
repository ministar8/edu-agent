# papers-rebuild — 重排版真题（Markdown）

来源：`neville-studio/408-exam-paper` 重排版 PDF（2009–2025）。

| 项 | 说明 |
|---|---|
| 原始 | `YYYY.pdf`（Word 重排打印版，文字层可抽取） |
| 转换 | `YYYY.md`（`pymupdf4llm.to_markdown`） |
| 可信度 | 第三方重排原题（图像→文字重排，约 5 错/100KB）；**非回忆版** |
| 可信度排序 | 大纲原题 > 第三方原题 > 回忆版 |

已另结构化为 `knowledge/questions/YYYY_408_exam.md`（按题切分、带选项/答案/可信度标注）供 RAG 使用。

转换脚本：`scripts/convert_rebuild_papers.py`（结构化）；PDF→MD 原文与 PDF 同目录同名。
