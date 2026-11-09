"""デモ体験のデスクトップ確認（一覧・冒頭・見どころ・判断・判断後の仕様・終了画面）。AIは使わない。

使い方：python scripts/demo_flow_check.py <URL> <保存先>
左メニューは閉じたまま、本文の操作だけで進める。
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8")
URL, OUT = sys.argv[1], Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
H = 900
problems: list[str] = []
DEMOS = [("d1", "経費申請アプリの刷新", "対立する要望から、判断と変更を追う", "経費申請のデモを見る", "見どころへ：3案の比較と採用理由", "3案を比べて、再申請を採用した"),
         ("d2", "拠点売上集計の自動化とクラウド移行", "曖昧な要望を、測れる要件にする", "売上集計・クラウド移行のデモを見る", "見どころへ：「毎朝すぐ」を測れる条件にする", "「毎朝すぐ」「失いたくない」を測れる条件に分ける"),
         ("d3", "拠点ネットワーク更新と遠隔保守", "録画の発言から、合意の根拠を確認する", "ネットワーク更新のデモを見る", "見どころへ：録画の発言と提案の扱い", "保守会社の発言は「提案」であり、決定ではない")]


def check(ok, message):
    print(("OK  " if ok else "NG  ") + message)
    if not ok:
        problems.append(message)


def wait(g, ms=1800):
    g.wait_for_timeout(ms)


def main(g):
    return g.locator("[data-testid=stMain]")


def btn(g, name):
    return main(g).get_by_role("button", name=name, exact=True).first


def click(g, name, ms=2600):
    btn(g, name).click()
    wait(g, ms)


def title(g):
    return g.locator(".dr-g-h").first.inner_text()


def in_view(loc):
    b = loc.bounding_box()
    return bool(b) and 0 <= b["y"] and b["y"] + min(b["height"], 50) <= H


def close_sidebar(g):
    g.evaluate("(()=>{const b=document.querySelector('[data-testid=stSidebarCollapseButton] button');const s=document.querySelector('[data-testid=stSidebar]');"
               "if(b&&s&&s.getAttribute('aria-expanded')!=='false')b.click()})()")
    wait(g, 900)


def cut_labels(g):
    """本文のボタンで、文字が枠からはみ出して切れているものの名前。"""
    return g.evaluate("""[...document.querySelectorAll('[data-testid=stMain] button')].filter(b=>b.offsetParent).filter(b=>{const p=b.querySelector('p')||b;
        return p.scrollWidth>p.clientWidth+1||b.scrollWidth>b.clientWidth+1}).map(b=>b.innerText)""")


def overflow(g):
    return g.evaluate("[...document.querySelectorAll('.dr-t-wrap')].some(w=>w.scrollWidth>w.clientWidth+1)") or \
        g.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth") > 0


def top(g):
    g.goto(URL)
    g.wait_for_selector(".dr-hero", timeout=120000)
    wait(g)


def start(g, demo):
    top(g)
    click(g, demo[3], 3500)
    close_sidebar(g)


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    g = b.new_context(viewport={"width": 1440, "height": H}, accept_downloads=True).new_page()

    # 1. 一覧
    top(g)
    g.get_by_role("link", name="案内付きでデモを見る").click()
    wait(g, 1200)
    text = g.inner_text("body")
    ys = [round(btn(g, d[3]).bounding_box()["y"]) for d in DEMOS]
    card_ok = all(text.index(d[1]) < text.index(d[2]) for d in DEMOS)
    check(card_ok and len(set(ys)) == 1 and all(in_view(btn(g, d[3])) for d in DEMOS), f"1 一覧：3件の名前→分かること、開始ボタンが初期表示で横一列にそろう（y={ys}）")
    check(all(w in text for w in ("登録・APIキー不要", "架空データの閲覧専用", "AIの結果は用意済みのサンプル")) and not cut_labels(g), "1 一覧：共通の説明があり、ボタンの文字が切れない")
    g.screenshot(path=OUT / "1_list.png")

    # 2. デモ1の冒頭
    start(g, DEMOS[0])
    text = g.inner_text("body")
    boxes = g.locator(".dr-q-box")
    first = boxes.count() == 2 and "現場の要望" in boxes.nth(0).inner_text() and "経理の制約" in boxes.nth(1).inner_text() and in_view(boxes.nth(0)) and         in_view(g.locator(".dr-q-focus")) and "元の記録を残しながら、どう訂正するか？" in g.locator(".dr-q-focus").inner_text()
    check(first and text.index("現場の要望") < text.index("今回の論点") and in_view(btn(g, "次へ：会議前の確認点を見る")) and in_view(btn(g, "見どころへ：3案の比較と採用理由")),
          "2 デモ1の初期表示で、現場の要望・経理の制約・今回の論点と、2つの進み方が見える")
    g.screenshot(path=OUT / "2_d1_first.png")
    click(g, "次へ：会議前の確認点を見る")
    check("ステップ 2/8" in g.inner_text("body") and "規程にない" in title(g), "2 順に進む操作で、ステップ2へ")
    click(g, "前へ：案件の背景")
    click(g, "見どころへ：3案の比較と採用理由")
    t = g.inner_text("body")
    check("ステップ 5/8" in t and "この案件の論点" in t and g.locator(".dr-ph li.on").inner_text().endswith("比較と判断"), "2 見どころへ直接進み、現在地（比較と判断・ステップ5）と論点が出る")

    # 3. 判断の画面
    vd = g.locator(".dr-vd").inner_text()
    order = [vd.index(x) for x in ("1. 採用した案", "2. 採用理由", "3. この判断の根拠")]
    check(order == sorted(order) and "本人確認済みの記録" in vd and "判断に使っていない発言（話者未確認）" in vd and "関係者による判断" in vd, "3 採用案・理由・根拠が順に、種類を分けて表示される")
    check(g.locator(".dr-t-cmp .dr-t-win").inner_text().startswith("再申請") and not overflow(g), "3 3案の比較で採用行が分かり、表がはみ出さない")
    g.screenshot(path=OUT / "3_d1_decision.png", full_page=True)
    click(g, "この判断に使った確認メールを見る", 3000)
    # 本文は表（キャンバス描画）のため、選ばれた記録の名前で確かめる。画面写真でも確認する
    g.screenshot(path=OUT / "3_mail.png")
    picked = g.locator("[data-testid=stSelectbox]").filter(has_text="表示する項目").evaluate("e=>e.textContent+' '+[...e.querySelectorAll('input')].map(i=>i.value+' '+(i.getAttribute('aria-label')||'')).join(' ')")
    check("判断の確認メール" in picked and btn(g, "← 5. 訂正方法の比較に戻る").count() == 1, f"3 確認メールの記録が開き、戻り先が「← 5. 訂正方法の比較に戻る」（{picked.strip()[:40]}）")
    click(g, "← 5. 訂正方法の比較に戻る", 3000)
    check("ステップ 5/8" in g.inner_text("body"), "3 確認メールから、ステップ5へ戻る")
    click(g, "決定・合意の一覧を見る", 3000)
    g.screenshot(path=OUT / "3_decisions.png")
    check(g.locator(".dr-title").first.inner_text() == "決定・合意" and btn(g, "← 5. 訂正方法の比較に戻る").count() == 1, "3 決定・合意の一覧（案件全体の判断記録）が開き、戻り先を表示")
    click(g, "← 5. 訂正方法の比較に戻る", 3000)

    # 4. 判断後の仕様
    click(g, "次へ：追加要望の影響を見る")
    click(g, "次へ：判断後の仕様を見る")
    cs = g.locator(".dr-cs")
    table = g.locator(".dr-t").first
    check(in_view(g.locator(".dr-cs-grid")) and cs.bounding_box()["y"] < table.bounding_box()["y"] and "引き続き守る制約" in cs.inner_text() and "下書きの作成まで" in cs.inner_text(),
          "4 変更前・変更後・守る制約が、比較表より先に初期表示で見える")
    g.screenshot(path=OUT / "4_d1_after.png")
    check(not cut_labels(g) and not overflow(g), "7 判断後の仕様：ボタンの文字が切れず、表がはみ出さない")

    # 6. 終了画面
    click(g, "次へ：体験の終了と資料を見る", 3500)
    t = g.inner_text("body")
    check("デモ体験はここで終了です" in t and "案件に残る未確認の項目" in t and "4件" in g.locator(".dr-end-n").inner_text(), "6 体験の終了と、残る未確認項目4件を別々に表示")
    check(in_view(btn(g, "ほかのデモを見る")) and in_view(btn(g, "この案件の機能画面を詳しく見る")), "6 次の選択肢が、スクロールせずに見える")
    check("再申請方式を採用した理由と、未確認の項目がどう記録されたかを確認できます" in t, "6 要件定義書で見てほしい内容を1文で示す")
    g.screenshot(path=OUT / "6_d1_end.png")
    click(g, "要件定義書の内容を見る", 3000)
    check("要件定義書の内容" in g.inner_text("body") and "この文書について" in g.inner_text("body"), "6 要件定義書のプレビューが開く")
    for label, kind in (("要件定義書をWordでダウンロード", "docx"), ("打ち合わせ確認資料をWordでダウンロード", "docx"), ("要件一覧をExcelでダウンロード", "xlsx")):
        with g.expect_download() as d:
            main(g).get_by_role("button", name=label).first.click()
        path = OUT / f"dl.{kind}"
        d.value.save_as(path)
        check(zipfile.is_zipfile(path) and path.stat().st_size > 5000, f"6 {label}（{path.stat().st_size:,}バイト）")
    check(not cut_labels(g), "7 終了画面：ボタンの文字が切れない")
    click(g, "ほかのデモを見る", 3000)
    check(g.locator("#dr-demo").count() == 1 and "体験済み" in g.inner_text("body"), "6 「ほかのデモを見る」で一覧へ戻る（体験済みの表示）")

    # 5. デモ2・3の近道と通常の順路
    for demo in DEMOS[1:]:
        start(g, demo)
        click(g, demo[4])
        check(title(g) == demo[5] and "この案件の論点" in g.inner_text("body"), f"5 {demo[0]} の見どころ：{demo[5]}")
        g.screenshot(path=OUT / f"5_{demo[0]}_shortcut.png")
        start(g, demo)  # 通常の順路は最初から
        steps = 0
        while btn(g, "ほかのデモを見る").count() == 0 and steps < 10:
            nxt = main(g).get_by_role("button").filter(has_text="次へ：").last
            nxt.click()
            wait(g, 2600)
            steps += 1
            if cut_labels(g) or overflow(g):
                check(False, f"7 {demo[0]} ステップ{steps}で文字切れ・はみ出し {cut_labels(g)}")
        check(btn(g, "ほかのデモを見る").count() == 1 and "デモ体験はここで終了です" in g.inner_text("body"), f"5 {demo[0]} を通常の順路で終了画面まで進める（{steps}回）")
    # デモ1も通常の順路で最後まで
    start(g, DEMOS[0])
    n = 0
    while btn(g, "ほかのデモを見る").count() == 0 and n < 10:
        main(g).get_by_role("button").filter(has_text="次へ：").last.click()
        wait(g, 2600)
        n += 1
    check(btn(g, "ほかのデモを見る").count() == 1, f"5 d1 を通常の順路で終了画面まで進める（{n}回）")
    b.close()

print("問題", len(problems))
for x in problems:
    print(" -", x)
