"""各画面の「今どこ・何が済んだか・次に何を押すか」の実ブラウザ確認（デスクトップ 1440×900、架空の案件）。

自分の案件は、AIの応答だけを代替応答に差し替えたサーバーで確認する（有料APIは使わない）。
デモはAIを使わない。左メニューは閉じたまま、本文の操作だけで進む。
使い方：python scripts/screen_flow_check.py <URL> <保存先> <AIパスワード>
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
URL, OUT, CODE = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
OUT.mkdir(parents=True, exist_ok=True)
H = 900
problems: list[str] = []
MINUTES = "第1回打ち合わせ（架空）。講師が出欠を登録し、月別CSVを出力する。繰上げ回答期限の起算点と休日扱いは未確認。"


def check(ok, message):
    print(("OK  " if ok else "NG  ") + message)
    if not ok:
        problems.append(message)


def wait(g, ms=1800):
    g.wait_for_timeout(ms)


def body(g):
    return g.inner_text("body")


def main(g):
    return g.locator("[data-testid=stMain]")


def btn(g, name):
    return main(g).get_by_role("button", name=name, exact=True).first


def click(g, name, ms=2500):
    btn(g, name).click()
    wait(g, ms)


def in_view(loc):
    b = loc.bounding_box()
    return bool(b) and 0 <= b["y"] and b["y"] + min(b["height"], 40) <= H


def title(g):
    return g.locator(".dr-title, .dr-g-h").first.inner_text()


def close_sidebar(g):
    g.evaluate("document.querySelector('[data-testid=stSidebarCollapseButton] button')?.click()")
    wait(g, 900)


def top(g):
    g.goto(URL)
    g.wait_for_selector(".dr-hero", timeout=120000)
    wait(g)


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    g = b.new_context(viewport={"width": 1440, "height": H}).new_page()

    # ---- 自分の案件 ----
    top(g)
    g.get_by_label("AIパスワード").fill(CODE)
    g.get_by_label("AIパスワード").press("Enter")
    wait(g, 2200)
    g.get_by_label("案件名").fill("研修申込の管理（架空・画面の確認）")
    g.get_by_label("案件名").press("Tab")
    wait(g)
    g.get_by_role("button", name="案件を作成").click()
    g.wait_for_selector(".dr-title", timeout=30000)
    wait(g, 2300)
    close_sidebar(g)
    check(main(g).locator(".dr-next").count() == 0 and btn(g, "背景・目的・関係者を入力").count() == 1 and btn(g, "資料・議事録を取り込む").count() == 1,
          "2 議事録0件・背景なし：準備画面は2枚のカードが開始操作（次にすることは出さない）")

    # 議事録を貼り付けて登録
    click(g, "資料・議事録を取り込む")
    check(main(g).locator(".dr-brief").count() == 0 and main(g).get_by_text("どちらからでも始められます").count() == 0, "3 登録前の資料画面は取り込みに集中（共通の案内なし）")
    g.get_by_role("tab", name="文章を貼り付けて取り込む").click()
    wait(g, 600)
    g.get_by_label("貼り付ける文章の名称").fill("第1回打ち合わせ議事録")
    g.get_by_role("textbox", name="文章を貼り付ける").fill(MINUTES)
    g.get_by_role("textbox", name="文章を貼り付ける").press("Tab")
    wait(g, 900)
    click(g, "貼り付けた文章を案件内に登録", 3200)
    ok_msg = main(g).get_by_text("議事録1件を登録しました", exact=True)
    go = btn(g, "会議の記録を整理する →")
    check(ok_msg.count() == 1 and in_view(ok_msg) and in_view(go), "3 登録直後：「議事録1件を登録しました」と次の主ボタンが画面内に見える")
    check(not g.get_by_role("textbox", name="文章を貼り付ける").is_visible() and btn(g, "続けて資料を追加する").count() == 1, "3 登録後は追加のフォームを閉じ、「続けて資料を追加する」がある")
    g.screenshot(path=OUT / "1_議事録の登録直後.png")

    # 記録の整理の初期表示
    click(g, "会議の記録を整理する →", 3000)
    run = btn(g, "選択した議事録をAIで整理する")
    status = main(g).locator(".dr-now").first.inner_text()
    picked = main(g).locator("[data-testid=stMultiSelect]").first.inner_text()
    check(title(g) == "会議の記録を整理" and "未整理の議事録 1件" in status and "第1回打ち合わせ議事録" in status and "第1回打ち合わせ議事録" in picked,
          f"1 記録の整理：未整理の件数と対象の議事録名（選択済み）を表示（{status.splitlines()[0]}）")
    check(in_view(run) and run.is_enabled(), "1 「選択した議事録をAIで整理する」が初期表示に入り、押せる")
    check(main(g).locator("[data-testid=stExpander]").filter(has_text="議事録・録画を追加する").count() == 1 and g.get_by_label("貼り付ける議事録の名称").is_visible() is False,
          "1 取り込み欄は「議事録・録画を追加する」にまとめて閉じている（再取り込み不要）")
    check("件の候補を作成しました" not in body(g), "1 画面を開いただけではAIを実行しない")
    g.screenshot(path=OUT / "2_記録の整理の初期表示.png")
    run.click()
    g.get_by_text("件の候補を作成しました").first.wait_for(timeout=60000)
    wait(g, 2500)
    check("AI整理完了" in main(g).locator(".dr-now").first.inner_text() and btn(g, "AI候補を確認する →").count() == 1, "1 AIは押したときに実行され、件数と「AI候補を確認する」が出る（代替応答）")

    # 準備画面と記録整理の案内が状態と一致
    click(g, "← 案件の準備に戻る")
    nx = main(g).locator(".dr-next").inner_text()
    check("確認待ちの要件候補" in nx and btn(g, "AI候補を確認する →").count() == 1, f"2 候補あり：準備画面は「AI候補を確認する」（{nx.splitlines()[0]}）")

    # 背景を編集して保存
    click(g, "背景・目的・関係者を入力")
    check(main(g).locator(".dr-brief").count() == 0, "3 背景の編集中は、上部に別工程を勧める表示がない")
    box = g.get_by_label("背景", exact=True).first
    box.fill("申込をメールで受け、Excelで定員を管理している")
    box.press("Tab")
    wait(g, 800)
    click(g, "案件情報を保存", 2800)
    saved = main(g).get_by_text("案件情報を保存しました", exact=False)
    nxt = btn(g, "次へ：AI候補を確認する →")
    check(saved.count() == 1 and nxt.count() == 1, "3 保存後：フォームの近くに「案件情報を保存しました」と、状態に合う次の操作")
    click(g, "← 案件の準備に戻る")
    click(g, "背景・目的・関係者を編集")
    check(g.get_by_label("背景", exact=True).first.input_value() == "申込をメールで受け、Excelで定員を管理している", "3 最新の入力が保存されている")

    # その他の資料を登録 → 追加フォームを開く
    click(g, "資料・議事録へ")
    if btn(g, "続けて資料を追加する").count():
        click(g, "続けて資料を追加する")
    g.get_by_text("その他の資料を取り込む", exact=True).click()
    wait(g, 1500)
    g.get_by_role("tab", name="文章を貼り付けて取り込む").click()
    wait(g, 600)
    g.get_by_label("貼り付ける文章の名称").fill("要望書")
    g.get_by_role("textbox", name="文章を貼り付ける").fill("申込から受講履歴までを一つのアプリで管理したい。")
    g.get_by_role("textbox", name="文章を貼り付ける").press("Tab")
    wait(g, 900)
    click(g, "貼り付けた文章を案件内に登録", 3000)
    check(main(g).get_by_text("要望1件を登録しました", exact=True).count() == 1 and main(g).locator(".st-key-src_next").count() == 1, "3 その他の資料：「要望1件を登録しました」と状態に合う次の操作")
    click(g, "続けて資料を追加する")
    g.screenshot(path=OUT / "1b_続けて追加.png")
    other_checked = g.get_by_role("radio", name="その他の資料を取り込む").is_checked()
    check(g.get_by_role("tab", name="文章を貼り付けて取り込む").is_visible() and g.get_by_role("tab", name="ファイルから取り込む").is_visible() and other_checked,
          "3 「続けて資料を追加する」で追加のフォームを開ける（直前に選んだ「その他の資料」を引き継ぐ）")
    g.context.close()

    # ---- デモ ----
    g = b.new_context(viewport={"width": 1440, "height": H}, accept_downloads=True).new_page()
    for name, start in (("d1", "経費申請のデモを見る"), ("d2", "売上集計・クラウド移行のデモを見る"), ("d3", "ネットワーク更新のデモを見る")):
        top(g)
        g.get_by_role("button", name=start).click()
        wait(g, 3500)
        close_sidebar(g)
        nexts = main(g).get_by_role("button").filter(has_text="次へ：")
        loc = g.locator(".dr-loc").inner_text()
        check(nexts.count() == 1 and in_view(nexts.first) and main(g).get_by_role("button").filter(has_text="見どころへ：").count() == 1 and loc == "ステップ 1/8 · " + loc.split(" · ")[1],
              f"4 {name} 冒頭：「次へ」は1つ、見どころへの近道あり、現在地「{loc}」")
        if name == "d1":
            click(g, "次へ：会議前の確認点を見る")
            check(g.locator(".dr-loc").inner_text() == "ステップ 2/8 · 背景と準備", "4 d1 順に進むと現在地が更新される")
            click(g, "前へ：案件の背景")
            click(g, "見どころへ：3案の比較と採用理由", 3000)
            check(g.locator(".dr-loc").inner_text() == "ステップ 5/8 · 比較と判断", "4 d1 見どころから入っても現在地が一致（ステップ 5/8 · 比較と判断）")
            win = g.locator(".dr-vd-win")
            table = g.locator(".dr-t-cmp")
            nxt = btn(g, "次へ：追加要望の影響を見る")
            check(in_view(win) and "再申請を採用" in win.inner_text() and table.bounding_box()["y"] < H and in_view(nxt),
                  f"5 判断：採用案と理由、3案の比較（上端 {table.bounding_box()['y']:.0f}px）、次へ が根拠を開かずに初期表示に入る")
            check(g.locator(".dr-t-cmp .dr-t-win").inner_text().startswith("再申請") and "採用" in g.locator(".dr-t-cmp .dr-t-win .dr-chip").inner_text() and "根拠：本人の確認メール" in win.inner_text(),
                  "5 採用行に「採用」の表示、根拠の短い要約")
            g.screenshot(path=OUT / "3_デモ1の判断.png")
            g.get_by_text("判断の根拠と経緯を見る").click()
            wait(g, 900)
            check(main(g).get_by_text("判断に使っていない発言（話者未確認）").is_visible(), "5 詳細を開くと、話者未確認の発言を判断に使っていないことが分かる")
            click(g, "この判断に使った確認メールを見る", 3000)
            picked = g.locator("[data-testid=stSelectbox]").filter(has_text="表示する項目").evaluate("e=>[...e.querySelectorAll('input')].map(i=>i.value).join(' ')+e.textContent")
            check("判断の確認メール" in picked and btn(g, "← 5. 訂正方法の比較に戻る").count() == 1, "5 確認メールが開き、戻り先を表示")
            click(g, "← 5. 訂正方法の比較に戻る", 3000)
            click(g, "決定・合意の一覧を見る", 3000)
            check(g.locator(".dr-title").first.inner_text() == "決定・合意", "5 決定・合意の一覧が開く")
            click(g, "← 5. 訂正方法の比較に戻る", 3000)
            check(g.locator(".dr-loc").inner_text() == "ステップ 5/8 · 比較と判断", "5 元のステップへ戻る")
            click(g, "次へ：追加要望の影響を見る")
            click(g, "次へ：判断後の仕様を見る", 3000)
            grid = g.locator(".dr-cs-grid")
            nxt = btn(g, "次へ：要件定義書を見る")
            details = main(g).locator("[data-testid=stExpander]").filter(has_text="判断の詳細を見る")
            check(in_view(grid) and in_view(nxt) and nxt.bounding_box()["y"] < details.bounding_box()["y"] and "下書きの作成まで" in grid.inner_text() and "直接変更しない" in grid.inner_text(),
                  "6 変更後の仕様：3枚のカード（下書きまで・直接変更しない）と「次へ：要件定義書を見る」が詳細より先に見える")
            check(main(g).get_by_role("button").filter(has_text="次へ：").count() == 1, "6 「次へ」は1つ")
            g.screenshot(path=OUT / "4_デモ1の変更後の仕様.png")
            click(g, "次へ：要件定義書を見る", 3500)
            check(in_view(btn(g, "要件定義書の内容を見る")) and "デモ体験はここで終了です" in body(g), "6 成果物の画面へ進み、要件定義書のカードがすぐ見える")
        else:
            nxt = main(g).get_by_role("button").filter(has_text="次へ：").first
            for _ in range(6):  # 判断後の仕様まで進む
                main(g).get_by_role("button").filter(has_text="次へ：").last.click()
                wait(g, 2600)
            check(btn(g, "次へ：要件定義書を見る").count() == 1 and in_view(g.locator(".dr-cs-grid")) and main(g).get_by_role("button").filter(has_text="次へ：").count() == 1,
                  f"6 {name} 判断後の仕様：3枚のカードと「次へ：要件定義書を見る」（次へは1つ）")
            g.screenshot(path=OUT / f"5_{name}の変更後の仕様.png")
    b.close()

print("問題", len(problems))
for x in problems:
    print(" -", x)
