"use client";

import { useState, useEffect } from "react";
import axios from "axios";

import { API_BASE_URL } from "@/lib/api";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

export default function KnowledgeGraphPanel() {
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [loading, setLoading] = useState(false);
  const [showImport, setShowImport] = useState(false);

  const fetchGraph = async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API_BASE_URL}/api/visualization/knowledge-graph`);
      const data = res.data;

      const reactNodes: Node[] = data.nodes.map((n: { id: string; category: string; description: string }, i: number) => {
        const angle = (2 * Math.PI * i) / data.nodes.length;
        const radius = 250;
        return {
          id: n.id,
          type: "default",
          position: {
            x: 400 + radius * Math.cos(angle),
            y: 300 + radius * Math.sin(angle),
          },
          data: { label: n.id },
          style: {
            background: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
            color: "white",
            border: "2px solid #5a67d8",
            borderRadius: "8px",
            padding: "8px 16px",
            fontSize: "13px",
          },
        };
      });

      const relationColors: Record<string, string> = {
        PREREQUISITE_OF: "#f59e0b",
        RELATED_TO: "#10b981",
      };

      const reactEdges: Edge[] = data.edges.map((e: { source: string; target: string; relation: string }) => ({
        id: `${e.source}-${e.target}`,
        source: e.source,
        target: e.target,
        label: e.relation === "PREREQUISITE_OF" ? "前置" : "相关",
        animated: e.relation === "PREREQUISITE_OF",
        style: {
          stroke: relationColors[e.relation] || "#94a3b8",
          strokeWidth: 2,
        },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: relationColors[e.relation] || "#94a3b8",
        },
      }));

      setNodes(reactNodes);
      setEdges(reactEdges);
    } catch {
      setNodes([]);
      setEdges([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchGraph();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const importDemoData = async () => {
    const demoNodes = [
      { name: "Python基础", category: "programming", description: "变量、数据类型、控制流" },
      { name: "函数", category: "programming", description: "函数定义、参数、返回值" },
      { name: "面向对象", category: "programming", description: "类、继承、多态" },
      { name: "装饰器", category: "programming", description: "函数装饰器、类装饰器" },
      { name: "生成器", category: "programming", description: "yield、迭代器协议" },
      { name: "异常处理", category: "programming", description: "try/except/finally" },
      { name: "文件IO", category: "programming", description: "读写文件、上下文管理器" },
      { name: "模块与包", category: "programming", description: "import、__init__.py" },
      { name: "机器学习基础", category: "ml", description: "监督/无监督学习概念" },
      { name: "数据预处理", category: "ml", description: "清洗、特征工程、归一化" },
      { name: "线性回归", category: "ml", description: "最小二乘法、梯度下降" },
      { name: "神经网络", category: "ml", description: "感知机、反向传播" },
      { name: "深度学习", category: "ml", description: "CNN、RNN、Transformer" },
    ];

    const demoEdges = [
      { source: "Python基础", target: "函数", relation: "PREREQUISITE_OF" },
      { source: "函数", target: "面向对象", relation: "PREREQUISITE_OF" },
      { source: "函数", target: "装饰器", relation: "PREREQUISITE_OF" },
      { source: "函数", target: "生成器", relation: "PREREQUISITE_OF" },
      { source: "Python基础", target: "异常处理", relation: "PREREQUISITE_OF" },
      { source: "Python基础", target: "文件IO", relation: "PREREQUISITE_OF" },
      { source: "面向对象", target: "模块与包", relation: "PREREQUISITE_OF" },
      { source: "Python基础", target: "机器学习基础", relation: "PREREQUISITE_OF" },
      { source: "机器学习基础", target: "数据预处理", relation: "PREREQUISITE_OF" },
      { source: "数据预处理", target: "线性回归", relation: "PREREQUISITE_OF" },
      { source: "线性回归", target: "神经网络", relation: "PREREQUISITE_OF" },
      { source: "神经网络", target: "深度学习", relation: "PREREQUISITE_OF" },
      { source: "装饰器", target: "生成器", relation: "RELATED_TO" },
      { source: "面向对象", target: "装饰器", relation: "RELATED_TO" },
    ];

    try {
      await axios.post(`${API_BASE_URL}/api/visualization/knowledge-graph/import`, {
        nodes: demoNodes,
        edges: demoEdges,
      });
      fetchGraph();
      setShowImport(false);
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error);
      alert("导入失败: " + msg);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 bg-white border-b flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-gray-800">知识图谱可视化</h2>
          <p className="text-sm text-gray-500">
            Neo4j 知识图谱 — 知识点依赖关系与学习路径
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={fetchGraph}
            className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 text-sm"
          >
            刷新
          </button>
          <button
            onClick={() => setShowImport(!showImport)}
            className="px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
          >
            导入示例数据
          </button>
        </div>
      </div>

      {showImport && (
        <div className="p-4 bg-yellow-50 border-b text-sm">
          <p className="text-yellow-700 mb-2">
            点击下方按钮导入 Python 学习路径的示例知识图谱数据到 Neo4j：
          </p>
          <button
            onClick={importDemoData}
            className="px-4 py-2 bg-yellow-500 text-white rounded-lg hover:bg-yellow-600 text-sm"
          >
            确认导入示例数据
          </button>
          <button
            onClick={() => setShowImport(false)}
            className="ml-2 px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 text-sm"
          >
            取消
          </button>
        </div>
      )}

      <div className="flex-1">
        {nodes.length > 0 ? (
          <div style={{ height: "calc(100vh - 220px)" }}>
            <ReactFlow nodes={nodes} edges={edges} fitView>
              <Background color="#e2e8f0" gap={20} />
              <Controls />
              <MiniMap
                nodeStrokeColor="#667eea"
                nodeColor="#667eea"
                maskColor="rgba(102, 126, 234, 0.1)"
              />
            </ReactFlow>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400">
            <div className="text-center">
              <div className="text-5xl mb-3">🕸️</div>
              <p className="text-lg">知识图谱为空</p>
              <p className="text-sm mt-1">点击"导入示例数据"添加演示数据</p>
              <p className="text-xs mt-3 text-gray-300">
                确保 Neo4j 服务已启动 (bolt://localhost:7687)
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
