"""工程を開いてもデモの続きに戻れることの実ブラウザ確認（デスクトップ 1440×900）。AIは使わない。

デモ途中 → 本文の補助ボタン／サイドバーから工程を開く → 工程内で別ページへ移動 → 元のデモステップへ戻る → 次へ。
見どころから始めた場合の戻り先、「デモを最初から見る」、別のデモへの切り替え、サイドバーの番号つき工程名も確かめる。
使い方：python scripts/process_return_check.py <URL> <保存先>
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
URL, OUT = sys.argv[1], Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
GROUPS = ["1. 案件の準備", "2. 会議の準備", "3. 記録の取り込み・整理", "4. 要件の確認・判断", "5. 共有・変更管理"]
problems: list[str] = []


def check(ok, message):
    print(("OK  " if ok else "NG  ") + message)
    if not ok:
        problems.append(message)


def wait(g, ms=2800):
    g.wait_for_timeout(ms)


def main(g):
    return g.locator("[data-testid=stMain]")


def side(g):
    return g.locator("[data-testid=stSidebar]")


def loc(g):
    return g.locator(".dr-loc").first.inner_text() if g.locator(".dr-loc").count() else ""


def selected(g):
    """サイドバーで選択表示（白い背景）になっている機能ページの名前。"""
    return g.evaluate("[...document.querySelectorAll('[data-testid=stSidebar] [class*=st-key-nav_sub_] button[kind=primary]')].map(b=>b.innerText.trim())")


def top(g):
    g.goto(URL)
    g.wait_for_selector(".dr-hero", timeout=120000)
    wait(g, 1500)


def to_step3(g):
    top(g)
    g.get_by_role("button", name="経費申請のデモを見る").click()
    wait(g, 3500)
    main(g).get_by_role("button", name="次へ：会議前の準備").click()
    wait(g)
    main(g).get_by_role("button", name="次へ：会議後の整理").click()
    wait(g)


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    g = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
    for entry in ("本文の補助ボタン", "サイドバー"):
        to_step3(g)
        names = side(g).locator("[class*=st-key-nav_group_] button").all_inner_texts()
        check([x.strip() for x in names] == GROUPS and loc(g) == "デモステップ 3/8 · 会議後の整理" and selected(g) == [],
              f"{entry}：番号つきの工程、本文の現在地、案内中は機能ページを選択表示にしない")
        if entry == "本文の補助ボタン":
            g.evaluate("document.querySelector('[data-testid=stSidebarCollapseButton] button')?.click()")  # 左メニューを閉じて本文だけで
            wait(g, 900)
            main(g).get_by_role("button", name="この案件のAI候補を確認する").click()
        else:
            opener = g.locator("[data-testid=stExpandSidebarButton]")  # 閉じていれば開く
            if opener.count() and opener.first.is_visible():
                opener.first.click()
                wait(g, 900)
            side(g).get_by_role("button", name="4. 要件の確認・判断").click()  # 案内中は工程を開くだけ（ステップは変わらない）
            wait(g, 2000)
            check(loc(g) == "デモステップ 3/8 · 会議後の整理" and selected(g) == [], "サイドバー：工程を開いてもステップは変わらず、選択表示もしない")
            side(g).get_by_role("button", name="AI候補の確認", exact=True).click()
        wait(g, 3000)
        back = main(g).get_by_role("button", name="← デモステップ 3/8『会議後の整理』に戻る")
        check(back.count() == 1, f"{entry}：工程を開くと本文に「← デモステップ 3/8『会議後の整理』に戻る」")
        if entry == "サイドバー":
            check(selected(g) == ["AI候補の確認"], f"サイドバー：実際に表示しているページだけを選択（{selected(g)}）")
            side(g).get_by_role("button", name="要件", exact=True).click()
        else:
            main(g).get_by_role("button", name="この案件の要件一覧を見る").first.click() if main(g).get_by_role("button", name="この案件の要件一覧を見る").count() else None
        wait(g, 3000)
        check(main(g).get_by_role("button", name="← デモステップ 3/8『会議後の整理』に戻る").count() == 1, f"{entry}：工程内で別ページへ移っても戻り先を保つ")
        main(g).get_by_role("button", name="← デモステップ 3/8『会議後の整理』に戻る").click()
        wait(g, 3000)
        check(loc(g) == "デモステップ 3/8 · 会議後の整理" and main(g).get_by_role("button", name="前へ：会議前の準備").count() == 1, f"{entry}：同じステップに戻り、前へ・次へが出る")
        main(g).get_by_role("button", name="次へ：会議での発言").click()
        wait(g)
        check(loc(g) == "デモステップ 4/8 · 会議での発言", f"{entry}：戻った後「次へ」で続きへ進める")

    # 見どころから始めた場合
    top(g)
    main(g).get_by_role("button", name="ステップ5「判断」から見る").click()
    wait(g, 3500)
    side(g).get_by_role("button", name="2. 会議の準備").click()
    wait(g, 2000)
    side(g).get_by_role("button", name="質問・議題", exact=True).click()
    wait(g, 3000)
    check(main(g).get_by_role("button", name="← デモステップ 5/8『判断』に戻る").count() == 1, "見どころから始めても、開いたステップ（5/8）が戻り先")
    side(g).get_by_role("button", name="デモを最初から見る").click()
    wait(g, 3000)
    check(loc(g) == "デモステップ 1/8 · 案件の背景", "「デモを最初から見る」でステップ1へ")
    top(g)
    g.get_by_role("button", name="ネットワーク更新のデモを見る").click()
    wait(g, 3500)
    check(loc(g) == "デモステップ 1/8 · 案件の背景" and "拠点ネットワーク" in g.locator(".dr-sit").first.inner_text(), "別のデモは、そのデモの開始位置から")
    b.close()

print("問題", len(problems))
for x in problems:
    print(" -", x)
