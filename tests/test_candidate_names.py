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
DEMO_EXPLAIN = "このデモでは、議事録や録画からAIが拾った候補と、人が確認した結果を閲覧できます。"
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
    assert chain.index("元の発言") < chain.index("AIが拾った内容") < chain.index("人の判断")
    label = "機能画面で会議記録の候補を見る"
    key = next(b.key for b in at.button if b.label == label)
    at = button(at, key).click().run()
    assert at.session_state["page"] == "candidates" and button(at, "nav_candidates").proto.type == "primary"
    # デモは閲覧専用の説明（登録できるとは書かない）
    assert "会議記録の候補確認" in html(at) and DEMO_EXPLAIN in html(at) and EXPLAIN not in html(at)
    at = button(at, "tour_back").click().run()  # 元のステップへ戻る
    assert at.session_state["tour_on"] and at.session_state["tour_index"] == n_after


# ---- 公開版レビューの5点 ----
def _extract_project(p):
    m = registry.ingest_paste(p, "第1回議事録", "講師が出欠を登録する。定員は30名とする。", kind="議事録")
    ai.run_task(p, "extract", "c", Ledger(), LLM([item("決定", "定員は30名とする"), item("決定", "申込は先着順とする"), item("質問", "講師の登録方法は"), item("要望", "出欠を登録する")]),
                source_ids=[m["id"]])
    return p


def test_processed_shows_registration_not_agreement(p):
    """候補の処理は「登録済み・追加済み」で示し、反映先の現在の状態は反映先の記録から読む。"""
    from definereq.logic import intake
    from definereq.ui.candidates import processed

    _extract_project(p)
    d1, d2, q, r = p["candidates"]
    intake.apply(p, d1["id"], new_requirement=True)
    hist, now = processed(p, d1)
    dec, req = d1["resolved_items"]
    assert hist == f"判断記録の下書き {dec} と要件の下書き {req} を作成しました" and now == f"{dec} 下書き／{req} 下書き"
    intake.apply(p, d2["id"], link_requirements=[req])
    hist, _ = processed(p, d2)
    assert hist.startswith("判断記録の下書きに登録済み（DEC-") and hist.endswith(f"既存要件 {req} に関連付け済み")
    intake.apply(p, q["id"])
    assert processed(p, q)[0].startswith("会議の質問に追加済み")
    created = intake.adopt_requirement(p, r["id"])
    hist, now = processed(p, r)
    assert hist == f"要件の下書きに登録済み（{created[0]['id']}）" and now.endswith("下書き")
    created[0]["status"] = "合意済み"  # 後から正式に合意された場合：処理の履歴は変えず、現在の状態は反映先の実データ
    hist2, now2 = processed(p, r)
    assert hist2 == hist and now2 == f"{created[0]['id']} 合意済み"
    at = open_app(p, "candidates")
    h = html(at)
    assert "人が確定した内容です" not in h and f"反映先の現在の状態：{created[0]['id']} 合意済み" in h and "要件の下書きに登録済み" in h


def test_network_demo_shows_proposal_and_rejection_together():
    from definereq.demos import builder

    at = AppTest.from_file(APP, default_timeout=60).run()
    at = button(at, "tour_d3").click().run()
    at = button(at, "tour_go_2").click().run()  # ステップ3「録画の発言」
    h = html(at)
    chain = h[h.index('class="dr-chain"'):]
    assert "外部からの遠隔保守を提案します" in chain and "遠隔保守を採用する" in chain and "却下" in chain and "提案であり、決定ではない" in chain
    at = button(at, "tour_cand_open").click().run()
    h = html(at)
    card = h[h.index("遠隔保守を採用する"):]
    assert card.index("却下（人の判断）") < card.index("人の判断") and "記録された説明：岡田の発言。提案であり、決定ではない。" in card
    assert DEMO_EXPLAIN in h
    at = button(at, "tour_back").click().run()
    assert at.session_state["tour_on"] and at.session_state["tour_index"] == 2


def test_prep_ai_entrance_opens_confirmation_without_running(p):
    at = open_app(p, "prep")
    key = f"draft_{p['id']}_prep_agenda"
    at = next(t for t in at.text_area if t.key == key).set_value("入力途中の議題").run()
    runs = len(at.session_state["project"]["ai_runs"])
    at = button(at, "prep_ai_open").click().run()  # 初期画面（理解と議題）から見つけられる入口
    assert at.session_state["prep_tabs"] == "質問" and at.session_state["ai_exp_prep"] is True
    assert len(at.session_state["project"]["ai_runs"]) == runs and at.session_state["project"]["prep"].get("agenda") in (None, [])  # 実行も保存もしない
    assert any(b.label == "この内容でAIを実行" for b in at.button)  # 実行は確認欄のボタンで
    assert next(t for t in at.text_area if t.key == key).value == "入力途中の議題"  # 入力途中の議題を保持


def test_prep_meeting_button_once_after_save(p):
    at = open_app(p, "prep")
    at = next(t for t in at.text_area if t.key == f"draft_{p['id']}_prep_agenda").set_value("申込の流れ").run()
    at = button(at, "prep_save").click().run()
    assert [b.label for b in at.button].count("会議へ進む →") == 1


# ---- 正式な合意から要件定義書まで：要件から判断と根拠をたどれる。下書きを含めない設定では残件表にも出さない ----
def test_spec_links_requirement_decision_and_evidence_and_hides_excluded_drafts(p):
    from definereq.export import share
    from definereq.logic import agreement as ag
    from definereq.logic import intake

    _extract_project(p)
    d1, _, _, r = p["candidates"]
    intake.apply(p, d1["id"], new_requirement=True)
    dec, req = d1["resolved_items"]
    draft = intake.adopt_requirement(p, r["id"])[0]["id"]
    pj.add(p, "stakeholders", {"name": "佐藤", "org": None, "position": None, "authority": "判断者", "certainty": "本人申告", "note": None})
    pj.get(p, "decisions", dec).update(adopted="A", decider="佐藤", decided_on="2026-11-10")
    ag.set_state(p, dec, "合意済み", "human")
    ag.apply_decision(p, dec, [req], "human")
    text = "\n".join(x for s in share.build(p, share.Options(doc_type="spec")) for x in [s.heading, *s.paragraphs, *("|".join(r) for r in (s.table or {}).get("rows", []))])
    import re

    block = text[re.search(rf"^{req} .+（合意済み）$", text, re.M).start():]  # 要件ごとの詳細の見出しから読む
    assert f"関連する判断：{dec}" in block[:600] and "（合意済み・判断日 2026-11-10）" in block[:600] and "根拠：" in block[:600]  # 根拠の資料名と位置は agreement_e2e_check.py で確認
    opt = share.Options(doc_type="spec")
    opt.include_drafts = False
    hidden = "\n".join(x for s in share.build(p, opt) for x in [s.heading, *s.paragraphs, *("|".join(r) for r in (s.table or {}).get("rows", []))])
    assert draft not in hidden and req in hidden  # 除外した下書きは、記入不足の表にも出さない


def test_demo_representative_lists_decision_chain():
    """最終画面の代表例：途中の判断を経て確定した要件は、関係する判断を判断日の順に示す（要件定義書と同じ）。"""
    at = AppTest.from_file(APP, default_timeout=60).run()
    at = button(at, "tour_d1").click().run()
    at = button(at, "tour_go_7").click().run()
    h = html(at)
    rep = h[h.index('class="dr-rep"'):]
    chain = rep[rep.index("この要件に関係する判断（判断日の順）"):]
    assert chain.index("DEC-001") < chain.index("DEC-004") and "決め手になった判断" in rep
