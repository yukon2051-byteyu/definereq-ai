"""状況案内と、デモの入口・最終画面の確認。実APIは呼ばない。"""
from __future__ import annotations

import copy
import io
import json
from pathlib import Path

import pytest
from docx import Document
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from definereq import project as pj
from definereq.ai import guidance as ai_gd
from definereq.ai.client import AIError, AIResult
from definereq.demos import builder, guide
from definereq.export import excelx, jsonio, share, wordx
from definereq.ingest import registry
from definereq.logic import agreement as ag
from definereq.logic import diffview
from definereq.logic import guidance as gd

APP = str(Path(__file__).resolve().parent.parent / "app.py")
DEMOS = ["d1", "d2", "d3"]


class FakeLLM:
    def __init__(self, items=None, error=None):
        self.calls = 0
        self.items = items if items is not None else [{"kind": "確認する質問", "text": "利用人数を確認する", "detail": "資料に記載がないため", "ask": "現場", "evidence": []}]
        self.error = error

    def complete(self, system, user, schema, max_tokens):
        self.calls += 1
        self.system, self.user = system, user
        if self.error:
            raise self.error
        return AIResult({"items": self.items, "notes": ""}, 100, 50)


class FakeLedger:
    def __init__(self):
        self.reserved, self.settled = [], []

    def reserve(self, limits, code, kind, task, est, minutes=0):
        self.reserved.append(task)
        return len(self.reserved)

    def settle(self, run_id, status, cost, *a, **k):
        self.settled.append((status, cost))


@pytest.fixture
def blank():
    return pj.new_project("勤怠の更新", ["app"])


def ids(p, page=None):
    return [a.id for a in gd.collect(p, page)]


def add_request(p, text="承認の現状を確認したい"):
    return registry.ingest_paste(p, "要望メモ", text, kind="要望")


# ---- プログラムの判定 ----
def test_empty_project_gets_start_advice(blank):
    r = gd.assess(blank, "overview")
    assert r["main"].id == "start" and r["main"].page == "setup" and "未入力" in r["main"].reason
    assert not r["stage_question"]


def test_advice_updates_after_source_and_question(blank):
    add_request(blank)
    assert gd.assess(blank, "overview")["main"].id == "sources_added"
    pj.add(blank, "questions", {"text": "利用人数は？", "why": None, "ask": "現場", "priority": None, "status": "未質問", "answer": None, "perspective_id": None, "evidence": []})
    assert "sources_added" not in ids(blank)
    main = gd.assess(blank, "prep")["main"]
    assert main.id == "prep" and "1件" in main.situation


def test_resolved_advice_disappears(blank):
    add_request(blank)
    q = pj.add(blank, "questions", {"text": "Q", "why": None, "ask": None, "priority": None, "status": "未質問", "answer": None, "perspective_id": None, "evidence": []})
    assert "prep" in ids(blank)
    q["status"] = "回答済み"
    assert "prep" not in ids(blank)


def test_stage_is_not_assumed_and_user_choice_is_kept(blank):
    add_request(blank)
    pj.add(blank, "questions", {"text": "Q", "why": None, "ask": None, "priority": None, "status": "未質問", "answer": None, "perspective_id": None, "evidence": []})
    assert gd.assess(blank, "prep")["main"].title == "会議の準備" and gd.assess(blank)["stage_question"]
    gd.guidance_store(blank)["user_stage"] = "before_first"
    assert gd.assess(blank, "prep")["main"].title == "初回会議の準備"
    gd.guidance_store(blank)["user_stage"] = "after_first"
    assert "meeting_missing" in ids(blank)


def test_candidates_conflict_order_prefers_current_page():
    p = builder.build("d3", 4)
    # 次にすることは案件の状態で決まり、開いている画面で変わらない
    assert gd.assess(p, "conflicts")["main"].id == gd.assess(p, "prep")["main"].id
    r = gd.assess(p, "prep")
    assert len(r["extra"]) <= 1 and r["main"].id not in [a.id for a in r["extra"] + r["rest"]]


def test_change_registration_does_not_change_requirement_and_gets_advice(blank):
    src = add_request(blank, "承認済みの申請は変更しない")
    r = pj.add(blank, "requirements", pj.new_requirement(title="変更禁止", body="承認後は変更しない", status="合意済み"))
    before = copy.deepcopy(r)
    chg = ag.receive_change(blank, "承認後も変更したい", related_requirements=[r["id"]], evidence=[])
    assert "change_new" in ids(blank)
    assert pj.get(blank, "requirements", r["id"]) == before
    ag.add_impact(blank, chg["id"], "データ", r["id"], "影響あり", "確認済み")
    assert "change_new" not in ids(blank) and "change_wait" in ids(blank)
    assert src


def test_decision_recorded_removes_waiting_advice(blank):
    r = pj.add(blank, "requirements", pj.new_requirement(title="T", body="B", status="提案"))
    d = ag.new_decision(blank, "論点", [{"id": "A", "label": "案A"}], related_requirements=[r["id"]], state="提案")
    assert "decision_wait" in ids(blank)
    d.update(adopted="A", rationale="理由", decider="山本", decided_on="2026-11-01")
    ag.set_state(blank, d["id"], "合意済み", "human", "担当")
    assert "decision_wait" not in ids(blank) and "after_decision" in ids(blank)


def test_guidance_does_not_modify_project():
    p = builder.build("d1", 4)
    before = pj.fingerprint(p)
    gd.assess(p, "share", resumed=True)
    assert pj.fingerprint(p) == before


def test_export_advice_does_not_guarantee_completion():
    p = builder.build("d1", 4)
    a = gd.assess(p, "share")["main"]
    assert a.id == "export" and "保証するものではありません" in a.todo


