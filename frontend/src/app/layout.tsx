import type { Metadata } from "next";
import { Pacifico } from "next/font/google";
import { AuthProvider } from "@/shared/lib/auth";
import "katex/dist/katex.min.css";
import "./globals.css";

const pacifico = Pacifico({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-pacifico",
  display: "swap",
});

export const metadata: Metadata = {
  title: "智能教学辅导多Agent系统",
  description: "基于LangChain + LangGraph的多智能体协作教学系统",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className={pacifico.variable}>
      <body className="min-h-screen bg-[#F5F5F5] font-sans text-slate-800 antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
