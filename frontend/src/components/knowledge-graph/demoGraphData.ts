import type { ImportGraphEdge, ImportGraphNode } from "@/types/knowledgeGraph";

export const demoGraphNodes: ImportGraphNode[] = [
  { name: "进程管理", category: "operating_system", description: "进程概念、状态转换、PCB" },
  { name: "进程调度", category: "operating_system", description: "FCFS、SJF、RR等调度算法" },
  { name: "进程同步", category: "operating_system", description: "信号量、管程、PV操作" },
  { name: "死锁", category: "operating_system", description: "四个必要条件、预防与检测" },
  { name: "内存管理", category: "operating_system", description: "分页、分段、虚拟内存" },
  { name: "文件管理", category: "operating_system", description: "目录结构、文件系统" },
  { name: "二叉树", category: "data_structure", description: "遍历、BST、AVL、红黑树" },
  { name: "图论", category: "data_structure", description: "BFS、DFS、最短路径、最小生成树" },
  { name: "排序算法", category: "data_structure", description: "快排、归并、堆排序" },
  { name: "CPU结构", category: "computer_organization", description: "数据通路、控制器、流水线" },
  { name: "存储器", category: "computer_organization", description: "Cache、主存、虚拟存储器" },
  { name: "TCP/UDP", category: "computer_network", description: "传输层协议、可靠传输" },
  { name: "数据链路层", category: "computer_network", description: "差错控制、流量控制、MAC" },
];

export const demoGraphEdges: ImportGraphEdge[] = [
  { source: "进程管理", target: "进程调度", relation: "PREREQUISITE_OF" },
  { source: "进程调度", target: "进程同步", relation: "PREREQUISITE_OF" },
  { source: "进程同步", target: "死锁", relation: "PREREQUISITE_OF" },
  { source: "内存管理", target: "文件管理", relation: "RELATED_TO" },
  { source: "二叉树", target: "图论", relation: "PREREQUISITE_OF" },
  { source: "排序算法", target: "二叉树", relation: "RELATED_TO" },
  { source: "CPU结构", target: "存储器", relation: "PREREQUISITE_OF" },
  { source: "TCP/UDP", target: "数据链路层", relation: "PREREQUISITE_OF" },
  { source: "进程管理", target: "内存管理", relation: "RELATED_TO" },
  { source: "存储器", target: "内存管理", relation: "RELATED_TO" },
];
