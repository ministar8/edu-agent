"""缺失值填充模块

在清洗后、分块前执行，对文档内容和元数据中的缺失值进行填充/标记：

内容层：
- 正文为空/过短 → 标记 content_status="empty"，不入库
- 含占位符（"此处为图片"等）→ 标记 has_placeholder=True
- 未闭合围栏/括号 → 标记 truncated=True

元数据层（核心）：
- heading 缺失 → 优先级：Markdown标题解析 > 章节标记识别 > 文件名推断 > 首行提取(停用词过滤) > 关键词组合
- heading_path 缺失 → 从 heading 构建
- category 缺失 → 从 source_path 路径推断

结构层：
- PDF 无章节标题 → 字体大小/加粗特征检测标题 + 语义连贯性分段
- 纯文本分段 → 语义连贯性检测（句子相似度）+ 空行边界

原则：不虚构内容，只标记缺失状态；不覆盖已有元数据。

子模块：
- `_resources`：资源配额监控与超时装饰器
- `_constants`：正则、停用词表、分段参数档案、置信度分级
- `_heading`：heading / heading_path / category 推断
- `_segmentation`：长文档自动分段标注
- `_pipeline`：单文档填充 + 集合级调度
"""

from ._pipeline import impute_documents

__all__ = ["impute_documents"]
