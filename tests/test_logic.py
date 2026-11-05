"""業務ロジック：根拠、合意、変更、履歴、基準版、分野別の切替、残件、回答。"""
import pytest

from definereq import project as pj
from definereq import schema
from definereq.demos import builder
from definereq.ingest import registry
from definereq.logic import agreement as ag
from definereq.logic import baseline, checks, why
from definereq.logic import evidence as ev


def add_req(p, **kw):
    return pj.add(p, "requirements", pj.new_requirement(title=kw.pop("title", "要件"), body=kw.pop("body", "本文"), **kw))


def agreed_decision(p, req_id, **kw):
    d = ag.new_decision(p, "論点", [{"id": "A", "label": "案A"}, {"id": "B", "label": "案B"}], related_requirements=[req_id],
                        adopted="A", decider="部長", decided_on="2026-09-01", **kw)
    ag.set_state(p, d["id"], "合意済み", "human")
    return d


# ---- 根拠 ----
def test_evidence_verified_with_location(project):
    s = registry.ingest_paste(project, "メモ", "一行目\n承認後は変更できない")
    e = ev.make(project, s["id"], "承認後は変更できない")
    assert e["verified"] and e["locator"] == "2行目" and e["version"] == 1


def test_fabricated_quote_is_not_verified(project):
    s = registry.ingest_paste(project, "メモ", "本文")
    e = ev.make(project, s["id"], "資料にない引用")
    assert not e["verified"] and e["locator"] == "位置不明"


def test_evidence_becomes_stale_when_source_updated(project):
    registry.ingest_paste(project, "メモ", "旧の条件")
    s = project["sources"][0]
    add_req(project, evidence=[ev.make(project, s["id"], "旧の条件")])
    registry.ingest_paste(project, "メモ", "新の条件")
    bad = ev.verify_all(project)
    assert bad and bad[0]["stale"]


def test_recording_evidence_has_time():
    p = builder.build("d3", 2)
    r = next(x for x in p["requirements"] if x["title"].startswith("受発注の画面"))
    e = next(x for x in r["evidence"] if x["source_id"].startswith("REC"))
    assert e["verified"] and e["locator"].startswith("00:00:")


# ---- 未設定と該当なし ----
def test_unset_and_not_applicable_are_distinct():
    assert pj.field_state(None) == "未設定" and pj.field_state("") == "未設定"
    assert pj.field_state(schema.NA) == "該当なし"
    assert pj.field_state("値") == "設定済み"


def test_backlog_does_not_treat_na_acceptance_as_missing(project):
    add_req(project, acceptance=schema.NA, scope="今回必須")
    assert checks.backlog(project)["counts"]["受入条件未設定"] == 0


# ---- 合意 ----
def test_ai_cannot_agree_decision(project):
    r = add_req(project)
    d = ag.new_decision(project, "論点", [{"id": "A", "label": "案"}], adopted="A", decider="部長", decided_on="2026-09-01", related_requirements=[r["id"]])
    with pytest.raises(PermissionError):
        ag.set_state(project, d["id"], "合意済み", "ai")
    with pytest.raises(PermissionError):
        ag.set_state(project, d["id"], "合意済み", "program")


def test_agreement_requires_decider_date_adopted(project):
    d = ag.new_decision(project, "論点")
    with pytest.raises(ValueError, match="採用案・判断者・判断日"):
        ag.set_state(project, d["id"], "合意済み", "human")


def test_requirement_cannot_be_agreed_without_decision(project):
    r = add_req(project)
    with pytest.raises(ValueError):
        pj.set_requirement_status(project, r["id"], "合意済み", "human")
    with pytest.raises(PermissionError):
        pj.set_requirement_status(project, r["id"], "合意済み", "ai")


def test_hold_requires_reason(project):
    d = ag.new_decision(project, "論点")
    with pytest.raises(ValueError, match="保留"):
        ag.set_state(project, d["id"], "保留", "human")


def test_old_agreement_is_not_inherited(project):
    r = add_req(project)
    agreed_decision(project, r["id"])
    pj.set_requirement_status(project, r["id"], "合意済み", "human")
    pj.update_requirement(project, r["id"], {"body": "変更後"}, reason="変更")
    assert r["status"] == "確認待ち" and r["version"] == 2 and r["versions"][0]["body"] == "本文"


