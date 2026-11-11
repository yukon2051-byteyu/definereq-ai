"""正式な合意からWord出力・案件の復元・Word再出力までの実ブラウザ確認（デスクトップ 1440×900、架空の案件）。

架空の「社内貸出端末の返却管理」案件で、会議前の質問づくり → 会議の登録 → 議事録の整理 → 候補の登録 → 正式な合意
→ 要件定義書（Word）→ 再開用ファイルの読み戻し → Wordの再出力 までを画面から操作し、
要件・判断記録・根拠の対応が、画面・Word・復元後で保たれることを照合する。AIは代替応答のサーバーで動かす。

使い方：python scripts/agreement_e2e_check.py <URL> <保存先> <AIパスワード>
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
MINUTES = ("総務と利用部門は、貸出時に返却予定日を必須入力とすることで合意した。\n"
           "利用部門から、延長申請機能を追加してほしいとの要望があった。\n"
           "故障時の夜間連絡先は、次回会議で確認する。")
DECIDER = "佐藤（総務部長）"


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


def choose(g, label, option, scope=None):
    """選択欄（ラベルで探す）で、文字を含む選択肢を選ぶ。"""
    cb = (scope or main(g)).get_by_role("combobox", name=label, exact=True).first  # 選択欄の名前は完全一致で探す
    cb.scroll_into_view_if_needed()
    cb.click()
    cb.fill(option)  # 文字を入れて選択肢を絞り込む（画面の下端でも一覧が開くように）
    wait(g, 700)
    opt = g.get_by_role("option").filter(has_text=option)
    if opt.count() == 0:  # 選択肢が見つからないときは、画面と選択肢を記録して止める
        g.screenshot(path=OUT / f"選択肢なし_{label}.png")
        raise SystemExit(f"選択欄「{label}」に「{option}」がありません。選択肢：{[o.inner_text() for o in g.get_by_role('option').all()]}")
    opt.first.click()
    wait(g, 900)


def doc_text(data: bytes) -> str:
    d = Document(io.BytesIO(data))
    parts = [x.text for x in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts.append(" | ".join(c.text for c in row.cells))
    return "\n".join(parts)


def download(g, button, path):
    with g.expect_download(timeout=60000) as d:
        button.click()
    d.value.save_as(path)
    wait(g, 1200)
    return Path(path).read_bytes()


def save_json(g, path):
    return json.loads(download(g, side(g).get_by_role("button", name="再開用ファイルをダウンロード", exact=True), path).decode("utf-8"))


def word(g, path, drafts=True):
    """確認資料・要件定義書の画面で、要件定義書をWordで作ってダウンロードし、本文を返す。"""
    main(g).get_by_role("radio", name="要件定義書").first.check(force=True)  # 資料の種類
    wait(g, 1500)
    tog = main(g).get_by_role("switch", name="下書きの要件を含める")
    if tog.is_checked() != drafts:
        main(g).get_by_text("下書きの要件を含める").click()
        wait(g, 1500)
    main(g).get_by_role("button").filter(has_text=re.compile("（Word）|下書きとしてWordを作成する")).first.click()
    wait(g, 3500)
    return doc_text(download(g, main(g).get_by_role("button").filter(has_text="Wordでダウンロード").first if main(g).get_by_role("button").filter(has_text="Wordでダウンロード").count()
                             else main(g).locator("[data-testid=stDownloadButton] button").first, path))


def snap(data: dict) -> dict:
    """照合する項目：要件（ID・本文・合意状態・根拠）、判断記録（判断者・判断日・採用案・対象の要件・根拠）、確認事項、資料。"""
    src = {s["id"]: s["name"] for s in data["sources"]}
    ev = lambda x: tuple((src.get(e.get("source_id")), e.get("quote"), e.get("unit_id")) for e in x.get("evidence", []))
    out = {r["id"]: ("要件", r["body"], r["status"], ev(r)) for r in data["requirements"]}
    out.update({d["id"]: ("判断", d["topic"], d["state"], d.get("decider"), d.get("decided_on"), d.get("adopted"), tuple(d.get("related_requirements", [])), ev(d))
                for d in data["decisions"]})
    out.update({q["id"]: ("確認", q["text"], q["status"], q.get("category")) for q in data["questions"]})
    out["資料"] = tuple((s["id"], s["name"], s.get("meeting_id")) for s in data["sources"])
    return out


def norm(text: str) -> str:
    """生成日時・版番号・資料IDなど、出力ごとに変わる値を除く。"""
    return re.sub(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?|第\d+版|DOC-\d+|v\d+版", "", text)


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)
    c = b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    g = c.new_page()
    g.goto(URL)
    g.wait_for_selector(".dr-hero", timeout=120000)
    wait(g)
    g.get_by_label("AIパスワード").fill(CODE)
    g.get_by_label("AIパスワード").press("Enter")
    wait(g, 2200)
    g.get_by_label("案件名").fill("社内貸出端末の返却管理（架空）")
    g.get_by_label("案件名").press("Tab")
    wait(g)
    g.get_by_role("button", name="案件を作成").click()
    g.wait_for_selector(".dr-title", timeout=30000)
    wait(g, 2300)

    # ---- 会議前の質問づくり ----
    side(g).get_by_role("button", name="2. 会議の準備", exact=True).click()
    wait(g, 3000)
    agenda = main(g).get_by_label("議題（1行に1件）")
    agenda.fill("貸出時の入力項目")
    agenda.press("Tab")
    wait(g, 900)
    click(g, "AIで質問・議題を提案する", 3500)
    check(main(g).get_by_role("button", name="この内容でAIを実行").is_visible() and "送信先" in main(g).inner_text(), "会議前：初期画面の入口から実行確認欄（送信先・費用見込み）が開く")
    click(g, "この内容でAIを実行", 1000)
    g.get_by_text("件の候補を作成しました").first.wait_for(timeout=60000)
    wait(g, 2500)
    t = main(g).inner_text()
    check("会議前の質問・議題の候補" in t and "返却が遅れたときの連絡手順" in t and "確認観点の設定から作成。AIは使っていません" in t,
          "会議前：AIの結果は「会議前の質問・議題の候補」、設定から作る質問は出所の説明付き")
    g.get_by_role("tab", name="理解と議題").click()
    wait(g, 1500)
    check(main(g).get_by_label("議題（1行に1件）").input_value() == "貸出時の入力項目", "会議前：AIの実行中もタブを移っても入力途中の議題を保持")
    click(g, "案件内に反映", 3000)
    check(visible_count(g, "会議へ進む →") == 1, "会議前：反映の直後、「会議へ進む」は1つ")
    click(g, "会議へ進む →", 3000)
    main(g).get_by_label("会議名").fill("第1回打ち合わせ")
    main(g).get_by_label("開催日（不明なら空欄）").fill("2026-11-10")
    main(g).get_by_role("button", name="会議を追加").click()
    wait(g, 2600)
    check(visible_count(g, "会議の記録を整理 →") == 1, "会議：登録直後の「会議の記録を整理」は1つ")
    click(g, "会議の記録を整理 →", 3000)
    mtg = main(g).locator("[data-testid=stSelectbox]").filter(has_text="関連付ける会議").first.locator("input").input_value()
    check("第1回打ち合わせ" in mtg, f"会議：記録の整理で登録した会議を選択済み（{mtg}）")

    # ---- 議事録の整理と候補の登録 ----
    main(g).get_by_label("貼り付ける議事録の名称").fill("第1回打ち合わせ議事録")
    main(g).get_by_label("議事録の文章を貼り付ける").fill(MINUTES)
    main(g).get_by_label("議事録の文章を貼り付ける").press("Tab")
    wait(g, 900)
    click(g, "貼り付けた文章を議事録として登録", 3000)
    click(g, "選択した議事録をAIで整理する", 1000)
    g.get_by_text("件の候補を作成しました").first.wait_for(timeout=60000)
    wait(g, 2500)
    check("AIが会議記録から確認候補を3件抽出しました。" in main(g).inner_text(), "整理：AIが会議記録から確認候補を3件抽出")
    click(g, "会議記録の候補確認へ進む →", 3000)
    click(g, "判断記録の下書きの内容を確認", 2500)
    main(g).get_by_text("決定の内容から新しい要件の下書きを作る", exact=True).click()
    wait(g, 1500)
    check("判断記録と要件の下書きを作成します。" in main(g).inner_text(), "候補：確定前に「判断記録と要件の下書きを作成します。」")
    click(g, "判断記録の下書きを作成", 3500)
    t = main(g).inner_text()
    m = re.search(r"判断記録の下書き (DEC-\d+) と要件の下書き (REQ-\d+) を作成しました", t)
    check(bool(m) and "人が確定した内容です" not in t, f"候補：両方の下書きのIDを表示（{m.group(0) if m else 'なし'}）")
    DEC, REQ_A = (m.group(1), m.group(2)) if m else ("DEC-001", "REQ-001")
    check(f"反映先の現在の状態：{DEC} 下書き／{REQ_A} 下書き" in t, "候補：反映先の現在の状態は下書き（正式確定前）")
    check(visible_count(g, "決定・合意で下書きを開く") == 1 and visible_count(g, "要件の下書きを開く") == 1 and visible_count(g, "次の未確認候補へ") == 1,
          "候補：「決定・合意で下書きを開く」「要件の下書きを開く」「次の未確認候補へ」")
    click(g, "要件の下書きを開く", 3000)
    check(title(g).endswith("の要件一覧") and REQ_A in main(g).inner_text() and "合意状態：下書き" in main(g).inner_text(), f"候補：要件の下書き（{REQ_A}）を開ける・合意状態は下書き")
    side(g).get_by_role("button", name="会議記録の候補確認", exact=True).click()
    wait(g, 3000)
    click(g, "要件に採用する内容を確認", 2500)
    click(g, "この内容で採用", 3500)
    t = main(g).inner_text()
    m2 = re.search(r"要件の下書きに登録済み（(REQ-\d+)）", t)
    REQ_B = m2.group(1) if m2 else "REQ-002"
    check(bool(m2), f"候補：要望は「要件の下書きに登録済み（{REQ_B}）」")
    click(g, "次の未確認候補へ", 2500)
    click(g, "確認事項に追加", 3000)
    m3 = re.search(r"確認事項に追加済み（(QST-\d+)）", main(g).inner_text())
    QST = m3.group(1) if m3 else "QST-?"
    check(bool(m3), f"候補：未決は「確認事項に追加済み（{QST}）」")
    g.screenshot(path=OUT / "1_候補の登録結果.png", full_page=True)
    before = save_json(g, OUT / "a_下書き直後.json")
    s0 = snap(before)
    check(s0[DEC][2] == "下書き" and s0[REQ_A][2] == "下書き" and s0[REQ_B][2] == "下書き" and s0[QST][2] == "未質問", "下書き直後：判断記録・要件とも正式確定前（下書き）")
    ev_a = s0[REQ_A][3]
    check(ev_a and ev_a[0][0] == "第1回打ち合わせ議事録" and ev_a[0][1].startswith("総務と利用部門は"), f"下書き直後：{REQ_A} の根拠は議事録の該当箇所（{ev_a[:1]}）")
    check(s0[REQ_B][3] and s0[REQ_B][3][0][1].startswith("利用部門から"), f"下書き直後：{REQ_B} の根拠は要望の発言（誤った要件に根拠が付かない）")

    # ---- 正式な合意 ----
    side(g).get_by_role("button", name="決定・合意", exact=True).click()
    wait(g, 3000)
    choose(g, "表示する項目", DEC)
    main(g).get_by_text("判断者が一覧にない場合はここで登録").click()
    wait(g, 900)
    main(g).get_by_label("氏名・役割").fill(DECIDER)
    main(g).get_by_role("button", name="関係者として登録").click()
    wait(g, 2600)
    choose(g, "採用案", "返却予定日")
    main(g).get_by_label("採用理由").fill("返却の遅れを防ぐため、貸出時に返却予定日を必ず記録する。")
    choose(g, "判断者", DECIDER)
    main(g).get_by_label("判断日（YYYY-MM-DD）").fill("2026-11-10")
    choose(g, "状態", "合意済み")
    main(g).get_by_role("button", name="記録する").click()
    wait(g, 3500)
    t = main(g).inner_text()
    check("判断を合意済みとして記録しました" in t, "合意：判断記録を合意済みとして記録")
    main(g).get_by_text("この要件に反映する").first.click()
    wait(g, 900)
    click(g, "選んだ要件を合意済みにする", 3500)
    t = main(g).inner_text()
    check("関連する要件は全てこの判断に基づいて合意済みです" in t and visible_count(g, "確認資料・要件定義書へ進む →") == 1, "合意：要件にも反映（要件側の確定操作＝「選んだ要件を合意済みにする」）")
    g.screenshot(path=OUT / "2_合意の記録.png", full_page=True)
    side(g).get_by_role("button", name="要件", exact=True).click()
    wait(g, 3000)
    choose(g, "表示する項目", REQ_A)
    check("合意状態：合意済み" in main(g).inner_text(), f"合意：要件の画面で {REQ_A} は合意済み")
    choose(g, "表示する項目", REQ_B)
    check("合意状態：下書き" in main(g).inner_text(), f"合意：{REQ_B}（要望）は下書きのまま（合意済みと表示しない）")
    side(g).get_by_role("button", name="会議記録の候補確認", exact=True).click()
    wait(g, 3000)
    check(f"反映先の現在の状態：{DEC} 合意済み／{REQ_A} 合意済み" in main(g).inner_text() and "判断記録の下書き" in main(g).inner_text(),
          "合意：候補側は登録の履歴のまま、現在の状態は反映先の実データ（合意済み）")
    agreed = save_json(g, OUT / "b_合意後.json")
    s1 = snap(agreed)
    check(s1[DEC][2:6] == ("合意済み", DECIDER, "2026-11-10", "A") and s1[REQ_A][2] == "合意済み" and REQ_A in s1[DEC][6], f"合意：{DEC} 判断者・判断日・採用案・対象の要件 {REQ_A}")

    # ---- 要件定義書（Word） ----
    side(g).get_by_role("button", name="5. 共有・変更管理", exact=True).click()
    wait(g, 3000)
    w1 = word(g, OUT / "c_要件定義書_初回.docx")
    lines = w1.splitlines()
    head_a = next((n for n, l in enumerate(lines) if l.startswith(f"{REQ_A} ") and "（合意済み）" in l), None)
    block_a = "\n".join(lines[head_a:head_a + 8]) if head_a is not None else ""
    check(head_a is not None and f"関連する判断：{DEC}" in block_a and "（合意済み・判断日 2026-11-10）" in block_a and "根拠：第1回打ち合わせ議事録" in block_a,
          f"Word：{REQ_A}（合意済み）から判断 {DEC} と根拠（議事録）をたどれる")
    check(any(l.startswith(DEC) for l in lines) and f"対象の要件：{REQ_A}" in w1 and any(DECIDER in l and REQ_A in l for l in lines), f"Word：{DEC} の欄と変更履歴から {REQ_A}・判断者をたどれる")
    check(any(l.startswith(f"{REQ_B} ") and "（下書き）" in l for l in lines) and "故障時の夜間連絡先" in w1, f"Word：{REQ_B} は「下書き」、夜間連絡先は未決事項として、合意済みと見分けられる")
    wx = word(g, OUT / "d_要件定義書_下書き除外.docx", drafts=False)
    check(REQ_B not in wx and REQ_A in wx, f"Word：下書きを含めない設定では {REQ_B} を出さない")

    # ---- 再開用ファイルを新しいセッションで読み戻す ----
    path = OUT / "e_再開用.json"
    saved = save_json(g, path)
    c.close()
    c = b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    g = c.new_page()
    g.goto(URL)
    g.wait_for_selector(".dr-hero", timeout=120000)
    wait(g)
    g.get_by_label("AIパスワード").fill(CODE)
    g.get_by_label("AIパスワード").press("Enter")
    wait(g, 2200)
    g.locator('input[type="file"]').first.set_input_files(str(path))
    wait(g, 2500)
    g.get_by_role("button", name="この案件を再開する").click()
    g.wait_for_selector(".dr-title", timeout=30000)
    wait(g, 2500)
    restored = save_json(g, OUT / "f_復元後.json")
    sa, sb = snap(saved), snap(restored)
    diff = [k for k in sa if sa[k] != sb.get(k)]
    check(not diff and set(sa) == set(sb), f"復元：要件・判断記録・根拠・確認事項・資料が保存前と一致（差：{diff or 'なし'}）")
    side(g).get_by_role("button", name="要件", exact=True).click() if side(g).get_by_role("button", name="要件", exact=True).count() else (side(g).get_by_role("button", name="4. 要件の確認・判断", exact=True).click(), wait(g, 2000), side(g).get_by_role("button", name="要件", exact=True).click())
    wait(g, 3000)
    choose(g, "表示する項目", REQ_A)
    check("合意状態：合意済み" in main(g).inner_text(), f"復元：画面でも {REQ_A} は合意済み")
    side(g).get_by_role("button", name="5. 共有・変更管理", exact=True).click()
    wait(g, 3000)
    w2 = word(g, OUT / "g_要件定義書_復元後.docx")
    same = norm(w1) == norm(w2)
    if not same:
        import difflib
        print("\n".join(list(difflib.unified_diff(norm(w1).splitlines(), norm(w2).splitlines(), lineterm=""))[:20]))
    check(same, "復元：同じ設定のWord再出力が初回と一致（生成日時・版を除く）")
    b.close()

print("照合したID：", {"判断記録": DEC, "合意した要件": REQ_A, "要望の要件": REQ_B, "確認事項": QST})
print("問題", len(problems))
for x in problems:
    print(" -", x)
