"""前端体检动态实测：登录流 / 明暗主题 / 出题批改 / 二次生成清空缺陷 / 聊天错误路径 / 移动端 / 控制台。"""

import json
import os
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
SHOTS = os.path.join(os.environ["TEMP"], "edu_audit_shots")
os.makedirs(SHOTS, exist_ok=True)

console_msgs = []
page_errors = []
shot_log = []


def shot(pg, name):
    path = os.path.join(SHOTS, name)
    pg.screenshot(path=path, full_page=True)
    shot_log.append(name)
    print("shot:", name, flush=True)


with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    pg = ctx.new_page()
    pg.on("console", lambda m: console_msgs.append({"type": m.type, "text": m.text[:220]}))
    pg.on("pageerror", lambda e: page_errors.append(str(e)[:300]))
    pg.on(
        "requestfailed",
        lambda r: console_msgs.append({"type": "requestfailed", "text": f"{r.url} {r.failure}"}),
    )

    # 1) 登录页（浅色）
    pg.goto(f"{BASE}/login.html", wait_until="networkidle")
    shot(pg, "01_login_light.png")

    # 2) 登录页（深色）
    pg.click("#theme-toggle")
    time.sleep(0.4)
    shot(pg, "02_login_dark.png")
    pg.click("#theme-toggle")
    time.sleep(0.3)

    # 3) UI 登录 -> 主界面空态
    pg.fill("#username", "audit_20261017")
    pg.fill("#password", "auditpass123")
    pg.click("#submit-btn")
    pg.wait_for_url("**/index.html", timeout=20000)
    pg.wait_for_load_state("networkidle")
    time.sleep(0.5)
    shot(pg, "03_chat_empty_light.png")

    # 4) 主界面（深色）
    pg.click("#theme-toggle")
    time.sleep(0.4)
    shot(pg, "04_chat_empty_dark.png")
    pg.click("#theme-toggle")
    time.sleep(0.3)

    # 5) 练习视图空态
    pg.click('button[data-view="practice"]')
    time.sleep(0.4)
    shot(pg, "05_practice_empty.png")

    # 6) 出题（首题）
    pg.fill("#topic", "进程死锁")
    pg.click("#gen-btn")
    pg.wait_for_selector(".question-card", timeout=120000)
    shot(pg, "06_practice_generated.png")

    # 7) 作答 + 批改
    pg.locator(".answer-input").first.fill(
        "死锁的四个必要条件是互斥、请求与保持、不剥夺、循环等待。"
        "预防死锁可以破坏其中一个条件，例如静态分配资源破坏请求与保持条件。"
    )
    pg.locator(".question-submit").first.click()
    pg.wait_for_selector(".score-block", timeout=120000)
    time.sleep(0.6)
    shot(pg, "07_practice_graded.png")

    # 8) 再出第二题 —— 验证「清空已答题目」缺陷
    pg.fill("#topic", "二叉树遍历")
    pg.click("#gen-btn")
    time.sleep(45)
    shot(pg, "08_practice_second_gen.png")

    # 9) 聊天错误路径（embedding 不在线）
    pg.click('button[data-view="chat"]')
    pg.fill("#chat-input", "什么是进程死锁？")
    pg.click("#send-btn")
    time.sleep(30)
    shot(pg, "09_chat_error_path.png")

    # 10) 移动端：登录页 + 主界面
    ctx2 = b.new_context(
        viewport={"width": 375, "height": 812}, locale="zh-CN", is_mobile=True, has_touch=True
    )
    pg2 = ctx2.new_page()
    pg2.on(
        "console",
        lambda m: console_msgs.append({"type": m.type, "text": "[mobile] " + m.text[:200]}),
    )
    pg2.on("pageerror", lambda e: page_errors.append("[mobile] " + str(e)[:300]))
    pg2.goto(f"{BASE}/login.html", wait_until="networkidle")
    shot(pg2, "10_login_mobile.png")
    pg2.fill("#username", "audit_20261017")
    pg2.fill("#password", "auditpass123")
    pg2.click("#submit-btn")
    pg2.wait_for_url("**/index.html", timeout=20000)
    pg2.wait_for_load_state("networkidle")
    time.sleep(0.5)
    shot(pg2, "11_main_mobile.png")

    b.close()

result = {"shots": shot_log, "console": console_msgs, "page_errors": page_errors}
out = os.path.join(SHOTS, "audit_result.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=1)
print("=== DONE ===")
print(json.dumps(result, ensure_ascii=False, indent=1)[:3000])
