import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "智能教学辅导多Agent系统",
  description: "基于LangChain 1.0 + LangGraph 1.0的多智能体协作教学系统",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-gray-50">{children}</body>
    </html>
  );
}
