"""前端冒烟测试（backlog #19）：真实浏览器跑通「注册/登录 → 提问 → 回答」。

**为什么必须用真实浏览器**：前端的风险集中在**只有浏览器里才存在的东西** ——
DOM 选择器、事件绑定、SSE 流的解析与渲染、登录后跳转。
这些在 `TestClient` 层**完全测不到**：后端返回 200 **不代表页面上会出现回答**。
一个 `id` 改名、一个事件没绑上，后端测试全绿而用户看到的是空白页。

**为什么要真实 HTTP 服务**：Playwright 驱动的是真浏览器，必须有真实端口。
这里在后台线程跑 uvicorn —— 于是**真实 HTTP 栈 + 真实静态文件服务 + 真实 SSE**
都走到了，而模型仍由 `USE_FAKE_MODEL=true` 兜住（`tests` 的 pytest-env 默认值），
不需要联网、不需要 API key。

**失败时的定位**：断言失败会带上页面截图（见 `_shot`），
否则"元素没出现"这种失败很难判断是选择器变了还是接口挂了。
"""

from __future__ import annotations

import asyncio
import socket
import sys
import time
import uuid
from contextlib import closing
from pathlib import Path
from urllib.request import urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
SCREENSHOT_DIR = ROOT / "_e2e_artifacts"

# ── 等待超时（毫秒）──────────────────────────────────────────────
# 按「CI 比开发机慢约一个数量级」定：实测本地整个 E2E 文件 **6.6s**，
# 而 CI 的 Test 步骤要 **72~94s**（runner 有资源争抢）。
# 在开发机上这些等待通常 <1s 就满足，但 CI 上偶发踩线会让整个 job 变红 ——
# 所以留足余量。**注意**：调大只是消除「环境慢」造成的假红，
# 真出问题时仍会失败（只是晚一点），不会把 bug 掩盖掉。
_WAIT_UI_MS = 20_000  # 纯前端渲染（localStorage → DOM、插入消息节点）
_WAIT_NAV_MS = 30_000  # 一次服务端往返 + 跳转（注册 → index.html）
_WAIT_ANSWER_MS = 90_000  # 一轮完整问答：多 Agent 编排 + 8 阶段检索链 + LLM


def _free_port() -> int:
    """要一个空闲端口 —— 固定端口在并行/重复运行时容易撞车。"""
    with closing(socket.socket()) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def live_server():
    """子进程跑 uvicorn，返回 base URL。

    **为什么用子进程而不是线程**：uvicorn 会调 `loop.add_signal_handler()`，
    而 Windows 的 asyncio **不支持**在非主线程里这么做，会抛 `NotImplementedError`
    让服务起不来（覆写 `install_signal_handlers` 也拦不住它在别处的调用）。
    子进程里的 uvicorn 跑在**主线程**，天然没这个问题。
    """
    import os
    import subprocess
    import sys

    port = _free_port()
    env = {
        **os.environ,
        "PYTHONPATH": str(SRC_DIR),
        # 与 pytest-env 一致：假模型 + 假 key，全程不联网
        "USE_FAKE_MODEL": "true",
        "DASHSCOPE_API_KEY": "sk-fake-dashscope-key",
    }
    # **stderr 必须落文件，不能用 PIPE**：用 PIPE 而不持续读取，
    # 管道缓冲区写满后子进程会**阻塞在写日志上**，表现为"服务永远起不来"。
    log_path = ROOT / "_e2e_artifacts" / "server.log"
    log_path.parent.mkdir(exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8")

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "service.service:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
        cwd=str(ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )

    def _fail(msg: str) -> None:
        log_file.flush()
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-2000:]
        pytest.fail(f"{msg}\n服务日志尾部:\n{tail}")

    base = f"http://127.0.0.1:{port}"
    # **就绪探针用 `/api/metrics` 而不是 `/health`**：
    # `/health` 会**并发探测 embedding / reranker / chromadb 三个外部依赖**，
    # 假模型环境下这些地址不可达，要等各自的超时才返回 —— 单次耗时远超探针超时，
    # 于是"服务明明起来了却一直探不到就绪"。
    # `/api/metrics` 只读本地缓存统计，毫秒级返回，且同样经过完整 app（含 lifespan）。
    deadline = time.time() + 180
    while time.time() < deadline:
        if proc.poll() is not None:
            _fail(f"服务进程提前退出（code={proc.returncode}）")
        try:
            with urlopen(f"{base}/api/metrics", timeout=3) as resp:  # noqa: S310
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.5)
    else:
        proc.terminate()
        _fail("服务未能在 180 秒内就绪")

    yield base

    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log_file.close()


@pytest.fixture(scope="module")
def browser():
    """Playwright + Chromium。

    浏览器缺失时 **skip 而不是 fail** —— 本地没装浏览器不该让整个测试套件红掉，
    但 CI 里必须装上（见 .github/workflows/test.yml）。
    """
    sync_api = pytest.importorskip("playwright.sync_api", reason="playwright 未安装")

    # **Windows 必须切到 Proactor 事件循环**：Playwright 的 sync API 内部用
    # `asyncio.create_subprocess_exec` 起 driver 子进程，而**只有 Proactor 支持**
    # 子进程 —— 默认的 `_WindowsSelectorEventLoop` 会抛 `NotImplementedError`。
    # （pytest-asyncio 在 Windows 上会设成 Selector，所以这里显式切回来。）
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    with sync_api.sync_playwright() as pw:
        try:
            # **用 `channel="chromium"` 而不是默认的 headless 模式**：
            # Playwright ≥1.49 的默认 headless 走 `chromium_headless_shell`
            # （一个独立下载的二进制），而 `channel="chromium"` 用的是
            # `playwright install chromium` 装的那份完整 Chromium。
            # 少一个下载目标，CI 也少一步。
            instance = pw.chromium.launch(channel="chromium")
        except Exception as exc:  # 浏览器二进制缺失
            pytest.skip(f"Chromium 不可用（请先跑 playwright install chromium）: {exc}")
        yield instance
        instance.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context()
    p = ctx.new_page()
    yield p
    ctx.close()


