"""E2E 聊天演示：登录 → SSE 对话 → 校验有回复且无 hard failure。

定位（毕业设计工程表「E2E Demo」）：
- **只求跑通**，不求效果数字；与 task_eval / RAGAS 分工不同。
- 覆盖主路径：JWT 注册登录 → `POST /api/stream` → token/message 双流 → 终答回复。
- 可选前置检查：`/health`、TEI embedding（检索依赖）。

用法::

    # 服务已在 127.0.0.1:8000 时：
    .venv/Scripts/python.exe scripts/ops/e2e_chat_demo.py

    # 自动拉起服务（后台）再跑：
    .venv/Scripts/python.exe scripts/ops/e2e_chat_demo.py --start-service

    # 跳过 TEI 预检（仅验证 HTTP+SSE+Agent 图，检索可能降级）：
    .venv/Scripts/python.exe scripts/ops/e2e_chat_demo.py --skip-tei

退出码：0 = 全部通过；1 = 任一场景失败或前置检查失败。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8000")
PYTHON = sys.executable

# 演示三场景：对应「学 → 练 → 测」主闭环（聊天路径）
DEMO_TURNS: list[tuple[str, str]] = [
    ("qa", "什么是二叉搜索树？请简要说明其性质。"),
    ("generate", "请出 1 道关于二叉搜索树的基础选择题，给出答案与解析。"),
    ("grade", "判断对错并说明原因：二叉搜索树的中序遍历一定是升序序列。我的答案：对。"),
]


def _log(msg: str) -> None:
    print(msg, flush=True)


def _port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


async def _http_json(
    client: Any,
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    resp = await client.request(method, url, json=json_body, headers=headers)
    ctype = resp.headers.get("content-type", "")
    if "application/json" in ctype:
        try:
            return resp.status_code, resp.json()
        except Exception:
            return resp.status_code, resp.text
    return resp.status_code, resp.text


async def check_health(client: Any, base: str) -> bool:
    code, body = await _http_json(client, "GET", f"{base}/health")
    if code != 200:
        _log(f"  ✗ /health HTTP {code}")
        return False
    status = body.get("status") if isinstance(body, dict) else None
    _log(f"  ✓ /health status={status}")
    # embedding 依赖单独点名（TEI 宕机时检索会降级，但不阻断聊天图）
    deps = body.get("dependencies") if isinstance(body, dict) else None
    if isinstance(deps, dict):
        emb = deps.get("embedding") or {}
        _log(f"      embedding={emb.get('status')} latency_ms={emb.get('latency_ms')}")
    return True


def _load_tei_ready():
    import importlib.util

    path = ROOT / "scripts" / "ops" / "tei_ready.py"
    spec = importlib.util.spec_from_file_location("tei_ready_mod", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载 {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def ensure_auth(client: Any, base: str) -> dict[str, str]:
    """注册或登录，返回 Authorization 头。"""
    username = f"e2e_{secrets.token_hex(4)}"
    password = f"E2e!{secrets.token_hex(8)}"
    display = "E2E Demo"

    code, body = await _http_json(
        client,
        "POST",
        f"{base}/api/auth/register",
        json_body={"username": username, "password": password, "display_name": display},
    )
    token = None
    if code == 200 and isinstance(body, dict):
        token = body.get("access_token")
        _log(f"  ✓ 注册成功 user={username}")
    elif code == 400:
        code, body = await _http_json(
            client,
            "POST",
            f"{base}/api/auth/login",
            json_body={"username": username, "password": password},
        )
        if code == 200 and isinstance(body, dict):
            token = body.get("access_token")
            _log(f"  ✓ 登录成功 user={username}")
    if not token:
        _log(f"  ✗ 认证失败 HTTP {code}: {body}")
        raise SystemExit(1)
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def run_stream_turn(
    client: Any,
    base: str,
    headers: dict[str, str],
    message: str,
    *,
    timeout_s: float = 180.0,
) -> dict[str, Any]:
    """打 `/api/stream`，解析 SSE，返回统计。"""
    payload = {
        "message": message,
        "stream_tokens": True,
        "thread_id": str(uuid.uuid4()),
    }
    tokens: list[str] = []
    messages: list[dict[str, Any]] = []
    customs: list[Any] = []
    errors: list[str] = []
    done = False

    async with client.stream(
        "POST",
        f"{base}/api/stream",
        json=payload,
        headers=headers,
        timeout=timeout_s,
    ) as resp:
        if resp.status_code != 200:
            body = await resp.aread()
            return {
                "ok": False,
                "http_status": resp.status_code,
                "error": body.decode("utf-8", "replace")[:500],
                "reply": "",
                "n_tokens": 0,
                "n_messages": 0,
                "n_custom": 0,
            }
        async for raw in resp.aiter_lines():
            if not raw or not raw.startswith("data:"):
                continue
            data = raw[5:].strip()
            if data == "[DONE]":
                done = True
                break
            try:
                ev = json.loads(data)
            except json.JSONDecodeError:
                continue
            etype = ev.get("type")
            if etype == "token":
                tokens.append(str(ev.get("content") or ""))
            elif etype == "message":
                messages.append(ev.get("content") or ev)
            elif etype == "custom":
                customs.append(ev.get("content"))
            elif etype == "error":
                errors.append(str(ev.get("content") or "error"))

    # 终答：优先最后一条带 content 的 AI message，否则拼 token
    reply = ""
    for m in reversed(messages):
        if isinstance(m, dict) and m.get("type") in ("ai", "AIMessage") and m.get("content"):
            reply = str(m["content"])
            break
    if not reply:
        reply = "".join(tokens).strip()

    ok = bool(reply) and not errors and done
    return {
        "ok": ok,
        "http_status": 200,
        "reply": reply,
        "n_tokens": len(tokens),
        "n_messages": len(messages),
        "n_custom": len(customs),
        "errors": errors,
        "done": done,
    }


def start_service(base: str, log_path: Path) -> subprocess.Popen[str] | None:
    """后台启动 run_service.py；已监听则返回 None。"""
    host_port = base.rsplit("//", 1)[-1]
    host, _, port_s = host_port.partition(":")
    port = int(port_s or "8000")
    if _port_open(host or "127.0.0.1", port):
        _log(f"  · 服务已在 {base} 监听")
        return None

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _log(f"  · 启动服务 → 日志 {log_path}")
    log_f = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 — 进程存活期间保持
    proc = subprocess.Popen(
        [PYTHON, str(ROOT / "src" / "run_service.py")],
        cwd=str(ROOT),
        env=env,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        text=True,
    )
    # 等待就绪
    deadline = time.time() + 45
    while time.time() < deadline:
        if _port_open(host or "127.0.0.1", port):
            _log("  ✓ 服务已就绪")
            return proc
        if proc.poll() is not None:
            _log(f"  ✗ 服务进程退出 code={proc.returncode}，见 {log_path}")
            break
        time.sleep(0.4)
    _log("  ✗ 等待服务超时")
    return proc


async def main() -> int:
    ap = argparse.ArgumentParser(description="EDU-Agent E2E 聊天演示")
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--start-service", action="store_true", help="服务未起时后台拉起")
    ap.add_argument("--skip-tei", action="store_true", help="跳过 TEI embedding 预检")
    ap.add_argument("--timeout", type=float, default=180.0, help="单轮 SSE 超时秒数")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    _log("=" * 60)
    _log("EDU-Agent · E2E 聊天演示")
    _log(f"base={base}  python={PYTHON}")
    _log("=" * 60)

    proc: subprocess.Popen[str] | None = None
    if args.start_service:
        _log("\n[0] 服务")
        proc = start_service(base, ROOT / "data" / "logs" / "e2e_service.log")

    import httpx  # noqa: PLC0415

    hard_fail: list[str] = []
    async with httpx.AsyncClient(timeout=args.timeout) as client:
        _log("\n[1] 健康检查")
        if not await check_health(client, base):
            hard_fail.append("/health 不可用")
            if proc:
                proc.terminate()
            _log("\nE2E FAIL")
            return 1

        if not args.skip_tei:
            _log("\n[2] TEI embedding 预检")
            try:
                tei = _load_tei_ready()
                ok_emb, msg = tei.probe_embedding()
                _log(f"  {'✓' if ok_emb else '✗'} embedding: {msg}")
                if not ok_emb:
                    hard_fail.append(
                        "TEI embedding 不通 —— 完整检索演示需先起容器："
                        "powershell -File scripts/tei_deploy.ps1"
                        "（或加 --skip-tei 只验 HTTP/SSE/Agent 图）"
                    )
            except Exception as exc:  # noqa: BLE001
                hard_fail.append(f"TEI 预检异常: {type(exc).__name__}: {exc}")
                _log(f"  ✗ {hard_fail[-1]}")
        else:
            _log("\n[2] TEI 预检已跳过 (--skip-tei)")

        _log("\n[3] 认证")
        try:
            headers = await ensure_auth(client, base)
        except SystemExit:
            hard_fail.append("注册/登录失败")
            if proc:
                proc.terminate()
            return 1

        _log("\n[4] 聊天三场景（学 / 练 / 测）")
        for i, (name, message) in enumerate(DEMO_TURNS, 1):
            _log(f"\n  --- turn {i}/{len(DEMO_TURNS)} [{name}] ---")
            _log(f"  Q: {message[:80]}")
            t0 = time.time()
            try:
                result = await run_stream_turn(
                    client, base, headers, message, timeout_s=args.timeout
                )
            except Exception as exc:  # noqa: BLE001
                hard_fail.append(f"{name}: 异常 {type(exc).__name__}: {exc}")
                _log(f"  ✗ {hard_fail[-1]}")
                continue
            dt = time.time() - t0
            reply = result.get("reply") or ""
            _log(f"  A[{dt:.1f}s] len={len(reply)} tokens={result.get('n_tokens')} "
                 f"messages={result.get('n_messages')} custom={result.get('n_custom')}")
            if reply:
                _log(f"  preview: {reply[:160].replace(chr(10), ' ')}")
            if not result.get("ok"):
                hard_fail.append(
                    f"{name}: http={result.get('http_status')} "
                    f"errors={result.get('errors')} reply_len={len(reply)}"
                )
                _log(f"  ✗ {hard_fail[-1]}")
            else:
                _log("  ✓")

        _log("\n[5] 会话历史（可选）")
        # 用最后一轮 thread 不一定可回查（每轮新 thread）；再开一轮带固定 thread 验 history
        thread_id = str(uuid.uuid4())
        payload = {
            "message": "你好，简单打个招呼即可。",
            "stream_tokens": False,
            "thread_id": thread_id,
        }
        try:
            r = await client.post(
                f"{base}/api/stream", json=payload, headers=headers, timeout=args.timeout
            )
            _log(f"  stream(non-token) HTTP {r.status_code}")
            h = await client.post(
                f"{base}/api/history",
                json={"thread_id": thread_id},
                headers=headers,
                timeout=30,
            )
            _log(f"  history HTTP {h.status_code}")
            if h.status_code != 200:
                hard_fail.append(f"history HTTP {h.status_code}")
        except Exception as exc:  # noqa: BLE001
            hard_fail.append(f"history: {type(exc).__name__}: {exc}")

    if proc:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

    _log("\n" + "=" * 60)
    if hard_fail:
        _log("E2E FAIL")
        for x in hard_fail:
            _log(f"  - {x}")
        return 1
    _log("E2E PASS")
    _log("  登录 ✓ · SSE 流 ✓ · 三场景回复 ✓ · history ✓")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    raise SystemExit(asyncio.run(main()))
