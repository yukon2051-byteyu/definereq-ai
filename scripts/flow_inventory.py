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
    cards = [b.label for b in at.button if b.key in ("setup_profile", "setup_sources")]
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
             "## 自分の案件", ""]
    for name, p in states():
        lines += [f"### {name}", "", "| 工程 | 画面 | 状態の表示 | 主操作 | 移動先 | 戻る操作 |", "|---|---|---|---|---|---|"]
        for key in names:
            r = look(p, key)
            menu = names[key] + ("（詳細メニュー）" if key in ADVANCED else "")
            to = names.get(r["target"], r["target"])
            lines.append(f"| {group_of[key]} | {menu} | {r['status']} | {r['main']} | {to} | {'← 準備の概要に戻る' if r['back'] else '見出し付近に独自の戻る操作' if key in ('profile', 'sources') else 'ー'} |"
                         + (" **エラー**" if r["error"] else ""))
        lines.append("")
    lines += ["## デモ（3件）", "", "| デモ | ステップ | 工程 | 本文の操作 |", "|---|---|---|---|"]
    for demo_id in ("d1", "d2", "d3"):
        steps = demo_guide.load(demo_id)
        target, short = demo_guide.SHORTCUTS[demo_id]
        for n, s in enumerate(steps):
            ops = [f"前へ：{steps[n - 1]['process']}"] if n else []
            if s.get("finale"):
                ops += ["要件定義書の内容を見る（主操作）", "ほかのデモを見る", "この案件の機能画面を詳しく見る", "Word／Excelのダウンロード"]
            else:
                ops.append(f"次へ：{steps[n + 1]['process']}（主操作）")
                ops.append(f"詳細：{s['detail'](demo_guide.Ctx(__import__('definereq.demos.builder', fromlist=['build']).build(demo_id, s['stage'])))}")
            if n == target:
                ops.append(f"トップの近道「{demo_guide.shortcut_label(demo_id)}」の行き先（前提の1文と「案件の背景から見る」を表示）")
            lines.append(f"| {demo_id} | {n + 1}. {s['process']} | {group_of.get(s['page'], '')} | {'／'.join(ops)} |")
    lines += ["", "デモのステップからサイドバーで機能を開くと、本文の先頭に「← ステップN「ステップ名」に戻る」が出て、開いた元のステップへ戻ります（`tests/test_project_flow.py` の `test_every_demo_detail_page_returns_to_step`）。", ""]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("作成", OUT)


if __name__ == "__main__":
    main()
