"""公開アプリで、状況案内のAI補足と録画の文字起こしを実際に実行して確認する（有料。架空の案件を使う）。

パスワードはファイルから読み、画面にもログにも出さない。
使い方：python scripts/real_paid_check.py <URL> <保存先> <パスワードのファイル>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
URL, OUT, CODE_FILE = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
OUT.mkdir(parents=True, exist_ok=True)
CODE = CODE_FILE.read_text(encoding="utf-8-sig").strip()
VIDEO = Path(__file__).resolve().parent.parent / "definereq" / "demos" / "files" / "d3_拠点ネットワーク定例.mp4"
MINUTES = "勤怠システム更新の初回ヒアリング。利用対象は社員100名。給与ソフトへはCSVで連携したいが項目と形式は未確認。導入時期と予算は未定。上記の機能はまだ合意していない。"


def wait(g, ms=1800):
    g.wait_for_timeout(ms)


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    g = b.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True).new_page()
    g.goto(URL)
    g.wait_for_selector(".dr-hero", timeout=120000)
    wait(g)
    g.get_by_label("AIパスワード").fill(CODE)
    g.get_by_label("AIパスワード").press("Enter")
    wait(g)
    g.get_by_label("案件名").fill("自動チャージ確認（架空テスト）")
    g.get_by_label("案件名").press("Tab")
    wait(g)
    g.get_by_role("button", name="案件を作成").click()
    g.wait_for_selector(".dr-title", timeout=30000)
    wait(g)

    # 議事録を登録し、状況案内のAI補足を実行する
    g.get_by_role("button", name="記録の取り込み・整理", exact=True).first.click()
    wait(g)
    g.get_by_label("貼り付ける議事録の名称").fill("初回ヒアリング議事録")
    g.get_by_label("貼り付ける議事録の名称").press("Tab")
    wait(g, 800)
    g.get_by_label("議事録の文章を貼り付ける").fill(MINUTES)
    g.get_by_label("議事録の文章を貼り付ける").press("Control+Enter")
    wait(g)
    g.get_by_role("button", name="貼り付けた文章を議事録として登録").click()
    wait(g, 3000)
    g.get_by_text("AIに補足してもらう").click()
    wait(g)
    g.get_by_role("button", name="AIで補足を作成").click()
    g.get_by_text("AIの提案（").wait_for(timeout=240000)
    wait(g, 2500)
    g.screenshot(path=OUT / "guidance.png")
    print("AI補足の表示", g.get_by_text("AIの提案（").count() > 0, "再実行ボタンなし", g.get_by_role("button", name="AIで補足を作成").count() == 0)

    # 録画の文字起こし
    g.get_by_role("button", name="録画・発言", exact=True).first.click()
    wait(g, 2500)
    g.locator('input[type="file"]').first.set_input_files(str(VIDEO))
    g.get_by_text("音声 aac").wait_for(timeout=90000)
    wait(g, 2500)
    g.locator("[data-testid=stRadio] label").filter(has_text="OpenAI").first.click()
    wait(g, 2500)
    g.get_by_role("button", name="この内容で文字起こしを実行").click()
    g.get_by_text("件の発言を登録しました").first.wait_for(timeout=280000)
    wait(g, 3000)
    g.screenshot(path=OUT / "transcribe.png")

    with g.expect_download() as d:
        g.get_by_role("button", name="再開用ファイルをダウンロード").first.click()
    saved = OUT / "paid.json"
    d.value.save_as(saved)
    b.close()

p = json.loads(saved.read_text(encoding="utf-8"))
for n in p["guidance"]["notes"]:
    print("AI補足", n["advice_title"], "／", n["model"], "／", round(n["cost_jpy"], 2), "円")
    for i in n["items"]:
        print(f"  [{i['kind']}] {i['text']}｜根拠{'なし' if i['no_evidence'] else 'あり'}｜数値{i['unsupported_numbers']}")
print("確認：要件", len(p["requirements"]), "判断", len(p["decisions"]), "（AIだけで作られていれば不具合）")
for r in p["recordings"]:
    print("文字起こし", r["name"], r["method"], len(r["segments"]), "区間", "話者確認済み", sum(1 for s in r["segments"] if s["speaker_status"] == "確認済み"))
    for s in r["segments"][:4]:
        print("  ", round(s["start"], 1), s.get("speaker_label"), s["text"][:44])
