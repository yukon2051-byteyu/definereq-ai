"""背景・資料の画面の実ブラウザ確認（架空の案件、AIは使わない）。

確認すること：
1. 画面名と最初の操作が初期表示で分かる。左メニューを閉じても、案件の準備・背景・資料の間を移動できる
2. 議事録は「議事録」で登録され、会議の記録として扱われる（貼り付けとファイルの両方）。その他の資料は選んだ種類で登録される
3. 下書きが往復で残り、入力欄にフォーカスを置いたまま保存・移動ボタンを1回押すと、最新の内容が保存されて資料の画面が開く
4. 往復後も資料が残り、案件の準備に「入力済み」「取り込み済み 1件」。関係者・用語はそれぞれの追加で反映される
5. 再開用ファイルを新しいセッションで読み込むと、保存した内容と資料が戻る。旧形式のファイルも読み込める

使い方：python scripts/source_flow_check.py <URL> <保存先> <AIパスワード> [pc|sp]
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
HEIGHT = CTX["viewport"]["height"]
FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "v1_public_export.json"
problems: list[str] = []
doc = Document()
doc.add_paragraph("第2回打ち合わせ議事録（架空）")
doc.add_paragraph("受講者は申込画面から研修を選ぶ。定員を超えたらキャンセル待ちにする。")
doc.save(OUT / "第2回議事録.docx")
(OUT / "申込手順.txt").write_text("1. 申込書をメールで送る\n2. 担当者が定員を確認する\n", encoding="utf-8")


def check(ok, message):
    print(("OK  " if ok else "NG  ") + f"[{SIZE}] " + message)
    if not ok:
        problems.append(message)


def wait(g, ms=1700):
    g.wait_for_timeout(ms)


def body(g):
    return g.inner_text("body")


def title(g):
    return g.locator(".dr-title").first.inner_text()


def button(g, name):
    return g.locator("[data-testid=stMain]").get_by_role("button", name=name, exact=True).first


def click(g, name):
    button(g, name).click()
    wait(g, 2300)


def slow_click(g, name, hold=600):
    """人の操作に近い押し方。押してから離すまでに時間がかかると、押している間の再描画の影響を受ける。"""
    b = button(g, name)
    b.scroll_into_view_if_needed()
    wait(g, 300)
    box = b.bounding_box()
    g.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    g.mouse.down()
    g.wait_for_timeout(hold)
    g.mouse.up()
    wait(g, 3000)


def in_view(locator):
    box = locator.bounding_box()
    return bool(box) and box["y"] >= 0 and box["y"] + min(box["height"], 60) <= HEIGHT, (round(box["y"]) if box else None)


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


def sidebar_closed(g):
    return g.evaluate("(()=>{const s=document.querySelector('[data-testid=stSidebar]');return !s||s.getAttribute('aria-expanded')==='false'||s.getBoundingClientRect().right<=5})()")


def close_sidebar(g):
    if not sidebar_closed(g):
        g.evaluate("document.querySelector('[data-testid=stSidebarCollapseButton] button').click()")
        wait(g, 900)


def paste_tab(g):
    g.get_by_role("tab", name="文章を貼り付けて取り込む").click()
    wait(g, 600)


def choose_kind(g, kind):
    g.get_by_text("その他の資料を取り込む", exact=True).click()
    wait(g, 1500)
    g.locator("[data-testid=stSelectbox]").filter(has_text="資料の種類").locator("input").click()
    wait(g, 500)
    g.get_by_role("option", name=kind, exact=True).click()
    wait(g, 1500)


def kind_label(g):
    return g.locator(".dr-kind").first.inner_text().replace("\n", "")


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)

    # ---- 案件A：背景と資料の往復（条件1・3・4・5） ----
    c = b.new_context(accept_downloads=True, **CTX)
    g = c.new_page()
    create(g, "研修申込の管理（架空・往復の確認）")
    close_sidebar(g)
    check(sidebar_closed(g), "1 左メニューを閉じた状態で確認する")
    click(g, "背景・目的・関係者を入力")
    first = g.get_by_label("背景", exact=True).first
    head_ok, head_y = in_view(g.locator(".dr-title").first)
    input_ok, input_y = in_view(first)
    back_ok, _ = in_view(button(g, "← 案件の準備に戻る"))
    order = g.evaluate("""(()=>{const y=e=>e.getBoundingClientRect().top;const t=document.querySelector('.dr-title'),f=document.querySelector('textarea'),
        bk=[...document.querySelectorAll('[data-testid=stMain] button')].find(x=>x.innerText.includes('案件の準備に戻る'));return y(bk)<y(t)&&y(t)<y(f)})()""")
    g.screenshot(path=OUT / f"{SIZE}_profile_first.png")
    if SIZE == "pc":
        check(title(g) == "背景・目的・関係者" and head_ok and input_ok and back_ok and order, f"1 背景：戻る→見出し→入力欄の順で、最初の入力欄が初期表示に入る（見出し {head_y}px、入力欄 {input_y}px）")
    else:
        check(title(g) == "背景・目的・関係者" and head_ok and back_ok and order, f"1 背景：戻る→見出し→入力欄の順。見出しが初期表示に入る（見出し {head_y}px、最初の入力欄 {input_y}px）")
    check(g.locator(".dr-sit-work").count() == 0 and g.locator(".dr-brief").count() == 1, "1 背景：大きな案内の枠を出さず、見出しの下に短い1行だけ")

    # 3. 背景に入力 → 保存せず資料へ → 資料を登録 → 背景へ戻る
    first.click()
    g.keyboard.type("申込をメールで受け、Excelで定員を管理している")
    click(g, "資料・議事録へ")  # 保存しないで移動
    check(title(g) == "資料・議事録", "1 背景から資料へ本文のボタンで移動")
    mode_ok, mode_y = in_view(g.get_by_text("議事録を取り込む", exact=True).first)
    tab_ok, _ = in_view(g.get_by_role("tab", name="ファイルから取り込む"))
    g.screenshot(path=OUT / f"{SIZE}_sources_first.png")
    if SIZE == "pc":
        check(mode_ok and tab_ok, f"1 資料：取り込むもの（議事録／その他）と取り込み方法が初期表示に入る（{mode_y}px）")
    else:
        check(title(g) == "資料・議事録" and in_view(g.locator(".dr-title").first)[0], f"1 資料：見出しが初期表示に入る（取り込むもの {mode_y}px）")
    check(kind_label(g) == "登録する種類議事録", "2 初期の取り込みは「議事録」で、登録ボタンの近くに種類を表示")
    paste_tab(g)
    g.get_by_label("貼り付ける文章の名称").fill("第1回打ち合わせ議事録")
    g.get_by_label("文章を貼り付ける").fill("講師が出欠を登録する。予算は未確認。")
    g.get_by_label("文章を貼り付ける").press("Tab")
    wait(g, 900)
    click(g, "貼り付けた文章を案件内に登録")
    check("種類：議事録" in body(g), "2 貼り付けた議事録を「議事録」で登録")
    check(g.get_by_label("文章を貼り付ける").input_value() == "", "2 登録後は貼り付け欄を空にする（二重登録を防ぐ）")
    click(g, "背景・目的・関係者を編集")
    box = g.get_by_label("背景", exact=True).first
    check(box.input_value() == "申込をメールで受け、Excelで定員を管理している", "3 資料を登録して戻っても、背景の下書きが残る")
    box.click()
    g.keyboard.press("End")
    g.keyboard.type("。月末に集計している")  # 入力欄にフォーカスを置いたまま押す
    slow_click(g, "保存して資料・議事録を取り込む")
    t = body(g)
    check(title(g) == "資料・議事録" and "案件情報を保存しました" in t, "3 フォーカスを外さずに1回押すと、保存して資料の画面が開き、保存したことを表示")
    check("第1回打ち合わせ議事録" in g.content(), "4 資料の画面に戻っても登録済みの資料が残る")

    # 3. 保存済みの状態から編集して、1回で保存・移動する（以前、1回目のクリックが無効になった条件）
    click(g, "背景・目的・関係者を編集")
    box = g.get_by_label("目的", exact=True).first
    box.click()
    g.keyboard.type("申込の状況を一つの画面で見られるようにする")
    slow_click(g, "保存して資料・議事録を取り込む")
    check(title(g) == "資料・議事録", "3 保存済みの状態から編集しても、1回の操作で保存して移動する")

    # 4. 関係者・用語はそれぞれの追加で反映する
    click(g, "背景・目的・関係者を編集")
    check(g.get_by_label("背景", exact=True).first.input_value().endswith("月末に集計している") and
          g.get_by_label("目的", exact=True).first.input_value() == "申込の状況を一つの画面で見られるようにする", "3 保存した最新の内容が背景の画面に出る")
    g.get_by_label("氏名・役割").first.fill("架空の研修責任者")
    g.get_by_label("氏名・役割").first.press("Tab")
    wait(g, 800)
    check("「関係者を追加」を押すと、入力した1件が案件に反映されます" in body(g), "4 関係者の追加ボタンの近くに反映範囲の説明")
    click(g, "関係者を追加")
    check("関係者「架空の研修責任者」を追加しました" in body(g), "4 関係者の追加結果を、その欄の近くに表示")
    g.get_by_label("用語", exact=True).first.fill("キャンセル待ち")
    g.get_by_label("用語", exact=True).first.press("Tab")
    wait(g, 800)
    click(g, "用語を追加")
    check("用語「キャンセル待ち」を追加しました" in body(g), "4 用語も、それぞれの追加で反映")
    click(g, "← 案件の準備に戻る")
    t = body(g)
    check(title(g) == "案件の準備" and "入力済み" in t and "取り込み済み 1件" in t, "4 案件の準備に「入力済み」「取り込み済み 1件」")
    check(t.count("元のWord・PDFファイルは含まれません") == 1, "4 再開用ファイルの説明は本文の1か所だけ")
    g.screenshot(path=OUT / f"{SIZE}_setup.png", full_page=True)

    # 5. 再開用ファイル
    with g.expect_download() as d:
        g.locator("[data-testid=stMain]").get_by_role("button", name="再開用ファイルをダウンロード").click()
    saved = OUT / f"{SIZE}_resume.json"
    d.value.save_as(saved)
    data = json.loads(saved.read_text(encoding="utf-8"))
    check(data["profile"]["background"]["value"].endswith("月末に集計している") and len(data["sources"]) == 1 and data["sources"][0]["kind"] == "議事録"
          and data["stakeholders"][0]["name"] == "架空の研修責任者" and data["glossary"][0]["term"] == "キャンセル待ち", "5 ファイルに保存した背景・資料（議事録）・関係者・用語が入る")
    c.close()

    # ---- 案件B：資料の種類（条件2） ----
    c = b.new_context(accept_downloads=True, **CTX)
    g = c.new_page()
    create(g, "研修申込の管理（架空・資料の種類）")
    click(g, "資料・議事録を取り込む")
    # 入力中の文章と選んだファイルは、種類を切り替えても残る
    g.locator('input[type="file"]').first.set_input_files(str(OUT / "申込手順.txt"))
    wait(g, 1500)
    paste_tab(g)
    g.get_by_label("文章を貼り付ける").fill("切り替えても残る文章")
    g.get_by_label("文章を貼り付ける").press("Tab")
    wait(g, 800)
    choose_kind(g, "手順")
    check(kind_label(g) == "登録する種類手順", "2 その他の資料では、選んだ種類を登録ボタンの近くに表示")
    keep_text = g.get_by_label("文章を貼り付ける").input_value() == "切り替えても残る文章"
    g.get_by_role("tab", name="ファイルから取り込む").click()
    wait(g, 600)
    keep_file = g.get_by_text("申込手順.txt").count() > 0
    check(keep_text and keep_file, "2 種類と取り込み方法を切り替えても、入力中の文章と選んだファイルが残る")
    click(g, "読み込む")
    check("種類：手順" in body(g), "2 その他の資料（ファイル）を選んだ種類で登録")
    g.get_by_text("議事録を取り込む", exact=True).click()
    wait(g, 1500)
    g.locator('input[type="file"]').first.set_input_files(str(OUT / "第2回議事録.docx"))
    wait(g, 2000)
    click(g, "読み込む")
    check("種類：議事録" in body(g), "2 議事録のファイル（Word）を「議事録」で登録")
    paste_tab(g)
    check(g.get_by_label("文章を貼り付ける").input_value() == "切り替えても残る文章", "2 ファイルを登録しても、貼り付け欄の入力は残る")
    click(g, "貼り付けた文章を案件内に登録")
    check("種類：議事録" in body(g), "2 貼り付けた文章を「議事録」で登録")
    # 既存の判定：会議の記録を整理する画面に、議事録だけが会議の記録として並ぶ
    g.evaluate("window.scrollTo(0,0)")
    if SIZE == "sp":
        g.locator("[data-testid=stExpandSidebarButton], [data-testid=stSidebarCollapsedControl] button").first.click()
        wait(g, 900)
    g.locator("[data-testid=stSidebar]").get_by_role("button", name="会議の記録を整理", exact=True).click()
    wait(g, 2500)
    rec = next((x for x in g.locator("[data-testid=stCaptionContainer]").all_inner_texts() if x.startswith("登録済みの記録")), "")
    check("第2回議事録.docx" in rec and "申込手順.txt" not in rec and "AIで候補を作る：会議後の整理" in body(g), f"2 議事録はAIで整理する会議の記録に入り、手順は入らない（{rec}）")
    check(g.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth") <= 0, "1 横にはみ出さない")
    c.close()

    # ---- 新しいセッションで再開（条件5） ----
    for path, label in ((saved, "改修後のファイル"), (FIXTURE, "旧形式のファイル")):
        g = b.new_context(**CTX).new_page()
        top(g)
        g.locator('input[type="file"]').first.set_input_files(str(path))
        wait(g, 2500)
        g.get_by_role("button", name="この案件を再開する").click()
        g.wait_for_selector(".dr-title", timeout=30000)
        wait(g)
        if label == "改修後のファイル":
            close_sidebar(g)
            click(g, "← 案件の準備に戻る")
            ok = "入力済み" in body(g) and "取り込み済み 1件" in body(g)
            click(g, "背景・目的・関係者を編集")
            ok = ok and g.get_by_label("背景", exact=True).first.input_value().endswith("月末に集計している") and "架空の研修責任者" in g.content()
            click(g, "資料・議事録へ")
            ok = ok and "第1回打ち合わせ議事録" in g.content()
            check(ok, "5 新しいセッションで、保存した背景・関係者と資料が戻り、準備の状態も一致")
        else:
            check(g.locator("[data-testid=stException]").count() == 0 and "再開" in g.locator(".dr-sit-work").first.inner_text(), "5 旧形式のファイルも読み込める")
        g.context.close()
    b.close()

print("問題", len(problems))
for x in problems:
    print(" -", x)
