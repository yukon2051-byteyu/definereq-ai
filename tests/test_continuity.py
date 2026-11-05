"""複数回の会議をまたぐ継続利用（架空データ・有料AIなし）。

指示書の一連の操作を、JSONの保存と読込を挟んで確認する。別のセッションの代わりに、
読み込んだバイト列だけから案件を復元する。
"""
import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from definereq import project as pj
from definereq.ai import tasks as ai
from definereq.demos import builder
from definereq.export import jsonio
from definereq.ingest import registry
from definereq.logic import agreement as ag
from definereq.logic import continuity as ct
from definereq.logic import evidence as ev
from definereq.logic import checks, why
from definereq.schema import COLLECTIONS

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")
V1_FILE = Path(__file__).parent / "fixtures" / "v1_public_export.json"


def first_session() -> dict:
    p = pj.new_project("架空の勤怠更新", ["app"])
    m1 = ct.add_meeting(p, "第1回打ち合わせ", "2026-11-01")
    src = registry.ingest_paste(p, "第1回メモ", "佐藤：打刻の修正は上長が承認する。\n田中：月末の締めは翌月3日とする。", kind="議事録", meeting_id=m1["id"])
    r = pj.add(p, "requirements", pj.new_requirement(title="打刻修正の承認", body="打刻の修正は上長が承認する。", kind="機能",
                                                     priority="高", scope="今回必須", evidence=[ev.make(p, src["id"], "打刻の修正は上長が承認する")],
                                                     acceptance=[{"given": "修正申請", "when": "上長が承認", "then": "打刻が更新される", "how": "画面で確認"}]))
    pj.add(p, "stakeholders", {"name": "佐藤", "org": "総務", "position": "担当", "authority": "確認", "certainty": "確認済み", "note": None})
    pj.add(p, "questions", {"text": "代理承認は必要ですか", "why": "例外の確認", "ask": "佐藤", "priority": "高", "status": "回答待ち", "answer": None,
                            "perspective_id": None, "evidence": [], "meeting_id": m1["id"]})
    pj.add(p, "actions", {"content": "現行の規程を確認する", "owner": "田中", "due": "2026-11-10", "related": [r["id"]], "state": "未着手"})
    d = ag.new_decision(p, "承認者", [{"id": "A", "label": "上長", "pros": "明確", "cons": None}], adopted="A", rationale="現行の運用に合うため", decider="佐藤",
                        decided_on="2026-11-01", evidence=[ev.make(p, src["id"], "打刻の修正は上長が承認する")], related_requirements=[r["id"]], meeting_id=m1["id"])
    ag.set_state(p, d["id"], "合意済み", "human")
    pj.set_requirement_status(p, r["id"], "合意済み", "human")
    from definereq.logic import baseline
    baseline.create(p, "第1回の合意版")
    return p


def second_session(data: bytes) -> dict:
    p = jsonio.loads(data)
    m2 = ct.add_meeting(p, "第2回打ち合わせ", "2026-11-08")
    src = registry.ingest_paste(p, "第2回メモ", "佐藤：上長が不在のときは代理者も承認できるようにしたい。\n佐藤：代理は課長補佐までとする。", kind="議事録", meeting_id=m2["id"])
    q = next(x for x in p["questions"] if x["status"] == "回答待ち")
    q.update(status="回答済み", answer="代理者は課長補佐まで", evidence=[ev.make(p, src["id"], "代理は課長補佐までとする")])
    r = p["requirements"][0]
    chg = ag.receive_change(p, "代理者も承認できるようにしたい", "佐藤", evidence=[ev.make(p, src["id"], "代理者も承認できるようにしたい")],
                            related_requirements=[r["id"]], requested_at="2026-11-08", meeting_id=m2["id"])
    d = ag.new_decision(p, "代理承認", [{"id": "A", "label": "課長補佐まで"}], adopted="A", rationale="上長の不在時に申請が止まらないようにするため", decider="佐藤",
                        decided_on="2026-11-08", evidence=[ev.make(p, src["id"], "代理は課長補佐までとする")], related_requirements=[r["id"]],
                        related_changes=[chg["id"]], meeting_id=m2["id"])
    ag.set_state(p, d["id"], "合意済み", "human")
    ag.apply_change(p, chg["id"], d["id"], {r["id"]: {"body": "打刻の修正は上長が承認する。上長の不在時は課長補佐が代理できる。"}}, "human", applied_on="2026-11-09")
    return p