def test_resume_advice_does_not_invent_last_position():
    p = builder.build("d1", 4)
    a = gd.assess(p, "overview", resumed=True)["main"]
    assert a.id == "resume" and "記録されていません" in a.situation and "記録なし" in a.situation


# ---- AI補足 ----
def test_ai_runs_once_for_same_state_and_again_after_change(blank):
    add_request(blank)
    llm, ledger = FakeLLM(), FakeLedger()
    a = gd.assess(blank, "overview")["main"]
    n1 = ai_gd.run(blank, a, "code", ledger, llm)
    n2 = ai_gd.run(blank, a, "code", ledger, llm)
    assert llm.calls == 1 and n1 is n2 and ledger.reserved == ["guidance"]
    assert ai_gd.current_note(blank, gd.state_fingerprint(blank), a.id)
    add_request(blank, "別の要望")
    fp = gd.state_fingerprint(blank)
    assert ai_gd.current_note(blank, fp, a.id) is None and ai_gd.stale_notes(blank, fp)
    ai_gd.run(blank, gd.assess(blank, "overview")["main"], "code", ledger, llm)
    assert llm.calls == 2


def test_ai_failure_keeps_program_advice(blank):
    add_request(blank)
    llm, ledger = FakeLLM(error=AIError("接続できません", billed=False)), FakeLedger()
    a = gd.assess(blank, "overview")["main"]
    with pytest.raises(AIError):
        ai_gd.run(blank, a, "code", ledger, llm)
    assert ledger.settled == [("失敗", 0.0)] and not (blank.get("guidance") or {}).get("notes")
    assert gd.assess(blank, "overview")["main"].id == a.id


def test_ai_note_does_not_change_requirements_and_is_validated():
    p = pj.new_project("t", ["app"])
    add_request(p, "利用者は20人")
    r = pj.add(p, "requirements", pj.new_requirement(title="T", body="B", status="提案"))
    r["internal_note"] = "社外秘のメモ"
    before = copy.deepcopy(p["requirements"])
    items = [{"kind": "勝手な種類", "text": "<b>300人</b>を確認", "detail": "", "ask": "", "evidence": [{"source_id": "SRC-999", "unit_id": "", "quote": "架空"}]}, "壊れた行", {"text": ""}]
    llm = FakeLLM(items)
    note = ai_gd.run(p, gd.assess(p)["main"], "c", FakeLedger(), llm)
    assert p["requirements"] == before and "社外秘のメモ" not in llm.user
    assert len(note["items"]) == 1
    it = note["items"][0]
    assert it["kind"] == "確認する質問" and it["no_evidence"] and "300人" in it["unsupported_numbers"]
    assert "<資料>" in llm.user and "要件の確定" in llm.system


def test_state_fingerprint_survives_json_round_trip():
    p = builder.build("d1", 2)
    p.update(is_demo=False, demo=None)
    gd.guidance_store(p)["user_stage"] = "after_first"
    q = jsonio.loads(jsonio.dumps(p))
    assert gd.state_fingerprint(q) == gd.state_fingerprint(p) and gd.user_stage(q) == "after_first"


def test_old_json_without_guidance_loads(blank):
    raw = json.loads(jsonio.dumps(blank))
    raw.pop("guidance", None)
    q = jsonio.loads(json.dumps(raw).encode())
    assert "guidance" not in q and gd.assess(q, "overview")["main"].id == "start"


@pytest.mark.parametrize("bad", ["文字", {"notes": "x"}, {"notes": [{"state_fp": 1}]}, {"user_stage": "勝手な値"}])
def test_broken_guidance_does_not_block_load(blank, bad):
    raw = json.loads(jsonio.dumps(blank))
    raw["guidance"] = bad
    q = jsonio.loads(json.dumps(raw).encode())
    assert gd.assess(q, "overview")["main"].id == "start"
    assert not (q.get("guidance") or {}).get("notes") and gd.user_stage(q) is None


# ---- 差分 ----
def test_diff_marks_only_added_text():
    a, b = "再申請で訂正する。", "再申請で訂正する。下書きは経理が代行できる。"
    d = diffview.parts(a, b)
    assert d["mode"] == "partial" and ("add", "下書きは経理が代行できる。") in d["after"] and all(k == "same" for k, _ in d["before"])


def test_diff_whole_change_is_not_fragmented():
    d = diffview.parts("保守会社が遠隔保守を行う（提案）。ログの条件は未確認。", "今回の保守は現地対応とする。")
    assert d["mode"] == "whole" and len(d["before"]) == len(d["after"]) == 1


def test_diff_same_text():
    assert diffview.parts("同じ", "同じ")["mode"] == "same"


# ---- デモの案内 ----
@pytest.mark.parametrize("demo", DEMOS)
def test_every_step_has_scene_and_real_detail_label(demo):
    steps = guide.load(demo)
    assert len(steps) == 8
    for s in steps:
        ctx = guide.Ctx(builder.build(demo, s["stage"]))
        assert s["scene"]
        assert s["detail"](ctx) != "詳細画面を見る"
        check = s["check"](ctx) if callable(s["check"]) else s["check"]
        assert len(check) <= 70, check  # 状況案内は短く保つ
        assert not check or check not in s["title"]
        assert ctx.background()


def test_known_facts_are_not_listed_as_unknown():
    d1 = guide.load("d1")[1]
    items = d1["open"](guide.Ctx(builder.build("d1", d1["stage"])))
    assert ("関係者の申告", "金額の誤りは月に数件（現場の申告）") in items and not any("発生頻度" in x for _, x in items)
    d3 = guide.load("d3")[2]
    items = d3["open"](guide.Ctx(builder.build("d3", d3["stage"])))
    assert any(k == "資料に記載" and "例外" in x for k, x in items) and not any("有無" in x for _, x in items)


