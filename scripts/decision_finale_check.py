"""AI候補からの判断記録・会議登録・再開用ファイルの通知・デモの最終画面の実ブラウザ確認（デスクトップ 1440×900、架空データ）。

AIは代替応答のサーバーで動かす（有料APIは使わない）。確認すること：
  1. AI候補の確認欄を開いただけでは登録されず、「判断記録の下書きを作成」で1回だけ作られる。
     判断記録だけの場合と要件も作る場合で、完了表示と遷移先が実際の結果に一致する
  2. 質問・議題の未反映入力を保ったまま会議へ進める。初回・次回の会議の登録直後にボタンが重複せず、選んだ会議が記録画面に引き継がれる
  3. 再開用ファイルを出力して案件を更新すると通知が出て、再出力で消える。読み戻すと更新した内容が戻る
  4. デモ3件を1から8まで進め、最終画面で代表例を追加操作なしで読める。全文のプレビューとWord出力が使え、機能画面から元のステップへ戻れる

使い方：python scripts/decision_finale_check.py <URL> <保存先> <AIパスワード>
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

from docx import Document
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
URL, OUT, CODE = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
OUT.mkdir(parents=True, exist_ok=True)
problems: list[str] = []
NOTICE = "前回のファイルには、最新の変更が入っていません。閉じる前に、もう一度ダウンロードしてください。"
MINUTES = "第1期は照合と履歴の閲覧のみとする。確認時刻を記録したい。保存期間は未定。"


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


def title(g):
    return g.locator(".dr-title").first.inner_text()


def click(g, name, ms=2600):
    main(g).get_by_role("button", name=name, exact=True).first.click()
    wait(g, ms)


def count(g, name):
    return main(g).get_by_role("button", name=name, exact=True).count()


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


def project_counts(g, path):
    """再開用ファイルを保存して、判断記録と要件の件数を読む（画面の外からデータを確かめる）。"""
    with g.expect_download() as d:
        side(g).get_by_role("button", name="再開用ファイルをダウンロード").click()
    d.value.save_as(path)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    wait(g, 1500)
    return data


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    c = b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    g = c.new_page()

    # ---- 2：質問・議題 → 会議（初回・次回）→ 会議の記録を整理 ----
    create(g, "備品貸出の判断（架空）")
    side(g).get_by_role("button", name="2. 会議の準備").click()
    wait(g, 3000)
    agenda = main(g).get_by_label("議題（1行に1件）")
    agenda.fill("貸出の申請方法")
    agenda.press("Tab")
    wait(g, 900)
    click(g, "反映して会議へ進む →", 3500)
    check(title(g) == "会議", "2 未反映の入力を「反映して会議へ進む」で反映し、会議へ進む")
    for name in ("第1回打ち合わせ", "第2回打ち合わせ"):
        main(g).get_by_label("会議名").fill(name)
        main(g).get_by_role("button", name="会議を追加").click()
        wait(g, 2600)
        check(count(g, "会議の記録を整理 →") == 1 and count(g, "質問・議題に戻る") == 1, f"2 「{name}」の登録直後、ボタンは完了欄の1組だけ")
    main(g).locator("[data-testid=stSelectbox]").filter(has_text="表示する項目").locator("input").click()
    wait(g, 500)
    g.get_by_role("option").filter(has_text="第1回打ち合わせ").first.click()
    wait(g, 2400)
    check(count(g, "会議の記録を整理 →") == 1 and count(g, "質問・議題に戻る") == 1, "2 既存の会議を開き直すと、詳細に1組だけ")
    click(g, "会議の記録を整理 →", 3000)
    mtg = main(g).locator("[data-testid=stSelectbox]").filter(has_text="関連付ける会議").first.locator("input").input_value()
    check(title(g) == "会議の記録を整理" and "第1回打ち合わせ" in mtg, f"2 選んだ会議が記録画面に引き継がれる（{mtg}）")
    main(g).get_by_label("貼り付ける議事録の名称").fill("第1回議事録")
    main(g).get_by_label("議事録の文章を貼り付ける").fill(MINUTES)
    main(g).get_by_label("議事録の文章を貼り付ける").press("Tab")
    wait(g, 900)
    click(g, "貼り付けた文章を議事録として登録", 3000)
    click(g, "選択した議事録をAIで整理する", 1000)
    g.get_by_text("件の候補を作成しました").first.wait_for(timeout=60000)
    wait(g, 2500)
    click(g, "AI候補を確認する →", 3000)

    # ---- 1：判断記録の下書き（判断記録だけ → 要件も作る） ----
    for how, label in (("none", "要件を伴わない判断として記録する"), ("new", "決定の内容から新しい要件の下書きを作る")):
        open_btn = main(g).get_by_role("button", name="判断記録の下書きの内容を確認")
        if open_btn.count() == 0:
            check(False, f"1 {how}：判断記録の下書きの内容を確認（決定の候補が残っていない）")
            break
        before = project_counts(g, OUT / f"before_{how}.json")
        open_btn.first.click()
        wait(g, 2500)
        after_open = project_counts(g, OUT / f"open_{how}.json")
        check((len(after_open["decisions"]), len(after_open["requirements"])) == (len(before["decisions"]), len(before["requirements"])),
              f"1 {how}：確認欄を開いただけでは登録されない")
        main(g).get_by_text(label, exact=True).click()
        wait(g, 1500)
        plan = "判断記録と要件の下書きを作成します。" if how == "new" else "判断記録の下書きだけを作成します（要件は作成しません）。"
        check(plan in main(g).inner_text(), f"1 {how}：確定前に「{plan}」")
        click(g, "判断記録の下書きを作成", 3000)
        done = project_counts(g, OUT / f"done_{how}.json")
        add_dec = len(done["decisions"]) - len(before["decisions"])
        add_req = len(done["requirements"]) - len(before["requirements"])
        msg = main(g).locator("[data-testid=stAlertContentSuccess]").filter(has_text="を作成しました").first.inner_text()
        dec_id = done["decisions"][-1]["id"]
        check(add_dec == 1 and add_req == (1 if how == "new" else 0), f"1 {how}：確定で1回だけ作成（判断記録 +{add_dec}／要件 +{add_req}）")
        check(dec_id in msg and (("要件の下書き" in msg) == (how == "new")), f"1 {how}：完了表示が実際の結果と一致（{msg[:60]}）")
        check(count(g, "決定・合意で下書きを開く") == 1 and (count(g, "要件の下書きを開く") == 1) == (how == "new") and count(g, "採用した要件を確認する →") == 0,
              f"1 {how}：主ボタン「決定・合意で下書きを開く」{'と副導線「要件の下書きを開く」' if how == 'new' else ''}。結果と違う移動ボタンは出さない")
        check(title(g) == "AI候補の確認", f"1 {how}：登録後に自動では移動しない")
        g.screenshot(path=OUT / f"1_判断記録の下書き_{how}.png")
        if how == "new":
            req_id = done["requirements"][-1]["id"]
            click(g, "要件の下書きを開く", 3000)
            check(title(g).endswith("の要件一覧") and req_id in main(g).inner_text(), f"1 new：要件の下書き（{req_id}）が開く")
            side(g).get_by_role("button", name="AI候補の確認").click()
            wait(g, 3000)
        else:
            click(g, "決定・合意で下書きを開く", 3000)
            sel = main(g).locator("[data-testid=stSelectbox]").filter(has_text="表示する項目").first.locator("input").input_value()
            check(title(g) == "決定・合意" and dec_id in sel, f"1 none：決定・合意で作成した判断記録（{dec_id}）を選択済みで開く")
            side(g).get_by_role("button", name="AI候補の確認").click()
            wait(g, 3000)

    # ---- 3：再開用ファイルの通知 ----
    side(g).get_by_role("button", name="1. 案件の準備").click()
    wait(g, 3000)
    data = project_counts(g, OUT / "resume_1.json")
    check(NOTICE not in g.inner_text("body"), "3 出力した直後は通知を出さない")
    side(g).get_by_role("button", name="2. 会議の準備").click()
    wait(g, 2500)
    side(g).get_by_role("button", name="会議", exact=True).click()
    wait(g, 2500)
    main(g).get_by_label("会議名").fill("第3回打ち合わせ")
    main(g).get_by_role("button", name="会議を追加").click()
    wait(g, 2600)
    side_text = side(g).inner_text()
    check(NOTICE.replace("。閉じる", "。\n閉じる") in side_text or NOTICE in side_text.replace("\n", ""), "3 案件を更新すると、ダウンロードボタンの近くに通知")
    data = project_counts(g, OUT / "resume_2.json")
    check(NOTICE not in side(g).inner_text().replace("\n", ""), "3 再出力すると通知が消える")
    c.close()
    c = b.new_context(viewport={"width": 1440, "height": 900})
    g = c.new_page()
    top(g)
    g.locator('input[type="file"]').first.set_input_files(str(OUT / "resume_2.json"))
    wait(g, 2500)
    g.get_by_role("button", name="この案件を再開する").click()
    g.wait_for_selector(".dr-title", timeout=30000)
    wait(g, 2000)
    side(g).get_by_role("button", name="2. 会議の準備").click()
    wait(g, 2500)
    side(g).get_by_role("button", name="会議", exact=True).click()
    wait(g, 2500)
    main(g).locator("[data-testid=stSelectbox]").filter(has_text="表示する項目").locator("input").click()
    wait(g, 500)
    opts = [o.inner_text() for o in g.get_by_role("option").all()]
    check(any("第3回打ち合わせ" in o for o in opts), f"3 読み戻すと更新した内容（第3回打ち合わせ）が戻る（{opts}）")
    c.close()

    # ---- 4：デモ3件の最終画面 ----
    for demo, rid in (("経費申請", "REQ-002"), ("売上集計・クラウド移行", "REQ-004"), ("ネットワーク更新", "REQ-006")):
        c = b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        g = c.new_page()
        g.goto(URL)
        g.wait_for_selector(".dr-hero", timeout=120000)
        wait(g, 1500)
        g.get_by_role("button", name=f"{demo}のデモを見る").click()
        g.wait_for_selector(".dr-loc", timeout=60000)
        wait(g, 2500)
        # 機能画面を開くボタンは「機能画面で〜を見る」。開いて元のステップへ戻る
        main(g).get_by_role("button", name=re.compile("^次へ：")).first.click()
        wait(g, 2600)
        fn = main(g).get_by_role("button", name=re.compile("^機能画面で"))
        check(fn.count() >= 1, f"4 {demo}：ステップ2の機能画面を開くボタンは「機能画面で〜」（{fn.first.inner_text() if fn.count() else 'なし'}）")
        fn.first.click()
        wait(g, 3000)
        main(g).get_by_role("button").filter(has_text="← デモステップ 2/8").first.click()
        wait(g, 3000)
        check("デモステップ 2/8" in g.locator(".dr-loc").first.inner_text(), f"4 {demo}：機能画面から元のステップ2へ戻る")
        for _ in range(6):
            main(g).get_by_role("button", name=re.compile("^次へ：")).first.click()
            wait(g, 2600)
        g.wait_for_selector(".dr-end-h", timeout=30000)
        wait(g, 3000)
        t = main(g).inner_text()
        check(g.locator(".dr-end-h").inner_text() == "この案件の要件定義書と成果物" and "デモ完了" in t, f"4 {demo}：大見出しは成果物、「デモ完了」は補助表示")
        rep = g.locator(".dr-rep")
        rb = rep.bounding_box()
        check(rep.count() == 1 and rid in rep.inner_text() and "元の記録" in rep.inner_text() and "理由" in rep.inner_text() and rb["y"] < 900,
              f"4 {demo}：代表例（{rid}）を追加操作なしで読める（上端 {rb['y']:.0f}px）")
        g.screenshot(path=OUT / f"4_{demo}_最終画面.png")
        with g.expect_download(timeout=30000) as d:
            main(g).get_by_role("button", name="要件定義書をWordでダウンロード").click()
        doc = Document(io.BytesIO(Path(d.value.path()).read_bytes()))
        check(rid in "\n".join(x.text for x in doc.paragraphs) or any(rid in cell.text for tb in doc.tables for row in tb.rows for cell in row.cells),
              f"4 {demo}：Word出力（{d.value.suggested_filename}）に代表例の要件が含まれる")
        click(g, "要件定義書の全文を見る", 1000)
        try:
            main(g).get_by_text("この文書について").first.wait_for(timeout=20000)
        except Exception:
            pass
        check("この文書について" in main(g).inner_text() and g.locator(".dr-end-h").count() == 1, f"4 {demo}：全文のプレビューが最終画面のまま開く")
        click(g, "機能画面でこの案件の現在の状況を見る", 3000)
        main(g).get_by_role("button").filter(has_text="← デモステップ 8/8").first.click()
        wait(g, 3000)
        check(g.locator(".dr-end-h").count() == 1, f"4 {demo}：機能画面から最終画面へ戻る")
        c.close()
    b.close()

print("問題", len(problems))
for x in problems:
    print(" -", x)
