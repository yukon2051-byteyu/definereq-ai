"""主ボタンの配色の実ブラウザ確認（デスクトップ 1440×900）。AIは使わない（自分の案件は代替応答のサーバーで確認）。

トップの4ボタン、デモの主なステップと終了画面、自分の案件の背景編集・議事録登録直後・AI整理前後・候補採用で、
オレンジの主ボタンが1つであること、通常・ホバー・キーボードフォーカス・無効の見た目を、計算済みのスタイルで確かめる。
使い方：python scripts/button_color_check.py <URL> <保存先> <AIパスワード>
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
URL, OUT, CODE = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
OUT.mkdir(parents=True, exist_ok=True)
ORANGE, HOVER, INK = "rgb(249, 120, 50)", "rgb(249, 92, 14)", "rgb(23, 23, 23)"
problems: list[str] = []
MINUTES = "第1回打ち合わせ（架空）。講師が出欠を登録し、月別CSVを出力する。"


def check(ok, message):
    print(("OK  " if ok else "NG  ") + message)
    if not ok:
        problems.append(message)


def wait(g, ms=2600):
    g.wait_for_timeout(ms)


def oranges(g):
    """表示されているオレンジのボタンの文字（本文のみ）。"""
    return g.evaluate(f"""[...document.querySelectorAll('[data-testid=stMain] button, .dr-hero a.dr-btn')].filter(b=>b.offsetParent&&b.getBoundingClientRect().width>0
        &&getComputedStyle(b).backgroundColor==='{ORANGE}').map(b=>b.innerText.trim())""")


def style(loc):
    return loc.evaluate("b=>{const s=getComputedStyle(b);const p=b.querySelector('p')||b;return {bg:s.backgroundColor,color:getComputedStyle(p).color,outline:s.outlineStyle+' '+s.outlineWidth,border:s.borderStyle}}")


def main(g):
    return g.locator("[data-testid=stMain]")


def click(g, name, ms=2800):
    main(g).get_by_role("button", name=name, exact=True).first.click()
    wait(g, ms)


def one(g, want, label):
    found = oranges(g)
    check(found == [want], f"{label}：オレンジは「{want}」だけ（{found}）")


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    g = b.new_context(viewport={"width": 1440, "height": 900}).new_page()

    # トップ
    g.goto(URL)
    g.wait_for_selector(".dr-hero", timeout=120000)
    wait(g, 2000)
    hero = g.locator(".dr-hero a.dr-btn-p")
    s = style(hero)
    check(s["bg"] == ORANGE and s["color"] == INK, f"トップ：ヒーローの「案内付きでデモを見る」がオレンジ・濃い文字（{s}）")
    found = sorted(oranges(g))
    check(found == sorted(["案内付きでデモを見る", "経費申請のデモを見る", "売上集計・クラウド移行のデモを見る", "ネットワーク更新のデモを見る"]), f"トップ：オレンジはデモ開始の4ボタンだけ（{found}）")
    new = g.locator(".dr-hero a.dr-btn-s").first
    check(style(new)["bg"] == "rgb(255, 255, 255)", "トップ：「新しい案件を始める」「保存した案件から再開」は白いボタン")
    g.evaluate("document.getElementById('dr-demo').scrollIntoView({block:'start'})")
    wait(g, 800)
    g.screenshot(path=OUT / "1_トップのデモ一覧.png")
    card = main(g).get_by_role("button", name="経費申請のデモを見る")
    card.hover()
    wait(g, 400)
    hv = style(card)
    check(hv["bg"] == HOVER and hv["color"] == INK, f"ホバー：#F95C0E に変わり、濃い文字のまま（{hv['bg']}）")
    g.mouse.move(5, 5)
    card.focus()
    g.keyboard.press("Shift+Tab")
    g.keyboard.press("Tab")
    wait(g, 300)
    fc = style(card)
    check(fc["outline"].startswith("solid 3px"), f"キーボードフォーカス：太い枠でフォーカス位置を示す（{fc['outline']}）")
    g.screenshot(path=OUT / "2_フォーカス.png")
    for name, demo in (("経費申請のデモを見る", "経費申請アプリの刷新"), ("売上集計・クラウド移行のデモを見る", "拠点売上集計の自動化とクラウド移行"), ("ネットワーク更新のデモを見る", "拠点ネットワーク更新と遠隔保守")):
        g.goto(URL)
        g.wait_for_selector(".dr-hero", timeout=120000)
        wait(g, 1500)
        main(g).get_by_role("button", name=name).click()
        g.wait_for_selector(".dr-loc", timeout=30000)  # デモの画面に切り替わるのを待つ
        wait(g, 2000)
        check(demo in g.locator(".dr-sit").first.inner_text(), f"トップの「{name}」が対応するデモ（{demo}）につながる")
        if name == "経費申請のデモを見る":
            one(g, "次へ：会議前の準備", "デモ1 冒頭")
            main(g).get_by_role("button", name="ステップ一覧").click()
            wait(g, 700)
            g.locator("[data-testid=stPopoverBody]").get_by_role("button", name="5. 判断", exact=True).click()
            wait(g, 3000)
            one(g, "次へ：追加要望と影響", "デモ1 判断")
            g.screenshot(path=OUT / "3_デモ1の判断.png")
            click(g, "次へ：追加要望と影響")
            click(g, "次へ：判断後の仕様")
            one(g, "次へ：要件定義書と成果物", "デモ1 判断後の仕様")
            click(g, "次へ：要件定義書と成果物", 1000)
            g.wait_for_selector(".dr-end-h", timeout=30000)
            wait(g, 2500)
            one(g, "要件定義書の内容を見る", "デモ1 終了画面")
            g.screenshot(path=OUT / "4_デモ1の終了画面.png")

    # 自分の案件
    g.goto(URL)
    g.wait_for_selector(".dr-hero", timeout=120000)
    wait(g, 1500)
    g.get_by_label("AIパスワード").fill(CODE)
    g.get_by_label("AIパスワード").press("Enter")
    wait(g, 2200)
    g.get_by_label("案件名").fill("研修申込の管理（架空・配色の確認）")
    g.get_by_label("案件名").press("Tab")
    wait(g)
    g.get_by_role("button", name="案件を作成").click()
    g.wait_for_selector(".dr-title", timeout=30000)
    wait(g, 2300)
    click(g, "背景・目的・関係者を入力")
    one(g, "案件情報を保存", "背景の編集中")
    g.get_by_label("背景", exact=True).first.fill("申込をメールで受けている")
    g.get_by_label("背景", exact=True).first.press("Tab")
    wait(g, 800)
    click(g, "保存して資料・議事録へ進む", 3000)
    disabled = main(g).get_by_role("button", name="読み込む", exact=True)
    ds = style(disabled)
    check(disabled.is_disabled() and ds["bg"] != ORANGE and ds["border"] == "dashed", f"無効の主ボタン（ファイル未選択の「読み込む」）は色を抜いた点線の枠（{ds}）")
    g.get_by_role("tab", name="文章を貼り付けて取り込む").click()
    wait(g, 600)
    g.get_by_label("貼り付ける文章の名称").fill("第1回打ち合わせ議事録")
    g.get_by_role("textbox", name="文章を貼り付ける").fill(MINUTES)
    g.get_by_role("textbox", name="文章を貼り付ける").press("Tab")
    wait(g, 800)
    click(g, "貼り付けた文章を案件内に登録", 3200)
    one(g, "会議の記録を整理する →", "議事録を登録した直後")
    g.screenshot(path=OUT / "5_議事録の登録直後.png")
    click(g, "会議の記録を整理する →", 3000)
    one(g, "選択した議事録をAIで整理する", "整理対象を選択済み")
    click(g, "選択した議事録をAIで整理する", 1000)
    g.get_by_text("件の候補を作成しました").first.wait_for(timeout=60000)
    wait(g, 2500)
    one(g, "AI候補を確認する →", "AI整理が完了")
    click(g, "AI候補を確認する →", 3000)
    one(g, "未確認の候補を確認する ↓", "AI候補の確認")
    click(g, "要件に採用する内容を確認", 2800)
    one(g, "この内容で採用", "個別候補の採用確認を開いている")
    g.screenshot(path=OUT / "6_採用の確認.png", full_page=True)
    click(g, "この内容で採用", 3000)
    check("要件に採用 1件" in g.locator(".dr-now").first.inner_text(), "主ボタンで既存の操作（要件への採用）が行える")
    b.close()

print("問題", len(problems))
for x in problems:
    print(" -", x)