def test_support_describes_only_real_functions():
    for demo in DEMOS:
        for s in guide.load(demo)[1:-1]:
            labels = [k for k, _ in s["support"]]
            assert labels[0] == "入力・根拠" and labels[-1] == "人が行うこと"
            assert "プログラムの処理" in labels


def test_final_counts_match_lists():
    for demo in DEMOS:
        s = guide.Ctx(builder.build(demo, 4)).summary()
        from definereq.logic import checks
        assert s["todo_total"] == checks.backlog(builder.build(demo, 4))["unique_total"] == len(s["todo"])


def test_no_zero_count_in_open_items():
    for demo in DEMOS:
        for s in guide.load(demo):
            assert not [x for x in s["open"](guide.Ctx(builder.build(demo, s["stage"]))) if " 0件" in str(x)], (demo, s["process"])


def test_speech_separates_name_source_and_checks():
    c = guide.Ctx(builder.build("d1", 2)).speech("金額の訂正は再申請で進めます")
    assert c["who_label"] == "字幕上の話者" and c["who"] == "山本" and c["speaker_check"] == "未実施" and c["content_check"] == "確認済み"
    assert "部長" not in c["who"]


def test_measure_shows_origin_and_does_not_claim_confirmation():
    g = guide.Ctx(builder.build("d2", 2))
    m = g.measure("1日分まで", "許容データ損失", "データを失いたくない")
    assert m["origin"].startswith("関係者が提示")
    assert m["ai_asked"] and m["agreement"].startswith("済み") and m["verify"] == "復旧試験：未実施" and "どこまでのデータ損失" in m["help"]
    t = g.measure("毎朝8時30分", "集計の完了時刻", "毎朝すぐに売上の数字を見たい")
    assert t["agreement"].startswith("未合意") and t["verify"] != "未検証済み"


def test_case_specific_wording():
    text = json.dumps(builder.build("d1", 4)["decisions"], ensure_ascii=False)
    assert "元の金額が残らない" not in text and "今回の再承認案では元の金額を保持しない" in text
    assert '"cons": "監査で説明できない"' not in text


def test_option_verdict_short_labels():
    d = guide.Ctx(builder.build("d3", 2)).decision("遠隔保守の扱い")
    assert {r["verdict"] for r in d["rows"]} == {"未判断"}
    d = guide.Ctx(builder.build("d1", 2)).decision("承認後の金額訂正の方式")
    assert [r["verdict"] for r in d["rows"]] == ["不採用", "不採用", "採用"]


@pytest.mark.parametrize("demo", DEMOS)
def test_first_screen_story_matches_records(demo):
    """背景の説明が資料・発言と一致する（一致しなければ例外になる）。"""
    s = guide.load(demo)[0]
    assert s["main"](guide.Ctx(builder.build(demo, s["stage"])))[0]["type"] == "story"


@pytest.mark.parametrize("demo,later", [("d1", ["再申請", "代行"]), ("d2", ["8時30分", "4時間", "翌営業日"]), ("d3", ["現地対応とする", "常時接続"])])
def test_first_screen_does_not_reveal_later_conclusions(demo, later):
    s = guide.STORIES[demo]
    text = str([s["title"], s["rows"], s["people"], s["issue"], s["demo"]])
    assert not [w for w in later if w in text]


@pytest.mark.parametrize("demo", DEMOS)
def test_background_can_be_rechecked_on_every_step(demo):
    for s in guide.load(demo):
        assert guide.Ctx(builder.build(demo, s["stage"])).background()


def test_story_rejects_text_not_in_records(monkeypatch):
    bad = {**guide.STORIES["d1"], "checks": ["資料に存在しない文"]}
    monkeypatch.setitem(guide.STORIES, "d1", bad)
    with pytest.raises(KeyError):
        guide.Ctx(builder.build("d1", 2)).story("d1")


def test_recheck_background_keeps_step():
    at = button(button(app(), "tour_d1").click().run(), "tour_next").click().run()
    at = button(at, "tour_next").click().run()
    assert at.session_state["tour_index"] == 2 and any("現在の業務" in m.value for e in at.expander if e.label == "案件の背景を確認" for m in e.markdown)


def test_cloud_reason_is_in_records():
    assert guide.Ctx(builder.build("d2", 1)).has("基盤の保守をベンダーへ任せられるクラウドへの移行も検討している")


# ---- 成果物 ----
@pytest.mark.parametrize("demo", DEMOS)
def test_final_documents_open_and_match(demo):
    p = builder.build(demo, 4)
    for t in ("spec", "meeting", "change"):
        doc = share.latest_doc(p, t)
        assert doc and share.doc_is_current(p, doc), t
        data = wordx.render(p, share.options_for(doc), doc["id"], doc["version"], doc["issued_at"])
        d = Document(io.BytesIO(data))
        text = "\n".join(x.text for x in d.paragraphs) + "\n".join(x.text for s in d.sections for x in s.header.paragraphs)
        assert "サンプル" in text and f"第{doc['version']}版" in text and "版（v" not in text
    name = wordx.filename(p, "spec", 1)
    assert name.startswith("サンプル_") and "要件定義書_第1版" in name and p["name"] in name
    assert "（第1版）" not in str([d["title"] for d in p["shared_docs"]])
    wb = load_workbook(io.BytesIO(excelx.render(p)))
    assert "サンプル" in str(wb["表紙"]["B7"].value)


