"""実案件の流れの確認（初回、AI入力、候補の反映先、合意と版、出力前確認）。実APIは呼ばない。"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from docx import Document
from streamlit.testing.v1 import AppTest

from definereq import project as pj
from definereq.ai import tasks as ai
from definereq.ai.client import AIResult
from definereq.export import jsonio, share, wordx
from definereq.ingest import registry
from definereq.logic import agreement as ag
from definereq.logic import guidance as gd
from definereq.logic import intake

APP = str(Path(__file__).resolve().parent.parent / "app.py")
INITIAL = "社員100名の会社で、Excelによる勤怠集計をWebシステムへ更新したい。打刻漏れの確認と月末集計に時間がかかる。Web打刻、上長の修正承認、給与ソフト向けCSV出力を検討している。予算、導入時期、勤務形態は未確認。"
MINUTES = ("勤怠システム更新の初回ヒアリング。利用対象は社員100名。現在はExcelで集計し、月末集計に2日かかる。従業員がWebで打刻し、打刻漏れや修正は上長が承認する案を検討する。"
           "給与ソフトへはCSVで連携したいが項目と形式は未確認。導入時期と予算は未定。次回までに人事担当が現行の勤怠表を用意する。上記の機能はまだ合意していない。")


class Ledger:
    def reserve(self, *a, **k):
        return 1

    def settle(self, *a, **k):
        pass


class LLM:
    def __init__(self, items):
        self.items, self.calls, self.user = items, 0, None

    def complete(self, system, user, schema, max_tokens):
        self.calls += 1
        self.user = user
        return AIResult({"items": self.items, "notes": ""}, 10, 10)


def cand(kind, text, **kw):
    return {"kind": kind, "text": text, "detail": "", "ask": "", "evidence": [], **kw}


@pytest.fixture
def p():
    return pj.new_project("勤怠システムの更新（架空テスト）", ["app"])


def run(p, task, items, **kw):
    return ai.run_task(p, task, "c", Ledger(), LLM(items), **kw)["candidates"]


# ---- 初回 ----
def test_phase_distinguishes_empty_and_unprocessed(p):
    assert gd.phase(p) == "empty"
    p["profile"]["problem"].update(value="月末集計に時間がかかる")
    assert gd.phase(p) == "unprocessed"
    run(p, "prep", [cand("質問", "利用人数は？")])
    assert gd.phase(p) == "open"


def test_no_issue_is_not_shown_as_complete_when_nothing_analyzed(p):
    registry.ingest_paste(p, "メモ", "メモ", kind="要望")
    assert gd.phase(p) == "unprocessed"


def test_profile_only_gets_two_entry_points(p):
    p["profile"]["problem"].update(value="月末集計に時間がかかる")
    r = gd.assess(p, "overview")
    assert r["main"].id == "next_input" and r["main"].alt == [("議事録を取り込む", "records")]


# ---- AI入力 ----
def test_prep_understanding_reaches_ai_and_changes_input(p):
    before = ai.build_context(p, ai.TASKS["prep"])
    p["prep"]["understanding"] = INITIAL
    after = ai.build_context(p, ai.TASKS["prep"])
    assert "社員100名" in after and len(after) > len(before) + len(INITIAL) - 5
    assert ai.input_fingerprint(before) != ai.input_fingerprint(after)


def test_profile_keeps_certainty_in_ai_input(p):
    p["profile"]["problem"].update(value="打刻漏れ", certainty="本人申告")
    assert "本人申告" in ai.build_context(p, ai.TASKS["prep"])


def test_internal_note_stays_out_of_ai_input(p):
    r = pj.add(p, "requirements", pj.new_requirement(title="T", body="B"))
    r["internal_note"] = "社外秘メモ"
    p["prep"]["understanding"] = "理解"
    for task in ai.TASKS.values():
        assert "社外秘メモ" not in ai.build_context(p, task)


def test_saved_input_makes_old_result_stale(p):
    run(p, "prep", [cand("質問", "Q")])
    assert ai.run_status(p, p["ai_runs"][0]) == "最新"
    p["prep"]["understanding"] = "更新"
    assert ai.run_status(p, p["ai_runs"][0]) != "最新"


def test_registered_info_reported_as_unknown_is_flagged(p):
    p["prep"]["understanding"] = INITIAL
    c = run(p, "prep", [cand("不足情報", "利用人数が不明です"), cand("不足情報", "勤務形態が不明です")])
    assert c[0]["already_known"] == "人数" and c[1]["already_known"] is None


# ---- 候補の反映先 ----
@pytest.mark.parametrize("kind,check", [
    ("質問", lambda p: p["questions"] and p["questions"][0].get("category") == "質問"),
    ("議題", lambda p: p["prep"]["agenda"]),
    ("必要資料", lambda p: p["prep"]["materials"]),
    ("不足情報", lambda p: p["questions"][0]["category"] == "確認事項"),
    ("未回答", lambda p: p["questions"][0]["category"] == "確認事項"),
    ("次の行動", lambda p: p["actions"]),
    ("リスク", lambda p: p["risks"] and p["risks"][0]["nature"] == "AI候補"),
    ("決定", lambda p: p["decisions"] and p["decisions"][0]["state"] == "下書き"),
])
def test_routes_go_to_the_right_place_and_never_become_requirements(p, kind, check):
    c = run(p, "extract", [cand(kind, "内容の文")])[0]
    intake.apply(p, c["id"])
    assert check(p) and not p["requirements"] and c["state"] == "採用"


def test_decision_candidate_does_not_create_agreement(p):
    c = run(p, "extract", [cand("決定", "Web打刻を採用する")])[0]
    intake.apply(p, c["id"])
    assert all(d["state"] != "合意済み" for d in p["decisions"])


def test_candidate_cannot_be_applied_twice(p):
    c = run(p, "prep", [cand("質問", "Q")])[0]
    intake.apply(p, c["id"])
    with pytest.raises(ValueError):
        intake.apply(p, c["id"])
    assert len(p["questions"]) == 1


def test_duplicate_candidates_do_not_grow_on_reanalysis_and_old_stay(p):
    run(p, "extract", [cand("要望", "Webで打刻できるようにしたい")])
    registry.ingest_paste(p, "追加", "追加の資料", kind="要望")
    c = run(p, "extract", [cand("要望", "Webで打刻できるようにしたい。"), cand("要望", "CSVで連携したい")])
    assert len(p["candidates"]) == 2 and [x["text"] for x in c] == ["CSVで連携したい"]
    assert p["ai_runs"][-1]["skipped_duplicates"] == 1


# ---- 要件への採用 ----
@pytest.mark.parametrize("text,kind", [("従業員がWebで打刻できる", "機能"), ("上長が修正を承認できる", "機能"), ("給与ソフトへCSVで連携する", "連携")])
def test_classification_suggestion(p, text, kind):
    s = intake.suggest(p, {"text": text, "detail": None})
    assert s["domain"] == "app" and s["kind"] == kind and s["basis"] == "ルールによる推測"


def test_adopt_keeps_classification_and_evidence(p):
    src = registry.ingest_paste(p, "議事録", MINUTES, kind="議事録")
    c = run(p, "extract", [cand("要望", "CSVで連携したい", evidence=[{"source_id": src["id"], "unit_id": "", "quote": "給与ソフトへはCSVで連携したい"}])])[0]
    r = intake.adopt_requirement(p, c["id"], {"domain": "app", "kind": "連携"})[0]
    assert r["kind"] == "連携" and r["domain"] == "app" and r["evidence"][0]["verified"] and r["from_candidate"] == c["id"] and r["status"] == "下書き"


def test_can_adopt_unclassified_and_it_is_reported(p):
    c = run(p, "extract", [cand("要望", "勤怠を見やすくしたい")])[0]
    intake.adopt_requirement(p, c["id"], {"domain": None, "kind": None})
    assert share.precheck(p)["rows"][2] == ("分類未設定の要件", 1, "requirements")
    assert "unclassified" in [a.id for a in gd.collect(p)]


def test_split_proposal_uses_only_original_words():
    parts = intake.split_proposal("従業員がWebで打刻し、打刻漏れや修正は上長が承認する")
    assert parts == ["従業員がWebで打刻する", "打刻漏れや修正は上長が承認する"]
    assert intake.split_proposal("従業員がWebで打刻できる") == []


def test_split_adoption_traces_each_part(p):
    c = run(p, "extract", [cand("要望", "打刻し、承認する")])[0]
    rs = intake.adopt_requirement(p, c["id"], parts=["打刻する", "承認する"])
    assert len(rs) == 2 and all(r["from_candidate"] == c["id"] for r in rs) and c["resolved_items"] == [r["id"] for r in rs]


def test_adoption_does_not_change_existing_requirement(p):
    old = pj.add(p, "requirements", pj.new_requirement(title="既存", body="本文", status="合意済み"))
    c = run(p, "extract", [cand("要望", "新しい要望")])[0]
    intake.adopt_requirement(p, c["id"])
    assert old["status"] == "合意済み" and old["version"] == 1


# ---- 判断と要件 ----
def agreed(p, *reqs):
    d = ag.new_decision(p, "方針", [{"id": "A", "label": "案A"}], adopted="A", decider="人事責任者", decided_on="2026-11-01", related_requirements=[r["id"] for r in reqs])
    ag.set_state(p, d["id"], "合意済み", "human")
    return d


def req(p, title="T"):
    return pj.add(p, "requirements", pj.new_requirement(title=title, body="本文"))


def test_decision_does_not_change_requirement_until_chosen(p):
    a, b = req(p, "A"), req(p, "B")
    d = agreed(p, a, b)
    assert a["status"] == b["status"] == "下書き"
    rows = ag.decision_targets(p, d)
    assert [r["after"] for r in rows] == ["合意済み", "合意済み"]
    ag.apply_decision(p, d["id"], [a["id"]], "human")
    assert a["status"] == "合意済み" and b["status"] == "下書き"


def test_ai_cannot_apply_decision(p):
    a = req(p)
    d = agreed(p, a)
    with pytest.raises(PermissionError):
        ag.apply_decision(p, d["id"], [a["id"]], "ai")


def test_old_version_decision_is_not_applied_to_new_version(p):
    a = req(p)
    d = agreed(p, a)
    pj.update_requirement(p, a["id"], {"body": "変更後"})
    assert not ag.decision_targets(p, d)[0]["same_version"]
    with pytest.raises(ValueError):
        ag.apply_decision(p, d["id"], [a["id"]], "human")
    with pytest.raises(ValueError):
        pj.set_requirement_status(p, a["id"], "合意済み", "human")
    ag.reconfirm_version(p, d["id"], a["id"], "human")
    ag.apply_decision(p, d["id"], [a["id"]], "human")
    assert a["status"] == "合意済み"


def test_changing_agreed_requirement_returns_to_recheck(p):
    a = req(p)
    d = agreed(p, a)
    ag.apply_decision(p, d["id"], [a["id"]], "human")
    pj.update_requirement(p, a["id"], {"body": "変更後"})
    assert a["status"] == "確認待ち"


def test_unrelated_requirement_is_rejected(p):
    a, b = req(p, "A"), req(p, "B")
    d = agreed(p, a)
    with pytest.raises(ValueError):
        ag.apply_decision(p, d["id"], [b["id"]], "human")


def test_legacy_decision_without_version_record_still_works(p):
    a = req(p)
    d = agreed(p, a)
    d.pop("target_versions")
    assert ag.decision_targets(p, d)[0]["same_version"]
    ag.apply_decision(p, d["id"], [a["id"]], "human")


# ---- 案件情報 ----
def test_understanding_is_suggested_not_overwritten(p):
    p["prep"]["understanding"] = INITIAL
    s = next(x for x in intake.profile_suggestions(p) if x["field"] == "background")
    assert p["profile"]["background"]["value"] is None
    intake.apply_profile(p, s)
    assert p["profile"]["background"]["value"] == INITIAL and p["profile"]["background"]["origin"] == s["origin"]
    p["prep"]["understanding"] = "別の内容"
    s = next(x for x in intake.profile_suggestions(p) if x["field"] == "background")
    assert s["current"] == INITIAL
    with pytest.raises(ValueError):
        intake.apply_profile(p, s)
    intake.apply_profile(p, s, "append")
    assert INITIAL in p["profile"]["background"]["value"] and "別の内容" in p["profile"]["background"]["value"]


def test_ai_profile_candidate_is_marked_unconfirmed(p):
    run(p, "extract", [cand("案件情報", "月末集計に2日かかる", ask="課題")])
    s = intake.profile_suggestions(p)[0]
    assert s["field"] == "problem" and s["certainty"] == "未確認"
    intake.apply_profile(p, s)
    assert p["candidates"][0]["state"] == "採用"


# ---- 出力 ----
def scenario(p):
    p["profile"]["background"].update(value="Excelの勤怠集計を見直す")
    web = pj.add(p, "requirements", pj.new_requirement(title="Web打刻", body="従業員がWebで打刻できる", domain="app", kind="機能"))
    csv = pj.add(p, "requirements", pj.new_requirement(title="給与CSV連携", body="給与ソフトへCSVで連携する", domain="app", kind="連携", open_items="項目と形式は未確認"))
    ag.apply_decision(p, agreed(p, web)["id"], [web["id"]], "human")
    return web, csv


def test_precheck_counts_come_from_data(p):
    scenario(p)
    run(p, "extract", [cand("要点", "未処理の候補")])
    c = share.precheck(p)
    rows = {k: n for k, n, _ in c["rows"]}
    assert rows["合意済みの要件"] == 1 and rows["未合意の要件"] == 1 and rows["受入条件未設定の要件"] == 2 and rows["未処理のAI候補（文書には入りません）"] == 1
    assert c["missing_profile"] == ["目的"] and c["is_draft"] and len(c["targets"]) == 2


def test_spec_separates_agreed_and_excludes_pending_candidates(p):
    scenario(p)
    run(p, "extract", [cand("要望", "勤務形態の管理を入れたい")])
    secs = share.build(p, share.Options(doc_type="spec"))
    text = str([s.__dict__ for s in secs])
    assert "合意済み" in text and "下書き" in text and "勤務形態の管理" not in text and "（v1）" in text
    assert "分類未設定の要件" not in [s.heading for s in secs]
    assert "Excelの勤怠集計を見直す" in text


def test_unclassified_requirement_has_own_section(p):
    pj.add(p, "requirements", pj.new_requirement(title="未分類", body="B"))
    heads = [s.heading for s in share.build(p, share.Options(doc_type="spec"))]
    assert "分類未設定の要件" in heads and "その他の要件" not in heads


def test_scope_label_is_not_confused_with_agreement(p):
    pj.add(p, "requirements", pj.new_requirement(title="X", body="B"))
    text = str([s.table for s in share.build(p, share.Options(doc_type="spec")) if s.table])
    assert "未確定" in text


def test_reflecting_decision_is_recorded_in_history(p):
    a = req(p)
    d = agreed(p, a)
    ag.apply_decision(p, d["id"], [a["id"]], "human")
    h = p["history"][-1]
    assert h["requirement_id"] == a["id"] and h["decision_id"] == d["id"] and h["decider"] == "人事責任者"


def test_id_and_date_columns_keep_minimum_width():
    from definereq.export.wordx import MIN_WIDTH, fit_widths

    cols = ["ID", "論点", "判断日", "状態"]
    w = fit_widths(cols, [1, 8, 1, 1], 17.0)
    assert round(sum(w), 3) == 17.0 and w[0] >= MIN_WIDTH["ID"] and w[2] >= MIN_WIDTH["判断日"]


def test_scope_table_uses_clear_label(p):
    pj.add(p, "requirements", pj.new_requirement(title="X", body="B"))
    sec = next(s for s in share.build(p, share.Options(doc_type="spec")) if s.heading == "範囲・対象外")
    assert sec.table["rows"][0][0] == "未確定"


def test_word_opens_with_japanese(p):
    scenario(p)
    data = wordx.render(p, share.Options(doc_type="spec"), "DOC-001", 1, pj.now_iso())
    d = Document(io.BytesIO(data))
    assert "勤怠システムの更新" in "\n".join(x.text for x in d.paragraphs) and d.tables


# ---- 研修案件の指摘の再発防止 ----
def training():
    p = pj.new_project("社内研修の申込・受講管理（架空テスト）", ["app"])
    p["profile"]["scope_out"].update(value="給与計算、経費精算の承認は対象外")
    p["profile"]["problem"].update(value="メールで申込み、Excelで定員を管理している")
    return p


def test_registered_open_items_reach_word_and_excel():
    p = training()
    cs = run(p, "extract", [cand("未回答", "繰上げ回答期限24時間の起算点・休日扱い"), cand("不足情報", "認証方式、保存期間、性能条件、予算、開始日は未確認"),
                            cand("次の行動", "講師・事務局の権限範囲を確認する"), cand("要望", "CSVを出力する")])
    for c in cs[:3]:
        intake.apply(p, c["id"])
    intake.adopt_requirement(p, cs[3]["id"], {"kind": "連携", "open_items": "CSV項目は未確認"})
    data = wordx.render(p, share.Options(doc_type="spec"), "DOC-001", 1, pj.now_iso())
    d = Document(io.BytesIO(data))
    text = "\n".join(c.text for t in d.tables for row in t.rows for c in row.cells)
    for w in ("起算点", "認証方式", "権限範囲", "CSV項目は未確認"):
        assert w in text, w
    o = share.open_items(p)
    assert o["registered"] == 4 and len(o["included"]) == 4 and not o["excluded"]
    assert share.precheck(p)["open"]["registered"] == 4


def test_open_item_has_required_columns_and_keeps_unset():
    p = training()
    r = pj.add(p, "requirements", pj.new_requirement(title="T", body="B", open_items="CSV項目は未確認"))
    row = next(s for s in share.build(p, share.Options(doc_type="spec")) if s.heading == "未決事項").table
    assert row["columns"] == ["ID", "種別", "内容", "関連要件", "確認相手", "期限", "状態"]
    assert row["rows"][0] == [r["id"], "要件の未確認事項", "CSV項目は未確認", r["id"], "未設定", "未設定", "未確認"]


def test_excluded_requirement_item_is_reported_not_silently_dropped():
    p = training()
    r = pj.add(p, "requirements", pj.new_requirement(title="T", body="B", open_items="CSV項目は未確認"))
    o = share.open_items(p, share.Options(doc_type="spec", exclude_ids={r["id"]}))
    assert not o["included"] and o["excluded"][0]["reason"]


def test_same_content_is_merged_keeping_links():
    p = training()
    r = pj.add(p, "requirements", pj.new_requirement(title="T", body="B", open_items="CSV項目は未確認"))
    pj.add(p, "questions", {"text": "CSV項目は未確認", "why": None, "ask": "人事", "priority": None, "status": "未質問", "answer": None, "perspective_id": None, "category": "確認事項", "evidence": []})
    o = share.open_items(p)
    assert len(o["included"]) == 1 and o["merged"] == 1 and r["id"] in o["included"][0]["related"]


def test_internal_note_not_in_open_items():
    p = training()
    r = pj.add(p, "requirements", pj.new_requirement(title="T", body="B"))
    r["internal_note"] = "社外秘メモ"
    assert "社外秘メモ" not in str(share.open_items(p))


def test_owner_field_rejects_sentences_and_keeps_human_value():
    p = training()
    c = run(p, "extract", [cand("次の行動", "研修事務局が権限範囲を確認する", ask="期限を設定するか確認してください。")])[0]
    assert c["ask"] is None and intake.owner_of(c) == "研修事務局"
    intake.apply(p, c["id"], "山田", "2026-12-01", "利用者", None, "")
    a = p["actions"][0]
    assert a["owner"] == "山田" and a["due"] == "2026-12-01" and a["ask"] is None


def test_cleared_owner_stays_empty():
    p = training()
    c = run(p, "extract", [cand("次の行動", "研修事務局が確認する", owner="研修事務局")])[0]
    intake.apply(p, c["id"], "", "", "利用者", None, "")
    assert p["actions"][0]["owner"] is None and p["actions"][0]["due"] is None


def test_owner_stays_empty_when_unknown():
    assert intake.owner_of({"text": "権限範囲を確認する"}) is None


@pytest.mark.parametrize("value", ["期限を設定するか確認してください。", "確認してください", "x" * 30])
def test_person_name_rejects_text(value):
    assert ai.person_name(value) is None


def test_decision_candidate_new_requirement_keeps_links_and_no_agreement():
    p = training()
    src = registry.ingest_paste(p, "議事録", "本人のキャンセルは開始前日17時までとする", kind="議事録")
    c = run(p, "extract", [cand("決定", "本人のキャンセルは開始前日17時まで", evidence=[{"source_id": src["id"], "unit_id": "", "quote": "本人のキャンセルは開始前日17時まで"}])])[0]
    intake.apply(p, c["id"], new_requirement=True)
    r, d = p["requirements"][0], p["decisions"][0]
    assert r["status"] == "下書き" and r["from_candidate"] == c["id"] and r["evidence"][0]["verified"]
    assert d["state"] == "下書き" and d["related_requirements"] == [r["id"]]


def test_decision_candidate_link_existing_and_none():
    p = training()
    r = pj.add(p, "requirements", pj.new_requirement(title="T", body="B"))
    cs = run(p, "extract", [cand("決定", "既存に関連付ける"), cand("決定", "要件なしの判断")])
    intake.apply(p, cs[0]["id"], link_requirements=[r["id"]])
    intake.apply(p, cs[1]["id"])
    assert p["decisions"][0]["related_requirements"] == [r["id"]] and p["decisions"][1]["related_requirements"] == [] and len(p["requirements"]) == 1


def test_split_parts_classified_separately():
    p = training()
    c = run(p, "extract", [cand("要望", "講師が出欠を登録し、月別CSVを出力する", detail="CSV項目は未確認")])[0]
    parts = intake.split_details(p, c, intake.split_proposal(c["text"]))
    assert parts[0]["kind"] == "機能" and parts[1]["kind"] == "連携"
    assert parts[0]["open_items"] is None and parts[1]["open_items"] == "CSV項目は未確認"
    rs = intake.adopt_requirement(p, c["id"], parts=[{"text": x["text"], "kind": x["kind"], "open_items": x["open_items"]} for x in parts])
    assert [r["kind"] for r in rs] == ["機能", "連携"] and rs[0]["open_items"] is None


def test_out_of_scope_word_is_not_suggested_as_trait():
    from definereq.logic import checks

    p = training()
    assert "approval" not in checks.suggest_traits(p)
    p["profile"]["request"].update(value="上長の承認を画面で行いたい")
    assert "approval" in checks.suggest_traits(p)


def test_next_action_uses_minutes_not_question_count():
    p = training()
    registry.ingest_paste(p, "議事録", "初回の内容", kind="議事録")
    for page in ("sources", "candidates", "overview", "prep"):
        assert gd.assess(p, page)["main"].id == "extract", page
    assert gd.assess(p, "sources")["main"].alt == [("次回の質問を準備する", "prep")]
    run(p, "extract", [cand("要望", "申込したい")], source_ids=[p["sources"][0]["id"]])
    assert gd.assess(p, "sources")["main"].id == "candidates"


def test_after_adoption_goes_to_decision_and_refine():
    p = training()
    c = run(p, "extract", [cand("要望", "申込したい")])[0]
    intake.adopt_requirement(p, c["id"], {"kind": "機能"})
    main = gd.assess(p, "requirements")["main"]
    assert main.id == "decide_next" and ("受入条件を具体化する", "refine") in main.alt


def test_user_can_choose_stage_and_it_changes_next_action():
    p = training()
    registry.ingest_paste(p, "議事録", "初回の内容", kind="議事録")
    gd.guidance_store(p)["user_stage"] = "output"
    assert gd.assess(p, "overview")["main"].id == "export"


def test_spec_requirement_table_is_compact_with_details():
    p = training()
    long = "講師が研修の出欠を登録し、事務局が月別の一覧を確認できるようにするために必要な画面を用意する"
    pj.add(p, "requirements", pj.new_requirement(title=long, body=long, kind="機能", open_items="CSV項目は未確認"))
    secs = share.build(p, share.Options(doc_type="spec"))
    table = next(s for s in secs if "機能" in s.heading and s.table).table
    assert "内容" not in table["columns"] and "…" in table["rows"][0][3]
    detail = next(s for s in secs if s.level == 3)
    assert any("未確認事項：CSV項目は未確認" in x for x in detail.paragraphs) and any("受入条件：未設定" in x for x in detail.paragraphs)


def test_unregistered_is_not_shown_as_not_applicable():
    p = training()
    text = str([(s.heading, s.table.get("empty")) for s in share.build(p, share.Options(doc_type="spec")) if s.table])
    assert "受入条件はまだ登録されていません" in text and "シナリオはまだ登録されていません" in text


def test_answer_request_only_in_docs_with_answer_column():
    p = training()
    spec = Document(io.BytesIO(wordx.render(p, share.Options(doc_type="spec"), "DOC-001", 1, pj.now_iso())))
    meet = Document(io.BytesIO(wordx.render(p, share.Options(doc_type="meeting"), "DOC-002", 1, pj.now_iso())))
    assert "回答欄" not in "\n".join(x.text for x in spec.paragraphs)
    assert "回答欄" in "\n".join(x.text for x in meet.paragraphs)


def test_real_project_candidates_page_has_no_demo_wording():
    p = training()
    run(p, "extract", [cand("要望", "申込したい")])
    assert not any("準備済みのAI候補" in c.value for c in open_app(p, "candidates").caption)


def test_early_home_has_no_zero_stats_or_backlog(p):
    p["profile"]["problem"].update(value="月末の集計に時間がかかる")
    at = open_app(p)
    assert not at.exception and 'class="dr-stat"' not in html(at)
    assert not any(s.value == "残件" for s in at.subheader)
    assert any(s.value == "確認・依頼すること" for s in at.subheader)


def test_home_shows_stats_and_backlog_after_requirements(p):
    pj.add(p, "requirements", pj.new_requirement(title="T", body="B", scope="今回必須"))
    at = open_app(p)
    assert 'class="dr-stat"' in html(at) and any(s.value == "残件" for s in at.subheader)


@pytest.mark.parametrize("stage,page", [("before_first", "prep"), ("after_first", "records"), ("deciding", "requirements"), ("output", "share")])
def test_choosing_stage_moves_to_that_work(p, stage, page):
    p["profile"]["problem"].update(value="月末の集計に時間がかかる")
    at = open_app(p, "recordings")
    at = next(r for r in at.radio if r.key == "guide_stage").set_value(stage).run()
    assert not at.exception and at.session_state["page"] == page


def test_auto_stage_has_no_destination():
    assert None not in gd.STAGE_PAGES


def _word_minutes() -> bytes:
    d = Document()
    d.add_paragraph("初回打ち合わせ議事録")
    d.add_paragraph("講師が出欠を登録する。予算は未確認。")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _excel_minutes() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(["発言者", "内容"])
    wb.active.append(["事務局", "講師が出欠を登録する。予算は未確認。"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.parametrize("name,data", [("議事録.docx", _word_minutes()), ("議事録.xlsx", _excel_minutes()), ("議事録.txt", "講師が出欠を登録する。予算は未確認。".encode())])
def test_minutes_files_without_recording_can_be_analyzed(p, name, data):
    item = registry.ingest_bytes(p, name, data, kind="議事録", visibility="社内のみ")
    assert any("出欠を登録" in u["text"] for u in item["units"])
    assert gd.assess(p, "recordings")["main"].id == "extract"
    ctx = ai.build_context(p, ai.TASKS["extract"], [item["id"]], [])
    assert "出欠を登録" in ctx
    run(p, "extract", [cand("要望", "出欠を登録する", evidence=[{"source_id": item["id"], "unit_id": "", "quote": "講師が出欠を登録する"}])], source_ids=[item["id"]])
    assert p["candidates"][0]["evidence"][0]["verified"] and gd.assess(p, "sources")["main"].id == "candidates"


def test_after_meeting_work_is_on_one_screen(p):
    """取込み・AIの整理・候補の確認が同じ画面にある。"""
    p["profile"]["problem"].update(value="月末の集計に時間がかかる")
    at = open_app(p, "recordings")
    at = next(r for r in at.radio if r.key == "guide_stage").set_value("after_first").run()
    assert not at.exception and at.session_state["page"] == "records"
    # 記録が0件のときは、取り込みが最初の操作。「次回の質問を準備する」は補助の操作
    assert "会議の記録はまだありません" in html(at) and any(t.key == "records_paste_b" for t in at.text_area)
    assert key(at, "records_prep").label == "ほかの作業：次回の質問を準備する"


def test_records_page_paste_to_candidates_without_moving(p):
    at = open_app(p, "records")
    next(t for t in at.text_area if t.key == "records_paste_b").set_value("講師が出欠を登録する。")
    at = key(at, "records_paste_go").click().run()
    assert not at.exception and at.session_state["page"] == "records"
    q = at.session_state["project"]
    assert q["sources"][0]["kind"] == "議事録"
    assert gd.assess(q, "records")["main"].page == "records"
    assert not any(b.key == "guide_go" for b in at.button)  # 同じ画面なので移動のボタンを出さない
    run(q, "extract", [cand("要望", "出欠を登録する")], source_ids=[q["sources"][0]["id"]])
    at.run()
    assert "AI整理完了" in html(at) and key(at, "records_go_cand").label == "AI候補を確認する →"
    at = key(at, "records_go_cand").click().run()
    assert at.session_state["page"] == "candidates" and "要件に採用する内容を確認" in [b.label for b in at.button]


def test_recordings_page_accepts_minutes_files(p):
    at = open_app(p, "recordings")
    assert not at.exception and any(b.key == "rec_paste_go" for b in at.button)
    assert not any("字幕ファイル" in str(x.label) for x in at.text_input)


@pytest.mark.parametrize("stage,want", [("before_first", "next_input"), ("after_first", "meeting_missing"), ("deciding", "stage_require"), ("output", "export")])
def test_every_stage_has_next_action(p, stage, want):
    p["profile"]["problem"].update(value="月末の集計に時間がかかる")
    gd.guidance_store(p)["user_stage"] = stage
    assert gd.assess(p, "overview")["main"].id == want


def test_deciding_stage_with_requirements_points_to_them(p):
    pj.add(p, "requirements", pj.new_requirement(title="T", body="B", status="合意済み", kind="機能", acceptance=[{"given": "a", "when": "b", "then": "c", "how": "d"}], scope="今回必須"))
    gd.guidance_store(p)["user_stage"] = "deciding"
    assert gd.assess(p, "overview")["main"].id == "stage_refine"


def test_profile_page_has_back_and_go(p):
    at = open_app(p, "profile")
    labels = [b.label for b in at.button]
    assert "案件情報を保存" in labels and "保存して資料・議事録へ進む" in labels and "← 準備の概要に戻る" in labels and "資料・議事録へ" in labels
    assert "準備の概要を開く" not in labels and labels.count("← 準備の概要に戻る") == 1  # 準備へ戻る操作は見出し付近の1か所だけ
    assert any("この欄の入力を案件に反映します" in c.value for c in at.caption)


def test_profile_shows_heading_and_inputs_before_guidance(p):
    """見出し→短い案内→入力欄の順。詳しい案内・作業の段階・AIの補足は入力欄より下に置く。"""
    at = open_app(p, "profile")
    text = html(at)
    assert 'class="dr-brief"' not in text and 'class="dr-sit dr-sit-work"' not in text  # 編集中は上部に別工程の案内を出さない
    order = [e for e in at.main if getattr(e, "type", "") in ("text_area", "expander")]
    first_input = next(i for i, e in enumerate(order) if e.type == "text_area")
    labels = [getattr(e, "label", "") for e in order]
    stage = next(i for i, x in enumerate(labels) if str(x).startswith("作業の段階を選び直す"))
    assert first_input < stage
    assert any(str(x).startswith("対象分野と特徴を変更する") for x in labels)  # 分野の変更は補助の操作として折りたたむ


def test_sources_shows_import_first(p):
    at = open_app(p, "sources")
    assert "dr-brief" in html(at) and 'class="dr-sit dr-sit-work"' not in html(at)
    labels = [b.label for b in at.button]
    assert labels.count("← 準備の概要に戻る") == 1 and "背景・目的・関係者を入力" in labels
    assert next(r for r in at.radio if r.key == "src_mode").value == "議事録を取り込む"
    assert "登録する種類<b>議事録</b>" in html(at)


def paste(at, text, title="議事録"):
    next(t for t in at.text_input if t.key.startswith("paste_t_")).set_value(title)
    next(t for t in at.text_area if t.key.startswith("paste_b_")).set_value(text)
    return key(at, "paste_go").click().run()


def test_minutes_mode_registers_minutes_for_ai(p):
    at = paste(open_app(p, "sources"), "講師が出欠を登録する。", "初回の議事録")
    q = at.session_state["project"]
    assert q["sources"][0]["kind"] == "議事録" and gd.unanalyzed_minutes(q) == ["初回の議事録"]
    assert any(s.value == "議事録1件を登録しました" for s in at.success)
    assert at.session_state["src_done"]  # 登録直後は追加のフォームを閉じる（画面では見えなくする）
    at = key(at, "src_more").click().run()
    assert "src_done" not in at.session_state
    assert next(t for t in at.text_area if t.key.startswith("paste_b_")).value == ""  # 二重登録を防ぐため空にする


def test_other_mode_registers_chosen_kind_and_keeps_text(p):
    at = open_app(p, "sources")
    next(t for t in at.text_area if t.key.startswith("paste_b_")).set_value("申込の手順")
    at = next(r for r in at.radio if r.key == "src_mode").set_value("その他の資料を取り込む").run()
    assert next(t for t in at.text_area if t.key.startswith("paste_b_")).value == "申込の手順"  # 種類を切り替えても入力は残る
    at = next(s for s in at.selectbox if s.key == "src_kind").set_value("手順").run()
    assert "登録する種類<b>手順</b>" in html(at) and "議事録" not in next(s for s in at.selectbox if s.key == "src_kind").options
    at = next(r for r in at.radio if r.key == "src_mode").set_value("議事録を取り込む").run()
    at = next(r for r in at.radio if r.key == "src_mode").set_value("その他の資料を取り込む").run()
    at = next(s for s in at.selectbox if s.key == "src_kind").set_value("手順").run()
    at = key(at, "paste_go").click().run()
    q = at.session_state["project"]
    assert q["sources"][0]["kind"] == "手順" and gd.unanalyzed_minutes(q) == []


def test_empty_paste_shows_reason(p):
    at = key(open_app(p, "sources"), "paste_go").click().run()
    assert not at.session_state["project"]["sources"] and any("貼り付ける文章を入力" in e.value for e in at.error)


def test_profile_save_message_is_near_and_does_not_add_people(p):
    at = open_app(p, "profile")
    next(t for t in at.text_area if t.key == bg_key(p, "v_background")).set_value("背景").run()
    next(t for t in at.text_input if t.key == bg_key(p, "stk_name")).set_value("未追加の人").run()
    at = key(at, "pf_save").click().run()
    q = at.session_state["project"]
    assert q["profile"]["background"]["value"] == "背景" and q["stakeholders"] == []
    msgs = [s.value for s in at.success]
    assert any(m.startswith("案件情報を保存しました") for m in msgs) and not any("関係者" in m for m in msgs)
    assert next(t for t in at.text_input if t.key == bg_key(p, "stk_name")).value == "未追加の人"


def test_stakeholder_and_term_need_their_own_add(p):
    at = open_app(p, "profile")
    at = key(at, "pf_add_stk").click().run()
    assert any("氏名・役割" in e.value for e in at.error)
    next(t for t in at.text_input if t.key == bg_key(p, "term_term")).set_value("受講枠").run()
    at = key(at, "pf_add_term").click().run()
    assert at.session_state["project"]["glossary"][0]["term"] == "受講枠" and any("用語「受講枠」を追加しました" in s.value for s in at.success)
    caps = [c.value for c in at.caption]
    assert any("「関係者を追加」を押すと、入力した1件" in c for c in caps) and any("「用語を追加」を押すと、入力した1件" in c for c in caps)


def test_save_failure_keeps_input_and_returns_reason(p):
    from definereq.ui.pages import prepare

    class Broken(dict):
        def update(self, *a, **k):
            raise RuntimeError("壊れた")

    p["profile"] = Broken(p["profile"])
    new = {k: {"value": "x", "certainty": "未確認"} for k in pj.PROFILE_FIELDS}
    assert prepare._save_profile(p, new)  # 理由を返し、例外で画面を止めない


def test_setup_resume_note_once_and_quiet(p):
    at = open_app(p, "setup")
    text = html(at)
    assert text.count("元のWord・PDFファイルは含まれません") == 1 and "再開用ファイルは、ブラウザーを閉じた後に案件を復元する" in text
    side = [c.value for c in at.sidebar.caption]
    assert not any("元のWord" in c for c in side)
    assert [b.key for b in at.get("download_button")].count("save_setup") == 1


# ---- JSON ----
def test_old_json_without_new_fields_loads(p):
    raw = json.loads(jsonio.dumps(p))
    raw["profile"].pop("users")
    q = jsonio.loads(json.dumps(raw).encode())
    assert q["profile"]["users"]["value"] is None and gd.phase(q) == "empty"


def test_round_trip_keeps_routes_and_versions(p):
    a = req(p)
    agreed(p, a)
    c = run(p, "prep", [cand("質問", "Q")])[0]
    intake.apply(p, c["id"])
    q = jsonio.loads(jsonio.dumps(p))
    assert q["decisions"][0]["target_versions"] == {a["id"]: 1} and q["questions"][0]["from_candidate"] == c["id"]


# ---- 画面 ----
def open_app(p, page="overview"):
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["project"] = p
    at.session_state["page"] = page
    return at.run()


def html(at):
    return "".join(h.proto.body for h in at.get("html"))


def key(at, k):
    return next(b for b in at.button if b.key == k)


def test_new_project_shows_setup_without_zero_stats(p):
    at = open_app(p, "setup")
    text = html(at)
    assert "案件の準備" in text and "どちらからでも始められます" in text and 'class="dr-stat"' not in text and "基準版なし" not in text
    assert key(at, "setup_profile").label == "背景・目的・関係者を入力" and key(at, "setup_sources").label == "資料・議事録を取り込む"
    assert "未入力" in text and "未取り込み" in text and not at.exception


def test_empty_overview_shows_setup(p):
    assert "どちらからでも始められます" in html(open_app(p, "overview"))


def test_setup_keeps_both_items_after_progress(p):
    p["profile"]["problem"].update(value="申込をメールで受けている")
    registry.ingest_paste(p, "議事録", "本文", kind="議事録")
    registry.ingest_paste(p, "資料", "本文2", kind="要望")
    at = open_app(p, "setup")
    text = html(at)
    assert "入力済み" in text and "取り込み済み 2件" in text
    assert key(at, "setup_profile").label == "背景・目的・関係者を編集" and key(at, "setup_sources").label == "資料・議事録を取り込む"


def test_start_from_records(p):
    at = key(open_app(p, "setup"), "setup_sources").click().run()
    assert at.session_state["page"] == "sources"
    at = key(at, "go_profile_top").click().run()
    assert at.session_state["page"] == "profile"
    at = key(at, "go_setup_top").click().run()
    assert at.session_state["page"] == "setup"


def bg_key(p, name):
    return f"draft_{p['id']}_{name}"


def test_draft_survives_navigation_and_shows_unsaved(p):
    at = open_app(p, "profile")
    next(t for t in at.text_area if t.key == bg_key(p, "v_background")).set_value("Excelで集計している").run()
    at = key(at, "go_setup_top").click().run()
    assert at.session_state["page"] == "setup" and "未保存の変更あり" in html(at)
    at.session_state["page"] = "requirements"  # 左メニューでほかの画面へ移る
    at.run()
    at.session_state["page"] = "profile"
    at.run()
    assert next(t for t in at.text_area if t.key == bg_key(p, "v_background")).value == "Excelで集計している"
    assert at.session_state["project"]["profile"]["background"]["value"] is None  # 保存までは案件を変えない


def test_save_and_save_go(p):
    at = open_app(p, "profile")
    next(t for t in at.text_area if t.key == bg_key(p, "v_background")).set_value("背景の文").run()
    at = key(at, "pf_save").click().run()
    q = at.session_state["project"]
    assert q["profile"]["background"]["value"] == "背景の文" and at.session_state["page"] == "profile"
    assert any(s.value.startswith("案件情報を保存しました") for s in at.success)
    next(t for t in at.text_area if t.key == bg_key(p, "v_purpose")).set_value("目的の文").run()
    at = key(at, "pf_save_go").click().run()
    assert at.session_state["page"] == "sources" and at.session_state["project"]["profile"]["purpose"]["value"] == "目的の文"
    assert any("案件情報を保存しました" in s.value for s in at.success)  # 移動先で保存したことが分かる
    at.session_state["page"] = "setup"
    at.run()
    assert "入力済み" in html(at) and "未保存の変更あり" not in html(at)


def test_drafts_are_kept_per_project():
    from definereq.ui import drafts

    a, b = pj.new_project("案件A", ["app"]), pj.new_project("案件B", ["app"])
    at = open_app(a, "profile")
    next(t for t in at.text_area if t.key == bg_key(a, "v_background")).set_value("Aの下書き").run()
    at.session_state["project"] = b
    at.run()
    assert next(t for t in at.text_area if t.key == bg_key(b, "v_background")).value == ""
    assert "Aの下書き" not in str(at.session_state["drafts"].get(b["id"], {}))


def test_stakeholder_draft_survives_navigation(p):
    at = open_app(p, "profile")
    next(t for t in at.text_input if t.key == bg_key(p, "stk_name")).set_value("架空の責任者").run()
    at.session_state["page"] = "setup"
    at.run()
    assert "未保存の変更あり" in html(at)
    at.session_state["page"] = "profile"
    at.run()
    assert next(t for t in at.text_input if t.key == bg_key(p, "stk_name")).value == "架空の責任者"
    at = key(at, "pf_add_stk").click().run()
    assert at.session_state["project"]["stakeholders"][0]["name"] == "架空の責任者"
    assert next(t for t in at.text_input if t.key == bg_key(p, "stk_name")).value == ""


def test_imported_records_survive_round_trip_and_status(p):
    registry.ingest_paste(p, "議事録", "講師が出欠を登録する。", kind="議事録")
    p["profile"]["purpose"].update(value="目的")
    q = jsonio.loads(jsonio.dumps(p))
    at = open_app(q, "setup")
    assert "取り込み済み 1件" in html(at) and "入力済み" in html(at)
    assert q["sources"][0]["units"][0]["text"].startswith("講師が出欠")


def test_new_project_opens_setup_and_loaded_opens_overview():
    import inspect

    from definereq.ui import state

    src = inspect.getsource(state.open_project)
    assert 'p.pop("last_page", None) if loaded' in src and 'else "setup"' in src  # 再開は保存時の画面へ。なければ案件の準備


def test_home_has_separate_entrances():
    at = AppTest.from_file(APP, default_timeout=60).run()
    text = html(at)
    assert 'href="#dr-new-create"' in text and 'href="#dr-resume"' in text and 'id="dr-new"' in text
    assert 'id="dr-new-create"' in text and 'id="dr-resume"' in text
    caps = [c.value for c in at.caption]
    common = "AIパスワードを入力し、Enterキーで確定すると、案件の作成・再開ができます。"
    assert sum(common in c for c in caps) == 1  # 共通の案内は一度だけ
    assert 'class="dr-home-h">新しい案件を始める' in text and 'class="dr-home-h">保存した案件から再開する' in text
    assert any("案件名と対象分野" in c for c in caps) and any("案件JSON" in c for c in caps)  # 各欄の固有の説明


def test_carryover_hidden_on_first_use(p):
    at = open_app(p, "prep")
    assert not any("前回からの引き継ぎ" in s.value for s in at.subheader)


def test_prep_candidates_are_shown_on_prep_page_with_matching_button(p):
    run(p, "prep", [cand("質問", "利用人数は？"), cand("議題", "打刻方法")])
    at = open_app(p, "prep")
    assert not at.exception
    labels = [b.label for b in at.button]
    assert "会議の質問に追加" in labels and "議題に追加" in labels and "振り分けて採用" not in labels
    at = next(b for b in at.button if b.label == "会議の質問に追加").click().run()
    assert at.session_state["project"]["questions"] and not at.session_state["project"]["requirements"]


def test_no_evidence_warning_only_for_claims(p):
    run(p, "prep", [cand("質問", "利用人数は？")])
    assert "根拠なし" not in html(open_app(p, "prep"))
    run(p, "extract", [cand("要望", "打刻したい")])
    assert "根拠なし" in html(open_app(p, "candidates"))


def test_question_candidate_has_no_new_requirement_option(p):
    run(p, "extract", [cand("質問", "Q")])
    at = open_app(p, "candidates")
    assert not at.exception and "要件候補として採用" not in [b.label for b in at.button]


def test_reflect_prompt_after_agreement_and_manual_choice(p):
    a = req(p, "Web打刻")
    d = agreed(p, a)
    at = open_app(p, "decisions")
    assert not at.exception and d
    assert any("判断を合意済みとして記録しました" in m.value for m in at.markdown)
    assert key(at, f"rf_go_{d['id']}").disabled
    at = next(c for c in at.checkbox if c.label == "この要件に反映する").check().run()
    at = key(at, f"rf_go_{d['id']}").click().run()
    assert not at.exception and at.session_state["project"]["requirements"][0]["status"] == "合意済み"


def test_requirement_label_has_no_status_and_chips_are_named(p):
    from definereq.ui.pages.organize import _req_label

    r = req(p, "Web打刻")
    assert "下書き" not in _req_label(r)
    assert "対象範囲：未確定" in html(open_app(p, "requirements")) and "合意状態：下書き" in html(open_app(p, "requirements"))


def test_scroll_frame_stays_in_place_between_reruns(p):
    """枠の有無で部品の位置がずれると、開いているタブが閉じる。"""
    run(p, "prep", [cand("質問", "Q")])
    at = open_app(p, "requirements")
    first = len(at.get("iframe"))
    at.run()
    assert first == len(at.get("iframe")) == 1


def test_precheck_on_share_page(p):
    scenario(p)
    at = open_app(p, "share")
    assert not at.exception
    next(r for r in at.radio if r.key == "sh_type").set_value("spec").run()
    assert any("出力前確認" in m.value for m in at.markdown) and key(at, "share_word").label == "下書きとしてWordを作成する"
    at = key(at, "share_word").click().run()
    assert not at.exception and any("要件定義書を作成しました" in s.value for s in at.success)


# ---- 案件の準備の「次にすること」と、資料の登録直後の案内 ----
def test_setup_next_follows_project_state(p):
    assert gd.setup_next(p)["page"] == "sources"  # 何もない
    p["profile"]["background"].update(value="背景")
    assert (gd.setup_next(p)["label"], gd.setup_next(p)["page"]) == ("会議の準備へ進む", "prep")
    registry.ingest_paste(p, "要望書", "申込を一覧で見たい", kind="要望")
    assert gd.setup_next(p)["page"] == "prep"  # 議事録ではない資料だけ
    m = registry.ingest_paste(p, "第1回議事録", "講師が出欠を登録する。", kind="議事録")
    nx = gd.setup_next(p)
    assert (nx["label"], nx["page"]) == ("会議の記録を整理する", "records") and "第1回議事録" in nx["detail"]
    run(p, "extract", [cand("要望", "出欠を登録する")], source_ids=[m["id"]])
    assert (gd.setup_next(p)["label"], gd.setup_next(p)["page"]) == ("AI候補を確認する", "candidates")
    registry.ingest_paste(p, "第2回議事録", "定員は30名。", kind="議事録")
    nx = gd.setup_next(p)  # 未整理の議事録が増えたら、記録の整理を先に勧め、候補の確認はほかの作業に出す
    assert nx["page"] == "records" and ("AI候補を確認する", "candidates") in nx["alts"]


def test_setup_next_without_profile_goes_to_records(p):
    registry.ingest_paste(p, "議事録", "本文", kind="議事録")
    assert gd.setup_next(p)["page"] == "records"


def test_setup_page_next_button_opens_work_screen(p):
    p["profile"]["background"].update(value="背景")
    registry.ingest_paste(p, "議事録", "講師が出欠を登録する。", kind="議事録")
    at = open_app(p, "setup")
    assert key(at, "setup_next_go").label == "会議の記録を整理する →"
    text = html(at)
    assert text.index("背景・目的・関係者") < text.index("次にすること") < text.index("続きの作業に備える")
    at = key(at, "setup_next_go").click().run()
    assert at.session_state["page"] == "records" and not at.exception


def test_after_register_shows_next_near_success(p):
    at = paste(open_app(p, "sources"), "講師が出欠を登録する。", "第1回議事録")
    assert any(s.value == "議事録1件を登録しました" for s in at.success)
    assert key(at, "src_next_go").label == "会議の記録を整理する →" and key(at, "src_more").label == "続けて資料を追加する"
    assert not at.session_state.get("flash")
    at = key(at, "src_next_go").click().run()
    assert at.session_state["page"] == "records" and "src_done" not in at.session_state


def test_after_register_other_material_suggests_prep(p):
    at = open_app(p, "sources")
    at = next(r for r in at.radio if r.key == "src_mode").set_value("その他の資料を取り込む").run()
    at = paste(at, "申込を一覧で見たい", "要望書")
    assert key(at, "src_next_go").label == "会議の準備へ進む →"
    at = key(at, "src_more").click().run()
    assert not any(b.key == "src_next_go" for b in at.button)


def test_no_next_panel_without_registration(p):
    at = key(open_app(p, "sources"), "paste_go").click().run()  # 空のまま押す（失敗）
    assert not any(b.key == "src_next_go" for b in at.button)


def test_work_pages_have_back_to_setup(p):
    p["profile"]["background"].update(value="背景")
    for page in ("prep", "records", "requirements", "overview"):
        at = open_app(p, page)
        back = next(b for b in at.button if b.label == "← 準備の概要に戻る")
        at = back.click().run()
        assert at.session_state["page"] == "setup", page


def test_resumed_project_gets_matching_next(p):
    registry.ingest_paste(p, "議事録", "講師が出欠を登録する。", kind="議事録")
    q = jsonio.loads(jsonio.dumps(p))
    assert key(open_app(q, "setup"), "setup_next_go").label == "会議の記録を整理する →"


# ---- 記録の整理の初期表示、準備画面の開始、背景の保存後 ----
def test_records_with_unanalyzed_minutes_shows_target_and_run_first(p):
    m = registry.ingest_paste(p, "第1回打ち合わせ議事録", "講師が出欠を登録する。", kind="議事録")
    registry.ingest_paste(p, "要望書", "申込を一覧で見たい", kind="要望")
    at = open_app(p, "records")
    text = html(at)
    assert "未整理の議事録 1件" in text and "第1回打ち合わせ議事録" in text
    assert next(s for s in at.multiselect if s.key == "ai_src_extract").value == [m["id"]]  # 登録した議事録を選んだ状態
    assert key(at, "ai_go_extract").label == "選択した議事録をAIで整理する"
    labels = [e.label for e in at.expander]
    assert "議事録・録画を追加する" in labels  # 登録済みのときは、取り込みを閉じた欄にまとめる
    assert not at.session_state["project"]["ai_runs"]  # 画面を開いただけではAIを実行しない
    assert key(at, "records_prep").label.startswith("ほかの作業")


def test_records_after_extract_shows_zero_and_candidates(p):
    m = registry.ingest_paste(p, "議事録", "講師が出欠を登録する。", kind="議事録")
    run(p, "extract", [cand("要望", "出欠を登録する")], source_ids=[m["id"]])
    at = open_app(p, "records")
    assert "AI整理完了" in html(at) and "確認待ち1件" in html(at)
    assert key(at, "records_go_cand").label == "AI候補を確認する →"


def test_empty_setup_uses_cards_as_start(p):
    at = open_app(p, "setup")
    assert not any(b.key == "setup_next_go" for b in at.button) and 'class="dr-next"' not in html(at)


def test_profile_after_save_points_to_next(p):
    at = open_app(p, "profile")
    assert key(at, "pf_save_go").label == "保存して資料・議事録へ進む"
    next(t for t in at.text_area if t.key == bg_key(p, "v_background")).set_value("背景").run()
    at = key(at, "pf_save").click().run()
    assert key(at, "pf_next_go").label == "次へ：資料・議事録を取り込む →"
    registry.ingest_paste(at.session_state["project"], "議事録", "本文", kind="議事録")
    at.run()
    assert key(at, "pf_save_go").label == "保存して会議の記録を整理へ進む" and key(at, "pf_next_go").label == "次へ：会議の記録を整理する →"
    at = key(at, "pf_next_go").click().run()
    assert at.session_state["page"] == "records"


def test_profile_save_go_follows_project_state(p):
    registry.ingest_paste(p, "議事録", "本文", kind="議事録")
    at = open_app(p, "profile")
    next(t for t in at.text_area if t.key == bg_key(p, "v_purpose")).set_value("目的の最新").run()
    at = key(at, "pf_save_go").click().run()
    assert at.session_state["page"] == "records" and at.session_state["project"]["profile"]["purpose"]["value"] == "目的の最新"


# ---- 全ページの次の操作、候補の確認と採用、背景の任意項目、再開 ----
def reviewed(p):
    """レビュー用JSONと同じ状態：候補7件のうち1件を要件に採用、6件が確認待ち。"""
    m = registry.ingest_paste(p, "第1回打ち合わせ議事録", "容器と配膳先のコードを照合する。", kind="議事録")
    items = [cand("要望", "容器と配膳先のコードを読み取り照合する"), cand("要望", "変更の確認時刻を記録する"), cand("決定", "第1期は照合と履歴の閲覧のみ"),
             cand("保留", "通信障害時の扱い"), cand("保留", "照合記録の保存期間"), cand("未回答", "当日変更が第1期に含まれるか"), cand("次の行動", "次回会議で保存期間を確認する")]
    cs = run(p, "extract", items, source_ids=[m["id"]])
    intake.adopt_requirement(p, cs[0]["id"])
    return p


def test_candidate_status_follows_adoption(p):
    reviewed(p)
    at = open_app(p, "candidates")
    assert "AI整理完了" in html(at) and "確認待ち6件 · 要件に採用 1件" in html(at)
    assert key(at, "cand_go_list").label == "未確認の候補を確認する ↓"
    assert "採用済み" in html(at)  # 採用した候補にも表示する
    labels = [e.label for e in at.expander]
    assert any("要望" in x and "確定すると：要件一覧（下書き）" in x for x in labels)
    assert any("決定" in x and "判断記録の下書き" in x for x in labels) and any("保留" in x and "確認事項" in x for x in labels)
    # 1件を確認欄で採用（確認と確定は別の操作）
    at = next(b for b in at.button if b.label == "要件に採用する内容を確認").click().run()
    at = next(b for b in at.button if b.label == "この内容で採用").click().run()
    assert "確認待ち5件 · 要件に採用 2件" in html(at) and len(at.session_state["project"]["requirements"]) == 2
    assert not any(b.label == "この内容で採用" for b in at.button)  # 確定後は確認欄を閉じ、同じ候補を再び採用できない


def test_candidates_zero_waiting_points_to_requirements(p):
    reviewed(p)
    for c in p["candidates"]:
        if c["state"] == "候補":
            c["state"] = "却下"
    at = open_app(p, "candidates")
    assert "確認待ち0件" in html(at) and key(at, "cand_go_reqs").label == "採用した要件を確認する →"
    at = key(at, "cand_go_reqs").click().run()
    assert at.session_state["page"] == "requirements"


def test_double_adoption_is_rejected(p):
    reviewed(p)
    done = next(c for c in p["candidates"] if c["state"] == "採用")
    with pytest.raises(ValueError):
        intake.adopt_requirement(p, done["id"])
    assert len(p["requirements"]) == 1


def test_profile_optional_fields_fold_and_keep_values(p):
    p["profile"]["budget"].update(value="未定（架空）")
    at = open_app(p, "profile")
    assert any(e.label.startswith("案件情報を詳しく入力") and "入力済み1項目" in e.label for e in at.expander)
    areas = [t.key for t in at.text_area if t.key.startswith(f"draft_{p['id']}_v_")]
    assert areas[:3] == [bg_key(p, "v_background"), bg_key(p, "v_purpose"), bg_key(p, "v_problem")]  # 背景・目的・課題を先に
    next(t for t in at.text_area if t.key == bg_key(p, "v_timeline")).set_value("来年4月").run()
    at = key(at, "pf_save").click().run()
    q = at.session_state["project"]
    assert q["profile"]["timeline"]["value"] == "来年4月" and q["profile"]["budget"]["value"] == "未定（架空）"


def test_resume_shows_one_line_and_next(p):
    reviewed(p)
    q = jsonio.loads(jsonio.dumps(p))
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["project"], at.session_state["page"], at.session_state["resumed"] = q, "setup", True
    at.run()
    assert "案件を再開しました" in html(at) and "AI候補が6件確認待ちです" in html(at)
    assert key(at, "setup_next_go").label == "AI候補を確認する →"
    at.session_state["page"] = "overview"
    at.run()
    assert key(at, "guide_go").label == "AI候補を確認する →" and "保存した案件を再開しました" not in html(at)


def test_resume_file_records_last_page(p):
    q = jsonio.loads(jsonio.dumps({**p, "last_page": "candidates"}))
    assert q["last_page"] == "candidates"
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["project"], at.session_state["page"] = pj.new_project("t", ["app"]), "zzz"  # 無効な画面は案件の準備で開く
    at.run()
    assert not at.exception and "準備の概要" in html(at)


def test_every_project_page_has_next_or_back_in_body(p):
    """全ページの遷移：本文に、次の操作（主ボタン）か、この画面で作業する表示と戻る操作がある。"""
    from definereq.ui.shell import PAGES

    reviewed(p)
    p["profile"]["background"].update(value="背景")
    for page in PAGES:
        at = open_app(p, page)
        assert not at.exception, page
        keys = {b.key for b in at.button}
        body = html(at) + "".join(c.value for c in at.caption)
        assert keys & {"guide_go", "setup_next_go", "pf_save", "src_read", "paste_go", "ai_go_extract", "records_go_cand", "cand_go_list", "cand_go_reqs", "cand_go_overview"} \
            or "この画面で作業します" in body, page
        if page not in ("setup", "profile", "sources"):
            assert any(b.label == "← 準備の概要に戻る" for b in at.button), page


def test_every_demo_detail_page_returns_to_step():
    """デモのステップから、サイドバーの全工程・全機能を開いても、本文に元のステップへ戻る操作がある。"""
    at = AppTest.from_file(APP, default_timeout=60).run()
    at = next(b for b in at.button if b.key == "tour_d1_hl").click().run()
    opened = set()
    for n in range(5):
        at = next(b for b in at.sidebar.button if b.key == f"nav_group_{n}").click().run()
        for b in [b for b in at.sidebar.button if b.key.startswith("nav_") and b.key[4:] in PAGES_KEYS()]:
            at = next(x for x in at.sidebar.button if x.key == b.key).click().run()
            assert not at.exception and at.session_state["tour_on"] is False, b.key
            assert next(x for x in at.button if x.key == "tour_back").label == "← デモステップ 5/8『判断』に戻る", b.key
            opened.add(b.key[4:])
    assert len(opened) >= 15  # 詳細メニュー以外の機能をすべて開いた
    at = next(x for x in at.button if x.key == "tour_back").click().run()
    assert at.session_state["tour_on"] and at.session_state["tour_index"] == 4


def PAGES_KEYS():
    from definereq.ui.shell import PAGES

    return set(PAGES)


# ---- 主ボタン（オレンジ）は、その状態で進める操作を1つだけ ----
def primaries(at):
    """本文の主ボタン（サイドバーの選択表示を除く）。タブで切り替わる登録ボタンは、表示中のタブの1つとして数える。"""
    # 押せるオレンジのボタン（押せない主ボタンは点線の枠で表示されるため数えない。サイドバーの選択表示も数えない）
    labels = [b.label for b in at.main.button if b.proto.type == "primary" and not b.disabled]
    labels += [b.label for b in at.get("download_button") if b.proto.type == "primary"]
    if {"読み込む", "貼り付けた文章を案件内に登録"} <= set(labels):
        labels.remove("貼り付けた文章を案件内に登録")
    return labels


def test_one_primary_per_page_in_each_state(p):
    from definereq.ui.shell import PAGES

    reviewed(p)
    p["profile"]["background"].update(value="背景")
    for page in PAGES:
        found = primaries(open_app(p, page))
        assert len(found) <= 1, (page, found)


def test_primary_follows_the_state(p):
    at = open_app(p, "profile")
    assert primaries(at) == ["案件情報を保存"]  # 編集中は保存
    next(t for t in at.text_area if t.key == bg_key(p, "v_background")).set_value("背景").run()
    at = key(at, "pf_save").click().run()
    assert primaries(at) == ["次へ：資料・議事録を取り込む →"]  # 保存した直後は次の工程
    q = at.session_state["project"]
    registry.ingest_paste(q, "議事録", "講師が出欠を登録する。", kind="議事録")
    at = open_app(q, "records")  # テストではAIのキーがないため押せない。主ボタン（押せるとオレンジ）であることを確かめる
    assert key(at, "ai_go_extract").proto.type == "primary" and primaries(at) == []
    run(q, "extract", [cand("要望", "出欠を登録する")], source_ids=[q["sources"][0]["id"]])
    assert primaries(open_app(q, "records")) == ["AI候補を確認する →"]
    at = open_app(q, "candidates")
    assert primaries(at) == ["未確認の候補を確認する ↓"]
    at = next(b for b in at.button if b.label == "要件に採用する内容を確認").click().run()
    assert primaries(at) == ["この内容で採用"]  # 開いた候補の確定ボタンを強調する


def test_home_primary_is_only_demo_start():
    """トップで押せるオレンジはデモ開始のボタン。「案件を作成」はパスワードが確定するまで押せない（点線の枠）。"""
    at = AppTest.from_file(APP, default_timeout=60).run()
    enabled = [b.label for b in at.main.button if b.proto.type == "primary" and not b.disabled]
    assert sorted(enabled) == sorted(["経費申請のデモを見る", "売上集計・クラウド移行のデモを見る", "ネットワーク更新のデモを見る"])
    assert next(b for b in at.main.button if b.key == "create_project").proto.type == "primary" and next(b for b in at.main.button if b.key == "create_project").disabled
    assert 'class="dr-btn dr-btn-p" href="#dr-demo">案内付きでデモを見る' in html(at)


def test_demo_steps_have_one_primary():
    at = AppTest.from_file(APP, default_timeout=60).run()
    at = next(b for b in at.button if b.key == "tour_d1").click().run()
    for n in range(8):
        at = next(b for b in at.button if b.key == f"tour_go_{n}").click().run() if n else at
        found = primaries(at)
        assert len(found) == 1, (n, found)
    assert found == ["要件定義書の内容を見る"]  # 終了画面は成果物の確認を主操作にする


def test_project_requirements_states_and_links(p):
    at = open_app(p, "requirements")
    assert "要件はまだ登録されていません" in "".join(i.value for i in at.info) and f"{p['name']}の要件一覧" in html(at)
    reviewed(p)
    assert key(open_app(p, "requirements"), "guide_go").label == "AI候補を確認する →"
    for c in p["candidates"]:
        if c["state"] == "候補":
            c["state"] = "却下"
    at = open_app(p, "overview")
    if key(at, "guide_go").label == "確認待ちの要件を見る →":
        at = key(at, "guide_go").click().run()
        assert at.session_state["page"] == "requirements" and "合意待ちの要件" in html(at)
    at = open_app(p, "profile")
    assert key(at, "pf_save_go").label.startswith("保存して") and key(at, "pf_save_go").label.endswith("へ進む")


def test_project_action_links_to_related_requirement(p):
    reviewed(p)
    r = p["requirements"][0]
    pj.add(p, "actions", {"content": "照合の手順を現場に確認する", "owner": None, "due": None, "related": [r["id"]], "state": "未着手"})
    at = open_app(p, "overview")
    link = next(b for b in at.button if b.key and b.key.startswith("todo_req_"))
    at = link.click().run()
    assert at.session_state["page"] == "requirements" and at.session_state["rq_sel"] == r["id"] and "照合の手順を現場に確認する" in html(at)
    at = key(at, "req_back").click().run()
    assert at.session_state["page"] == "overview"


def test_resumed_project_next_matches_state(p):
    reviewed(p)
    q = jsonio.loads(jsonio.dumps({**p, "last_page": "overview"}))
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["project"], at.session_state["page"], at.session_state["resumed"] = q, q.pop("last_page"), True
    at.run()
    assert key(at, "guide_go").label == "AI候補を確認する →" and "行き先：要件の確認・判断 › AI候補の確認" in "".join(c.value for c in at.caption)


# ---- AI候補の採用直後：次の未確認候補へ、登録した要件を開く ----
def adopt_via_ui(at, label="要件に採用する内容を確認"):
    at = next(b for b in at.button if b.label == label).click().run()
    return next(b for b in at.button if b.label == "この内容で採用").click().run()


def test_after_adopt_shows_next_and_open_requirement(p):
    reviewed(p)
    run(p, "extract", [cand("要望", "申込の状況を一覧で見る")], source_ids=[p["sources"][0]["id"]])  # 採用できる要望を2件にする
    at = adopt_via_ui(open_app(p, "candidates"))
    q = at.session_state["project"]
    new = [r["id"] for r in q["requirements"]][1:]
    assert any(s.value.startswith("要件を下書きとして登録しました") and new[0] in s.value for s in at.success)
    assert key(at, "cand_next").label == "次の未確認候補へ" and key(at, "cand_next").proto.type == "primary"
    assert key(at, "cand_open_reqs").label == "登録した要件を開く" and key(at, "cand_go_list").proto.type == "secondary"  # オレンジは1つ
    at = key(at, "cand_next").click().run()
    assert at.session_state.get("cand_focus_shown") in [c["id"] for c in q["candidates"] if c["state"] == "候補"]
    at = adopt_via_ui(open_app(p, "candidates"))
    at = key(at, "cand_open_reqs").click().run()
    assert at.session_state["page"] == "requirements" and set(at.session_state["req_focus"]["ids"]) == {at.session_state["project"]["requirements"][-1]["id"]}
    assert key(at, "req_back").label == "← AI候補の確認に戻る"
    at = key(at, "req_back").click().run()
    assert at.session_state["page"] == "candidates"


def test_after_adopt_with_no_waiting_opens_requirement(p):
    reviewed(p)
    target = next(c for c in p["candidates"] if c["state"] == "候補" and c["kind"] == "要望")
    for c in p["candidates"]:
        if c["state"] == "候補" and c is not target:
            c["state"] = "却下"
    at = adopt_via_ui(open_app(p, "candidates"))
    assert key(at, "cand_open_reqs").proto.type == "primary" and key(at, "cand_all_reqs").label == "要件一覧を開く"
    assert not any(b.key == "cand_next" for b in at.button)
    before = len(at.session_state["project"]["requirements"])
    at.run()  # 再描画しても二重に登録しない
    assert len(at.session_state["project"]["requirements"]) == before


def test_after_split_adopt_opens_only_new_requirements(p):
    m = registry.ingest_paste(p, "議事録", "講師が出欠を登録し、月別CSVを出力する。", kind="議事録")
    run(p, "extract", [cand("要望", "講師が出欠を登録し、月別CSVを出力する")], source_ids=[m["id"]])
    at = adopt_via_ui(open_app(p, "candidates"))
    q = at.session_state["project"]
    assert len(q["requirements"]) >= 2  # 分割して採用
    at = key(at, "cand_open_reqs").click().run()
    assert set(at.session_state["req_focus"]["ids"]) == {r["id"] for r in q["requirements"]}
