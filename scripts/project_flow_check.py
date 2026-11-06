"""実案件の一連の流れの実ブラウザ確認（初回→AI整理→採用→合意→出力→再開）。

架空の案件を使う。AIの応答は呼び出し側で代替応答にしておくこと（有料APIを使わない）。
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
NAME = "勤怠システムの更新（架空テスト）"
INITIAL = "社員100名の会社で、Excelによる勤怠集計をWebシステムへ更新したい。打刻漏れの確認と月末集計に時間がかかる。Web打刻、上長の修正承認、給与ソフト向けCSV出力を検討している。予算、導入時期、勤務形態は未確認。"
MINUTES = ("勤怠システム更新の初回ヒアリング。利用対象は社員100名。現在はExcelで集計し、月末集計に2日かかる。従業員がWebで打刻し、打刻漏れや修正は上長が承認する案を検討する。"
           "給与ソフトへはCSVで連携したいが項目と形式は未確認。導入時期と予算は未定。次回までに人事担当が現行の勤怠表を用意する。上記の機能はまだ合意していない。")
problems: list[str] = []


def check(ok, message):
    print(("OK  " if ok else "NG  ") + message)
    if not ok:
        problems.append(message)


def wait(g, ms=1600):
    g.wait_for_timeout(ms)


def shot(g, name):
    g.screenshot(path=OUT / f"{SIZE}_{name}.png")


def menu(g):
    """スマートフォン幅ではサイドバーを開く。"""
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
    if SIZE == "sp":
        wait(g, 600)


def body(g):
    return g.inner_text("body")


def sit(g):
    return g.locator(".dr-sit-tag").first.inner_text() if g.locator(".dr-sit-tag").count() else ""


def over(g):
    return g.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")


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

    # 1. 初回
    t = body(g)
    check("の準備を始めましょう" in t and "資料・議事録から始める" in t and "背景・困りごとを入力する" in t, "初回：開始画面と2つの入口")
    check("基準版なし" not in t and "分類別の合計" not in t and "前回からの引き継ぎ" not in t, "初回：0件の指標や基準版なしを出さない")
    shot(g, "01_start")
    g.get_by_role("button", name="背景・困りごとを入力する").click()
    wait(g)
    g.get_by_label("現在、何に困っていますか").fill("打刻漏れの確認と月末集計に時間がかかる")
    g.get_by_label("何を変えたいですか").fill("Excelによる勤怠集計をWebシステムへ更新したい")
    g.get_by_role("button", name="案件内に反映").first.click()
    wait(g, 2200)
    check("の準備を始めましょう" not in body(g) and bool(sit(g)), f"入力後は案件ホームへ移行（案内：{sit(g)}）")
    shot(g, "02_home")

    # 2. 会議準備とAI入力
    nav(g, "会議の準備")
    check("前回からの引き継ぎ" not in body(g), "会議準備：初回は引き継ぎを出さない")
    g.get_by_label("現時点の理解").fill(INITIAL)
    g.get_by_role("button", name="案件内に反映").first.click()
    wait(g, 2200)
    g.get_by_role("tab", name="質問").click()
    wait(g, 800)
    g.get_by_text("AIで候補を作る：会議前の準備").click()
    wait(g)
    t = body(g)
    check("AIが参照する案件の情報" in t and "社員100名" in t, "AI実行前に参照する情報を確認できる")
    shot(g, "03_ai_refs")
    g.get_by_role("button", name="この内容でAIを実行").click()
    g.locator("strong", has_text="AIが作成した準備の候補").wait_for(timeout=30000)
    wait(g, 2200)
    active = g.locator("[role=tab][aria-selected=true]").first.inner_text()
    check("質問" in active, f"AI実行後もタブを維持（{active}）")
    t = body(g)
    check("会議の質問に追加" in t and "議題に追加" in t and "資料の依頼事項に追加" in t and "確認事項に追加" in t, "会議前の候補を同じ画面で確認でき、種類に合うボタンが出る")
    check("新規要望" not in t, "候補に一律の「新規要望」を出さない")
    shot(g, "04_prep_candidates")
    g.get_by_role("button", name="会議の質問に追加").first.click()
    wait(g, 2500)
    g.get_by_role("button", name="議題に追加").first.click()
    wait(g, 2500)

    # 3. 議事録
    nav(g, "記録を取り込む")
    g.get_by_text("資料を追加する").first.click() if g.get_by_label("貼り付ける文章の名称").count() == 0 else None
    wait(g, 700)
    box = g.locator("[data-testid=stSelectbox]").filter(has_text="資料の種類")
    box.locator("input").click()
    g.keyboard.type("議事録")
    g.keyboard.press("Enter")
    wait(g)
    g.get_by_label("貼り付ける文章の名称").fill("初回ヒアリング議事録")
    g.get_by_label("貼り付ける文章の名称").press("Tab")
    wait(g, 800)
    g.get_by_label("文章を貼り付ける").fill(MINUTES)
    g.get_by_label("文章を貼り付ける").press("Control+Enter")
    wait(g, 1500)
    g.get_by_role("button", name="貼り付けた文章を案件内に登録").click()
    wait(g, 2800)
    print("案内", sit(g))

    # 4. AI解析
    nav(g, "要件を整理・判断")
    g.get_by_text("AIで候補を作る：会議後の整理").click()
    wait(g)
    g.get_by_role("button", name="この内容でAIを実行").click()
    g.get_by_text("件を確認する").first.wait_for(timeout=30000)
    wait(g, 2500)
    check("解析が完了" in sit(g), f"解析後の案内：{sit(g)}")
    p_state = body(g)
    check("要件候補として採用" in p_state and "確認・依頼事項に追加" in p_state, "要望と宿題に別のボタンが出る")
    shot(g, "05_candidates")

    # 5. 採用：分割して採用
    g.get_by_role("button", name="要件候補として採用").first.click()
    wait(g, 2200)
    t = body(g)
    check("ルールによる推測" in t and "分割案" in t, "採用時に分類候補と分割案を提示")
    shot(g, "06_adopt")
    g.get_by_role("button", name="この内容で要件に採用").click()
    wait(g, 2800)
    g.get_by_role("button", name="要件候補として採用").first.click()
    wait(g, 2200)
    g.get_by_role("button", name="この内容で要件に採用").click()
    wait(g, 2800)
    g.get_by_role("button", name="確認・依頼事項に追加").first.click()
    wait(g, 2500)
    g.get_by_role("button", name="確認事項に追加").first.click()
    wait(g, 2500)

    nav(g, "要件を整理・判断", "要件")
    t = body(g)
    check("対象範囲：未確定" in t and "合意状態：下書き" in t, "合意状態と対象範囲を区別")
    shot(g, "07_requirements")

    # 6. 判断の登録
    nav(g, "要件を整理・判断", "決定・合意")
    g.get_by_text("判断を追加する").click()
    wait(g)
    g.get_by_label("論点").fill("Web打刻と上長承認の方針")
    g.get_by_label("選択肢（1行に1件）").fill("Web打刻と上長承認を採用する\n現行のExcel運用を続ける")
    g.get_by_label("選択肢（1行に1件）").press("Control+Enter")
    wait(g, 1000)
    g.get_by_role("button", name="追加", exact=True).click()
    wait(g, 2800)
    g.get_by_text("判断者が一覧にない場合はここで登録").click()
    wait(g, 800)
    form_reason = g.get_by_label("採用理由")
    form_reason.fill("打刻漏れの確認を減らすため（テスト用の判断）")
    g.get_by_label("氏名・役割").fill("架空の人事責任者")
    g.get_by_role("button", name="関係者として登録").click()
    wait(g, 2800)
    check(g.get_by_label("採用理由").input_value().startswith("打刻漏れ"), "判断者の登録で入力途中の理由が消えない")
    def pick(label, text):
        box = g.locator("[data-testid=stSelectbox]").filter(has_text=label).first
        box.locator("input").click()
        g.keyboard.type(text)
        wait(g, 300)
        g.keyboard.press("Enter")
        wait(g, 500)
    ms = g.locator("[data-testid=stMultiSelect]").filter(has_text="関連する要件").last
    for rid in ("REQ-001", "REQ-002"):
        ms.locator("input").click()
        g.keyboard.type(rid)
        wait(g, 300)
        g.keyboard.press("Enter")
        wait(g, 400)
    pick("採用案", "Web打刻")
    pick("判断者", "架空の人事責任者")
    g.get_by_label("判断日（YYYY-MM-DD）").fill("2026-11-06")
    pick("状態", "合意済み")
    g.get_by_role("button", name="記録する").click()
    wait(g, 3000)
    t = body(g)
    check("判断を合意済みとして記録しました" in t and "この要件に反映する" in t, "合意記録の直後に要件への反映を案内")
    check("REQ-001" in t and "反映後" in t, "対象・現在の状態・反映後を表示")
    shot(g, "08_reflect")
    boxes = g.get_by_text("この要件に反映する")
    for i in range(boxes.count()):
        boxes.nth(i).click()
        wait(g, 1600)
    g.get_by_role("button", name="選んだ要件を合意済みにする").click()
    wait(g, 2800)

    nav(g, "要件を整理・判断", "要件")
    g.get_by_role("tab", name="編集").click()
    wait(g, 700)
    pick("分野", "ネットワーク")
    active = g.locator("[role=tab][aria-selected=true]").first.inner_text()
    check("編集" in active, f"選択操作でタブを維持（{active}）")
    pick("分野", "業務アプリ")
    label = g.locator("[data-testid=stSelectbox]").filter(has_text="表示する項目").locator("input").input_value() if False else g.locator("[data-testid=stSelectbox]").filter(has_text="表示する項目").inner_text()
    check("下書き" not in label, f"選択欄に古い状態が残らない（{label.strip()[:40]}）")
    check("合意状態：合意済み" in body(g), "保存後のバッジが合意済み")
    shot(g, "09_agreed")

    # 7. 案件情報への反映
    nav(g, "案件ホーム", "背景・目的・関係者")
    t = body(g)
    check("案件情報へ反映できる内容" in t, "案件情報への反映候補を表示")
    shot(g, "10_reflect_profile")
    g.get_by_role("button", name="確認して案件情報へ反映する").first.click()
    wait(g, 2800)

    # 8. 出力
    nav(g, "共有・変更管理")
    g.get_by_text("要件定義書", exact=True).first.click()
    wait(g, 2500)
    t = body(g)
    check("要件定義書の出力前確認" in t and "未合意の要件：1件" in t and "合意済みの要件：2件" in t, "出力前確認の件数が実データと一致")
    check("未採用のAI候補は文書に含まれません" in t, "未処理候補が文書に入らないことを明示")
    shot(g, "11_precheck")
    g.get_by_role("button", name="下書きとしてWordを作成する").click()
    wait(g, 3000)
    check("要件定義書を作成しました" in body(g), "作成完了の表示")
    with g.expect_download() as d:
        g.get_by_role("button", name="要件定義書をダウンロード（Word）").click()
    out = OUT / f"{SIZE}_spec.docx"
    d.value.save_as(out)
    doc = Document(io.BytesIO(out.read_bytes()))
    text = "\n".join(x.text for x in doc.paragraphs) + "\n".join(cell.text for t2 in doc.tables for row in t2.rows for cell in row.cells)
    check("決定（合意済み）" in text and "提案" in text and "給与ソフトへCSVで連携したい" in text, f"Wordで合意と未合意を区別（{d.value.suggested_filename}）")
    check("社員100名の会社" in text, "案件背景が文書へ反映")
    check("架空の人事責任者" in text, "判断者が文書へ反映")
    shot(g, "12_done")
    check(over(g) <= 0, f"はみ出しなし（{over(g)}）")

    # 9. 再開
    menu(g)
    with g.expect_download() as d:
        g.get_by_role("button", name="再開用ファイルをダウンロード").first.click()
    saved = OUT / f"{SIZE}_saved.json"
    d.value.save_as(saved)
    data = json.loads(saved.read_text(encoding="utf-8"))
    reqs = data["requirements"]
    check(len(reqs) == 3 and [r["kind"] for r in reqs] == ["機能", "機能", "連携"] and all(r["domain"] == "app" for r in reqs), f"分割で3件、分類を引き継ぐ（{[r['kind'] for r in reqs]}）")
    check(all(r["evidence"] and r["evidence"][0]["verified"] and r.get("from_candidate") for r in reqs), "引用と元の候補を要件へ引き継ぐ")
    check([r["status"] for r in reqs] == ["合意済み", "合意済み", "下書き"], f"合意はWeb打刻・上長承認のみ、CSVは未合意（{[r['status'] for r in reqs]}）")
    check(data["decisions"][0]["target_versions"] and data["decisions"][0]["state"] == "合意済み", "判断に対象の版が残る")
    check(any(s["name"] == "初回ヒアリング議事録" for s in data["sources"]), "議事録を登録")
    check(any(a["content"].startswith("人事担当") for a in data["actions"]) and any(q.get("category") == "確認事項" for q in data["questions"]), "宿題と確認事項が要件にならず正しい場所へ")
    check(data["profile"]["background"]["value"] and data["profile"]["background"].get("origin"), "案件情報に出所が残る")
    check(not any(d["state"] == "合意済み" for d in data["decisions"] if d.get("from_candidate")), "AIの候補から合意が成立していない")
    c2 = b.new_context(**CTX)
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
    check("再開" in sit(h), f"JSONから再開（{sit(h)}）")
    b.close()

print("問題", len(problems))
for x in problems:
    print(" -", x)