def test_spec_keeps_open_items():
    p = builder.build("d1", 4)
    doc = share.latest_doc(p, "spec")
    text = str([s.__dict__ for s in share.build(p, share.options_for(doc))])
    assert "代理承認" in text and "保留" in text


def test_real_project_filename_has_no_sample_mark():
    p = pj.new_project("勤怠/更新", ["app"])
    assert wordx.filename(p, "spec", 2) == "勤怠_更新_要件定義書_第2版.docx"


# ---- 画面 ----
def app():
    return AppTest.from_file(APP, default_timeout=60).run()


def button(at, key):
    return next(b for b in at.button if b.key == key)


def to_end(at):
    at = button(at, "tour_d1").click().run()
    for _ in range(7):
        at = button(at, "tour_next").click().run()
    return at


def test_home_cards_show_situation_and_highlights():
    """カードは 案件名 → このデモで分かること → 案件の背景 → 開始ボタン の順。共通の説明は一覧の上に1回だけ。"""
    at = app()
    html = "".join(h.proto.body for h in at.get("html"))
    for name, take in (("経費申請アプリの刷新", "対立する要望から、判断と変更を追う"), ("拠点売上集計の自動化とクラウド移行", "曖昧な要望を、測れる要件にする"),
                       ("拠点ネットワーク更新と遠隔保守", "録画の発言から、合意の根拠を確認する")):
        assert html.index(name) < html.index(take)
    assert html.index("対立する要望から") < html.index("現場と経理の意見が分かれています")
    assert html.count("登録・APIキー不要") == 1 and "架空データの閲覧専用" in html and "AIの結果は用意済みのサンプル" in html
    assert [button(at, f"tour_{d}").label for d in ("d1", "d2", "d3")] == ["経費申請のデモを見る", "売上集計・クラウド移行のデモを見る", "ネットワーク更新のデモを見る"]
    assert "3分" not in html


def test_first_and_later_banner():
    at = button(app(), "tour_d1").click().run()
    first = "".join(h.proto.body for h in at.get("html"))
    assert "デモ体験中｜経費申請アプリの刷新" in first and "デモ用の役割" in first and "現場と経理の要望を取りまとめる" in first
    # 冒頭は 現場の要望 ⇔ 経理の制約 → 今回の論点。紙・Excelの説明はその下（開閉式）
    assert first.index("現場の要望") < first.index("経理の制約") < first.index("今回の論点") < first.index("元の記録を残しながら、どう訂正するか？") < first.index("現在の業務")
    assert button(at, "tour_next").label == "次へ：会議前の準備" and not any(b.key == "tour_shortcut" for b in at.button)  # 近道は一覧へ移した
    assert sum(1 for b in at.button if b.label.startswith("次へ：")) == 1  # 冒頭の「次へ」は1つだけ
    assert any(e.label.startswith("案件の詳しい背景") for e in at.expander)
    at = button(at, "tour_next").click().run()
    later = "".join(h.proto.body for h in at.get("html"))
    assert "現場と経理の要望を取りまとめる" not in later and "デモステップ 2/8 · 会議前の準備" in later and "経費申請アプリの刷新｜第1回会議の前" in later and "アプリの支援" in later
    assert any(e.label == "案件の背景を確認" for e in at.expander)


def test_final_screen_flow():
    at = to_end(app())
    assert not at.exception
    html = "".join(h.proto.body for h in at.get("html"))
    # 大見出しは成果物。「デモ完了」は補助表示。見出しの直下に代表例、その後にほかの成果物
    assert 'class="dr-g-h dr-end-h">この案件の要件定義書と成果物' in html and "✓ デモ完了" in html and "要件定義の完了を示すものではありません" in html
    assert html.index("この案件の要件定義書と成果物") < html.index("代表的な要件の例") < html.index("ほかの成果物") < html.index("決まったことと残っていること")
    assert "残っていること：全4件" in html and "主な3件を表示しています" in html
    assert any(e.label == "全4件を見る" for e in at.expander)
    assert len(at.get("download_button")) == 4 and "demo_done" in at.session_state and "d1" in at.session_state["demo_done"]
    assert at.session_state["tour_index"] == 7
    at = button(at, "tour_view_spec").click().run()
    assert not at.exception and at.session_state["tour_index"] == 7 and at.session_state["doc_view"] == "spec"
    assert any("この文書について" in m.value for m in at.markdown)


def test_other_demo_returns_to_demo_list_with_done_mark():
    at = to_end(app())
    at = button(at, "tour_others").click().run()
    assert not at.exception
    assert button(at, "tour_d1").label == "経費申請のデモを見る" and button(at, "tour_d2").label == "売上集計・クラウド移行のデモを見る"
    assert "体験済み" in "".join(h.proto.body for h in at.get("html"))
    at = button(at, "tour_d1").click().run()
    assert at.session_state["tour_index"] == 0 and at.session_state["tour_on"] and "d1" in at.session_state["demo_done"]


def test_final_buttons_and_back_to_step():
    at = to_end(app())
    at = button(at, "tour_end").click().run()
    assert at.session_state["tour_on"] is False and at.session_state["page"] == "overview" and at.session_state["project"]["demo"]["stage"] == 4
    at = button(at, "tour_back").click().run()
    assert at.session_state["tour_on"] and at.session_state["tour_index"] == 7
    at = button(at, "tour_home").click().run()
    assert not at.exception and at.session_state["project"] if "project" in at.session_state else True


def test_play_button_opens_video_in_demo():
    at = button(app(), "tour_d3").click().run()
    for _ in range(2):
        at = button(at, "tour_next").click().run()
    play = next(b for b in at.button if (b.key or "").startswith("play_"))
    assert play.label.startswith("▶") and "から再生" in play.label
    at = play.click().run()
    assert not at.exception and at.get("video")
    assert next(b for b in at.button if (b.key or "").startswith("play_")).label == "■ 動画を閉じる"


