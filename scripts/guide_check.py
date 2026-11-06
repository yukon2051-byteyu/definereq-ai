"""案内付きデモの実ブラウザ確認（Edge ヘッドレス）。有料APIは使わない。

3件のデモの全画面を、PC幅とスマートフォン幅で確認する。
最終画面では資料を実際にダウンロードして開き、録画の再生位置も確かめる。

使い方：python scripts/guide_check.py <URL> <画像の保存先>
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

from docx import Document
from openpyxl import load_workbook
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
URL, OUT = sys.argv[1], Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
START = "案内付きでデモを見る"
ERRORS = "[data-testid=stException],[data-testid=stAlertContentError]"
SIZES = (("pc", {"viewport": {"width": 1440, "height": 900}}), ("sp", {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}))
problems: list[str] = []


def check(ok: bool, message: str) -> None:
    print(("OK  " if ok else "NG  ") + message)
    if not ok:
        problems.append(message)


def open_top(g):
    g.goto(URL)
    g.wait_for_selector(".dr-hero", timeout=120000)
    g.wait_for_timeout(2000)


def next_step(g) -> bool:
    nxt = g.get_by_role("button", name="次へ：")
    if nxt.count() == 0:
        return False
    nxt.first.click()
    g.wait_for_timeout(2200)
    return True


def downloads(g, name: str) -> None:
    for label, kind in (("Wordをダウンロード", "docx"), ("Excelをダウンロード", "xlsx")):
        buttons = g.get_by_role("button", name=label)
        for i in range(buttons.count()):
            with g.expect_download(timeout=30000) as d:
                buttons.nth(i).click()
            path = d.value.path()
            data = Path(path).read_bytes()
            filename = d.value.suggested_filename
            if kind == "docx":
                doc = Document(io.BytesIO(data))
                text = "\n".join(p.text for p in doc.paragraphs)
                check("サンプル" in text and filename.startswith("サンプル_") and "第" in filename, f"{name} Word {filename}")
            else:
                wb = load_workbook(io.BytesIO(data))
                check("要件" in wb.sheetnames and filename.endswith(".xlsx"), f"{name} Excel {filename}")


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    for size, ctx in SIZES:
        for n in range(3):
            name = f"{size}_d{n + 1}"
            c = b.new_context(accept_downloads=True, **ctx)
            g = c.new_page()
            open_top(g)
            if n == 0:
                g.screenshot(path=OUT / f"{size}_top.png", full_page=False)
                g.evaluate("document.getElementById('dr-demo').scrollIntoView({block:'start'})")
                g.wait_for_timeout(700)
                g.screenshot(path=OUT / f"{size}_cards.png")
            g.get_by_role("button", name=START).nth(n).click()
            i = 0
            while True:
                g.wait_for_selector(".dr-g-h", timeout=60000)
                g.wait_for_timeout(1500)
                body = g.inner_text("body")
                tag = g.locator(".dr-sit-tag").inner_text()
                check(g.locator(".dr-sit").count() == 1 and "｜" in tag and "ガイド" in body, f"{name}_{i} 状況案内（{tag[:36]}）")
                if i == 0:
                    check(all(w in body for w in ("現在の業務", "困りごと", "今回、変えたいこと", "関係者が重視すること", "検討中の論点", "このデモで確認すること")), f"{name} 背景の6項目")
                elif i < 7:
                    g.get_by_text("案件の背景を確認").click()
                    g.wait_for_timeout(600)
                    check("現在の業務" in g.inner_text("body") and g.locator(".dr-g-h").count() == 1, f"{name}_{i} 背景を再確認")
                    g.get_by_text("案件の背景を確認").click()
                    g.wait_for_timeout(300)
                over = g.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                check(over <= 0 and g.locator(ERRORS).count() == 0, f"{name}_{i} はみ出し{over}・エラーなし")
                check(" 0件" not in (g.locator(".dr-open").inner_text() if g.locator(".dr-open").count() else ""), f"{name}_{i} 未決に0件なし")
                g.screenshot(path=OUT / f"{name}_{i}.png")
                if i == 7 or not next_step(g):
                    break
                i += 1
            g.wait_for_selector(".dr-end-h", timeout=30000)
            g.wait_for_timeout(2500)
            body = g.inner_text("body")
            check(i == 7 and "デモ体験はここで終了です" in body and body.index("デモ体験はここで終了です") < body.index("作成されたサンプル資料"), f"{name} 最終画面")
            g.screenshot(path=OUT / f"{name}_end_full.png", full_page=False)
            downloads(g, name)
            check(g.locator(".dr-end-h").count() == 1, f"{name} ダウンロード後も最終画面のまま")
            g.get_by_role("button", name="内容を見る").first.click()
            g.wait_for_timeout(2000)
            check("この文書について" in g.inner_text("body"), f"{name} 内容を見る")
            more = g.get_by_text(re.compile(r"^全\d+件を見る$"))
            for k in range(more.count()):
                label = more.nth(k).inner_text()
                more.nth(k).click()
                g.wait_for_timeout(500)
                want = int(re.search(r"\d+", label).group())
                got = g.locator("[data-testid=stExpander]").filter(has_text=label).locator("[data-testid=stExpanderDetails] p").count()
                check(got == want, f"{name} {label}（表示{got}件）")
            g.get_by_role("button", name="ほかのデモを見る").click()
            g.wait_for_selector(".dr-hero", timeout=60000)
            g.wait_for_timeout(2500)
            top = g.evaluate("document.getElementById('dr-demo').getBoundingClientRect().top")
            check(-5 <= top <= 200, f"{name} デモ選択欄へ戻る（上端 {top:.0f}px）")
            check("体験済み" in g.inner_text("body") and g.get_by_role("button", name="もう一度見る").count() == 1, f"{name} 体験済み")
            c.close()

    # 録画の再生
    c = b.new_context(viewport={"width": 1440, "height": 900})
    g = c.new_page()
    open_top(g)
    g.get_by_role("button", name=START).nth(2).click()
    g.wait_for_selector(".dr-g-h", timeout=60000)
    for _ in range(2):
        g.wait_for_timeout(1200)
        next_step(g)
    play = g.get_by_role("button", name="から再生")
    label = play.first.inner_text()
    play.first.click()
    g.wait_for_selector("video", timeout=30000)
    g.wait_for_function("document.querySelector('video').readyState>=1", timeout=60000)  # 公開環境では読み込みに時間がかかる
    g.wait_for_timeout(1500)
    state = g.evaluate("(()=>{const v=document.querySelector('video');return {t:v.currentTime,err:v.error&&v.error.code,dur:v.duration}})()")
    want = int(label.split("▶")[-1].strip()[:2]) * 60 + int(label.split("▶")[-1].strip()[3:5])
    check(state["err"] is None and state["t"] >= want - 1 and state["dur"] > want, f"録画の再生 {label} → 位置 {state['t']:.1f}秒／長さ {state['dur']:.1f}秒")
    g.screenshot(path=OUT / "pc_play.png")
    # ガイドと機能画面の行き来
    title = g.locator(".dr-g-h").inner_text()
    g.get_by_role("button", name="確認状態を見る").click()
    g.wait_for_timeout(3000)
    check("機能画面" in g.inner_text("body"), "詳細へ移動すると機能画面の説明が出る")
    g.get_by_role("button", name="ガイドへ戻る").click()
    g.wait_for_selector(".dr-g-h", timeout=60000)
    g.wait_for_timeout(2500)
    check(g.locator(".dr-g-h").inner_text() == title, "ガイドの元の画面へ戻る")
    c.close()
    b.close()

print("問題", len(problems))
for x in problems:
    print(" -", x)