def test_full_cycle_two_meetings_survive_two_reloads():
    p1 = first_session()
    saved1 = jsonio.dumps(p1)
    restored = jsonio.loads(saved1)
    # 手順4：ID・根拠・状態・履歴・関連付けが復元される
    for col in COLLECTIONS:
        assert restored[col] == json.loads(json.dumps(p1[col], default=str)), col
    r = restored["requirements"][0]
    assert r["id"] == "REQ-001" and r["status"] == "合意済み" and r["priority"] == "高" and r["acceptance"]
    assert r["evidence"][0]["verified"] and ev.verify_all(restored) == []
    assert restored["decisions"][0]["meeting_id"] == "MTG-001"

    # 手順5〜6：第2回を追加し、未決事項を引き継ぎ、変更を記録する
    before = ct.carryover(restored)
    assert before["未回答の質問"] and before["宿題"][0]["ask"] == "田中"
    p2 = second_session(saved1)
    assert not ct.carryover(p2)["未回答の質問"]
    assert ct.carryover(p2)["宿題"], "完了していない宿題は残る"

    # 手順7：もう一度保存して読み込む
    final = jsonio.loads(jsonio.dumps(p2))
    assert [m["name"] for m in final["meetings"]] == ["第1回打ち合わせ", "第2回打ち合わせ"]
    assert len(final["sources"]) == 2 and final["sources"][0]["units"], "過去の資料が残る"
    r = final["requirements"][0]
    assert r["version"] == 2 and r["versions"][0]["body"] == "打刻の修正は上長が承認する。"
    h = final["history"][-1]
    assert (h["before"], h["decided_on"], h["applied_on"], h["meeting_id"], h["meeting_date"]) == ("打刻の修正は上長が承認する。", "2026-11-08", "2026-11-09", "MTG-002", "2026-11-08")
    assert h["rationale"] == "上長の不在時に申請が止まらないようにするため" and h["evidence"]
    assert ev.verify_all(final) == [] or all(b["collection"] != "requirements" for b in ev.verify_all(final))
    a = why.answer(final, "打刻修正の承認はなぜ変わったのか")
    assert a["status"] == "answered" and any(x["meeting"] == "MTG-002" for x in a["history"])
    assert "課長補佐" not in a["past_versions"][0]["body"]
    assert ct.meeting_items(final, "MTG-002")["変更履歴"] and ct.meeting_items(final, "MTG-001")["判断"]
    assert jsonio.validate(final) == []


def test_ids_continue_after_reload():
    p = jsonio.loads(jsonio.dumps(first_session()))
    assert pj.add(p, "requirements", pj.new_requirement(title="次", body="b"))["id"] == "REQ-002"


def test_ai_candidate_does_not_overwrite_agreed_requirement():
    p = first_session()
    r = p["requirements"][0]
    before = dict(r)
    c = pj.add(p, "candidates", {"kind": "要望", "text": "代理者も承認したい", "detail": None, "ask": None, "evidence": [], "state": "候補", "origin": "AI", "unsupported_numbers": [], "no_evidence": True})
    for kind in ("既存要件の補足", "変更候補"):
        item = ct.intake_candidate(p, c["id"], kind, r["id"], "MTG-001")
        assert item["id"].startswith("CHG-") and item["status"] == "受付"
        assert r == before


@pytest.mark.parametrize("kind,prefix", [("新規要望", "REQ-"), ("確認事項", "QST-"), ("変更候補", "CHG-"), ("既存要件の補足", "CHG-")])
def test_intake_routes_new_information(kind, prefix):
    p = first_session()
    c = pj.add(p, "candidates", {"kind": "要望", "text": "新しい情報", "evidence": [], "state": "候補", "origin": "AI"})
    item = ct.intake_candidate(p, c["id"], kind, "REQ-001", "MTG-001")
    assert item["id"].startswith(prefix) and c["state"] == "採用" and c["intake"] == kind


def test_intake_requires_target_for_change():
    p = first_session()
    c = pj.add(p, "candidates", {"kind": "要望", "text": "x", "evidence": [], "state": "候補", "origin": "AI"})
    with pytest.raises(ValueError, match="対象の要件"):
        ct.intake_candidate(p, c["id"], "変更候補")


def test_version1_export_is_converted():
    raw = json.loads(jsonio.dumps(builder.build("d1", 4)))
    raw.pop("meetings")
    raw.pop("exported_at")
    raw["format_version"] = 1
    for col in ("sources", "recordings", "decisions", "history"):
        for it in raw[col]:
            it.pop("meeting_id", None)
    p = jsonio.loads(json.dumps(raw).encode())
    assert p["format_version"] == 2 and p["migrated_from"] == 1 and p["meetings"] and not jsonio.validate(p)


def test_real_export_from_public_v1_loads():
    """公開版から実際に出力した版1のファイル。"""
    p = jsonio.loads(V1_FILE.read_bytes())
    assert p["requirements"] and p["meetings"] and p["recordings"][0]["segments"]
    assert not p["is_demo"] and p["from_demo"]
    assert ev.verify_all(p) == []