def test_lfs_pointer_is_not_treated_as_video(tmp_path):
    from definereq.demos import fetch_media

    pointer = tmp_path / "a.mp4"
    head = "version https://git-lfs.github.com/spec/v1 oid sha256:" + "a" * 64
    pointer.write_bytes(head.encode())
    assert fetch_media.is_pointer(pointer) and fetch_media.expected_hash(pointer) == "a" * 64
    real = next(fetch_media.FILES.glob("*.mp4"))
    assert not fetch_media.is_pointer(real)


def project_app(p, page="overview", **state):
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["project"] = p
    at.session_state["page"] = page
    for k, v in state.items():
        at.session_state[k] = v
    return at.run()


def test_project_panel_can_close_and_reopen_and_has_no_demo_words(blank):
    """見出しの直後に状態の1行と主ボタン。理由などの詳しい説明は画面の下の開閉式の欄にまとめる。"""
    at = project_app(blank, "trail")  # 共通の状態表示を使う画面（質問・議題は「会議へ進む」が主）
    html = "".join(h.proto.body for h in at.get("html"))
    assert "案件を作成した直後" in html and "デモ体験中" not in html and not at.exception
    assert button(at, "guide_go").label == "準備の概要を開く →"
    assert any(e.label == "次にすることの詳しい説明" for e in at.expander)
    labels = [m.value for m in at.markdown]
    assert "**この操作をおすすめする理由**" in labels  # 開閉式の欄の中にある


def test_profile_shows_brief_guidance_and_details_below(blank):
    """背景の画面：見出しの下に短い1行、詳しい説明と作業の段階は入力欄より下に折りたたむ。"""
    at = project_app(blank, "profile")
    html = "".join(h.proto.body for h in at.get("html"))
    assert 'class="dr-brief"' not in html and "デモ体験中" not in html  # 編集中は上部に別工程の案内を出さない
    labels = [e.label for e in at.expander]
    assert "次にすることの詳しい説明" in labels and any(x.startswith("作業の段階を選び直す") for x in labels)


def test_next_action_stays_after_closing_detail_on_other_pages(blank):
    """説明を閉じても、状況の文と次の操作は別の画面でも残る。"""
    blank["profile"]["problem"].update(value="申込をメールで受けている")
    at = project_app(blank, "overview")
    assert button(at, "guide_go").label == "会議を準備する →" and button(at, "guide_alt_0").label == "ほかの作業：議事録を取り込む"
    assert "背景・目的を登録しました" in "".join(h.proto.body for h in at.get("html"))
    at.session_state["page"] = "requirements"
    at.run()
    assert button(at, "guide_go").label == "会議を準備する →"


