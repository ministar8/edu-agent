"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/shared/lib/auth";
import { getErrorMessage } from "@/shared/lib/errors";

export default function LoginPage() {
  const { login, register, user, loading } = useAuth();
  const router = useRouter();
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState("student");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!loading && user) {
      router.replace("/");
    }
  }, [loading, user, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      if (isRegister) {
        await register(username, password, displayName || username, role);
      } else {
        await login(username, password);
      }
    } catch (err: unknown) {
      setError(getErrorMessage(err, "操作失败"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#eef3f8] p-6 md:p-8">
      <div className="mx-auto flex min-h-[calc(100vh-3rem)] max-w-7xl overflow-hidden rounded-[32px] border border-slate-200 bg-white shadow-[0_24px_80px_rgba(15,23,42,0.08)]">
        <div className="flex w-full flex-col justify-center bg-white px-8 py-10 md:w-[44%] md:px-14 lg:px-16">
          <div className="mb-10">
            <div className="mb-5 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-100 text-3xl text-slate-700">
              🎓
            </div>
            <div className="space-y-3">
              <p className="text-sm font-medium tracking-[0.28em] text-slate-400">EDU AGENT</p>
              <h1 className="text-3xl font-semibold tracking-tight text-slate-900">智能教学辅导多Agent系统</h1>
              <p className="max-w-md text-sm leading-6 text-slate-500">
                以多 Agent 协作、RAG 检索与知识图谱为核心，为教学问答、练习生成与学习路径推荐提供统一入口。
              </p>
            </div>
          </div>

          <div className="w-full max-w-md rounded-3xl border border-slate-200 bg-slate-50/70 p-7 shadow-sm">
            <div className="mb-6 flex items-center justify-between">
              <div>
                <h2 className="text-xl font-semibold text-slate-800">{isRegister ? "创建账号" : "欢迎登录"}</h2>
                <p className="mt-1 text-sm text-slate-500">请输入账号信息以进入系统</p>
              </div>
              <span className="rounded-full bg-slate-200 px-3 py-1 text-xs font-medium text-slate-600">
                {isRegister ? "注册" : "登录"}
              </span>
            </div>

            {error && (
              <div className="mb-4 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">用户名</label>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-slate-800 outline-none transition focus:border-slate-400 focus:ring-4 focus:ring-slate-200/70"
                  placeholder="请输入用户名"
                  required
                  minLength={3}
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">密码</label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-slate-800 outline-none transition focus:border-slate-400 focus:ring-4 focus:ring-slate-200/70"
                  placeholder="请输入密码"
                  required
                  minLength={6}
                />
              </div>

              {isRegister && (
                <>
                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-slate-700">显示名称</label>
                    <input
                      type="text"
                      value={displayName}
                      onChange={(e) => setDisplayName(e.target.value)}
                      className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-slate-800 outline-none transition focus:border-slate-400 focus:ring-4 focus:ring-slate-200/70"
                      placeholder="可选，默认同用户名"
                    />
                  </div>

                  <div>
                    <label className="mb-1.5 block text-sm font-medium text-slate-700">角色</label>
                    <select
                      value={role}
                      onChange={(e) => setRole(e.target.value)}
                      className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-slate-800 outline-none transition focus:border-slate-400 focus:ring-4 focus:ring-slate-200/70"
                    >
                      <option value="student">学生</option>
                      <option value="teacher">教师</option>
                    </select>
                  </div>
                </>
              )}

              <button
                type="submit"
                disabled={submitting}
                className="w-full rounded-2xl bg-slate-800 px-4 py-3 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? "处理中..." : isRegister ? "注册并进入系统" : "进入系统"}
              </button>
            </form>

            <div className="mt-6 flex items-center justify-between gap-4 text-sm">
              <span className="text-slate-400">LangChain · LangGraph · RAG</span>
              <button
                onClick={() => {
                  setIsRegister(!isRegister);
                  setError("");
                }}
                className="font-medium text-slate-700 transition hover:text-slate-900"
              >
                {isRegister ? "已有账号，返回登录" : "没有账号，立即注册"}
              </button>
            </div>
          </div>
        </div>

        <div className="relative hidden flex-1 overflow-hidden bg-[linear-gradient(180deg,#f7fafc_0%,#e8f0f7_100%)] md:flex">
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(148,163,184,0.16),transparent_38%),radial-gradient(circle_at_bottom_right,rgba(59,130,246,0.12),transparent_36%)]" />
          <div className="relative flex w-full flex-col justify-between px-12 py-14 lg:px-16">
            <div className="max-w-xl space-y-4">
              <span className="inline-flex rounded-full border border-slate-300 bg-white/70 px-4 py-1 text-xs font-medium tracking-[0.24em] text-slate-500 backdrop-blur">
                MULTI-AGENT TEACHING SYSTEM
              </span>
              <h2 className="text-4xl font-semibold leading-tight text-slate-800">
                让多Agent协作、知识检索与教学辅导在同一平台高效完成。
              </h2>
              <p className="max-w-lg text-base leading-7 text-slate-500">
                面向教学场景，融合智能问答、练习生成、批改评估、知识库管理与知识图谱分析，帮助教师与学生构建更高效、更清晰的学习支持流程。
              </p>
            </div>

            <div className="relative mt-10 h-[420px] w-full">
              <div className="absolute left-8 top-10 h-56 w-56 rounded-[36px] border border-slate-200 bg-white/75 shadow-[0_20px_60px_rgba(15,23,42,0.08)] backdrop-blur" />
              <div className="absolute left-24 top-28 h-64 w-72 rounded-[40px] border border-slate-200 bg-slate-50 shadow-[0_22px_64px_rgba(15,23,42,0.08)]" />
              <div className="absolute right-12 top-12 h-44 w-44 rounded-[32px] bg-slate-200/70" />
              <div className="absolute right-20 top-24 h-24 w-24 rounded-full bg-slate-300/80" />
              <div className="absolute left-36 top-44 h-36 w-48 rounded-[28px] bg-[#dbe7f3]" />
              <div className="absolute left-48 top-56 h-28 w-24 rounded-[24px] bg-[#bfd2e4]" />
              <div className="absolute bottom-8 right-10 h-48 w-64 rounded-[36px] border border-slate-200 bg-white/80 p-6 shadow-[0_24px_70px_rgba(15,23,42,0.08)] backdrop-blur">
                <div className="mb-4 flex items-center gap-3">
                  <div className="h-10 w-10 rounded-2xl bg-slate-700" />
                  <div>
                    <div className="h-3 w-28 rounded-full bg-slate-300" />
                    <div className="mt-2 h-2.5 w-20 rounded-full bg-slate-200" />
                  </div>
                </div>
                <div className="space-y-3">
                  <div className="h-3 w-full rounded-full bg-slate-200" />
                  <div className="h-3 w-5/6 rounded-full bg-slate-200" />
                  <div className="h-3 w-2/3 rounded-full bg-slate-200" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
