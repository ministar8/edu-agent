import type { Metadata } from "next";
import { AuthProvider } from "@/lib/auth";
import "katex/dist/katex.min.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "智能教学辅导多Agent系统",
  description: "基于LangChain + LangGraph的多智能体协作教学系统",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen bg-[#f4f6fb] font-sans text-slate-800 antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