def test_issuing_document_does_not_agree(project):
    from definereq.export import share

    r = add_req(project)
    doc = share.register_doc(project, share.Options(doc_type="meeting"), "資料")
    share.record_response(project, doc["id"], r["id"], "了解です")
    assert r["status"] == "下書き"


# ---- 追加要望 ----
def test_receiving_change_does_not_touch_requirements(project):
    r = add_req(project)
    before = dict(r)
    ag.receive_change(project, "変えてほしい", related_requirements=[r["id"]])
    assert r == before


def test_apply_change_needs_agreed_linked_decision(project):
    r = add_req(project)
    c = ag.receive_change(project, "変えてほしい")
    d = ag.new_decision(project, "論点", related_changes=[c["id"]])
    with pytest.raises(ValueError, match="合意済み"):
        ag.apply_change(project, c["id"], d["id"], {r["id"]: {"body": "新"}}, "human")
    with pytest.raises(PermissionError):
        ag.apply_change(project, c["id"], d["id"], {r["id"]: {"body": "新"}}, "ai")
    other = agreed_decision(project, r["id"])
    with pytest.raises(ValueError, match="関連付いていません"):
        ag.apply_change(project, c["id"], other["id"], {r["id"]: {"body": "新"}}, "human")


def test_apply_change_records_history_and_requires_reconfirmation(project):
    r = add_req(project)
    c = ag.receive_change(project, "変えてほしい", requested_at="2026-09-01")
    d = agreed_decision(project, r["id"], related_changes=[c["id"]], rationale="理由")
    pj.set_requirement_status(project, r["id"], "合意済み", "human")
    ag.apply_change(project, c["id"], d["id"], {r["id"]: {"body": "新本文"}}, "human", applied_on="2026-09-05")
    h = project["history"][-1]
    assert (h["before"], h["after"], h["rationale"], h["applied_on"], h["proposed_on"]) == ("本文", "新本文", "理由", "2026-09-05", "2026-09-01")
    assert r["status"] == "確認待ち" and c["status"] == "反映済み"


def test_unsurveyed_areas_are_listed(project):
    c = ag.receive_change(project, "x")
    ag.add_impact(project, c["id"], "権限", None, "影響あり", "確認済み")
    left = ag.unsurveyed_areas(c)
    assert "権限" not in left and "通信" in left


# ---- 履歴 ----
def test_unknown_dates_are_not_filled_with_record_time(project):
    h = ag.record_history(project, None, "採用", "きっかけ")
    assert h["decided_on"] is None and h["proposed_on"] is None and h["applied_on"] is None and h["recorded_at"]


def test_correction_keeps_original(project):
    h = ag.record_history(project, None, "採用", "きっかけ", rationale="誤り", decided_on="2026-01-01")
    fixed = ag.correct_history(project, h["id"], {"rationale": "正しい理由"}, "入力誤り")
    assert pj.get(project, "history", h["id"])["rationale"] == "誤り"
    assert fixed["corrects"] == h["id"] and fixed["rationale"] == "正しい理由"


def test_split_merge_keeps_trace(project):
    a = add_req(project)
    b = add_req(project)
    parts = pj.split_requirement(project, a["id"], [{"title": "x", "body": "1"}, {"title": "y", "body": "2"}], "分割")
    m = pj.merge_requirements(project, [parts[0]["id"], b["id"]], "統合", "本文", "統合")
    assert a["status"] == "廃止"
    assert m["id"] in pj.lineage(project, a["id"]) and a["id"] in pj.lineage(project, m["id"])


# ---- 基準版 ----
def test_baseline_detects_change_and_shared_doc(project):
    from definereq.export import share

    r = add_req(project)
    agreed_decision(project, r["id"])
    pj.set_requirement_status(project, r["id"], "合意済み", "human")
    b = baseline.create(project, "合意版")
    share.register_doc(project, share.Options(doc_type="meeting"), "資料")
    assert baseline.compare(project, b["id"])["changed"] == []
    pj.update_requirement(project, r["id"], {"body": "変更"}, reason="x")
    assert baseline.compare(project, b["id"])["changed"][0]["id"] == r["id"]
    ids = {t["id"] for t in baseline.reconfirm_targets(project)}
    assert r["id"] in ids and project["shared_docs"][0]["id"] in ids


