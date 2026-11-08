"""离线文档处理/清洗工具：规范化、去重、异常检测、缺失值填充。

不参与运行时；仅由入库管线（`rag.chunking.cleaner`）与离线 ETL 脚本按需导入子模块。
包名 `document_processing`（原 `src/tools/`）与运行时 `agents/runtime/tools.py` 消歧。
"""
