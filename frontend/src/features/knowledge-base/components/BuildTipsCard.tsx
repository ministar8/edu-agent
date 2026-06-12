import { memo } from "react";

function BuildTipsCardComponent() {
  return (
    <section className="rounded-[28px] border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="text-lg font-semibold text-slate-900">构建提示</h3>
      <div className="mt-5 space-y-4">
        <div className="rounded-3xl bg-slate-50 p-4">
          <div className="text-sm font-medium text-slate-800">流程</div>
          <div className="mt-2 text-sm leading-6 text-slate-500">
            加载 → 清洗 → 分块 → 关键词增强 → 去重入库 → 图谱构建
          </div>
        </div>
        <div className="rounded-3xl bg-slate-50 p-4">
          <div className="text-sm font-medium text-slate-800">分类建议</div>
          <div className="mt-2 text-sm leading-6 text-slate-500">
            `data_structure` 数据结构，`computer_organization` 组成原理，`operating_system` 操作系统，`computer_network` 计算机网络，`questions` 题库。
          </div>
        </div>
        <div className="rounded-3xl bg-slate-50 p-4">
          <div className="text-sm font-medium text-slate-800">说明</div>
          <div className="mt-2 text-sm leading-6 text-slate-500">
            重复内容会自动去重；图谱构建失败时不影响主入库流程。
          </div>
        </div>
      </div>
    </section>
  );
}

export const BuildTipsCard = memo(BuildTipsCardComponent);
