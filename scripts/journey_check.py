"""本文の導線とサイドバーの実ブラウザ確認（デスクトップ 1440×900、左メニューは閉じたまま本文だけで進む）。

自分の案件：背景入力 → 議事録の登録 → AI整理 → 候補の確認・採用 → 成果物の出力 → 再開用ファイルの再開。
AIの応答は代替応答に差し替えたサーバーで確認する（有料APIは使わない）。
デモ：サイドバーの工程名を自分の案件と比べ、3件を本文だけで終了画面まで進める。

使い方：python scripts/journey_check.py <URL> <保存先> <AIパスワード> [レビュー用JSON]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
URL, OUT, CODE = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
REVIEW = Path(sys.argv[4]) if len(sys.argv) > 4 else None
OUT.mkdir(parents=True, exist_ok=True)
H = 900
GROUPS = ["1. 案件の準備", "2. 会議の準備", "3. 記録の取り込み・整理", "4. 要件の確認・判断", "5. 共有・変更管理"]
MINUTES = "第1回打ち合わせ（架空）。講師が出欠を登録し、月別CSVを出力する。繰上げ回答期限の起算点と休日扱いは未確認。本人によるキャンセルは開始前日17時までとする。"
problems: list[str] = []


def check(ok, message):
    print(("OK  " if ok else "NG  ") + message)
    if not ok:
        problems.append(message)


def wait(g, ms=1800):
    g.wait_for_timeout(ms)


def main(g):
    return g.locator("[data-testid=stMain]")


def btn(g, name, exact=True):
    return main(g).get_by_role("button", name=name, exact=exact).first


def click(g, name, ms=2600, exact=True):
    btn(g, name, exact).click()
    wait(g, ms)


def in_view(loc):
    b = loc.bounding_box()
    return bool(b) and 0 <= b["y"] and b["y"] + min(b["height"], 40) <= H


def title(g):
    return g.locator(".dr-title").first.inner_text()


def now(g):
    loc = main(g).locator(".dr-now")
    return " ".join(loc.first.inner_text().split()) if loc.count() else ""


def close_sidebar(g):
    g.evaluate("(()=>{const s=document.querySelector('[data-testid=stSidebar]');if(s&&s.getAttribute('aria-expanded')!=='false')document.querySelector('[data-testid=stSidebarCollapseButton] button')?.click()})()")
    wait(g, 900)


def sidebar_groups(g):
    """サイドバーの工程の名前（閉じていても文書の中にある文字で読む）。"""
    return g.evaluate("[...document.querySelectorAll('[data-testid=stSidebar] [class*=st-key-nav_group_] button')].map(b=>b.textContent.trim())")


def top(g):
    g.goto(URL)
    g.wait_for_selector(".dr-hero", timeout=120000)
    wait(g)


def login(g):
    g.get_by_label("AIパスワード").fill(CODE)
    g.get_by_label("AIパスワード").press("Enter")
    wait(g, 2200)


def resume(g, path):
    top(g)
    login(g)
    g.locator('input[type="file"]').first.set_input_files(str(path))
    wait(g, 2500)
    g.get_by_role("button", name="この案件を再開する").click()
    g.wait_for_selector(".dr-title", timeout=30000)
    wait(g, 2200)
    close_sidebar(g)


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    c = b.new_context(viewport={"width": 1440, "height": H}, accept_downloads=True)
    g = c.new_page()

    # ---- 自分の案件 ----
    top(g)
    login(g)
    g.get_by_label("案件名").fill("社内研修の申込管理（架空・導線の確認）")
    g.get_by_label("案件名").press("Tab")
    wait(g)
    g.get_by_role("button", name="案件を作成").click()
    g.wait_for_selector(".dr-title", timeout=30000)
    wait(g, 2300)
    project_groups = sidebar_groups(g)
    check(project_groups == GROUPS, f"3 自分の案件のサイドバー：{' → '.join(project_groups)}")
    close_sidebar(g)
    click(g, "背景・目的・関係者を入力")
    save = btn(g, "案件情報を保存")
    check(in_view(save), "5 背景・目的・課題のすぐ下の保存操作が、初期表示で見える")
    for label, text in (("背景", "メールで申し込み、Excelで定員を管理している"), ("目的", "申込から受講履歴までを一つの画面で見る"), ("課題", "定員の確認に時間がかかる")):
        box = g.get_by_label(label, exact=True).first
        box.fill(text)
        box.press("Tab")
        wait(g, 700)
    main(g).get_by_text("案件情報を詳しく入力").first.click()
    wait(g, 700)
    g.get_by_label("時期", exact=True).first.fill("来年4月に開始したい（未確認）")
    g.get_by_label("時期", exact=True).first.press("Tab")
    wait(g, 800)
    main(g).get_by_text("案件情報を詳しく入力").first.click()  # 閉じる
    wait(g, 700)
    main(g).get_by_text("案件情報を詳しく入力").first.click()  # 開き直す
    wait(g, 700)
    check(g.get_by_label("時期", exact=True).first.input_value() == "来年4月に開始したい（未確認）", "5 任意項目を開閉しても入力が残る")
    click(g, "案件情報を保存", 2800)
    check(btn(g, "次へ：質問・議題 →").count() == 1 and btn(g, "参考資料を登録する").count() == 1, "5 保存後：会議の準備（質問・議題）と参考資料の登録を案内")
    click(g, "← 準備の概要に戻る")
    click(g, "すでに議事録がある場合は、議事録を取り込む →")  # 議事録が手元にある人は工程3へ直接

    g.get_by_role("tab", name="文章を貼り付けて取り込む").click()
    wait(g, 600)
    g.get_by_label("貼り付ける文章の名称").fill("第1回打ち合わせ議事録")
    g.get_by_role("textbox", name="文章を貼り付ける").fill(MINUTES)
    g.get_by_role("textbox", name="文章を貼り付ける").press("Tab")
    wait(g, 900)
    click(g, "貼り付けた文章を議事録として登録", 3200)
    click(g, "会議の記録を整理する →", 3000)
    check("未整理の議事録 1件" in now(g) and in_view(btn(g, "選択した議事録をAIで整理する")), f"2 記録の整理：{now(g)}")
    btn(g, "選択した議事録をAIで整理する").click()
    g.get_by_text("件の候補を作成しました").first.wait_for(timeout=60000)
    wait(g, 2500)
    status = now(g)
    check(status.startswith("AI整理完了") and "確認待ち" in status and in_view(btn(g, "AI候補を確認する →")), f"4 AI整理直後：{status}／主操作「AI候補を確認する」")
    g.screenshot(path=OUT / "1_AI整理直後.png")
    click(g, "AI候補を確認する →", 3000)
    first = now(g)
    waiting = int(first.split("確認待ち")[1].split("件")[0])
    check(title(g) == "AI候補の確認" and in_view(main(g).locator(".dr-now")) and in_view(btn(g, "未確認の候補を確認する ↓")), f"4 AI候補の確認：{first}")
    exp = main(g).locator("[data-testid=stExpander] summary").all_inner_texts()
    check(any("要望" in x and "要件一覧" in x for x in exp) and any("決定" in x and "判断記録の下書き" in x for x in exp), "4 区分ごとに、確定したときの反映先を表示")
    click(g, "未確認の候補を確認する ↓", 2500)
    click(g, "要件に採用する内容を確認", 2500)
    check(btn(g, "この内容で採用").count() == 1, "4 確認欄を開いてから「この内容で採用」で確定する（確認と確定を区別）")
    click(g, "この内容で採用", 3000)
    after = now(g)
    check(f"確認待ち{waiting - 1}件" in after and "要件に採用 1件" in after and main(g).get_by_text("採用済み").count() > 0, f"4 1件採用後：{after}、採用した候補に「採用済み」")
    check(btn(g, "この内容で採用").count() == 0, "4 確定後は確認欄が閉じ、同じ候補を再び採用できない")
    msg = main(g).get_by_text("要件を下書きとして登録しました", exact=False)
    nxt, open_req = btn(g, "次の未確認候補へ"), btn(g, "登録した要件を開く")
    check(msg.count() == 1 and in_view(msg.first) and nxt.count() == 1 and open_req.count() == 1, "4 採用直後：結果の表示と「次の未確認候補へ」「登録した要件を開く」が見える")
    g.screenshot(path=OUT / "2_1件採用後.png")
    click(g, "登録した要件を開く", 3000)
    check(title(g).endswith("の要件一覧") and "から登録した要件" in g.inner_text("body"), "4 「登録した要件を開く」で今回登録した要件だけを開く")
    click(g, "← AI候補の確認に戻る", 3000)
    check(title(g) == "AI候補の確認", "4 要件からAI候補の確認へ戻る")
    for _ in range(12):  # 残りは却下して、確認待ち0件の状態にする
        rej = main(g).get_by_role("button", name="却下", exact=True)
        if not rej.count():
            break
        rej.first.click()
        wait(g, 2400)
    done = now(g)
    check("確認待ち0件" in done and btn(g, "採用した要件を確認する →").count() == 1, f"4 確認待ち0件：{done}／主操作「採用した要件を確認する」")
    click(g, "採用した要件を確認する →", 3000)
    check(title(g).endswith("の要件一覧") and btn(g, "ほかの作業：確認資料・要件定義書を作る").count() == 1, "2 要件の画面から、本文で資料の作成へ進める")
    click(g, "ほかの作業：確認資料・要件定義書を作る", 3000)
    main(g).get_by_text("要件定義書", exact=True).first.click()
    wait(g, 2200)
    click(g, "下書きとしてWordを作成する", 3500)
    with g.expect_download() as d:
        main(g).get_by_role("button", name="要件定義書をダウンロード（Word）").click()
    spec = OUT / "spec.docx"
    d.value.save_as(spec)
    check(spec.stat().st_size > 5000, f"2 成果物（要件定義書のWord）を本文だけで出力（{spec.stat().st_size:,}バイト）")

    # 再開：成果物の画面で保存し、新しいセッションで開く
    g.locator("[data-testid=stExpandSidebarButton], [data-testid=stSidebarCollapsedControl] button").first.click()
    wait(g, 900)
    main_page = g.locator(".dr-title").first.inner_text()
    with g.expect_download() as d:
        g.locator("[data-testid=stSidebar]").get_by_role("button", name="再開用ファイルをダウンロード").click()
    saved = OUT / "resume.json"
    d.value.save_as(saved)
    last = json.loads(saved.read_text(encoding="utf-8")).get("last_page")
    c.close()
    g = b.new_context(viewport={"width": 1440, "height": H}).new_page()
    resume(g, saved)
    check(last and title(g) == main_page and "案件を再開しました" in now(g), f"5 再開用ファイルで、保存時の画面（{main_page}）へ戻り、1行の通知を表示")
    g.context.close()

    if REVIEW:
        g = b.new_context(viewport={"width": 1440, "height": H}).new_page()
        resume(g, REVIEW)
        line = now(g)
        check(title(g) == "準備の概要" and line.startswith("案件を再開しました") and "AI候補が6件確認待ちです" in line and in_view(btn(g, "AI候補を確認する →")),
              f"5 レビュー用JSON：{line}／主操作「AI候補を確認する」が初期表示に入る")
        g.screenshot(path=OUT / "3_レビュー用JSONの再開.png")
        click(g, "AI候補を確認する →", 3000)
        line = now(g)
        check(title(g) == "AI候補の確認" and "確認待ち6件" in line and "要件に採用 1件" in line and in_view(main(g).locator(".dr-title")) and in_view(btn(g, "未確認の候補を確認する ↓")),
              f"5 レビュー用JSON：AI候補の確認で「{line}」、見出しと主操作が初期表示")
        g.screenshot(path=OUT / "4_レビュー用JSONの候補確認.png")
        g.context.close()

    # ---- デモ ----
    g = b.new_context(viewport={"width": 1440, "height": H}).new_page()
    for name, start in (("d1", "経費申請のデモを見る"), ("d2", "売上集計・クラウド移行のデモを見る"), ("d3", "ネットワーク更新のデモを見る")):
        top(g)
        g.get_by_role("button", name=start).click()
        wait(g, 3500)
        demo_groups = sidebar_groups(g)
        check(demo_groups == project_groups, f"3 {name} のサイドバーの工程が自分の案件と一致")
        close_sidebar(g)
        if name == "d1":
            main(g).get_by_role("button", name="ステップ一覧").click()
            wait(g, 700)
            g.locator("[data-testid=stPopoverBody]").get_by_role("button", name="5. 判断", exact=True).click()  # ステップ一覧は本文の外に開く
            wait(g, 3000)
            check(g.locator(".dr-loc").inner_text() == "デモステップ 5/8 · 判断", "3 本文のステップ一覧からステップ5へ")
            click(g, "この案件の決定・合意を確認する", 3000)
            check(btn(g, "← デモステップ 5/8『判断』に戻る").count() == 1, "3 詳細から元のステップへ戻る操作")
            click(g, "← デモステップ 5/8『判断』に戻る", 3000)
            click(g, "← デモステップ 5/8『判断』に戻る", 300) if btn(g, "← デモステップ 5/8『判断』に戻る").count() else None
            top(g)
            g.get_by_role("button", name=start).click()
            wait(g, 3500)
        n = 0
        while btn(g, "ほかのデモを見る").count() == 0 and n < 10:
            main(g).get_by_role("button").filter(has_text="次へ：").first.click()
            wait(g, 2600)
            n += 1
        check(btn(g, "ほかのデモを見る").count() == 1 and "デモ体験はここで終了です" in g.inner_text("body"), f"2 {name} を本文だけで終了画面まで（{n}回）")
    b.close()

print("問題", len(problems))
for x in problems:
    print(" -", x)
