"""資料の入口（参考資料と議事録）と、本文から次の作業へ進む流れの実ブラウザ確認（デスクトップ 1440×900、架空の案件）。

AIは代替応答のサーバーで動かす（有料APIは使わない）。確認すること：
  A. 新規案件：背景を保存 → 参考資料を登録（工程1のまま・議事録は初期選択しない）→ 会議の準備
  B. 質問・議題を反映 → 会議へ進む → 会議を2件登録 → 選んだ会議を選択済みで会議の記録を整理 → AIで整理 → AI候補を確認
  C. 次回の準備：前回の候補が残っていても「会議へ進む」。準備中に参考資料を追加し、入力途中の議題を保ったまま戻る
  D. 2回目の議事録：今回分と整理済みの前回分を区別し、前回の会議に自動でひもづけない
  E. 議事録から始める：工程1の補助リンクから工程3へ直接 → 会議の記録を整理
  F. 再開用ファイルから再開しても、参考資料の件数と次の案内が実際のデータと一致する

使い方：python scripts/entrance_flow_check.py <URL> <保存先> <AIパスワード>
"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
URL, OUT, CODE = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
OUT.mkdir(parents=True, exist_ok=True)
problems: list[str] = []


def check(ok, message):
    print(("OK  " if ok else "NG  ") + message)
    if not ok:
        problems.append(message)


def wait(g, ms=1800):
    g.wait_for_timeout(ms)


def main(g):
    return g.locator("[data-testid=stMain]")


def side(g):
    return g.locator("[data-testid=stSidebar]")


def body(g):
    return g.inner_text("body")


def title(g):
    return g.locator(".dr-title").first.inner_text()


def click(g, name, ms=2600):
    main(g).get_by_role("button", name=name, exact=True).first.click()
    wait(g, ms)


def selected(g):
    return [x.inner_text() for x in side(g).locator("[data-testid=stBaseButton-primary]").all()]


def primaries(g):
    return [x.inner_text() for x in main(g).locator("[data-testid=stBaseButton-primary]").all() if x.is_visible() and x.is_enabled()]  # 表示中のタブ・欄だけ


def chosen_meeting(g):
    """「関連付ける会議」で選ばれている値（選択欄に表示されている文字）。"""
    box = main(g).locator("[data-testid=stSelectbox]").filter(has_text="関連付ける会議").first
    return box.locator("input").input_value()


def top(g):
    g.goto(URL)
    g.wait_for_selector(".dr-hero", timeout=120000)
    wait(g)
    g.get_by_label("AIパスワード").fill(CODE)
    g.get_by_label("AIパスワード").press("Enter")
    wait(g, 2200)


def create(g, name):
    top(g)
    g.get_by_label("案件名").fill(name)
    g.get_by_label("案件名").press("Tab")
    wait(g)
    g.get_by_role("button", name="案件を作成").click()
    g.wait_for_selector(".dr-title", timeout=30000)
    wait(g, 2300)


def paste(g, name, text, button):
    g.get_by_role("tab", name="文章を貼り付けて取り込む").click()
    wait(g, 600)
    g.get_by_label("貼り付ける文章の名称").fill(name)
    g.get_by_role("textbox", name="文章を貼り付ける").fill(text)
    g.get_by_role("textbox", name="文章を貼り付ける").press("Tab")
    wait(g, 900)
    click(g, button, 3000)


def add_meeting(g, name):
    main(g).get_by_label("会議名").fill(name)
    main(g).get_by_role("button", name="会議を追加").click()
    wait(g, 2600)


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    c = b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    g = c.new_page()

    # ---- A ----
    create(g, "備品貸出管理の見直し（架空）")
    check(main(g).get_by_role("button", name="参考資料を登録する").count() == 1
          and main(g).get_by_role("button", name="すでに議事録がある場合は、議事録を取り込む →").count() == 1, "A 準備の概要：「参考資料」カードと、議事録への補助リンク")
    click(g, "背景・目的・関係者を入力")
    g.get_by_label("背景", exact=True).first.fill("備品の貸出を紙の台帳で管理している")
    g.get_by_label("背景", exact=True).first.press("Tab")
    wait(g, 800)
    click(g, "案件情報を保存")
    check(main(g).get_by_role("button", name="次へ：質問・議題 →").count() == 1, "A 背景の保存後：次は質問・議題（議事録の登録へは誘導しない）")
    click(g, "参考資料を登録する")
    t = body(g)
    check(title(g) == "参考資料" and selected(g) == ["参考資料"] and "登録する種類参考資料（要望）" in t.replace("\n", "") and "議事録として登録" not in t,
          f"A 参考資料の登録中は工程1（{selected(g)}）。議事録は初期選択しない")
    paste(g, "備品貸出の要望書", "貸出中の備品を一覧で見たい。", "貼り付けた文章を参考資料として登録")
    check("参考資料を登録しました（種別：要望　1件）" in body(g) and title(g) == "参考資料" and selected(g) == ["参考資料"], "A 登録直後は同じ工程で結果を表示")
    check(primaries(g) == ["会議の準備へ進む →"] and main(g).get_by_role("button", name="続けて参考資料を追加").count() == 1, "A 主ボタンは「会議の準備へ進む」、続けて追加も選べる")
    g.screenshot(path=OUT / "A_参考資料の登録直後.png")
    click(g, "会議の準備へ進む →", 3000)
    check(title(g) == "質問・議題" and selected(g) == ["質問・議題"], "A 会議の準備（質問・議題）が開く")

    # ---- B ----
    agenda = main(g).get_by_label("議題（1行に1件）")
    agenda.fill("貸出の申請方法")
    agenda.press("Tab")
    wait(g, 900)
    click(g, "案件内に反映", 3000)
    box = g.locator(".st-key-prep_saved_box")
    check(box.count() == 1 and "案件内に反映しました" in box.inner_text() and box.get_by_role("button", name="会議へ進む →").count() == 1
          and box.get_by_role("button", name="会議が終わっていれば、議事録を取り込む").count() == 1, "B 反映結果の近くに「会議へ進む」と「議事録を取り込む」")
    bb = box.bounding_box()
    check(primaries(g) == ["会議へ進む →"] and bb and 0 <= bb["y"] and bb["y"] + 60 <= 900, f"B 主ボタンは1つ（{primaries(g)}）で、反映の結果が画面内に見える")
    g.screenshot(path=OUT / "B_質問議題の反映後.png")
    box.get_by_role("button", name="会議へ進む →").click()
    wait(g, 3000)
    check(title(g) == "会議", "B 会議が開く")
    add_meeting(g, "第1回打ち合わせ")
    add_meeting(g, "第2回打ち合わせ")
    done = g.locator(".st-key-mtg_done_box")
    check(done.count() == 1 and "第2回打ち合わせ" in done.inner_text() and done.get_by_role("button", name="会議の記録を整理 →").count() == 1
          and done.get_by_role("button", name="質問・議題に戻る").count() == 1, "B 登録した会議の近くに「会議の記録を整理」と「質問・議題に戻る」")
    g.screenshot(path=OUT / "B_会議の登録後.png")
    # 一覧で第1回を選び、その会議の記録へ（押した対象の会議を開く）
    main(g).locator("[data-testid=stSelectbox]").filter(has_text="表示する項目").locator("input").click()
    wait(g, 500)
    g.get_by_role("option").filter(has_text="第1回打ち合わせ").first.click()
    wait(g, 2200)
    click(g, "質問・議題に戻る")
    check(title(g) == "質問・議題", "B 会議の前なら「質問・議題に戻る」で準備を続けられる")
    click(g, "会議へ進む →")
    main(g).locator("[data-testid=stSelectbox]").filter(has_text="表示する項目").locator("input").click()
    wait(g, 500)
    g.get_by_role("option").filter(has_text="第1回打ち合わせ").first.click()
    wait(g, 2200)
    main(g).get_by_role("button", name="会議の記録を整理 →").last.click()
    wait(g, 3000)
    mtg = chosen_meeting(g)
    check(title(g) == "会議の記録を整理" and "第1回打ち合わせ" in mtg and "対象の会議：" in body(g), f"B 選んだ会議（第1回）を選択済みで記録の整理へ（{mtg}）")
    main(g).get_by_label("貼り付ける議事録の名称").fill("第1回議事録")
    main(g).get_by_label("議事録の文章を貼り付ける").fill("貸出の申請は上長の承認が必要。返却期限は2週間。")
    main(g).get_by_label("議事録の文章を貼り付ける").press("Tab")
    wait(g, 900)
    click(g, "貼り付けた文章を議事録として登録", 3000)
    click(g, "選択した議事録をAIで整理する", 1000)
    g.get_by_text("件の候補を作成しました").first.wait_for(timeout=60000)
    wait(g, 2500)
    check(main(g).get_by_role("button", name="AI候補を確認する →").count() == 1, "B AI整理の完了後に「AI候補を確認する」")
    click(g, "AI候補を確認する →", 3000)
    check(title(g) == "AI候補の確認", "B AI候補の確認が開く")

    # ---- C：次回の準備（候補が残っている）。参考資料を追加して戻る ----
    side(g).get_by_role("button", name="2. 会議の準備").click()
    wait(g, 3000)
    g.screenshot(path=OUT / "C_次回の質問議題.png", full_page=True)
    check(title(g) == "質問・議題" and primaries(g) == ["会議へ進む →"], f"C 前回のAI候補が残っていても、質問・議題の主ボタンは「会議へ進む」（{primaries(g)}）")
    agenda = main(g).get_by_label("議題（1行に1件）")
    agenda.fill("貸出の申請方法\n返却の督促")
    agenda.press("Tab")
    wait(g, 900)
    click(g, "参考資料を追加する", 3000)
    check(title(g) == "参考資料", "C 質問・議題から参考資料を開く")
    paste(g, "現行の貸出ルール", "貸出は1人3点まで。", "貼り付けた文章を参考資料として登録")
    check(primaries(g) == ["会議の準備に戻る →"], f"C 登録後は「会議の準備に戻る」（{primaries(g)}）")
    click(g, "会議の準備に戻る →", 3000)
    kept = main(g).get_by_label("議題（1行に1件）").input_value()
    check(title(g) == "質問・議題" and kept == "貸出の申請方法\n返却の督促" and "反映していない入力があります" in body(g), "C 戻ると入力途中の議題が残り、未反映であることを表示")
    check(main(g).get_by_role("button", name="反映して会議へ進む →").count() == 1, "C 未反映のときは「反映して会議へ進む」を選べる")
    click(g, "案件内に反映", 3000)

    # ---- D：2回目の議事録 ----
    click(g, "会議が終わっていれば、議事録を取り込む", 3000)
    check(title(g) == "資料・議事録" and selected(g) == ["資料・議事録"] and "登録する種類議事録" in body(g).replace("\n", ""), "D 議事録の入口は「議事録として登録」")
    mtg = chosen_meeting(g)
    check("関連付けない" in mtg, "D 前回の会議に自動でひもづけない（関連付けない）")
    paste(g, "第2回議事録", "督促はメールで行う。", "貼り付けた文章を議事録として登録")
    check(primaries(g) == ["会議の記録を整理する →"] and title(g) == "資料・議事録", "D 登録直後は同じ工程で結果を表示し、次は「会議の記録を整理する」")
    click(g, "会議の記録を整理する →", 3000)
    t = body(g)
    chosen = main(g).locator("[data-testid=stMultiSelect]").first.inner_text()
    check("今回登録した議事録：第2回議事録" in t and "第2回議事録" in chosen and "第1回議事録" not in chosen, f"D 今回分だけを選択済み（前回分は再処理しない）：{chosen.splitlines()[-1] if chosen else ''}")
    main(g).locator("[data-testid=stMultiSelect]").first.locator("input").click()
    wait(g, 500)
    opts = [o.inner_text() for o in g.get_by_role("option").all()]
    check(any("第1回議事録（議事録・整理済み）" in o for o in opts), f"D 整理済みの前回分も必要に応じて選べる（{opts}）")
    g.keyboard.press("Escape")
    g.screenshot(path=OUT / "D_2回目の議事録.png")
    with g.expect_download() as d:
        side(g).get_by_role("button", name="再開用ファイルをダウンロード").click()
    saved = OUT / "entrance_resume.json"
    d.value.save_as(saved)
    c.close()

    # ---- E：議事録から始める ----
    c = b.new_context(viewport={"width": 1440, "height": 900})
    g = c.new_page()
    create(g, "備品貸出（架空・議事録から）")
    click(g, "すでに議事録がある場合は、議事録を取り込む →", 3000)
    check(title(g) == "資料・議事録" and selected(g) == ["資料・議事録"], "E 工程1の補助リンクから工程3の議事録の登録へ直接")
    paste(g, "初回議事録", "貸出の記録を残したい。", "貼り付けた文章を議事録として登録")
    click(g, "会議の記録を整理する →", 3000)
    check(title(g) == "会議の記録を整理" and "今回登録した議事録：初回議事録" in body(g), "E 「会議の記録を整理する」で今回の議事録を確認できる")
    c.close()

    # ---- F：再開 ----
    c = b.new_context(viewport={"width": 1440, "height": 900})
    g = c.new_page()
    top(g)
    g.locator('input[type="file"]').first.set_input_files(str(saved))
    wait(g, 2500)
    g.get_by_role("button", name="この案件を再開する").click()
    g.wait_for_selector(".dr-title", timeout=30000)
    wait(g, 2000)
    if title(g) != "準備の概要":
        click(g, "← 準備の概要に戻る")
    t = body(g)
    g.screenshot(path=OUT / "F_再開後.png", full_page=True)
    nxt = main(g).locator(".st-key-setup_next").inner_text() if main(g).locator(".st-key-setup_next").count() else ""
    check("登録済み 2件" in t and main(g).get_by_role("button", name="参考資料を確認・追加する").count() == 1, "F 再開後も参考資料は2件（議事録は数えない）")
    check("会議の記録を整理する →" in nxt and "第2回議事録" in nxt, f"F 次の案内は未整理の第2回議事録の整理（{nxt.splitlines()[0] if nxt else ''}）")
    c.close()
    b.close()

print("問題", len(problems))
for x in problems:
    print(" -", x)