# ---- 分野別 ----
def cats(domains):
    return {i["category"] for i in checks.perspectives_for(domains)}


def test_questions_switch_by_domain():
    assert "画面・帳票" in cats(["app"]) and "画面・帳票" not in cats(["network"])
    assert "復旧" in cats(["infra"]) and "復旧" not in cats(["app"])
    assert "分離" in cats(["network"]) and "分離" not in cats(["infra"])


def test_chapters_switch_by_domain():
    assert "画面・帳票" in dict((c, d) for d, c in checks.chapters_for(["app"]))
    assert "分離" in [c for _, c in checks.chapters_for(["network"])]
    assert "配置制約" in [c for _, c in checks.chapters_for(["infra"])]


def test_composite_dedupes_same_topic():
    single = len(checks.perspectives_for(["infra"])) + len(checks.perspectives_for(["network"]))
    both = checks.perspectives_for(["infra", "network"])
    assert len(both) < single
    assert any(len(i["merged_ids"]) > 1 for i in both)


def test_answered_questions_are_not_repeated(project):
    first = checks.prep_questions(project)[0]
    pj.add(project, "questions", {"text": first["text"], "perspective_id": first["perspective_id"], "status": "回答済み"})
    assert first["perspective_id"] not in {q["perspective_id"] for q in checks.prep_questions(project)}


def test_trait_questions_added(project):
    before = len(checks.prep_questions(project))
    project["traits"] = ["approval"]
    assert len(checks.prep_questions(project)) == before + 3


def test_suggest_traits_is_only_a_suggestion(project):
    registry.ingest_paste(project, "メモ", "承認と差し戻しの流れ")
    assert "approval" in checks.suggest_traits(project)
    assert project["traits"] == []


# ---- 境界 ----
def test_person_count_alone_does_not_create_measures():
    """デモ3：利用者数の記載があっても、帯域は未計測のまま。"""
    p = builder.build("d3", 4)
    r = next(x for x in p["requirements"] if x["title"].startswith("受発注の画面"))
    m = next(x for x in r["measures"] if x["metric"] == "ピーク時の通信量")
    assert m["value"] is None and m["status"] == "未計測"


def test_ports_are_not_invented():
    p = builder.build("d3", 4)
    text = str([r["body"] for r in p["requirements"]])
    assert "未確認" in text
    assert not any(w in text for w in ("TCP", "UDP", "443", "3389", "22番"))


def test_rto_rpo_downtime_are_distinct_measures():
    p = builder.build("d2", 2)
    metrics = {m["metric"] for r in p["requirements"] for m in r["measures"]}
    assert {"目標復旧時間（RTO）", "許容データ損失（RPO）", "計画停止の頻度"} <= metrics


def test_measure_kinds_separate_requirement_and_candidate():
    p = builder.build("d3", 2)
    r = next(x for x in p["requirements"] if x["title"] == "回線を二重化する")
    assert r["measures"][0]["kind"] == "実現方式の候補" and r["status"] != "合意済み"


@pytest.mark.parametrize("body", ["回線は二重化する", "バックアップを取得する"])
def test_overclaim_warning_without_acceptance(project, body):
    add_req(project, body=body)
    assert checks.overclaims(project)


def test_no_overclaim_warning_when_acceptance_exists(project):
    add_req(project, body="バックアップを取得する", acceptance=[{"then": "復旧できる"}])
    assert not checks.overclaims(project)


def test_vague_words_generate_questions_without_numbers(project):
    add_req(project, title="画面を速くする", body="すぐ表示する")
    hits = checks.vague_requirements(project)[0]["hits"]
    assert {"速", "すぐ"} <= {h["word"] for h in hits}


# ---- 矛盾 ----
@pytest.mark.parametrize("a,b", [("承認後は変更できない", "承認後も変更できるようにしたい"), ("無停止で運用する", "切替のときは停止が必要"),
                                 ("外部からの接続は禁止する", "遠隔保守を行う"), ("データの損失は不可", "バックアップは日次で取得する"),
                                 ("締め後は固定する", "再集計したい")])
