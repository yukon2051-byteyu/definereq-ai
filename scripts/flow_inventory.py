"""全ページの遷移一覧を、実際の画面から作る（docs/画面遷移.md）。

自分の案件は代表的な4つの状態で全ページを描画し、画面名・状態の表示・主操作（強調したボタン）と、
押したときの移動先を記録する。デモは全ステップの本文の操作と、サイドバーから開いた機能の戻り先を記録する。
AIは呼ばない（候補はテスト用の代替応答で作る）。

使い方：python scripts/flow_inventory.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from streamlit.testing.v1 import AppTest  # noqa: E402

from definereq import project as pj  # noqa: E402
from definereq.ai import tasks as ai  # noqa: E402
from definereq.ai.client import AIResult  # noqa: E402
from definereq.demos import guide as demo_guide  # noqa: E402
from definereq.ingest import registry  # noqa: E402
from definereq.logic import intake  # noqa: E402
from definereq.ui.shell import ADVANCED, GROUPS  # noqa: E402

APP = str(ROOT / "app.py")
OUT = ROOT / "docs" / "画面遷移.md"


class Ledger:
    def reserve(self, *a, **k):
        return 1

    def settle(self, *a, **k):
        pass


class LLM:
    def __init__(self, items):
        self.items = items

    def complete(self, system, user, schema, max_tokens):
        return AIResult({"items": self.items, "notes": ""}, 10, 10)


def item(kind, text):
    return {"kind": kind, "text": text, "detail": "", "ask": "", "evidence": []}


def states() -> list[tuple[str, dict]]:
    """代表的な状態。①新規 ②背景と議事録を登録 ③AI整理後（確認待ち6件・採用1件） ④確認が終わり要件を整理中。"""
    a = pj.new_project("架空の案件（新規）", ["app"])
    b = pj.new_project("架空の案件（議事録を登録）", ["app"])
    b["profile"]["background"].update(value="紙の連絡票で変更を伝えている")
    registry.ingest_paste(b, "第1回議事録", "容器と配膳先のコードを照合する。", kind="議事録")
    c = pj.new_project("架空の案件（AI整理後）", ["app"])
    c["profile"]["background"].update(value="紙の連絡票で変更を伝えている")
    m = registry.ingest_paste(c, "第1回議事録", "容器と配膳先のコードを照合する。", kind="議事録")
    items = [item("要望", "コードを読み取り照合する"), item("要望", "確認時刻を記録する"), item("決定", "第1期は照合と履歴のみ"), item("保留", "通信障害時の扱い"),
             item("保留", "保存期間"), item("未回答", "当日変更の扱い"), item("次の行動", "次回会議で保存期間を確認する")]
    cs = ai.run_task(c, "extract", "c", Ledger(), LLM(items), source_ids=[m["id"]])["candidates"]
    intake.adopt_requirement(c, cs[0]["id"])
    d = pj.loads_copy(c) if hasattr(pj, "loads_copy") else __import__("copy").deepcopy(c)
    d["name"] = "架空の案件（確認後）"
    for x in d["candidates"]:
        if x["state"] == "候補":
            x["state"] = "却下"
    return [("① 新規", a), ("② 議事録を登録", b), ("③ AI整理後・確認待ち6件", c), ("④ 確認待ち0件・要件あり", d)]


def demo_guide_first_after(steps):
    from definereq.ui.guide import first_after_meeting

    return first_after_meeting(steps)


# 本文の次の操作の一覧（画面の実装と同じ内容。変更したらここも直す）
FLOW_RULES = [
    ("案件の準備", "準備の概要", "常に", "背景・目的・関係者を入力／参考資料を登録する（カード）", "すでに議事録がある場合は、議事録を取り込む → 資料・議事録", "なし"),
    ("案件の準備", "背景・目的・関係者", "保存の直後", "次へ：質問・議題 → 質問・議題（未整理の議事録・確認待ちの候補があればその作業）", "参考資料を登録する（参考資料が0件のとき）", "なし"),
    ("案件の準備", "参考資料", "登録の直後", "会議の準備へ進む → 質問・議題（質問・議題から開いたときは「会議の準備に戻る」）", "続けて参考資料を追加", "質問・議題の入力途中の内容（下書き）"),
    ("会議の準備", "質問・議題", "反映の直後（反映結果の近く）／それ以外（画面の下）", "会議へ進む → 会議", "会議が終わっていれば、議事録を取り込む／参考資料を追加する", "なし"),
    ("会議の準備", "質問・議題", "未反映の入力があるとき", "案件内に反映", "反映して会議へ進む（入力は下書きに残る）", "入力途中の内容"),
    ("記録の取り込み・整理", "資料・議事録", "議事録の登録直後", "会議の記録を整理する → 会議の記録を整理", "続けて議事録を追加／参考資料を登録する", "今回登録した議事録（整理の対象に選択済み）"),
    ("記録の取り込み・整理", "会議の記録を整理", "未整理の議事録があるとき", "選択した議事録をAIで整理する", "前回の整理で作成したAI候補を確認する", "整理済みの議事録は初期の選択に入れない"),
    ("記録の取り込み・整理", "会議の記録を整理", "AI整理の後", "AI候補を確認する → AI候補の確認", "次回の質問を準備する", "なし"),
    ("要件の確認・判断", "AI候補の確認", "採用の直後", "次の未確認候補へ（0件なら登録した要件を開く）", "登録した要件を開く／要件一覧を開く", "採用した候補から作った要件"),
    ("要件の確認・判断", "AI候補の確認", "決定の候補で「判断記録の下書きを作成」の直後（確認欄を開いただけでは作らない）", "決定・合意で下書きを開く → 決定・合意", "要件の下書きを開く（要件も作ったとき）／次の未確認候補へ", "作成した判断記録（選択済み）・要件の下書き"),
    ("会議の準備", "会議", "会議の登録直後は完了欄に1組だけ。開き直した会議は詳細に1組だけ", "会議の記録を整理 → 会議の記録を整理", "質問・議題に戻る", "押した会議"),
    ("要件の確認・判断", "要件", "要件が0件", "AI候補を確認する → AI候補の確認（候補がなければ会議の記録を整理）", "要件を追加する（手入力の欄を開いた状態）", "なし"),
    ("要件の確認・判断", "決定・合意", "判断を合意済みにし、関連する要件へ反映し終えたとき", "確認資料・要件定義書へ進む → 確認資料・要件定義書", "なし", "なし"),
    ("共有・変更管理", "確認資料・要件定義書", "Wordの作成後", "（ダウンロード）", "現在の状況へ戻る／再開用ファイルをダウンロード", "なし"),
    ("各工程", "その他の画面・詳細メニュー", "常に", "状態に合う次の作業（見出しの直下）", "← 準備の概要に戻る", "残件から開いたときは対象の要件"),
]


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()


def look(p: dict, page: str) -> dict:
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["project"], at.session_state["page"] = p, page
    at.run()
    html = "".join(h.proto.body for h in at.get("html"))
    now = re.findall(r'<div class="dr-(?:now|next)[^"]*">(.*?)</div>', html)
    status = clean(now[0]) if now else ""
    primary = [b for b in at.button if b.proto.type == "primary" and b.key and not b.key.startswith("nav_")]
    main = primary[0] if primary else None
    here = "この画面で作業します" in "".join(c.value for c in at.caption)
    back = any(b.label == "← 準備の概要に戻る" for b in at.button)  # 主ボタンを押して移動する前に判定する
    cards = [b.label for b in at.button if b.key in ("setup_profile", "setup_refs", "setup_minutes")]
    target = ""
    if main and "→" in main.label:
        try:
            after = main.click().run()
            target = after.session_state["page"]
        except Exception:  # 押せない状態（条件不足）のときは移動先なし
            target = ""
    label = main.label if main else ("（この画面で作業）" if here else "／".join(f"{x}（カード）" for x in cards))
    return {"status": status[:60], "main": label, "target": target, "back": back, "error": bool(at.exception)}


def main() -> None:
    names = {key: label for _, items in GROUPS for key, label, _ in items}
    group_of = {key: group for group, items in GROUPS for key, _, _ in items}
    lines = ["# 画面遷移の一覧", "",
             "`scripts/flow_inventory.py` で、実際の画面を描画して作成した一覧です（手で書き換えないでください）。AIは呼んでいません。",
             "主操作は、その状態で強調表示されるボタンです。「→」の付いた主操作は、押したときの移動先を記録しています。", "",
             "## 本文の次の操作（作業の結果から次の作業へ）", "",
             "各画面の作業を終えた後に、本文に出る操作です。表示の条件と、移動先へ引き継ぐ対象を示します（`tests/test_project_flow.py` で確認）。", "",
             "| 工程 | 画面 | 表示の条件 | 主操作 → 移動先 | 補助の操作 | 引き継ぐ対象 |", "|---|---|---|---|---|---|",
             *[f"| {' | '.join(row)} |" for row in FLOW_RULES], "",
             "## 自分の案件（状態ごとの主操作）", ""]
    for name, p in states():
        lines += [f"### {name}", "", "| 工程 | 画面 | 状態の表示 | 主操作 | 移動先 | 戻る操作 |", "|---|---|---|---|---|---|"]
        for key in names:
            r = look(p, key)
            menu = names[key] + ("（詳細メニュー）" if key in ADVANCED else "")
            to = names.get(r["target"], r["target"])
            lines.append(f"| {group_of[key]} | {menu} | {r['status']} | {r['main']} | {to} | {'← 準備の概要に戻る' if r['back'] else '見出し付近に独自の戻る操作' if key in ('profile', 'refs', 'sources') else 'ー'} |"
                         + (" **エラー**" if r["error"] else ""))
        lines.append("")
    lines += ["## デモ（3件）", "", "| デモ | ステップ | 工程 | 本文の操作 |", "|---|---|---|---|"]
    for demo_id in ("d1", "d2", "d3"):
        steps = demo_guide.load(demo_id)
        target, short = demo_guide.SHORTCUTS[demo_id]
        for n, s in enumerate(steps):
            ops = [f"前へ：{steps[n - 1]['process']}"] if n else []
            if s.get("finale"):
                ops += ["代表的な要件1件を最初から表示", "要件定義書の全文を見る（主操作）", "要件定義書をWordでダウンロード", "ほかの成果物（Word／Excel）", "ほかのデモを見る", "機能画面でこの案件の現在の状況を見る"]
            else:
                ops.append(f"次へ：{steps[n + 1]['process']}（主操作）")
                if n:  # ステップ1（案件の背景）からは機能画面へ直接は飛ばない（背景・目的・関係者を見る操作だけ）
                    ops.append(f"詳細：{s['detail'](demo_guide.Ctx(__import__('definereq.demos.builder', fromlist=['build']).build(demo_id, s['stage'])))}")
                else:
                    ops.append("機能画面で背景・目的・関係者を見る")
                if n == demo_guide_first_after(steps):
                    ops.append("機能画面で会議後に残った確認事項を見る（現在の状況を、この場面と同じ時点のデータで開く）")
            if n == target:
                ops.append(f"トップの近道「{demo_guide.shortcut_label(demo_id)}」の行き先（前提の1文と「案件の背景から見る」を表示）")
            lines.append(f"| {demo_id} | {n + 1}. {s['process']} | {group_of.get(s['page'], '')} | {'／'.join(ops)} |")
    lines += ["", "デモの案内中は、ステップを進めてもサイドバーの工程は自動で開きません（工程名を押すと開閉だけします）。"
              "工程を開いて機能を選ぶと、その工程とページを選択表示し、本文の先頭に「← デモステップ N/8『ステップ名』に戻る」が出ます。"
              "戻ると元のステップと、機能を開く前の開閉状態に戻ります（`tests/test_guidance.py` の `test_open_process_and_return_to_step`）。", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("作成", OUT)


if __name__ == "__main__":
    main()
