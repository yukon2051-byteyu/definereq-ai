"""公開アプリで実際のAIを実行して確認する（有料。架空の案件を使う）。

AIを実行するのは「会議準備」と「議事録の整理」の2回だけ。
パスワードはファイルから読み、画面にもログにも出さない。結果にはAIの出力（架空案件の内容）だけを記録する。

使い方：python scripts/real_ai_check.py <URL> <保存先> <パスワードのファイル>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
URL, OUT, CODE_FILE = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
OUT.mkdir(parents=True, exist_ok=True)
CODE = CODE_FILE.read_text(encoding="utf-8-sig").strip()
INITIAL = "社員100名の会社で、Excelによる勤怠集計をWebシステムへ更新したい。打刻漏れの確認と月末集計に時間がかかる。Web打刻、上長の修正承認、給与ソフト向けCSV出力を検討している。予算、導入時期、勤務形態は未確認。"
MINUTES = ("勤怠システム更新の初回ヒアリング。利用対象は社員100名。現在はExcelで集計し、月末集計に2日かかる。従業員がWebで打刻し、打刻漏れや修正は上長が承認する案を検討する。"
           "給与ソフトへはCSVで連携したいが項目と形式は未確認。導入時期と予算は未定。次回までに人事担当が現行の勤怠表を用意する。上記の機能はまだ合意していない。")
AI_WAIT = 240000


def wait(g, ms=1800):
    g.wait_for_timeout(ms)


def run_ai(g, title):
    g.get_by_text(title).click()
    wait(g)
    g.get_by_role("button", name="この内容でAIを実行").click()
    g.get_by_text("件の候補を作成しました").first.wait_for(timeout=AI_WAIT)
    wait(g, 2500)


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    g = b.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True).new_page()
    g.goto(URL)
    g.wait_for_selector(".dr-hero", timeout=120000)
    wait(g)
    g.get_by_label("AIパスワード").fill(CODE)
    g.get_by_label("AIパスワード").press("Enter")
    wait(g)
    g.get_by_label("案件名").fill("勤怠システムの更新（架空テスト）")
    g.get_by_label("案件名").press("Tab")
    wait(g)
    g.get_by_role("button", name="案件を作成").click()
    g.wait_for_selector(".dr-title", timeout=30000)
    wait(g)

    g.get_by_role("button", name="会議の準備", exact=True).first.click()
    wait(g)
    g.get_by_label("現時点の理解").fill(INITIAL)
    g.get_by_role("button", name="案件内に反映").first.click()
    wait(g, 2500)
    g.get_by_role("tab", name="質問").click()
    wait(g, 800)
    run_ai(g, "AIで候補を作る：会議前の準備")
    g.screenshot(path=OUT / "prep.png")

    g.get_by_role("button", name="記録を取り込む", exact=True).first.click()
    wait(g)
    box = g.locator("[data-testid=stSelectbox]").filter(has_text="資料の種類")
    box.locator("input").click()
    g.keyboard.type("議事録")
    g.keyboard.press("Enter")
    wait(g)
    g.get_by_label("貼り付ける文章の名称").fill("初回ヒアリング議事録")
    g.get_by_label("貼り付ける文章の名称").press("Tab")
    wait(g, 800)
    g.get_by_label("文章を貼り付ける").fill(MINUTES)
    g.get_by_label("文章を貼り付ける").press("Control+Enter")
    wait(g)
    g.get_by_role("button", name="貼り付けた文章を案件内に登録").click()
    wait(g, 3000)

    g.get_by_role("button", name="要件を整理・判断", exact=True).first.click()
    wait(g)
    run_ai(g, "AIで候補を作る：会議後の整理")
    g.screenshot(path=OUT / "extract.png")

    with g.expect_download() as d:
        g.get_by_role("button", name="再開用ファイルをダウンロード").first.click()
    saved = OUT / "real.json"
    d.value.save_as(saved)
    b.close()

p = json.loads(saved.read_text(encoding="utf-8"))
runs = {r["id"]: r for r in p["ai_runs"]}
print("AI実行", [(r["task"], r["source"], r["items"], round(r["cost_jpy"], 2)) for r in p["ai_runs"]])
for c in p["candidates"]:
    print(f"[{runs[c['origin_run']]['task']}] {c['kind']}｜{c['text']}｜根拠{'なし' if c['no_evidence'] else 'あり'}｜数値{c['unsupported_numbers']}｜重複疑い{c.get('already_known')}")

texts = [c for c in p["candidates"] if c["kind"] in ("不足情報", "未回答")]
known = [c["text"] for c in texts if re.search(r"(利用|社員|従業員|対象).{0,6}(人数|規模)|背景|現状の集計|月末集計", c["text"]) and re.search(r"不明|未確認|未定", c["text"])]
print("確認：登録済みを不明と扱った疑い", known or "なし")
print("確認：要件", len(p["requirements"]), "判断", len(p["decisions"]), "（AIだけで作られていれば不具合）")
print("確認：未合意の維持", any("合意していない" in (c["text"] + (c.get("detail") or "")) for c in p["candidates"]))
weak = [c["text"] for c in p["candidates"] if runs[c["origin_run"]]["task"] == "extract" and c["no_evidence"]]
print("確認：議事録の候補で根拠なし", weak or "なし")
