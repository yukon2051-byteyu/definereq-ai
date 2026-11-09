"""「案件の準備」と画面間の往復の実ブラウザ確認（架空の案件、AIは使わない）。

使い方：python scripts/setup_flow_check.py <URL> <保存先> <AIパスワード> [pc|sp]
sp では左メニューを開かず、本文のボタンだけで移動する。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from docx import Document
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
URL, OUT, CODE = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
SIZE = sys.argv[4] if len(sys.argv) > 4 else "pc"
OUT.mkdir(parents=True, exist_ok=True)
CTX = {"pc": {"viewport": {"width": 1440, "height": 900}}, "sp": {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}}[SIZE]
FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "v1_public_export.json"
problems: list[str] = []
doc = Document()
doc.add_paragraph("初回打ち合わせ議事録（架空）")
doc.add_paragraph("講師が出欠を登録する。予算は未確認。")
doc.save(OUT / "議事録.docx")


def check(ok, message):
    print(("OK  " if ok else "NG  ") + f"[{SIZE}] " + message)
    if not ok:
        problems.append(message)


def wait(g, ms=1700):
    g.wait_for_timeout(ms)


def body(g):
    return g.inner_text("body")


def click(g, name):
    g.get_by_role("button", name=name, exact=True).first.click()
    wait(g, 2300)


def title(g):
    return g.locator(".dr-title").first.inner_text()


def fill(g, label, text):
    box = g.get_by_label(label, exact=True).first
    box.fill(text)
    box.press("Tab")
    wait(g, 900)


def top(g):
    g.goto(URL)
    g.wait_for_selector(".dr-hero", timeout=120000)
    wait(g)


def position(g, anchor):
    return g.evaluate(f"Math.round(document.getElementById('{anchor}').getBoundingClientRect().top)")


def login(g):
    g.get_by_label("AIパスワード").fill(CODE)
    g.get_by_label("AIパスワード").press("Enter")
    wait(g, 2200)


def create(g, name):
    g.get_by_label("案件名").fill(name)
    g.get_by_label("案件名").press("Tab")
    wait(g)
    g.get_by_role("button", name="案件を作成").click()
    g.wait_for_selector(".dr-title", timeout=30000)
    wait(g)


def sidebar(g, name):
    """左メニューで移動する（PC幅のみ）。"""
    g.locator("[data-testid=stSidebar]").get_by_role("button", name=name, exact=True).first.click()
    wait(g, 2300)


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)

    # 6. トップの入口（パスワードの前後）
    for anchor, link in (("dr-new-create", "新しい案件を始める"), ("dr-resume", "保存した案件から再開")):
        g = b.new_context(**CTX).new_page()
        top(g)
        g.get_by_role("link", name=link).click()
        wait(g, 1500)
        height = CTX["viewport"]["height"]
        mark = f"(()=>{{const c=document.getElementById('{anchor}').closest('[data-testid=stColumn]');return getComputedStyle(c).outlineStyle}})()"
        other = "dr-resume" if anchor == "dr-new-create" else "dr-new-create"
        unmarked = f"(()=>{{const c=document.getElementById('{other}').closest('[data-testid=stColumn]');return getComputedStyle(c).outlineStyle}})()"
        before = position(g, anchor)
        hint = "作成するには" if anchor == "dr-new-create" else "再開するには"
        check(-10 <= before <= height - 200 and g.evaluate(mark) == "solid" and g.evaluate(unmarked) == "none" and hint in body(g), f"6 「{link}」で目的の欄が見え、その欄だけ強調（上端 {before}px）。パスワードの説明あり")
        login(g)
        wait(g, 1500)
        after = position(g, anchor)
        check(-10 <= after <= height - 200 and g.evaluate(mark) == "solid", f"6 パスワード確定後も同じ欄が見えて強調が続く（上端 {after}px）")
        g.screenshot(path=OUT / f"{SIZE}_{anchor}.png")
        g.context.close()

    # 1. 背景から始める
    c = b.new_context(accept_downloads=True, **CTX)
    g = c.new_page()
    top(g)
    login(g)
    create(g, "研修申込の管理（架空・背景から）")
    t = body(g)
    check(title(g) == "案件の準備" and "未入力" in t and "未取り込み" in t, "4 作成直後は案件の準備（未入力・未取り込み）")
    g.screenshot(path=OUT / f"{SIZE}_setup_new.png")
    click(g, "背景・目的・関係者を入力")
    fill(g, "課題", "メールで申し込み、Excelで定員を管理している")
    click(g, "案件情報を保存")
    check("案件情報を保存しました" in body(g) and title(g) == "背景・目的・関係者", "1 保存すると、その場で反映を表示")
    click(g, "保存して資料・議事録を取り込む")
    check(title(g) == "資料・議事録", "1 保存して資料・議事録へ移動")
    g.get_by_role("tab", name="文章を貼り付けて取り込む").click()
    wait(g, 600)
    fill(g, "貼り付ける文章の名称", "要望メモ")
    g.get_by_label("文章を貼り付ける").fill("申込から受講履歴までを一つのアプリで管理したい。")
    g.get_by_label("文章を貼り付ける").press("Tab")
    wait(g, 800)
    click(g, "貼り付けた文章を案件内に登録")
    click(g, "背景・目的・関係者を編集")
    keep = g.get_by_label("課題", exact=True).first.input_value()
    check(keep.startswith("メールで申し込み"), "1 背景へ戻ると保存済みの入力が見える")
    fill(g, "目的", "申込の状況を一つの画面で見られるようにする")
    click(g, "案件情報を保存")
    click(g, "← 案件の準備に戻る")
    t = body(g)
    check("入力済み" in t and "取り込み済み 1件" in t and "背景・目的・関係者を編集" in t and "資料・議事録を取り込む" in t, "4 準備に戻ると2項目とも選べ、状態と件数が正しい")

    # 3. 入力途中で移動しても下書きが残る
    click(g, "背景・目的・関係者を編集")
    fill(g, "時期", "来年4月の開始を希望（未確認）")
    if SIZE == "pc":
        sidebar(g, "案件の準備")
        how = "左メニュー"
    else:
        click(g, "← 案件の準備に戻る")
        how = "本文の戻る操作"
    check(title(g) == "案件の準備" and "未保存の変更あり" in body(g), f"3 {how}で移動すると「未保存の変更あり」")
    click(g, "背景・目的・関係者を編集")
    check(g.get_by_label("時期", exact=True).first.input_value() == "来年4月の開始を希望（未確認）", f"3 {how}で戻っても下書きが残る")
    click(g, "案件情報を保存")
    click(g, "← 案件の準備に戻る")
    g.screenshot(path=OUT / f"{SIZE}_setup_progress.png")

    # 5. 再開用ファイル
    with g.expect_download() as d:
        g.get_by_role("button", name="再開用ファイルをダウンロード").last.click()
    saved = OUT / f"{SIZE}_resume.json"
    d.value.save_as(saved)
    data = json.loads(saved.read_text(encoding="utf-8"))
    check(data["profile"]["timeline"]["value"] == "来年4月の開始を希望（未確認）" and len(data["sources"]) == 1, "5 ファイルに保存済みの入力と取り込んだ本文を含む")
    c.close()

    # 2. 資料から始める（7. sp では本文のボタンだけで移動）
    c = b.new_context(accept_downloads=True, **CTX)
    g = c.new_page()
    top(g)
    login(g)
    create(g, "研修申込の管理（架空・資料から）")
    click(g, "資料・議事録を取り込む")
    g.locator('input[type="file"]').first.set_input_files(str(OUT / "議事録.docx"))
    wait(g, 2000)
    click(g, "読み込む")
    check("議事録1件を登録しました" in body(g), "2 資料から始めて取り込める")
    click(g, "背景・目的・関係者を入力")
    fill(g, "背景", "研修の申込をメールで受けている")
    click(g, "案件情報を保存")
    click(g, "資料・議事録へ")
    t = body(g)
    g.screenshot(path=OUT / f"{SIZE}_sources_back.png", full_page=True)
    shown = g.get_by_text("SRC-001 議事録.docx v1").count() + g.locator("input[value*='議事録.docx'], [title*='議事録.docx']").count()
    check(title(g) == "資料・議事録" and "抽出した本文" in t and (shown > 0 or "議事録.docx" in g.content()), "2 資料へ戻ると取り込み済みの内容を確認できる（画面写真でも確認）")
    check(g.get_by_text("議事録1件を登録しました").count() == 0, "2 往復しただけでは再取り込みしない（登録の表示が出ない。件数は下の「4」で確認）")
    click(g, "← 案件の準備に戻る")
    check("入力済み" in body(g) and "取り込み済み 1件" in body(g), "4 資料から始めた案件の状態と件数")
    check(g.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth") <= 0, "7 横にはみ出さない")
    c.close()

    # 5. 新しいセッションで再開（改修後のファイルと旧形式）
    for path, label in ((saved, "改修後のファイル"), (FIXTURE, "旧形式のファイル")):
        g = b.new_context(**CTX).new_page()
        top(g)
        login(g)
        g.locator('input[type="file"]').first.set_input_files(str(path))
        wait(g, 2500)
        click(g, "この案件を再開する")
        g.wait_for_selector(".dr-title", timeout=30000)
        wait(g)
        if label == "改修後のファイル":
            g.locator(".st-key-go_setup_ov button").click()  # 本文のボタン（左メニューを使わない）
            wait(g, 2300)
            ok = "入力済み" in body(g) and "取り込み済み 1件" in body(g)
            if SIZE == "pc":
                sidebar(g, "背景・目的・関係者")
            else:
                click(g, "背景・目的・関係者を編集")
            ok = ok and g.get_by_label("時期", exact=True).first.input_value() == "来年4月の開始を希望（未確認）"
            check(ok, "5 改修後のファイルから、保存済みの入力と取り込み件数が戻る")
        else:
            check(g.locator("[data-testid=stException]").count() == 0 and "再開" in g.locator(".dr-sit-work").first.inner_text(), "5 旧形式のファイルも読み込める")
        g.context.close()
    b.close()

print("問題", len(problems))
for x in problems:
    print(" -", x)
