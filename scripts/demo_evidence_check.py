"""デモの登録内容と根拠の閲覧の実ブラウザ確認（デスクトップ 1440×900）。AIは使わない。

1. 共通のサイドバーから「背景・目的・関係者」「資料・議事録」を開き、登録内容を閲覧できる（閲覧専用）
2. 見どころから資料・発言・判断の根拠を開ける（デモ1は確認メール、デモ3は録画の発言）
3. 詳細を開く前に現在地・要点・「次へ」が見え、戻ると元のステップから続けられる
4. 左メニューを閉じたまま、本文から根拠を開き、戻り、「次へ」で進める

使い方：python scripts/demo_evidence_check.py <URL> <保存先>
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
URL, OUT = sys.argv[1], Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
H = 900
problems: list[str] = []
DEMOS = {"d1": "経費申請のデモを見る", "d2": "売上集計・クラウド移行のデモを見る", "d3": "ネットワーク更新のデモを見る"}


def check(ok, message):
    print(("OK  " if ok else "NG  ") + message)
    if not ok:
        problems.append(message)


def wait(g, ms=2600):
    g.wait_for_timeout(ms)


def main(g):
    return g.locator("[data-testid=stMain]")


def btn(g, name):
    return main(g).get_by_role("button", name=name, exact=True).first


def click(g, name, ms=2800):
    btn(g, name).click()
    wait(g, ms)


def in_view(loc):
    b = loc.bounding_box()
    return bool(b) and 0 <= b["y"] and b["y"] + min(b["height"], 40) <= H


def loc_line(g):
    return g.locator(".dr-loc").first.inner_text() if g.locator(".dr-loc").count() else ""


def start(g, demo, sidebar_open=False):
    g.goto(URL)
    g.wait_for_selector(".dr-hero", timeout=120000)
    wait(g, 1500)
    g.get_by_role("button", name=DEMOS[demo]).click()
    wait(g, 3500)
    if not sidebar_open:
        g.evaluate("document.querySelector('[data-testid=stSidebarCollapseButton] button')?.click()")
        wait(g, 900)


def step_to(g, n, label):
    main(g).get_by_role("button", name="ステップ一覧").click()
    wait(g, 700)
    g.locator("[data-testid=stPopoverBody]").get_by_role("button", name=label, exact=True).click()
    wait(g, 3000)


def side(g, name):
    g.locator("[data-testid=stSidebar]").get_by_role("button", name=name, exact=True).first.click()
    wait(g, 3000)


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    g = b.new_context(viewport={"width": 1440, "height": H}).new_page()

    for demo in DEMOS:
        # 1. 共通サイドバーから登録内容を開く
        start(g, demo, sidebar_open=True)
        side(g, "背景・目的・関係者")
        t = g.inner_text("body")
        check(g.locator(".dr-title").first.inner_text() == "背景・目的・関係者" and "デモデータ · 閲覧専用" in t and g.get_by_text("関係者", exact=True).count() > 0
              and main(g).get_by_role("button", name="案件情報を保存").is_visible() is False, f"1 {demo} 共通サイドバーの「背景・目的・関係者」：登録内容を閲覧専用で表示")
        side(g, "3. 記録の取り込み・整理")
        side(g, "資料・議事録")
        t = g.inner_text("body")
        check("収録されている本文" in t and "デモデータ · 閲覧専用" in t and g.get_by_role("tab", name="ファイルから取り込む").count() == 0,
              f"1 {demo} 共通サイドバーの「資料・議事録」：収録されている本文を閲覧でき、登録の操作は出ない")
        if demo == "d1":
            g.screenshot(path=OUT / "1_d1_資料・議事録.png", full_page=True)
        back = main(g).get_by_role("button").filter(has_text="に戻る").first
        label = back.inner_text()
        back.click()
        wait(g, 3000)
        check(loc_line(g).startswith("デモステップ 1/8"), f"3 {demo} 「{label}」で元のステップへ戻る")

    # 2〜4. 左メニューを閉じたまま、本文から根拠を開いて戻る
    start(g, "d1")
    nxt = main(g).get_by_role("button").filter(has_text="次へ：").first
    check(in_view(g.locator(".dr-loc")) and in_view(nxt) and in_view(btn(g, "登録された背景・目的・関係者を見る")), "3 d1 冒頭：現在地・要点・次へと、登録内容への入口が初期表示に見える")
    click(g, "登録された背景・目的・関係者を見る")
    check(g.locator(".dr-title").first.inner_text() == "背景・目的・関係者" and "承認までの状況が見えない" in g.inner_text("body"), "2 d1 冒頭から登録された背景・関係者を開ける")
    click(g, "← デモステップ 1/8『案件の背景』に戻る")
    main(g).get_by_role("button", name="ステップ一覧").click()
    wait(g, 700)
    g.locator("[data-testid=stPopoverBody]").get_by_role("button", name="5. 判断", exact=True).click()
    wait(g, 3000)
    ev = btn(g, "この判断に使った確認メールを見る")
    check(in_view(ev) and in_view(btn(g, "次へ：追加要望と影響")) and loc_line(g) == "デモステップ 5/8 · 判断", "3 d1 判断：根拠を開く入口と「次へ」が初期表示に見える（入口は控えめ）")
    g.screenshot(path=OUT / "2_d1_判断.png")
    ev.click()
    wait(g, 3000)
    focus = g.locator(".dr-focus").first.inner_text() if g.locator(".dr-focus").count() else ""
    check("判断の確認メール" in focus and "金額の訂正は再申請とする方式を承認します" in focus and in_view(g.locator(".dr-focus")), f"2 d1 確認メールの該当箇所を直接開く（{focus.splitlines()[0] if focus else ''}）")
    g.screenshot(path=OUT / "3_d1_確認メール.png")
    click(g, "← デモステップ 5/8『判断』に戻る", 3000)
    check(loc_line(g) == "デモステップ 5/8 · 判断" and btn(g, "次へ：追加要望と影響").count() == 1, "3 d1 戻ると元のステップ番号と「次へ」が出る")
    click(g, "議事録の該当発言を見る", 3000)
    focus = g.locator(".dr-focus").first.inner_text() if g.locator(".dr-focus").count() else ""
    check("開いた発言" in focus and "話者確認：確認済み" in focus, "2 d1 判断の根拠の発言（話者確認済み）を直接開く")
    click(g, "← デモステップ 5/8『判断』に戻る", 3000)
    main(g).get_by_text("判断の根拠と経緯を見る").click()
    wait(g, 900)
    check(main(g).get_by_text("判断に使っていない発言（話者未確認）").is_visible(), "2 d1 話者未確認で判断に使わなかった発言を区別して表示")
    click(g, "次へ：追加要望と影響")
    check(loc_line(g).startswith("デモステップ 6/8"), "4 d1 戻った後、「次へ」でデモを続けられる")

    start(g, "d2")
    step_to(g, 4, "5. 意見調整")
    evs = main(g).get_by_role("button").filter(has_text="の該当")
    n = evs.count()
    label = evs.first.inner_text() if n else ""
    if n:
        evs.first.click()
        wait(g, 3000)
    check(n > 0 and g.locator(".dr-focus").count() == 1, f"2 d2 判断の根拠（{label}）の該当箇所を開ける")
    click(g, "← デモステップ 5/8『意見調整』に戻る", 3000)
    check(loc_line(g).startswith("デモステップ 5/8"), "3 d2 元のステップへ戻る")

    start(g, "d3")
    step_to(g, 2, "3. 録画の発言")
    check(in_view(btn(g, "使用した資料・議事録を見る")), "3 d3 記録のステップ：使用した資料名と「使用した資料・議事録を見る」")
    click(g, "録画・発言の画面でこの発言を見る", 3500)
    focus = g.locator(".dr-focus").first.inner_text() if g.locator(".dr-focus").count() else ""
    check("外部からの遠隔保守を提案します" in focus and main(g).get_by_role("button").filter(has_text="から再生").count() > 0, "2 d3 収録されている発言の該当箇所を開き、その時刻から再生できる")
    g.screenshot(path=OUT / "4_d3_録画の発言.png")
    click(g, "← デモステップ 3/8『録画の発言』に戻る", 3000)
    click(g, "使用した資料・議事録を見る", 3000)
    check("収録されている本文" in g.inner_text("body"), "2 d3 使用した資料・議事録を開ける")
    click(g, "← デモステップ 3/8『録画の発言』に戻る", 3000)
    main(g).get_by_role("button").filter(has_text="次へ：").last.click()
    wait(g, 3000)
    check(loc_line(g).startswith("デモステップ 4/8"), "4 d3 戻った後、「次へ」でデモを続けられる")
    b.close()

print("問題", len(problems))
for x in problems:
    print(" -", x)