def test_project_panel_works_without_ai_and_never_calls_it(blank, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("AIが呼ばれました")

    monkeypatch.setattr(ai_gd, "run", boom)
    add_request(blank)
    at = project_app(blank, "profile")
    at = button(at, "guide_go").click().run()
    assert not at.exception and at.session_state["page"] == "prep"


def test_demo_detail_has_no_project_panel():
    at = project_app(builder.build("d1", 4))
    assert not any((b.key or "").startswith("guide_") for b in at.button)
    assert "現在：" not in "".join(h.proto.body for h in at.get("html"))


def test_demo_walk_never_uses_paid_ai(monkeypatch):
    import definereq.ai.client as client

    def boom(*a, **k):
        raise AssertionError("デモでAIが呼ばれました")

    monkeypatch.setattr(client.ClaudeClient, "__init__", boom)
    monkeypatch.setattr(ai_gd, "run", boom)
    at = to_end(app())
    assert not at.exception and at.session_state["tour_index"] == 7


# ---- デモの見どころ・判断・判断後の仕様・終了画面 ----
def html_of(at):
    return "".join(h.proto.body for h in at.get("html"))


def test_shortcut_goes_to_decision_with_issue_line():
    at = button(app(), "tour_d1_hl").click().run()
    assert at.session_state["tour_index"] == 4 and not at.exception
    h = html_of(at)
    assert "この案件の論点" in h and "デモステップ 5/8 · 判断" in h
    assert button(at, "tour_next").label == "次へ：追加要望と影響"


def test_decision_shows_choice_reason_basis_then_table():
    at = button(app(), "tour_d1_hl").click().run()
    h = html_of(at)
    h = h[h.index('class="dr-vd"'):]  # 判断の部品の中で順番を確かめる
    # 採用案と理由1文 → 根拠の短い要約 → 3案の比較。引用の全文と話者未確認の発言は、その後の開閉式の詳細
    order = ["再申請を採用", "元の記録が残り監査で説明できること", "関係者による判断", "根拠：本人の確認メール", "3案の比較", "判断に使っていない発言（話者未確認）"]
    assert [h.index(x) for x in order] == sorted(h.index(x) for x in order)
    assert "発言（話者確認済み）" in h and 'class="dr-t-win"' in h
    labels = [b.label for b in at.button]
    # 出典を開く操作は採用案と理由の近く（「次へ」より前）。「次へ」は1つだけ
    assert labels.index("機能画面でこの判断に使った確認メールを見る") < labels.index("次へ：追加要望と影響") and labels.count("次へ：追加要望と影響") == 1
    assert "機能画面で議事録の該当発言を見る" in labels
    assert any(e.label.startswith("判断の根拠と経緯を見る") for e in at.expander)
    assert button(at, "tour_evidence").label == "機能画面でこの判断に使った確認メールを見る" and button(at, "tour_detail").label == "機能画面で決定・合意を見る"


def test_evidence_and_decision_list_return_to_origin_step():
    base = button(app(), "tour_d1_hl").click().run()
    at = button(base, "tour_evidence").click().run()
    q = at.session_state["project"]
    assert at.session_state["page"] == "sources" and not at.session_state["tour_on"]
    assert next(s for s in q["sources"] if s["id"] == at.session_state["src_sel"])["name"] == "判断の確認メール"
    assert button(at, "tour_back").label == "← デモステップ 5/8『判断』に戻る"
    at = button(at, "tour_back").click().run()
    assert at.session_state["tour_on"] and at.session_state["tour_index"] == 4
    at = button(at, "tour_detail").click().run()
    assert at.session_state["page"] == "decisions" and button(at, "tour_back").label == "← デモステップ 5/8『判断』に戻る"
    # 別のステップから詳細を開いたときは、そのステップへ戻る
    at = button(at, "tour_back").click().run()
    at = button(at, "tour_next").click().run()
    at = button(at, "tour_detail").click().run()
    assert button(at, "tour_back").label == "← デモステップ 6/8『追加要望と影響』に戻る"


def test_after_spec_summary_comes_before_table():
    at = button(app(), "tour_d1").click().run()
    for _ in range(6):
        at = button(at, "tour_next").click().run()
    h = html_of(at)
    h = h[h.index('class="dr-cs"'):]
    order = ["変更前（v1）", "変更後（v2）", "下書きの作成まで", "引き続き守る制約", "承認済みの申請は直接変更しない", "採用理由", "追加要望", "過去の判断との衝突", "採用した対応", "<table"]
    assert [h.index(x) for x in order] == sorted(h.index(x) for x in order)
    assert [b.label for b in at.button if b.label.startswith("次へ：")] == ["次へ：要件定義書と成果物"]
    assert any(e.label.startswith("判断の詳細を見る") for e in at.expander)
    at = button(at, "tour_next").click().run()
    assert at.session_state["tour_index"] == 7 and any(b.label == "要件定義書の全文を見る" for b in at.button)


def test_finale_separates_end_and_open_items_and_puts_next_first():
    at = to_end(app())
    h = html_of(at)
    assert "この案件の要件定義書と成果物" in h and "案件に残る未確認の項目" in h and '<div class="dr-end-n">4件</div>' in h
    labels = [b.label for b in at.button]
    # 代表例の下に、要件定義書の全文とWord。ほかの成果物や機能画面への導線はその後
    assert labels.index("要件定義書の全文を見る") < labels.index("ほかのデモを見る") and labels.index("要件定義書の全文を見る") < labels.index("機能画面でこの案件の現在の状況を見る")
    downloads = [b.label for b in at.get("download_button")]
    assert downloads[0] == "要件定義書をWordでダウンロード"
    assert "要件定義書をWordでダウンロード" in downloads and "要件一覧をExcelでダウンロード" in downloads
    at = button(at, "tour_view_spec").click().run()
    assert any("要件定義書の内容" in m.value for m in at.markdown)


@pytest.mark.parametrize("demo,index,label", [("d1", 4, "ステップ5「判断」から見る"), ("d2", 2, "ステップ3「具体化」から見る"), ("d3", 2, "ステップ3「録画の発言」から見る")])
def test_list_shortcuts_open_highlight_with_premise(demo, index, label):
    """一覧の近道：番号と正式名のリンクで見どころを開き、現在地・前提・最初から見る操作を出す。"""
    at = app()
    assert button(at, f"tour_{demo}_hl").label == label and button(at, f"tour_{demo}_hl").proto.type == "tertiary"
    at = button(at, f"tour_{demo}_hl").click().run()
    h = html_of(at)
    assert at.session_state["tour_index"] == index and not at.exception
    assert f"デモステップ {index + 1}/8 · " in h and 'class="dr-premise"' in h and button(at, "tour_from_start").label == "案件の背景から見る"
    at = button(at, "tour_next").click().run()  # 既存の「次へ」で進める
    assert at.session_state["tour_index"] == index + 1 and 'class="dr-premise"' not in html_of(at)
    at = button(at, "tour_go_0").click().run()  # 最初へ戻ったら、近道の案内は残らない
    assert at.session_state["tour_index"] == 0 and 'class="dr-premise"' not in html_of(at)


# ---- デモの登録内容と根拠の閲覧 ----
def demo_at(demo="d1", step=None):
    at = button(app(), f"tour_{demo}").click().run()
    if step is not None:
        at = button(at, f"tour_go_{step}").click().run()
    return at


@pytest.mark.parametrize("demo", ["d1", "d2", "d3"])
def test_demo_profile_and_sources_are_browsable(demo):
    at = demo_at(demo)
    at = button(at, "tour_profile").click().run()  # 冒頭の「機能画面で背景・目的・関係者を見る」
    h = html_of(at)
    assert at.session_state["page"] == "profile" and "デモデータ · 閲覧専用" in h and button(at, "tour_back").label == "← デモステップ 1/8『案件の背景』に戻る"
    p = at.session_state["project"]
    assert p["stakeholders"] and any(v["value"] for v in p["profile"].values())
    at = button(at, "nav_group_2").click().run()  # 共通サイドバー：記録の取り込み・整理 → 会議の記録を整理
    at = button(at, "nav_sources").click().run()
    h = html_of(at)
    assert at.session_state["page"] == "sources" and "デモデータ · 閲覧専用" in h and "収録されている本文" in h
    assert not any(t.key and t.key.startswith("paste_b_") for t in at.text_area)  # 登録の操作は出さない


def test_d1_decision_opens_mail_and_speech_then_returns():
    at = demo_at("d1", 4)
    at = button(at, "tour_evidence").click().run()
    h = html_of(at)
    assert at.session_state["page"] == "sources" and "開いた根拠の箇所" in h and "金額の訂正は再申請とする方式を承認します" in h
    at = button(at, "tour_back").click().run()
    assert at.session_state["tour_index"] == 4 and button(at, "tour_next").label == "次へ：追加要望と影響"
    at = button(at, "tour_ev_speech").click().run()
    h = html_of(at)
    assert at.session_state["page"] == "recordings" and "開いた発言" in h and "話者確認：確認済み" in h


def test_d3_speech_opens_recording_segment():
    at = demo_at("d3", 2)
    at = button(at, "tour_ev_sp_0").click().run()
    h = html_of(at)
    assert at.session_state["page"] == "recordings" and "開いた発言" in h and "外部からの遠隔保守を提案します" in h
    assert button(at, "tour_back").label == "← デモステップ 3/8『録画の発言』に戻る"


def test_d2_decision_links_to_its_sources():
    at = demo_at("d2", 4)  # 停止の調整（判断あり）
    evs = [b for b in at.button if b.key and b.key.startswith("tour_ev_")]
    assert evs and all("該当" in b.label for b in evs)
    at = evs[0].click().run()
    assert at.session_state["page"] in ("sources", "recordings") and ("開いた根拠の箇所" in html_of(at) or "開いた発言" in html_of(at))


# ---- 残件から関係する要件を開く、ボタン名と行き先の名前 ----
def demo_overview(demo, stage_step=0):
    at = demo_at(demo, stage_step or None)
    return button(at, "nav_overview").click().run() if any(b.key == "nav_overview" for b in at.sidebar.button) else \
        button(button(at, "nav_group_0").click().run(), "nav_overview").click().run()


def test_d3_todo_opens_its_requirement_and_returns():
    at = demo_overview("d3")
    link = next(b for b in at.button if b.key and b.key.startswith("todo_req_") and b.label == "この残件に関係する要件を見る")
    at = link.click().run()
    h = html_of(at)
    assert at.session_state["page"] == "requirements" and "拠点ネットワーク更新と遠隔保守の要件一覧" in h
    assert "新しいネットワークや運用が満たすべき条件" in h and "に関係する要件 1件" in h and "閲覧専用" in "".join(c.value for c in at.caption)
    assert at.session_state["project"]["demo"]["stage"] == 2  # 段階は変わらない
    at = button(at, "req_back").click().run()
    assert at.session_state["page"] == "overview" and button(at, "tour_back").label.startswith("← デモステップ 1/8")
    at.session_state["page"] = "requirements"  # 通常の要件一覧には、前の絞り込みが残らない
    at.run()
    assert "に関係する要件" not in html_of(at)


def test_backlog_link_shows_count_for_multiple_requirements():
    from definereq.demos.builder import build
    from definereq.logic import checks

    p = build("d1", 3)
    multi = [i for items in checks.backlog(p)["categories"].values() for i in items if len(checks.related_requirements(p, i["target"])) > 1]
    assert multi  # 追加要望は2件の要件にひもづく
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["project"], at.session_state["page"] = p, "overview"
    at.run()
    labels = [b.label for b in at.button if b.key and b.key.startswith("bl_req_")]
    assert any(x.startswith("この残件に関係する要件を見る（") and x.endswith("件）") for x in labels)
    assert button(at, "bl_all_reqs").label == "この案件の要件一覧を見る"


def test_demo_function_page_resumes_tour():
    at = demo_overview("d1")
    resume = next(b for b in at.button if b.key and b.key.startswith("demo_resume_"))
    assert resume.label == "デモの続きに戻る（デモステップ 1/8『案件の背景』）" and resume.proto.type == "primary"
    assert next(b for b in at.button if b.key == "next_overview").label == "この案件の要件一覧を見る"
    at = resume.click().run()
    assert at.session_state["tour_on"] and at.session_state["tour_index"] == 0


@pytest.mark.parametrize("demo", ["d1", "d2", "d3"])
def test_step_labels_match_destination(demo):
    """「次へ」のボタン名、移動後の本文の現在地、サイドバーのデモのステップが同じ名前。"""
    from definereq.demos import guide as demo_guide

    steps = demo_guide.load(demo)
    at = demo_at(demo)
    for n in range(len(steps) - 1):
        nxt = button(at, "tour_next")
        assert nxt.label == f"次へ：{steps[n + 1]['process']}", n
        at = nxt.click().run()
        assert f"デモステップ {n + 2}/8 · {steps[n + 1]['process']}" in html_of(at)
        assert not any(b.key and b.key.startswith("tour_side_") for b in at.sidebar.button)  # ステップ一覧は本文に集約


# ---- 工程を開いても、直前のデモステップへ戻って続きを見る ----
@pytest.mark.parametrize("entry", ["body", "sidebar"])
def test_open_process_and_return_to_step(entry):
    at = demo_at("d1", 2)  # デモステップ 3/8
    if entry == "body":
        at = button(at, "tour_detail").click().run()  # 本文の補助ボタン（機能画面で〇〇を見る）
    else:
        at = button(at, "nav_group_3").click().run()  # サイドバーの工程を開き、機能を選ぶ
        assert at.session_state["tour_on"] and at.session_state["tour_index"] == 2
        at = button(at, "nav_candidates").click().run()
    assert not at.session_state["tour_on"] and button(at, "tour_back").label == "← デモステップ 3/8『会議後の整理』に戻る"
    page = at.session_state["page"]
    assert button(at, f"nav_{page}").proto.type == "primary"  # 実際に表示しているページだけを選択
    assert sum(1 for b in at.sidebar.button if b.proto.type == "primary") == 1
    at = button(at, "nav_requirements").click().run()  # 工程内で別ページへ移動しても戻り先を保つ
    assert button(at, "tour_back").label == "← デモステップ 3/8『会議後の整理』に戻る"
    at = button(at, "tour_back").click().run()
    assert at.session_state["tour_on"] and at.session_state["tour_index"] == 2 and "デモステップ 3/8 · 会議後の整理" in html_of(at)
    # 戻ると機能ページの選択表示は外れ、サイドバーは機能画面を開く前の開閉状態に戻る
    side = {b.key for b in at.sidebar.button}
    assert not any(b.proto.type == "primary" for b in at.sidebar.button)
    assert ("nav_candidates" in side) == (entry == "sidebar") and "nav_records" not in side
    at = button(at, "tour_next").click().run()
    assert at.session_state["tour_index"] == 3


def test_body_detail_button_names_the_page():
    at = demo_at("d1", 2)
    assert button(at, "tour_detail").label == "機能画面でAI候補を見る"
    assert button(at, "tour_detail").proto.type == "tertiary" and button(at, "tour_next").proto.type == "primary"


def test_highlight_start_is_the_return_point_and_restart():
    at = button(app(), "tour_d1_hl").click().run()
    at = button(at, "nav_group_1").click().run()  # 案内中は工程を開くだけ。機能を選ぶと機能画面へ
    at = button(at, "nav_prep").click().run()
    assert button(at, "tour_back").label == "← デモステップ 5/8『判断』に戻る"
    at = button(at, "nav_tour").click().run()  # デモを最初から見る
    assert at.session_state["tour_on"] and at.session_state["tour_index"] == 0
    at = button(at, "nav_home").click().run()
    at = button(at, "tour_d3").click().run()  # 別のデモは、そのデモの開始位置から
    assert at.session_state["project"]["demo"]["id"] == "d3" and at.session_state["tour_index"] == 0


# ---- デモ冒頭から会議後の状況へ飛ばない。残件は会議後の場面で、その時点のデータで見せる ----
@pytest.mark.parametrize("demo", ["d1", "d2", "d3"])
def test_step1_has_no_jump_to_post_meeting_state(demo):
    at = demo_at(demo)
    keys = {b.key for b in at.button}
    assert "tour_detail" not in keys and "tour_todo_open" not in keys and "tour_profile" in keys
    assert button(at, "tour_next").label == "次へ：会議前の準備"
    at = button(at, "tour_next").click().run()
    assert at.session_state["tour_index"] == 1 and "デモステップ 2/8 · 会議前の準備" in html_of(at)


@pytest.mark.parametrize("demo", ["d1", "d2", "d3"])
def test_post_meeting_todo_link_shows_same_time_and_returns(demo):
    from definereq.demos import guide as demo_guide
    from definereq.ui.guide import first_after_meeting

    steps = demo_guide.load(demo)
    n = first_after_meeting(steps)
    at = demo_at(demo, n)
    assert sum(1 for b in at.button if b.key == "tour_todo_open") == 1
    assert any("会議後の時点" in c.value for c in at.caption)
    at = button(at, "tour_todo_open").click().run()
    assert at.session_state["page"] == "overview" and at.session_state["project"]["demo"]["stage"] == 2
    body = html_of(at)
    assert "表示中のデータ：会議後の時点" in body and "デモの段階" not in body
    assert button(at, "tour_back").label == f"← デモステップ {n + 1}/8『{steps[n]['process']}』に戻る"
    at = button(at, "tour_back").click().run()
    assert at.session_state["tour_on"] and at.session_state["tour_index"] == n
    at = button(at, "tour_next").click().run()
    assert at.session_state["tour_index"] == n + 1


def test_sidebar_overview_from_step1_shows_time_and_return():
    at = demo_at("d3")
    at = button(at, "nav_group_0").click().run()
    at = button(at, "nav_overview").click().run()
    assert "表示中のデータ：会議後の時点" in html_of(at)
    assert button(at, "tour_back").label == "← デモステップ 1/8『案件の背景』に戻る"
    assert any(s.label.startswith("表示するデータの時点") for s in at.get("button_group"))
    at = button(at, "tour_back").click().run()
    assert at.session_state["tour_on"] and at.session_state["tour_index"] == 0



@pytest.mark.parametrize("demo,rid,did", [("d1", "REQ-002", "DEC-004"), ("d2", "REQ-004", "DEC-005"), ("d3", "REQ-006", "DEC-001")])
def test_finale_shows_representative_requirement_first(demo, rid, did):
    """最終画面：代表的な要件1件を追加操作なしで読める（内容・状態・元の記録・判断と理由）。値は既存のデモデータ。"""
    from definereq.demos import builder

    at = demo_at(demo, 7)
    h = html_of(at)
    p = builder.build(demo, 4)
    r = next(x for x in p["requirements"] if x["id"] == rid)
    d = next(x for x in p["decisions"] if x["id"] == did)
    rep = h[h.index('class="dr-rep"'):]
    assert f"{rid} {r['title']}" in rep and f"状態：{r['status']}" in rep and r["body"][:20] in rep
    assert "元の記録" in rep and r["evidence"][0]["quote"][:10] in rep
    assert d["topic"] in rep and d["rationale"][:15] in rep
    assert h.index("この案件の要件定義書と成果物") < h.index('class="dr-rep"')
    assert [b.label for b in at.get("download_button")][0] == "要件定義書をWordでダウンロード"
    at = button(at, "tour_view_spec").click().run()
    assert not at.exception and at.session_state["doc_view"] == "spec" and at.session_state["tour_index"] == 7
