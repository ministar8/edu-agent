import { memo } from "react";

type ImportDemoGraphPanelProps = {
  onImport: () => void;
  onCancel: () => void;
};

function ImportDemoGraphPanelComponent({ onImport, onCancel }: ImportDemoGraphPanelProps) {
  return (
    <div className="p-4 bg-amber-50 border-b text-sm">
      <p className="text-amber-700 mb-2">
        点击下方按钮导入 408考研 学习路径的示例知识图谱数据到 Neo4j：
      </p>
      <button
        onClick={onImport}
        className="px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 text-sm"
      >
        确认导入示例数据
      </button>
      <button
        onClick={onCancel}
        className="ml-2 px-4 py-2 bg-slate-200 text-slate-700 rounded-lg hover:bg-slate-300 text-sm"
      >
        取消
      </button>
    </div>
  );
}

export const ImportDemoGraphPanel = memo(ImportDemoGraphPanelComponent);