def test_unknown_date_is_not_invented_in_migration():
    p = pj.new_project("t", ["app"])
    registry.ingest_paste(p, "日付なし議事録", "本文", kind="議事録")
    ct.backfill(p)
    assert p["meetings"][0]["held_on"] is None
    assert jsonio.summary({**p, "exported_at": None})["保存用ファイルの作成日時"] == "記録なし"


def test_future_version_is_rejected_with_guidance():
    raw = json.loads(jsonio.dumps(first_session()))
    raw["format_version"] = 99
    with pytest.raises(jsonio.LoadError) as e:
        jsonio.loads(json.dumps(raw).encode())
    assert "最新" in e.value.hint


@pytest.mark.parametrize("name,fn", [("mtg", lambda q: q["sources"][0].update(meeting_id="MTG-999")), ("dup", lambda q: q["meetings"].append(dict(q["meetings"][0])))])
def test_broken_meeting_reference_rejected(name, fn):
    raw = json.loads(jsonio.dumps(first_session()))
    fn(raw)
    with pytest.raises(jsonio.LoadError):
        jsonio.loads(json.dumps(raw).encode())


def test_secrets_are_not_in_export():
    text = jsonio.dumps(first_session()).decode()
    for word in ("ai_code", "API_KEY", "sk-", "hf_", "ACCESS_CODES"):
        assert word not in text


def test_load_starts_no_ai_run():
    p = jsonio.loads(jsonio.dumps(first_session()))
    assert p["ai_runs"] == []
    assert ai.TASKS  # 読込の処理はAIの部品を呼ばない


def test_carryover_lists_open_items():
    p = first_session()
    c = ct.carryover(p)
    assert c["未回答の質問"][0]["meeting"].startswith("第1回") and c["宿題"][0]["due"] == "2026-11-10"
    assert checks.backlog(p)


# ---- 画面 ----
def app(**state):
    at = AppTest.from_file(APP, default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


def test_home_shows_both_entry_points():
    at = app()
    assert any("保存した案件から再開する" in m.value for m in at.markdown)
    assert any("引き継いで" in c.value for c in at.caption)
    assert at.get("file_uploader")


def test_back_to_top_keeps_project_and_warns():
    p = first_session()
    at = app(project=p, page="overview")
    next(b for b in at.button if b.key == "nav_home").click()
    at = at.run()
    assert at.session_state["project"]["name"] == p["name"]
    assert any("別の案件へ切り替える前に保存" in w.value for w in at.warning)
    assert any(b.key == "back_work" for b in at.button)
    next(b for b in at.button if b.key == "back_work").click()
    at = at.run()
    assert not at.session_state["show_home"] and not at.exception


def test_create_blocked_until_discard_confirmed(monkeypatch):
    monkeypatch.setenv("DEFINEREQ_ACCESS_CODES", "correct-password")
    at = app(project=first_session(), show_home=True)
    next(t for t in at.text_input if t.label == "AIパスワード").set_value("correct-password")
    at = at.run()
    create = next(b for b in at.button if b.key == "create_project")
    assert create.disabled
    next(c for c in at.checkbox if c.key == "discard_ok").check()
    at = at.run()
    assert not next(b for b in at.button if b.key == "create_project").disabled


def test_demo_does_not_lose_work_in_progress():
    p = first_session()
    at = app(project=p, show_home=True)
    next(b for b in at.button if b.key == "free_d1").click()
    at = at.run()
    assert at.session_state["project"]["is_demo"]
    next(b for b in at.button if b.key == "nav_home").click()
    at = at.run()
    assert at.session_state["project"]["name"] == p["name"] and at.session_state["show_home"]


def test_save_status_shown_in_sidebar():
    at = app(project=first_session(), page="overview")
    assert any("保存用ファイルはまだ作成していません" in c.value and "作成後の変更あり" in c.value for c in at.sidebar.caption)


def test_after_load_project_is_not_dirty():
    p = jsonio.loads(jsonio.dumps(first_session()))
    at = app(project=p, page="overview", save_fp=pj.fingerprint(p))
    assert any("作成後の変更なし" in c.value for c in at.sidebar.caption)


def test_meeting_and_prep_pages_show_carryover():
    p = first_session()
    for page in ("meetings", "prep"):
        at = app(project=p, page=page)
        assert not at.exception and not at.error
        assert any("未回答の質問" in e.label for e in at.expander)


def test_meetings_built_for_demos():
    p = builder.build("d1", 4)
    assert {m["held_on"] for m in p["meetings"]} >= {"2026-09-08", "2026-09-15"}
    assert any(h.get("meeting_id") for h in p["history"])
