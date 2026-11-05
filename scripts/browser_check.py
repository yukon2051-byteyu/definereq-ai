"""実ブラウザでの表示確認（開発用）。起動中のアプリを開き、スクリーンショットと横スクロールの有無を確認する。

使い方：python scripts/browser_check.py <URL> <保存先フォルダ>
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8599"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "shots")
OUT.mkdir(parents=True, exist_ok=True)


def wait(page):
    page.wait_for_selector('[data-testid="stApp"]', timeout=60000)
    page.wait_for_function("!document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=60000)
    page.wait_for_timeout(3500)


def overflow(page) -> int:
    return page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")


def click(page, text):
    page.get_by_role("button", name=text, exact=True).first.click()
    wait(page)


with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="msedge", headless=True)
    # スマートフォン幅
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    page.goto(URL)
    page.wait_for_selector(".dr-hero", timeout=60000)  # 初回の描画を待ってから撮影する
    wait(page)
    print("mobile home overflow", overflow(page))
    page.screenshot(path=OUT / "m_home.png")
    page.screenshot(path=OUT / "m_home_full.png", full_page=True)
    click(page, "全画面を見る")
    print("mobile demo overflow", overflow(page))
    page.screenshot(path=OUT / "m_demo.png", full_page=True)
    ctx.close()

    # PC幅
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL)
    page.wait_for_selector(".dr-hero", timeout=60000)
    wait(page)
    page.screenshot(path=OUT / "home.png")
    page.screenshot(path=OUT / "home_full.png", full_page=True)
    print("pc overflow", overflow(page))
    click(page, "3分の案内で見る")
    page.screenshot(path=OUT / "tour1.png")
    print("tour panel top", page.get_by_text("案内 1/").first.bounding_box()["y"])
    click(page, "次へ")
    page.screenshot(path=OUT / "tour2.png")
    click(page, "案内を閉じて全画面を見る")
    for name, label in (("overview", "概要・残件"), ("reqs", "要件"), ("decisions", "決定・合意"), ("why", "なぜこの仕様か"), ("share", "共有資料・出力")):
        click(page, label)
        page.screenshot(path=OUT / f"{name}.png")
    print("page errors", errors[:5])
    browser.close()
