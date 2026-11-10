"""公開版レビュー5点の実ブラウザ確認（デスクトップ 1440×900、架空データ。AIは代替応答のサーバー）。

  1. 会議記録の候補から判断記録と要件の下書きを作り、登録結果（登録済み）と反映先の現在の状態が分かれて表示される
  2. 「質問・議題」の初期画面に「AIで質問・議題を提案する」。押すと入力途中の議題を保ったまま実行確認欄が開き、AIは実行しない
  3. 「案件内に反映」の直後、「会議へ進む」は1つ。別のタブを開いていても見える
  4. ネットワーク更新のステップ3で、元の発言・AIの候補・却下が続けて読め、候補確認の機能画面から元のステップへ戻れる
  5. デモの候補確認は閲覧専用の説明

使い方：python scripts/review5_check.py <URL> <保存先> <AIパスワード>
"""
from __future__ import annotations

import re
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


def title(g):
    return g.locator(".dr-title").first.inner_text()


def click(g, name, ms=2600):
    main(g).get_by_role("button", name=name, exact=True).first.click()
    wait(g, ms)


def visible_count(g, name):
    return sum(1 for x in main(g).get_by_role("button", name=name, exact=True).all() if x.is_visible())


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    g = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
    g.goto(URL)
    g.wait_for_selector(".dr-hero", timeout=120000)
    wait(g)
    g.get_by_label("AIパスワード").fill(CODE)
    g.get_by_label("AIパスワード").press("Enter")
    wait(g, 2200)
    g.get_by_label("案件名").fill("備品貸出（架空・レビュー確認）")
    g.get_by_label("案件名").press("Tab")
    wait(g)
    g.get_by_role("button", name="案件を作成").click()
    g.wait_for_selector(".dr-title", timeout=30000)
    wait(g, 2300)

    # ---- 2・3 ----
    side(g).get_by_role("button", name="2. 会議の準備").click()
    wait(g, 3000)
    entry = main(g).get_by_role("button", name="AIで質問・議題を提案する")
    check(entry.count() == 1 and entry.is_visible() and g.get_by_role("tab", selected=True).inner_text() == "理解と議題", "2 初期画面（理解と議題）に「AIで質問・議題を提案する」")
    agenda = main(g).get_by_label("議題（1行に1件）")
    agenda.fill("貸出の申請方法")
    agenda.press("Tab")
    wait(g, 900)
    entry.click()
    wait(g, 3500)
    run_btn = main(g).get_by_role("button", name="この内容でAIを実行")
    box = g.locator(".st-key-prep_ai_box").bounding_box()
    check(g.get_by_role("tab", selected=True).inner_text() == "質問" and run_btn.count() == 1 and run_btn.is_visible() and "送信先" in main(g).inner_text() and box and box["y"] < 900,
          "2 押すと「質問」タブの実行確認欄（送信対象・送信先・費用見込み）が開き、その位置へ移動する")
    check("件の候補を作成しました" not in main(g).inner_text(), "2 確認欄を開いただけではAIを実行しない")
    g.get_by_role("tab", name="理解と議題").click()
    wait(g, 2000)
    check(main(g).get_by_label("議題（1行に1件）").input_value() == "貸出の申請方法" and "反映していない入力があります" in main(g).inner_text(),
          "2 タブを移っても入力途中の議題が残り、未反映のまま（保存・送信していない）")
    g.screenshot(path=OUT / "2_質問議題の冒頭.png")
    click(g, "案件内に反映", 3000)
    check(visible_count(g, "会議へ進む →") == 1, f"3 反映の直後、「会議へ進む」は1つ（{visible_count(g, '会議へ進む →')}）")
    g.get_by_role("tab", name="質問").click()
    wait(g, 2000)
    check(visible_count(g, "会議へ進む →") == 1, "3 別のタブ（質問）を開いても「会議へ進む」が見える")
    g.get_by_role("tab", name="理解と議題").click()
    wait(g, 1500)
    click(g, "会議へ進む →", 3000)
    main(g).get_by_label("会議名").fill("第1回打ち合わせ")
    main(g).get_by_role("button", name="会議を追加").click()
    wait(g, 2600)
    click(g, "会議の記録を整理 →", 3000)
    mtg = main(g).locator("[data-testid=stSelectbox]").filter(has_text="関連付ける会議").first.locator("input").input_value()
    check(title(g) == "会議の記録を整理" and "第1回打ち合わせ" in mtg, f"3 会議を登録し、その会議を選択済みで記録の整理へ（{mtg}）")

    # ---- 1 ----
    main(g).get_by_label("貼り付ける議事録の名称").fill("第1回議事録")
    # 実際のAIでも「決定」と分類されるよう、決定したことが文から分かる書き方にする（「〜とする」だけでは決定と読まれないことがある）
    main(g).get_by_label("議事録の文章を貼り付ける").fill("第1回打ち合わせでは、第1期の範囲を照合と履歴の閲覧のみとすることを決定した（決定者：山田部長）。保存期間は未定で、次回確認する。")
    main(g).get_by_label("議事録の文章を貼り付ける").press("Tab")
    wait(g, 900)
    click(g, "貼り付けた文章を議事録として登録", 3000)
    click(g, "選択した議事録をAIで整理する", 1000)
    g.get_by_text("件の候補を作成しました").first.wait_for(timeout=60000)
    wait(g, 2500)
    click(g, "会議記録の候補確認へ進む →", 3000)
    check("必要なものを要件の下書きや確認事項などに登録できます" in main(g).inner_text(), "5 自分の案件の候補確認は、登録できる説明")
    if main(g).get_by_role("button", name="判断記録の下書きの内容を確認").count() == 0:  # AIの結果に決定の候補がないときは、区分を記録して止める
        kinds = [x.inner_text().split(chr(10))[-1] for x in main(g).locator("[data-testid=stExpander] summary").all()]
        g.screenshot(path=OUT / "1_決定の候補なし.png", full_page=True)
        check(False, f"1 AIの結果に決定の候補がない（出た区分：{'、'.join(kinds)}）")
        print("問題", len(problems))
        sys.exit(1)
    main(g).get_by_role("button", name="判断記録の下書きの内容を確認").first.click()
    wait(g, 2500)
    main(g).get_by_text("決定の内容から新しい要件の下書きを作る", exact=True).click()
    wait(g, 1500)
    click(g, "判断記録の下書きを作成", 3500)
    t = main(g).inner_text()
    m = re.search(r"判断記録の下書き (DEC-\d+) と要件の下書き (REQ-\d+) を作成しました", t)
    check(bool(m) and "人が確定した内容です" not in t, f"1 両方の下書きを作成した表示（{m.group(0) if m else 'なし'}）")
    if m:
        check(f"反映先の現在の状態：{m.group(1)} 下書き／{m.group(2)} 下書き" in t, "1 反映先の現在の状態（下書き）を反映先の記録から表示")
    g.screenshot(path=OUT / "1_判断記録と要件の下書き.png")
    click(g, "決定・合意で下書きを開く", 3000)
    sel = main(g).locator("[data-testid=stSelectbox]").filter(has_text="表示する項目").first.locator("input").input_value()
    check(title(g) == "決定・合意" and m and m.group(1) in sel and "合意は判断者・判断日・採用案を人が記録して成立します" in main(g).inner_text(),
          "1 判断記録を開くと、正式な合意は別の操作（判断者・判断日・採用案の記録）と分かる")
    g.context.close()

    # ---- 4・5 ----
    g = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
    g.goto(URL)
    g.wait_for_selector(".dr-hero", timeout=120000)
    wait(g, 1500)
    g.get_by_role("button", name="ネットワーク更新のデモを見る").click()
    g.wait_for_selector(".dr-loc", timeout=60000)
    wait(g, 2500)
    for _ in range(2):
        main(g).get_by_role("button", name=re.compile("^次へ：")).first.click()
        wait(g, 2800)
    chain = g.locator(".dr-chain").first.inner_text()
    check("デモステップ 3/8" in g.locator(".dr-loc").first.inner_text() and "外部からの遠隔保守を提案します" in chain and "遠隔保守を採用する" in chain and "却下" in chain,
          "4 ステップ3で、元の発言 → AIの候補「遠隔保守を採用する」→ 人の判断：却下 を続けて読める")
    g.screenshot(path=OUT / "4_ネットワーク_ステップ3.png")
    click(g, "機能画面で会議記録の候補を見る", 3500)
    t = main(g).inner_text()
    check(title(g) == "会議記録の候補確認" and "このデモでは、議事録や録画からAIが拾った候補と、人が確認した結果を閲覧できます。" in t and "登録できます" not in t,
          "5 デモの候補確認は閲覧専用の説明")
    card = t[t.index("遠隔保守を採用する"):]
    check(card.index("却下（人の判断）") < 40 and "記録された説明：岡田の発言。提案であり、決定ではない。" in card, "4 候補名のすぐ横に「却下（人の判断）」、記録された説明を表示")
    g.screenshot(path=OUT / "4_ネットワーク_候補確認.png", full_page=True)
    main(g).get_by_role("button").filter(has_text="← デモステップ 3/8").first.click()
    wait(g, 3000)
    check("デモステップ 3/8" in g.locator(".dr-loc").first.inner_text(), "4 元のステップ3へ戻る")
    b.close()

print("問題", len(problems))
for x in problems:
    print(" -", x)
