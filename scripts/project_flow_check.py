"""実案件の一連の流れの実ブラウザ確認（架空の「社内研修の申込・受講管理」）。

初回入力→議事録の取込→AI候補の採用・分割→判断と合意→Word→JSONの再読込までを、実際の画面で操作する。
AIの応答は呼び出し側で代替応答にしておくこと（有料APIを使わない）。
使い方：python scripts/project_flow_check.py <URL> <画像の保存先> <AIパスワード> [pc|sp]
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from docx import Document
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
URL, OUT, CODE = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
SIZE = sys.argv[4] if len(sys.argv) > 4 else "pc"
OUT.mkdir(parents=True, exist_ok=True)
CTX = {"pc": {"viewport": {"width": 1440, "height": 1000}}, "sp": {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}}[SIZE]
NAME = "社内研修の申込・受講管理（架空テスト）"
MINUTES = ("社内研修の申込管理の初回打ち合わせ。利用者は社員200名、研修事務局2名、講師。現在はメールで申し込み、Excelで定員・出欠・受講履歴を管理している。"
           "講師が出欠を登録し、月別CSVを出力する。キャンセル待ちの繰上げは順番に1名ずつ。回答期限は24時間だが、起算点と休日扱いは未確認。"
           "本人によるキャンセルは開始前日17時までとする。認証方式、保存期間、性能条件、予算、開始日は未確認。")
problems: list[str] = []


def check(ok, message):
    print(("OK  " if ok else "NG  ") + message)
    if not ok:
        problems.append(message)


def wait(g, ms=1700):
    g.wait_for_timeout(ms)


def shot(g, name):
    g.screenshot(path=OUT / f"{SIZE}_{name}.png")


def menu(g):
    if SIZE == "sp":
        opener = g.locator("[data-testid=stExpandSidebarButton]")
        if opener.count():
            opener.first.click()
            wait(g, 700)


def nav(g, group, item=None):
    menu(g)
    g.get_by_role("button", name=group, exact=True).first.click()
    wait(g)
    if item:
        menu(g)
        g.get_by_role("button", name=item, exact=True).first.click()
        wait(g)
    wait(g, 500)


def body(g):
    return g.inner_text("body")


def sit(g):
    return g.locator(".dr-sit-work").first.inner_text() if g.locator(".dr-sit-work").count() else ""


def pick(g, label, text):
    box = g.locator("[data-testid=stSelectbox]").filter(has_text=label).first
    box.locator("input").click()
    g.keyboard.type(text)
    wait(g, 300)
    g.keyboard.press("Enter")
    wait(g, 500)


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    c = b.new_context(accept_downloads=True, **CTX)
    g = c.new_page()
    g.goto(URL)
    g.wait_for_selector(".dr-hero", timeout=120000)
    wait(g)
    g.get_by_label("AIパスワード").fill(CODE)
    g.get_by_label("AIパスワード").press("Enter")
    wait(g)
    g.get_by_label("案件名").fill(NAME)
    g.get_by_label("案件名").press("Tab")
    wait(g)
    g.get_by_role("button", name="案件を作成").click()
    g.wait_for_selector(".dr-title", timeout=30000)
    wait(g)

    # 1. 背景・目的・関係者
    g.get_by_role("button", name="背景・目的・関係者を入力").click()
    wait(g)
    g.get_by_label("課題").fill("メールで申し込み、Excelで定員と出欠を管理している")
    g.get_by_label("課題").press("Tab")
    wait(g, 800)
    g.get_by_role("button", name="案件情報を保存", exact=True).click()
    wait(g, 2300)
    check("案件情報を保存しました" in body(g), "1 保存成功を画面に表示")
    t = body(g)
    check("空欄のまま進められます" in t and "案件の準備に戻る" in t, "1 保存単位の説明と、戻る操作")
    g.get_by_label("氏名・役割").first.fill("架空の研修責任者")
    g.get_by_label("氏名・役割").first.press("Tab")
    wait(g, 800)
    g.get_by_role("button", name="関係者を追加").click()
    wait(g, 2500)
    shot(g, "01_profile")

    # 2. フォームの末尾から進む（未反映の入力も保存される）
    g.get_by_label("目的", exact=True).fill("申込から受講履歴までを一つのアプリで管理する")
    g.get_by_label("目的", exact=True).press("Tab")
    wait(g, 800)
    g.get_by_role("button", name="保存して資料・議事録を取り込む").click()
    wait(g, 2800)
    check("資料・議事録" in g.locator(".dr-title").first.inner_text(), "2 保存して資料・議事録へ進める")
    nav(g, "記録を取り込む")

    # 3. 説明を閉じても次の操作が残る
    g.get_by_role("button", name="詳しい説明を閉じる").click()
    wait(g, 1800)
    t = body(g)
    check("この操作をおすすめする理由" not in t and "詳しい説明を表示" in t and "現在の状況と次にすること" in t, f"3 説明を閉じても現在地が残る（{sit(g)[:44]}）")
    check(g.get_by_role("button", name="会議を準備する").count() > 0, "3 次の操作が残る")
    nav(g, "案件ホーム")
    check(g.get_by_role("button", name="会議を準備する").count() > 0 and "詳しい説明を表示" in body(g), "3 別の画面でも次の操作が残る")
    g.get_by_role("button", name="詳しい説明を表示").click()
    wait(g, 1800)
    shot(g, "02_panel")

    # 4. 議事録
    nav(g, "記録を取り込む")
    g.get_by_label("貼り付ける議事録の名称").fill("初回打ち合わせ議事録")
    g.get_by_label("貼り付ける議事録の名称").press("Tab")
    wait(g, 800)
    g.get_by_label("議事録の文章を貼り付ける").fill(MINUTES)
    g.get_by_label("議事録の文章を貼り付ける").press("Control+Enter")
    wait(g)
    g.get_by_role("button", name="貼り付けた文章を議事録として登録").click()
    wait(g, 3000)
    check("議事録を登録しました" in sit(g) and "AIで候補を作る：会議後の整理" in body(g), f"4 同じ画面でAIの整理へ進める（{sit(g)[:36]}）")
    check(g.get_by_role("button", name="次回の質問を準備する").count() == 1, "4 次回の準備は副操作")
    shot(g, "03_minutes")
    g.get_by_role("button", name="この内容でAIを実行").click()
    g.get_by_text("件の候補を作成しました").first.wait_for(timeout=60000)
    wait(g, 2500)
    check(g.get_by_role("button", name="要件候補として採用").count() > 0, f"4 候補の確認へ進む（{sit(g)[:36]}）")
    shot(g, "04_candidates")

    # 5. 分割
    g.get_by_role("button", name="要件候補として採用").first.click()
    wait(g, 2300)
    check("要件1の本文" in body(g) and "要件2の本文" in body(g), "5 分割案を1件ずつ確認できる")
    shot(g, "05_split")
    g.get_by_role("button", name="この内容で要件に採用").click()
    wait(g, 3000)

    # 6. 担当の修正
    own = g.get_by_label("担当（未設定可）").first
    check(own.input_value() == "研修事務局", f"6 担当に説明文が入らない（{own.input_value()}）")
    own.fill("架空の事務局員")
    own.press("Tab")
    wait(g, 1500)
    g.get_by_role("button", name="確認・依頼事項に追加").first.click()
    wait(g, 2800)
    while g.get_by_role("button", name="確認事項に追加").count():
        g.get_by_role("button", name="確認事項に追加").first.click()
        wait(g, 2500)

    # 7. 決定の候補
    g.get_by_role("button", name="判断記録の下書きに追加").first.click()
    wait(g, 2300)
    check("既存の要件に関連付ける" in body(g) and "要件を伴わない判断として記録する" in body(g), "7 決定候補の扱いを選べる")
    g.get_by_text("決定の内容から新しい要件の下書きを作る").click()
    wait(g, 800)
    g.get_by_role("button", name="判断記録の下書きに追加").last.click()
    wait(g, 3000)
    shot(g, "06_decision_draft")

    # 8. 判断と合意
    nav(g, "要件を整理・判断", "決定・合意")
    pick(g, "採用案", "本人")
    g.get_by_label("採用理由").fill("開始前日までなら代替の受講者を調整できるため（テスト用の判断）")
    pick(g, "判断者", "架空の研修責任者")
    g.get_by_label("判断日（YYYY-MM-DD）").fill("2026-11-06")
    pick(g, "状態", "合意済み")
    g.get_by_role("button", name="記録する").click()
    wait(g, 3000)
    t = body(g)
    check("判断を合意済みとして記録しました" in t and "この要件に反映する" in t, "8 合意の直後に反映の確認欄")
    shot(g, "07_reflect")
    g.get_by_text("この要件に反映する").first.click()
    wait(g, 1800)
    g.get_by_role("button", name="選んだ要件を合意済みにする").click()
    wait(g, 3000)

    # 9. Word
    nav(g, "共有・変更管理")
    g.get_by_text("要件定義書", exact=True).first.click()
    wait(g, 2500)
    t = body(g)
    check("未決事項" in t and "登録" in t and "掲載" in t and "除外" in t, "9 登録・掲載・除外の件数を表示")
    shot(g, "08_precheck")
    g.get_by_role("button", name="下書きとしてWordを作成する").click()
    wait(g, 3000)
    with g.expect_download() as d:
        g.get_by_role("button", name="要件定義書をダウンロード（Word）").click()
    out = OUT / f"{SIZE}_spec.docx"
    d.value.save_as(out)
    doc = Document(io.BytesIO(out.read_bytes()))
    text = "\n".join(x.text for x in doc.paragraphs) + "\n" + "\n".join(cell.text for t2 in doc.tables for row in t2.rows for cell in row.cells)
    for w in ("起算点", "認証方式", "権限範囲", "CSV項目は未確認"):
        check(w in text, f"9 Wordに未決事項：{w}")
    check("合意済み" in text and "下書き" in text and "開始前日までなら代替の受講者" in text, "9 Wordに合意状態と判断理由")
    check("架空の事務局員" in text, "6 修正した担当がWordまで保持")

    # 10. JSON
    menu(g)
    with g.expect_download() as d:
        g.get_by_role("button", name="再開用ファイルをダウンロード").first.click()
    saved = OUT / f"{SIZE}_saved.json"
    d.value.save_as(saved)
    data = json.loads(saved.read_text(encoding="utf-8"))
    reqs = data["requirements"]
    print("要件", [(r["id"], r["title"][:18], r["kind"], r["status"], r.get("open_items")) for r in reqs])
    check([r["kind"] for r in reqs[:2]] == ["機能", "連携"], "5 分割後の分類が別々（出欠登録は機能、CSVは連携）")
    check(reqs[0].get("open_items") is None and reqs[1].get("open_items") == "CSV項目は未確認", "5 未確認事項は該当する要件にだけ付く")
    check(all(r["evidence"] and r["evidence"][0]["verified"] and r.get("from_candidate") for r in reqs), "5 引用と元の候補を保持")
    check(data["actions"][0]["owner"] == "架空の事務局員", "6 修正した担当を保存")
    check(sum(1 for r in reqs if r["status"] == "合意済み") == 1 and data["decisions"][0]["state"] == "合意済み", "8 人の操作で1件だけ合意")
    check(bool(reqs[-1].get("from_candidate")) and data["decisions"][0]["related_requirements"] == [reqs[-1]["id"]], "7 決定候補から要件を作り関連付け")
    c2 = b.new_context(accept_downloads=True, **CTX)
    h = c2.new_page()
    h.goto(URL)
    h.wait_for_selector(".dr-hero", timeout=60000)
    wait(h)
    h.get_by_label("AIパスワード").fill(CODE)
    h.get_by_label("AIパスワード").press("Enter")
    wait(h)
    h.locator('input[type="file"]').first.set_input_files(str(saved))
    wait(h, 2500)
    h.get_by_role("button", name="この案件を再開する").click()
    h.wait_for_selector(".dr-sit", timeout=30000)
    wait(h)
    menu(h)
    with h.expect_download() as d:
        h.get_by_role("button", name="再開用ファイルをダウンロード").first.click()
    again = OUT / f"{SIZE}_again.json"
    d.value.save_as(again)
    data2 = json.loads(again.read_text(encoding="utf-8"))
    same = all(data[k] == data2[k] for k in ("requirements", "decisions", "questions", "actions", "history", "profile"))
    check(same, "10 JSONの再読込で内容と状態を保持")
    b.close()

print("問題", len(problems))
for x in problems:
    print(" -", x)