def test_conflict_candidates(project, a, b):
    add_req(project, body=a)
    add_req(project, body=b)
    found = checks.scan_conflicts(project)["candidates"]
    assert found and all(c["kind"] == "前提確認が必要な候補" for c in found)


def test_clear_conflict_needs_same_metric_and_condition(project):
    m = {"metric": "応答時間", "unit": "秒", "kind": "必要条件", "condition": "朝"}
    add_req(project, measures=[{**m, "value": 3}])
    add_req(project, measures=[{**m, "value": 5}])
    assert any(c["kind"] == "明確な矛盾" for c in checks.scan_conflicts(project)["candidates"])


def test_different_conditions_are_not_clear_conflict(project):
    add_req(project, measures=[{"metric": "応答時間", "value": 3, "kind": "必要条件", "condition": "朝"}])
    add_req(project, measures=[{"metric": "応答時間", "value": 5, "kind": "必要条件", "condition": "夜"}])
    assert not checks.scan_conflicts(project)["candidates"]


def test_scan_reports_scope_and_no_guarantee(project):
    assert "未検出は矛盾がないことを意味しません" in checks.scan_conflicts(project)["scope"]


# ---- 残件 ----
def test_backlog_unique_total_differs_from_category_total(project):
    add_req(project, scope="今回必須")
    b = checks.backlog(project)
    assert b["category_total"] == 2 and b["unique_total"] == 1


def test_backlog_does_not_fill_owner_or_due(project):
    add_req(project, scope="今回必須")
    for items in checks.backlog(project)["categories"].values():
        for i in items:
            assert i["due"] is None and i["ask"] is None


# ---- なぜこの仕様か ----
def test_why_no_reason_recorded():
    p = builder.build("d2", 4)
    a = why.answer(p, "なぜ保存期間は3年なのか")
    assert a["reason"] == why.NO_REASON and not a["reason_recorded"]


def test_why_uses_only_related_decision_reason():
    p = builder.build("d1", 4)
    a = why.answer(p, "なぜ部長の承認が必要なのか")
    assert "規程" in a["reason"] and "監査" not in a["reason"]


def test_why_resubmission_has_options_decider_citation():
    p = builder.build("d1", 4)
    a = why.answer(p, "なぜ再申請なのか")
    assert "監査" in a["reason"]
    d = next(x for x in a["decisions"] if x["adopted"] == "再申請")
    assert d["decider"] == "山本" and d["citations"] and all(c["verified"] for c in d["citations"])
    assert any(o["label"] == "直接変更" and o["rejected_reason"] for o in d["options"])


def test_why_distinguishes_current_and_past():
    p = builder.build("d1", 4)
    a = why.answer(p, "なぜ再申請なのか")
    assert a["current"]["version"] == 2 and a["past_versions"][0]["version"] == 1
    assert a["past_versions"][0]["body"] != a["current"]["body"]


def test_why_ambiguous_shows_candidates(project):
    add_req(project, title="画面の表示項目", body="本文")
    add_req(project, title="画面の表示順序", body="本文")
    assert why.answer(project, "なぜ画面の表示なのか")["status"] == "ambiguous"


def test_why_not_found_and_no_cross_project():
    a = builder.build("d1", 4)
    b = builder.build("d2", 4)
    assert why.answer(a, "なぜ復旧は4時間以内なのか")["status"] == "not_found"
    assert why.answer(b, "なぜ再申請なのか")["status"] == "not_found"


def test_why_by_id(project):
    r = add_req(project, title="全く別の名称")
    assert why.answer(project, f"{r['id']} の理由は")["target"]["id"] == r["id"]


def test_why_past_wording_flag():
    p = builder.build("d1", 4)
    assert why.answer(p, "以前の再申請の仕様はなぜ変わったのか")["wants_past"] is True


def test_why_unagreed_decision_is_not_used_as_reason(project):
    r = add_req(project, title="遠隔保守")
    ag.new_decision(project, "遠隔保守", [{"id": "A", "label": "案"}], rationale="提案の理由", related_requirements=[r["id"]], state="提案")
    a = why.answer(project, "なぜ遠隔保守なのか")
    assert a["reason"] == why.NO_REASON and a["not_agreed"]
