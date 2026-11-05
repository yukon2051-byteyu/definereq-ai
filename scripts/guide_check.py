"""3分の案内の実画面確認（開発用）。3件のデモの全工程を、PCとスマートフォンで撮影して測定する。

使い方：python scripts/guide_check.py <URL> <保存先フォルダ>
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL, OUT = sys.argv[1], Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
sys.stdout.reconfigure(encoding="utf-8")
JS = """()=>{const q=s=>document.querySelector(s);const h=q('.dr-g-h').getBoundingClientRect();const f=q('.dr-g-card');
return {title:q('.dr-g-h').innerText,prog:q('.dr-g-prog b').innerText,headTop:Math.round(h.top),firstCardTop:f?Math.round(f.getBoundingClientRect().top):null,
vh:innerHeight,overflow:document.documentElement.scrollWidth-document.documentElement.clientWidth,err:document.querySelectorAll('[data-testid=stException],[data-testid=stAlertContentError]').length}}"""

with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    for size, ctx in (("pc", {"viewport": {"width": 1440, "height": 900}}), ("sp", {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True})):
        for n in range(int(sys.argv[3]) if len(sys.argv) > 3 else 3):
            g = b.new_context(**ctx).new_page()
            g.goto(URL)
            g.wait_for_selector(".dr-hero", timeout=120000)
            g.wait_for_timeout(2500)
            g.get_by_role("button", name="3分の案内で見る").nth(n).click()
            i = 0
            while True:
                g.wait_for_selector(".dr-g-h", timeout=60000)
                g.wait_for_timeout(1800)
                r = g.evaluate(JS)
                print(size, f"d{n + 1}", r["prog"], "|", r["title"], "| 見出し", r["headTop"], "カード", r["firstCardTop"], "はみ出し", r["overflow"], "エラー", r["err"])
                if size == "pc" or i in (0, 3):
                    g.screenshot(path=OUT / f"{size}_d{n + 1}_{i}.png")
                nxt = g.get_by_role("button", name="次へ：")
                if nxt.count() == 0:
                    break
                nxt.first.click()
                g.wait_for_timeout(1200)
                i += 1
            g.context.close()
    b.close()
