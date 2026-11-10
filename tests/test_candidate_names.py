"""「AI候補」の呼び方：画面名で元の情報（会議記録／会議前の準備）を、説明で人が行う作業を伝える。"""
from __future__ import annotations

import pytest
from streamlit.testing.v1 import AppTest

from definereq import project as pj
from definereq.ai import tasks as ai
from definereq.ai.client import AIResult
from definereq.demos import guide as demo_guide
from definereq.ingest import registry
from definereq.ui.guide import first_after_meeting

APP = str(__import__("pathlib").Path(__file__).resolve().parent.parent / "app.py")
EXPLAIN = "議事録や録画の発言から、AIが要望・決定・未決事項などを拾い出します。内容を確認し、必要なものを要件の下書きや確認事項などに登録できます。"
PREP_EXPLAIN = "案件の背景や参考資料をもとに、会議で聞く質問や、当日決めたいことをAIが提案します。"


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


def html(at):
    return "".join(h.proto.body for h in at.get("html"))


def caps(at):
    return [c.value for c in at.caption]


def open_app(p, page):
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["project"], at.session_state["page"] = p, page
    return at.run()


def button(at, key):
    return next(b for b in at.button if b.key == key)


@pytest.fixture
def p():
    return pj.new_project("研修申込の管理（架空）", ["app"])


def test_sidebar_heading_and_position_use_new_name(p):
    at = open_app(p, "candidates")
    assert button(at, "nav_candidates").label == "会議記録の候補確認"
    assert "会議記録の候補確認" in html(at) and "作業位置：会議記録の候補確認" in html(at) and EXPLAIN in html(at)
    assert "AI候補" not in html(at)


def test_prep_candidates_and_extract_flow(p):
    """会議前の質問・議題の候補は「質問・議題」で、議事録の整理後は完了案内から「会議記録の候補確認」へ。"""
    ai.run_task(p, "prep", "c", Ledger(), LLM([item("質問", "講師の登録方法は")]))
    at = open_app(p, "prep")
    assert EXPLAIN not in html(at) and PREP_EXPLAIN in html(at) + "".join(caps(at))
    assert any(m.value.startswith("**会議前の質問・議題の候補**") for m in at.markdown)
    m = registry.ingest_paste(p, "第1回議事録", "講師が出欠を登録する。", kind="議事録")
    ai.run_task(p, "extract", "c", Ledger(), LLM([item("要望", "講師が出欠を登録する"), item("決定", "定員は30名とする")]), source_ids=[m["id"]])
    at = open_app(p, "records")
    assert "AIが会議記録から確認候補を2件抽出しました。" in html(at)
    assert button(at, "records_go_cand").label == "会議記録の候補確認へ進む →"
    at = button(at, "records_go_cand").click().run()
    assert at.session_state["page"] == "candidates"
    texts = html(at)
    assert "講師が出欠を登録する" in texts and "講師の登録方法は" not in texts  # 会議前の候補は混ぜない
    # 決定の候補では、この操作で作るものを具体的に示す（正式な合意とは別）
    cid = next(c["id"] for c in at.session_state["project"]["candidates"] if c["kind"] == "決定")
    at = button(at, f"go_dec_{cid}").click().run()
    assert any(c.startswith("この操作で判断記録の下書きを作成します。") for c in caps(at))


@pytest.mark.parametrize("demo", ["d1", "d2", "d3"])
def test_demo_explains_before_and_after_meeting(demo):
    steps = demo_guide.load(demo)
    at = AppTest.from_file(APP, default_timeout=60).run()
    at = button(at, f"tour_{demo}").click().run()
    n_prep = next(n for n, s in enumerate(steps) if s["process"] == "会議前の準備")
    at = button(at, f"tour_go_{n_prep}").click().run()
    assert "会議前：次の会議で何を聞くか" in html(at)
    n_after = first_after_meeting(steps)
    at = button(at, f"tour_go_{n_after}").click().run()
    h = html(at)
    if demo == "d2":  # 会議記録から抽出した候補がないデモには、抽出の例を出さない
        assert "会議後：会議で出た内容のうち" not in h
        return
    assert "会議後：会議で出た内容のうち、どれを案件に反映するか" in h
    chain = h[h.index('class="dr-chain"'):]
    assert chain.index("元の発言") < chain.index("AIが拾った内容") < chain.index("人が確認した反映先")
    label = "機能画面で会議記録の候補を見る"
    key = next(b.key for b in at.button if b.label == label)
    at = button(at, key).click().run()
    assert at.session_state["page"] == "candidates" and button(at, "nav_candidates").proto.type == "primary"
    assert "会議記録の候補確認" in html(at) and EXPLAIN in html(at)
    at = button(at, "tour_back").click().run()  # 元のステップへ戻る
    assert at.session_state["tour_on"] and at.session_state["tour_index"] == n_after
