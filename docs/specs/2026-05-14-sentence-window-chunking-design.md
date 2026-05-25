# Sentence Window 分块策略重构 — 设计文档

**日期**: 2026-05-14  
**状态**: 已确认

---

## 1. 问题诊断

### 1.1 Summary chunk 的问题

当前 `_generate_section_summary()` 是纯规则化生成：提取关键词 → 句子语义评分 → 贪心装箱。**核心缺陷**：规则化的句子评分无法理解语义，高频出现"定义句优先"误判——"XXX并不是YYY"这种否定句因匹配"是"被当作定义句得高分。Summary 内容质量不稳定，且与 detail chunk 的语义匹配度不可控。

### 1.2 QA chunk 的问题

当前 `_generate_qa_block()` 将陈述句通过正则模式匹配转为疑问句（如 `"X是Y" → "什么是X？"`）。**核心缺陷**：模式覆盖极其有限（9 条规则），大量教学内容无法匹配；生成的问句机械呆板（"什么是进程死锁？"反复出现）；问题质量无法与用户真实查询匹配。

### 1.3 chunk_size=400 的问题

固定 400 字符对所有内容类型一刀切。对于包含完整概念解释的段落（通常 600-1000 字），会被截断成碎片；对于列表或代码片段又显得过大。

---

## 2. 解决方案：Sentence Window 检索

### 2.1 核心思路

**删除 Summary 和 QA 两种 chunk 角色**，仅保留 detail chunk。检索后，对命中的 detail chunk 自动展开上下文窗口（前 N 句 + 后 N 句），让 LLM 获得完整上下文。

```
改造前:  Section → [Summary × N, QA × N, Detail × N]
        检索后: dedup_same_section → expand_hierarchical → contiguous_fill

改造后:  Section → [Detail × N (adaptive chunk_size)]
        检索后: sentence_window_expand
```

### 2.2 Adaptive chunk_size

根据 `content_type`（enhancer.py 已有检测逻辑）动态调整：

| content_type | chunk_size | 理由 |
|---|---|---|
| section / text | 800 | 概念解释需要完整段落 |
| list | 不拆，整个列表一个 chunk | 列表语义粒度在整体 |
| code_mixed | 400 | 代码片段相对独立 |
| exercise / answer | 600 | 题目+解析不宜截断 |
| table 类（pdf_table） | 不拆 | 表格完整性优先 |

### 2.3 Sentence Window 展开逻辑

`postprocess.py` 新增 `sentence_window_expand`，替代原有的 `expand_hierarchical_context` + `contiguous_fill`：

1. 对检索命中的每个 chunk，获取其 `section.id` 和 `section.chunk_index`
2. 从向量库查询同 section 的所有 detail chunk，按 chunk_index 排序
3. 以命中 chunk 为锚点，向前后各取 `window_size` 个 chunk（默认左右各 2）
4. 合并多个命中 chunk 产生的重叠窗口
5. 总字符数预算 3000 chars（超预算则缩窗）
6. 标记 `_window_expanded` 以区分子命中

### 2.4 简化检索后处理管线

```
原始: RRF merge → dedup_same_section → threshold → rerank → expand_hierarchical → contiguous_fill
新版: RRF merge → sentence_window_expand → threshold → rerank → build_rag_context
```

- `dedup_same_section`: 所有 chunk 同角色，简化为按 section.id 取高分 Top-2
- `expand_hierarchical_context`: **删除**
- `contiguous_fill`: **删除**

---

## 3. 影响范围

| 文件 | 改动 |
|---|---|
| `app/rag/splitter.py` | 移除 `_generate_section_summary`、`_generate_qa_block` 调用；chunk_size 从固定值改为按 content_type 查表；移除 summary/qa 角色相关 metadata 写入 |
| `app/rag/postprocess.py` | 新增 `sentence_window_expand`；简化 `dedup_same_section`（移除角色优先级）；删除 `expand_hierarchical_context`；删除 `contiguous_fill` |
| `app/rag/retriever.py` | 更新 `retrieve_documents` 中的后处理管线：summarize 调用链从 expand+fill 改为 window |
| `app/rag/enhancer.py` | 不需要改——`_detect_content_type` 已存在，`splitter` 直接复用 |

---

## 4. 预期效果

1. **上下文完整性**：Sentence Window 保证 LLM 看到命中 chunk 的完整上下文，不再依赖规则化 Summary
2. **检索精准度**：所有 chunk 都是原始正文（detail），语义空间一致，Reranker 排序更准确
3. **代码简化**：移除约 500 行规则生成代码，减少 bug 面
4. **无 LLM 调用增加**：所有改动均为规则化操作，不增加额外延迟

---

## 5. 与评估体系的关系

此改动完成后，评估体系可对比：
- 上下文宽度（window 大小）对 Context Precision/Recall 的影响
- Adaptive chunk_size 的各种策略的消融对比
- 新版 vs 旧版（summary+qa 模式）的 A/B 对比