def _shot(page, name: str) -> str:
    """存一张截图用于失败定位，返回路径（失败时由断言消息带出）。"""
    SCREENSHOT_DIR.mkdir(exist_ok=True)
    path = SCREENSHOT_DIR / f"{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception:
        return "(截图失败)"
    return str(path)


def _register(page, base: str, username: str, password: str = "secret123") -> None:
    """走真实的注册 UI —— 这正是要测的东西，不能用 API 绕过。"""
    page.goto(f"{base}/login.html")
    page.click('.tab[data-mode="register"]')
    page.fill("#username", username)
    page.fill("#password", password)
    page.click("#submit-btn")
    page.wait_for_url("**/index.html", timeout=_WAIT_NAV_MS)


class TestFrontendSmoke:
    """「注册 → 提问 → 回答」一条链路。"""

    def test_register_lands_on_index_and_shows_user(self, page, live_server):
        _register(page, live_server, f"e2e_{uuid.uuid4().hex[:8]}")

        assert page.url.endswith("/index.html"), f"注册后未跳转，停在 {page.url}"
        # 用户名来自 localStorage（auth.js 写入），渲染在 #user-name
        (
            page.wait_for_function(
                "() => (document.getElementById('user-name')||{}).textContent?.trim().length > 0",
                timeout=_WAIT_UI_MS,
            ),
            f"#user-name 未填充 —— 截图: {_shot(page, 'register')}",
        )

    def test_ask_question_and_get_answer(self, page, live_server):
        """**核心用例**：输入问题 → 点发送 → 页面上真的出现回答。

        断言的是 **DOM 里出现了非空回答**，而不是"接口返回了 200" ——
        后者在渲染逻辑坏掉时依然会通过。
        """
        _register(page, live_server, f"e2e_{uuid.uuid4().hex[:8]}")

        page.fill("#chat-input", "什么是进程？")
        page.click("#send-btn")

        # 前端会先插入一条空的 .msg.ai，再随 SSE 流填充内容
        try:
            page.wait_for_function(
                """() => {
                    const nodes = document.querySelectorAll('.msg.ai');
                    return nodes.length > 0 &&
                           [...nodes].some(n => n.textContent.trim().length > 0);
                }""",
                timeout=_WAIT_ANSWER_MS,
            )
        except Exception as exc:
            # 失败时把**页面当前状态**写进断言消息 —— 它直接进 CI 日志，
            # 比截图更容易看到（截图要另外下载 artifact）。
            # 区分「压根没渲染出气泡」和「气泡出来了但一直空着」这两类完全不同的故障。
            snapshot = page.eval_on_selector_all(
                ".msg", "els => els.map(e => e.className + ' :: ' + e.textContent.slice(0, 60))"
            )
            raise AssertionError(
                f"提问后页面上没有出现回答 —— 截图: {_shot(page, 'ask')}\n"
                f"  当前 .msg 节点: {snapshot}\n"
                f"  检索指示器 .thinking 是否还在: {page.query_selector('.thinking') is not None}"
            ) from exc

        answers = page.eval_on_selector_all(".msg.ai", "els => els.map(e => e.textContent)")
        assert any(a.strip() for a in answers), f"回答为空: {answers}"

    def test_user_message_is_rendered(self, page, live_server):
        """用户自己发的话也要出现在页面上（否则是"发出去了但没显示"）。"""
        _register(page, live_server, f"e2e_{uuid.uuid4().hex[:8]}")

        page.fill("#chat-input", "测试消息")
        page.click("#send-btn")

        page.wait_for_selector(".msg.user", timeout=_WAIT_UI_MS)
        text = page.eval_on_selector_all(".msg.user", "els => els.map(e => e.textContent)")
        assert any("测试消息" in t for t in text), f"用户消息未渲染: {text}"


class TestLoginRedirect:
    """未登录时的行为 —— 前端最容易出静默问题的地方。"""

    def test_login_page_has_expected_controls(self, page, live_server):
        """钉住前端选择器 —— 它们被改名时，本测试会先红，而不是用户先发现。"""
        page.goto(f"{live_server}/login.html")
        for sel in ("#auth-form", "#username", "#password", "#submit-btn", "#error"):
            assert page.query_selector(sel) is not None, f"登录页缺少 {sel}"

    def test_index_has_chat_controls(self, page, live_server):
        _register(page, live_server, f"e2e_{uuid.uuid4().hex[:8]}")
        for sel in ("#chat-form", "#chat-input", "#send-btn", "#messages", "#user-name"):
            assert page.query_selector(sel) is not None, f"首页缺少 {sel}"


class TestStaticAssetsLoad:
    """静态资源必须真的能取到 —— 404 的 JS 会让页面静默失去全部交互。"""

    def test_js_and_css_are_served(self, page, live_server):
        for asset in ("/api.js", "/auth.js", "/app.js", "/theme.js", "/style.css"):
            resp = page.request.get(f"{live_server}{asset}")
            assert resp.status == 200, f"{asset} 取不到（{resp.status}）"

    def test_no_console_errors_on_login(self, page, live_server):
        """登录页不应有 JS 报错 —— 报错通常意味着某个资源没加载或语法错误。"""
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{live_server}/login.html")
        page.wait_for_timeout(1000)
        assert not errors, f"登录页有 JS 报错: {errors}"
