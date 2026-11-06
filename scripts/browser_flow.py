"""実ブラウザでの操作確認（開発用）：資料と録画のアップロード、Word・Excel・JSONのダウンロード。

使い方：python scripts/browser_flow.py <URL> <保存先フォルダ>
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
FILES = ROOT / "definereq" / "demos" / "files"
URL, OUT = sys.argv[1], Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
sys.stdout.reconfigure(encoding="utf-8")


def wait(page, ms=2500):
    page.wait_for_function("!document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=60000)
    page.wait_for_timeout(ms)


def btn(page, name):
    page.get_by_role("button", name=name).first.click()
    wait(page)


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    page = ctx.new_page()
    page.goto(URL)
    page.wait_for_selector(".dr-hero", timeout=60000)
    wait(page)

    # 新規案件
    page.get_by_label("案件名").fill("ブラウザ確認の案件")
    page.get_by_label("AIパスワード").fill(os.environ["BROWSER_AI_PASSWORD"])
    page.get_by_label("AIパスワード").press("Enter")
    wait(page, 1500)
    page.get_by_label("案件名").press("Tab")
    wait(page, 800)
    btn(page, "案件を作成")
    print("案件作成", "ブラウザ確認の案件" in page.inner_text("body"))

    # 資料のアップロード
    btn(page, "資料")
    page.locator('input[type="file"]').first.set_input_files(str(FILES / "d2_移行計画案.pptx"))
    wait(page)
    btn(page, "読み込む")
    text = page.inner_text("body")
    print("PPT読込", "スライド別の抽出結果" in text, "図の警告", "理解していません" in text)
    page.screenshot(path=OUT / "flow_source.png")

    # 録画のアップロード（検証のみ。文字起こしは実行しない）
    btn(page, "録画・発言")
    page.locator('input[type="file"]').first.set_input_files(str(FILES / "d3_拠点ネットワーク定例.mp4"))
    page.get_by_text("音声 aac").wait_for(timeout=60000)  # 初回は動画ライブラリの読み込みに時間がかかる
    wait(page)
    text = page.inner_text("body")
    print("録画の検証", "音声 aac" in text, "費用の表示", "費用見込み" in text or "OpenAI" in text)
    page.screenshot(path=OUT / "flow_rec.png", full_page=True)

    # 出力
    btn(page, "← トップへ戻る")
    page.get_by_role("button", name="案内付きでデモを見る").nth(2).click()
    wait(page)
    btn(page, "全機能のメニューを見る")
    btn(page, "共有資料・出力")
    btn(page, "この内容でWordを作成する")
    with page.expect_download() as d:
        page.get_by_role("button", name="をダウンロード（Word）").click()
    d.value.save_as(OUT / "out.docx")
    print("Word", d.value.suggested_filename, (OUT / "out.docx").stat().st_size)
    wait(page)
    page.get_by_role("tab", name="Excel・JSON").last.click()
    wait(page, 1000)
    with page.expect_download() as d:
        page.get_by_role("button", name="Excelをダウンロード").click()
    d.value.save_as(OUT / "out.xlsx")
    print("Excel", (OUT / "out.xlsx").stat().st_size)
    with page.expect_download() as d:
        page.get_by_role("button", name="案件JSONをダウンロード").last.click()
    d.value.save_as(OUT / "out.json")
    print("JSON", (OUT / "out.json").stat().st_size)

    # 別のセッションで再開する
    ctx2 = b.new_context(viewport={"width": 1440, "height": 1000})
    p2 = ctx2.new_page()
    p2.goto(URL)
    p2.wait_for_selector(".dr-hero", timeout=60000)
    wait(p2)
    p2.get_by_label("AIパスワード").fill(os.environ["BROWSER_AI_PASSWORD"])
    p2.get_by_label("AIパスワード").press("Enter")
    wait(p2)
    p2.locator('input[type="file"]').first.set_input_files(str(OUT / "out.json"))
    wait(p2)
    print("概要の表示", p2.get_by_text("元の動画・資料ファイルはJSONに含まれません").count() > 0)
    p2.screenshot(path=OUT / "resume_summary.png", full_page=True)
    btn(p2, "この案件を再開する")
    print("再開", "拠点ネットワーク更新と遠隔保守" in p2.inner_text("body"), "保存の表示", "保存用ファイル" in p2.inner_text("body"))
    btn(p2, "会議")
    print("会議の画面", "前回からの引き継ぎ" in p2.inner_text("body"))
    p2.screenshot(path=OUT / "meetings.png", full_page=True)
    # 不正なファイルを読んでも案件を失わない
    bad = OUT / "bad.json"
    bad.write_text("{broken", encoding="utf-8")
    btn(p2, "← トップへ戻る")
    p2.locator('input[type="file"]').first.set_input_files(str(bad))
    wait(p2)
    text = p2.inner_text("body")
    print("不正JSONの案内", "読み込めませんでした" in text, "作業中の案件が残る", "作業中の案件" in text)
    btn(p2, "作業に戻る")
    print("作業に戻れる", "拠点ネットワーク更新と遠隔保守" in p2.inner_text("body"))
    b.close()
