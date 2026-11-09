"""「案件の準備」の「次にすること」と、資料の登録直後の案内の実ブラウザ確認（デスクトップ、架空の案件）。

AIは呼ばない。要件候補がある案件は、テストと同じ仮のAI応答で候補を作った再開用ファイルを読み込んで確認する。
使い方：python scripts/next_flow_check.py <URL> <保存先> <AIパスワード>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright  # noqa: E402

from definereq import project as pj  # noqa: E402
from definereq.ai import tasks as ai  # noqa: E402
from definereq.ai.client import AIResult  # noqa: E402
from definereq.export import jsonio  # noqa: E402
from definereq.ingest import registry  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
URL, OUT, CODE = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
OUT.mkdir(parents=True, exist_ok=True)
H = 900
problems: list[str] = []


class Ledger:
    def reserve(self, *a, **k):
        return 1

    def settle(self, *a, **k):
        pass


class LLM:  # 仮のAI応答（実際のAIは呼ばない）
    def complete(self, system, user, schema, max_tokens):
        return AIResult({"items": [{"kind": "要望", "text": "講師が出欠を登録する", "detail": "", "ask": "", "evidence": []}], "notes": ""}, 10, 10)


def candidate_file() -> Path:
    p = pj.new_project("研修申込の管理（架空・候補あり）", ["app"])
    m = registry.ingest_paste(p, "第1回議事録", "講師が出欠を登録する。", kind="議事録")
    ai.run_task(p, "extract", "c", Ledger(), LLM(), source_ids=[m["id"]])
    path = OUT / "candidates.json"
    path.write_bytes(jsonio.dumps(p))
    return path


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


def click(g, name, ms=2400):
    main(g).get_by_role("button", name=name, exact=True).first.click()
    wait(g, ms)


def title(g):
    return g.locator(".dr-title").first.inner_text()


def in_view(loc):
    b = loc.bounding_box()
    return bool(b) and 0 <= b["y"] and b["y"] + min(b["height"], 40) <= H


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
    g.evaluate("document.querySelector('[data-testid=stSidebarCollapseButton] button')?.click()")  # 左メニューは閉じて本文だけで進む
    wait(g, 900)


def resume(g, path):
    top(g)
    g.locator('input[type="file"]').first.set_input_files(str(path))
    wait(g, 2500)
    g.get_by_role("button", name="この案件を再開する").click()
    g.wait_for_selector(".dr-title", timeout=30000)
    wait(g, 2000)


def paste(g, name, text, other=None):
    if other:
        g.get_by_text("その他の資料を取り込む", exact=True).click()
        wait(g, 1500)
        g.locator("[data-testid=stSelectbox]").filter(has_text="資料の種類").locator("input").click()
        wait(g, 500)
        g.get_by_role("option", name=other, exact=True).click()
        wait(g, 1500)
    g.get_by_role("tab", name="文章を貼り付けて取り込む").click()
    wait(g, 600)
    g.get_by_label("貼り付ける文章の名称").fill(name)
    g.get_by_role("textbox", name="文章を貼り付ける").fill(text)
    g.get_by_role("textbox", name="文章を貼り付ける").press("Tab")
    wait(g, 900)
    click(g, "貼り付けた文章を案件内に登録", 2800)


def next_button(g):
    return main(g).get_by_role("button").filter(has_text="→")


with sync_playwright() as pw:
    b = pw.chromium.launch(channel="msedge", headless=True)

    # ---- 案件A：背景を保存 → 議事録を登録 → 準備へ戻る（条件1・2・5） ----
    c = b.new_context(viewport={"width": 1440, "height": H}, accept_downloads=True)
    g = c.new_page()
    create(g, "研修申込の管理（架空・次にすること）")
    t = body(g)
    check(main(g).locator(".dr-next").count() == 0 and main(g).get_by_role("button", name="資料・議事録を取り込む").count() == 1, "4 何もない案件：2枚のカードが開始操作（次にすることは出さない）")
    click(g, "背景・目的・関係者を入力")
    g.get_by_label("背景", exact=True).first.fill("申込をメールで受けている")
    g.get_by_label("背景", exact=True).first.press("Tab")
    wait(g, 800)
    click(g, "保存して資料・議事録へ進む", 2800)
    paste(g, "第1回打ち合わせ議事録", "講師が出欠を登録する。定員は30名。")
    ok_box = g.locator(".st-key-src_done_box")
    success_y = ok_box.locator("[data-testid=stAlert]").bounding_box()["y"]
    go = next_button(g).first
    check(go.inner_text() == "会議の記録を整理する →" and abs(go.bounding_box()["y"] - success_y) < 200 and in_view(go), f"2 議事録の登録直後、成功メッセージの近く（{go.bounding_box()['y'] - success_y:.0f}px下）に記録の整理を表示")
    check(main(g).get_by_role("button", name="続けて資料を追加する").count() == 1 and main(g).get_by_role("button", name="← 案件の準備に戻る").count() == 1, "2 続けて資料を追加する操作と、案件の準備に戻る操作も使える")
    g.screenshot(path=OUT / "2_after_register.png")
    click(g, "← 案件の準備に戻る")
    t = body(g)
    cards_bottom = g.locator(".st-key-setup_profile").bounding_box()["y"]
    nb = g.locator(".st-key-setup_next").bounding_box()["y"]
    resume_y = g.locator(".st-key-setup_resume").bounding_box()["y"]
    check(cards_bottom < nb < resume_y and next_button(g).first.inner_text() == "会議の記録を整理する →" and in_view(next_button(g).first),
          "1 準備画面：2枚のカードの直下（再開用ファイルより上）に「会議の記録を整理する」")
    check("入力済み" in t and "取り込み済み 1件" in t, "1 準備画面の状態：入力済み・取り込み済み 1件")
    g.screenshot(path=OUT / "1_setup_next.png")
    click(g, "会議の記録を整理する →", 3000)
    check(title(g) == "会議の記録を整理" and "第1回打ち合わせ議事録" in body(g), "1 1クリックで既存の整理画面が開く（取り込んだ議事録が並ぶ）")
    check(main(g).get_by_role("button", name="← 案件の準備に戻る").count() == 1 and "件の候補を作成しました" not in body(g), "どの画面でも上部に戻る操作。AIは画面を開いただけでは実行しない")
    click(g, "← 案件の準備に戻る")
    click(g, "背景・目的・関係者を編集")
    keep = g.get_by_label("背景", exact=True).first.input_value() == "申込をメールで受けている"
    click(g, "資料・議事録へ")
    check(keep and "第1回打ち合わせ議事録" in g.content(), "5 次の作業へ進んで戻っても、保存済みの背景と登録済みの資料が残る")
    click(g, "← 案件の準備に戻る")
    with g.expect_download() as d:
        main(g).get_by_role("button", name="再開用ファイルをダウンロード").click()
    saved = OUT / "resume_a.json"
    d.value.save_as(saved)
    c.close()

    # ---- 案件B：要望書だけ → 会議の準備。議事録を追加すると案内が変わる（条件3・4） ----
    c = b.new_context(viewport={"width": 1440, "height": H})
    g = c.new_page()
    create(g, "研修申込の管理（架空・要望書だけ）")
    click(g, "資料・議事録を取り込む")
    paste(g, "要望書", "申込から受講履歴までを一つのアプリで管理したい。", other="要望")
    check(next_button(g).first.inner_text() == "会議の準備へ進む →", "3 要望書を登録した直後は「会議の準備へ進む」")
    click(g, "← 案件の準備に戻る")
    check(next_button(g).first.inner_text() == "会議の準備へ進む →", "3 要望書だけの案件の準備画面は「会議の準備へ進む」")
    click(g, "会議の準備へ進む →", 3000)
    check(title(g) == "質問・議題", "3 1クリックで会議の準備（質問・議題）が開く")
    click(g, "← 案件の準備に戻る")
    click(g, "資料・議事録を取り込む")
    g.get_by_text("議事録を取り込む", exact=True).click()
    wait(g, 1200)
    paste(g, "第1回議事録", "受講者は研修を選んで申し込む。")
    click(g, "← 案件の準備に戻る")
    check(next_button(g).first.inner_text() == "会議の記録を整理する →" and "未入力" in body(g), "4 背景が未入力でも、議事録を追加すると記録の整理へ案内が変わる")
    c.close()

    # ---- 要件候補がある案件（条件3）と、再開用ファイルからの復元（条件5） ----
    for path, want, label in ((candidate_file(), "AI候補を確認する →", "3 確認する要件候補がある案件は「AI候補を確認する」"),
                              (saved, "会議の記録を整理する →", "5 再開用ファイルから復元した案件にも、状態に合う案内が出る")):
        c = b.new_context(viewport={"width": 1440, "height": H})
        g = c.new_page()
        resume(g, path)
        if title(g) != "案件の準備":  # 再開は保存時の画面で開く
            click(g, "← 案件の準備に戻る")
        got = next_button(g).first.inner_text()
        check(got == want, f"{label}（{got}）")
        if want.startswith("AI候補"):
            g.screenshot(path=OUT / "3_candidates.png")
            click(g, want, 3000)
            check(title(g) == "AI候補の確認", "3 1クリックでAI候補の確認画面が開く")
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
            check(data["profile"]["background"]["value"] == "申込をメールで受けている" and "取り込み済み 1件" in body(g), "5 復元後も背景と資料が戻る")
        c.close()
    b.close()

print("問題", len(problems))
for x in problems:
    print(" -", x)
