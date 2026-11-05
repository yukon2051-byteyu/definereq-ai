"""出力・JSON・デモ・公開構成の検証。"""
import io
import json
import re
from pathlib import Path

import pytest
from docx import Document
from openpyxl import load_workbook

from definereq import config
from definereq import project as pj
from definereq.ai import tasks as ai
from definereq.demos import builder
from definereq.export import excelx, jsonio, share, wordx
from definereq.logic import checks, why
from definereq.logic import evidence as ev
from definereq.schema import COLLECTIONS

ROOT = Path(__file__).resolve().parent.parent
DEMOS = ["d1", "d2", "d3"]


@pytest.fixture(scope="module")
def built():
    return {d: builder.build(d, 4) for d in DEMOS}


def docx_text(data: bytes) -> str:
    d = Document(io.BytesIO(data))
    parts = [x.text for x in d.paragraphs]
    for t in d.tables:
        for r in t.rows:
            parts += [c.text for c in r.cells]
    for s in d.sections:
        parts += [x.text for x in s.header.paragraphs]
    return "\n".join(parts)


# ---- 文書 ----
@pytest.mark.parametrize("demo", DEMOS)
@pytest.mark.parametrize("doc", ["meeting", "change", "spec"])
def test_word_has_id_version_and_no_internal_memo(built, demo, doc):
    p = built[demo]
    text = docx_text(wordx.render(p, share.Options(doc_type=doc), "DOC-009", 3, "2026-11-05T10:00:00"))
    assert "DOC-009" in text and "v3" in text and "合意を意味しません" in text
    assert "内部メモ" not in text.replace("内部メモ除外", "")
    notes = [r["internal_note"] for r in p["requirements"] if r.get("internal_note")]
    assert notes and not any(n in text for n in notes)


def test_internal_memo_only_when_chosen(built):
    p = built["d1"]
    data = wordx.render(p, share.Options(doc_type="spec", include_internal=True), "D", 1, "2026-11-05T10:00:00")
    assert "現場の不満が強い点" in docx_text(data)
    assert "社外共有不可" in docx_text(data)


def test_word_has_page_number_field(built):
    data = wordx.render(built["d1"], share.Options(doc_type="meeting"), "D", 1, "2026-11-05T10:00:00")
    d = Document(io.BytesIO(data))
    assert "PAGE" in d.sections[0].footer._element.xml and "NUMPAGES" in d.sections[0].footer._element.xml


def test_word_table_column_widths_are_applied(built):
    data = wordx.render(built["d1"], share.Options(doc_type="spec"), "D", 1, "2026-11-05T10:00:00")
    t = max(Document(io.BytesIO(data)).tables, key=lambda x: len(x.columns))
    widths = {c.width for c in t.columns}
    assert len(widths) > 1


def test_quotes_not_published_unless_selected(built):
    p = built["d3"]
    quote = "外部からの遠隔保守を提案します"
    text = docx_text(wordx.render(p, share.Options(doc_type="meeting"), "D", 1, "2026-11-05T10:00:00"))
    assert quote not in text
    key = next(q["key"] for q in share.quotable(p) if q["quote"] == quote and q["item"].startswith("REQ"))
    opt = share.Options(doc_type="meeting", quote_keys={key})
    assert not any(quote in str(s.paragraphs) for s in share.build(p, share.Options(doc_type="meeting")))
    assert any(quote in str(s.paragraphs) for s in share.build(p, opt))


def test_recording_full_text_not_published(built):
    p = built["d3"]
    text = docx_text(wordx.render(p, share.Options(doc_type="spec"), "D", 1, "2026-11-05T10:00:00"))
    assert "本日は大阪拠点のネットワーク更新について確認します" not in text


def test_meeting_doc_separates_decided_and_proposed():
    p = builder.build("d1", 2)
    secs = {s.heading: s for s in share.build(p, share.Options(doc_type="meeting"))}
    decided = str(secs["決定事項"].table["rows"])
    proposed = str(secs["提案・確認待ちの事項"].table["rows"])
    assert "再申請" in decided and "役割ごとの権限" in proposed
    assert "承認後の申請は変更しない" not in proposed


def test_confirmation_ids_and_answer_column():
    p = builder.build("d1", 1)
    sec = next(s for s in share.build(p, share.Options(doc_type="meeting")) if s.heading == "ご質問")
    assert sec.table["rows"][0][0].startswith("確認-QST-") and sec.table["columns"][-1] == "回答欄"


def test_excluded_item_not_in_doc(built):
    p = built["d1"]
    rid = p["requirements"][0]["id"]
    title = p["requirements"][0]["title"]
    secs = share.build(p, share.Options(doc_type="meeting", exclude_ids={rid}))
    assert title not in str([s.table for s in secs if s.heading == "提案・確認待ちの事項"])


@pytest.mark.parametrize("domains,want,absent", [(["app"], "業務アプリ：画面・帳票", "ネットワーク：分離"), (["network"], "ネットワーク：分離", "業務アプリ：画面・帳票"),
                                                 (["infra"], "インフラ：配置制約", "業務アプリ：業務")])
def test_spec_chapters_by_domain(domains, want, absent):
    p = pj.new_project("t", domains)
    heads = [s.heading for s in share.build(p, share.Options(doc_type="spec"))]
    assert want in heads and absent not in heads


def test_composite_spec_has_shared_section():
    p = builder.build("d2", 4)
    pj.add(p, "requirements", pj.new_requirement(title="共通の要件", body="x", kind=None))
    heads = [s.heading for s in share.build(p, share.Options(doc_type="spec"))]
    assert "共通・分野をまたぐ要件" in heads and "業務アプリ：機能" in heads and "インフラ：復旧" in heads


def test_spec_marks_draft_with_pending():
    p = builder.build("d2", 4)
    sec = share.build(p, share.Options(doc_type="spec"))[0]
    assert any("確認待ち" in x for x in sec.paragraphs)


def test_document_says_not_electronic_signature(built):
    secs = share.build(built["d1"], share.Options(doc_type="spec"))
    assert "電子署名ではありません" in str(next(s for s in secs if s.heading == "合意").paragraphs)


def test_change_doc_has_before_after_and_conclusion(built):
    p = built["d1"]
    secs = {s.heading: s for s in share.build(p, share.Options(doc_type="change", change_id=p["changes"][0]["id"]))}
    assert "代行作成" in str(secs["変更前後"].table["rows"]) and "合意済み" in str(secs["結論"].paragraphs)
    assert "未調査の領域" in str(secs["影響"].paragraphs)


def test_response_links_doc_version_and_item(built):
    r = built["d1"]["responses"][0]
    assert r["doc_id"].startswith("DOC-") and r["doc_version"] == 1 and r["item_id"].startswith("REQ-")


# ---- Excel ----
def test_excel_sheets_and_memo_excluded(built):
    p = built["d1"]
    wb = load_workbook(io.BytesIO(excelx.render(p)))
    assert {"要件", "質問", "残件", "リスク", "履歴"} <= set(wb.sheetnames)
    assert "内部メモ" not in [c.value for c in wb["要件"][1]]
    assert "内部メモ" in [c.value for c in load_workbook(io.BytesIO(excelx.render(p, True)))["要件"][1]]


@pytest.mark.parametrize("v", ["=HYPERLINK(\"http://x\")", "+1+1", "-1", "@SUM(A1)", "＝1"])
def test_excel_formula_injection_blocked(project, v):
    pj.add(project, "requirements", pj.new_requirement(title=v, body=v))
    ws = load_workbook(io.BytesIO(excelx.render(project)))["要件"]
    cell = ws["E2"]
    assert cell.value.startswith("'") and cell.data_type == "s"


def test_excel_shows_both_totals(built):
    ws = load_workbook(io.BytesIO(excelx.render(built["d2"])))["残件"]
    assert any("重複を除いた対象" in str(c.value) for row in ws.iter_rows() for c in row)


# ---- JSON ----
@pytest.mark.parametrize("demo", DEMOS)
def test_json_roundtrip_keeps_all_data(built, demo):
    p = built[demo]
    q = jsonio.loads(jsonio.dumps(p))
    for key in list(COLLECTIONS) + ["profile", "prep", "nfr_status", "domains", "traits"]:
        assert q[key] == json.loads(json.dumps(p[key], default=str)), key


def corrupt(p, fn):
    q = json.loads(jsonio.dumps(p))
    fn(q)
    return json.dumps(q).encode()


@pytest.mark.parametrize("name,fn", [
    ("app", lambda q: q.update(app="other")),
    ("dup", lambda q: q["requirements"].append(dict(q["requirements"][0]))),
    ("state", lambda q: q["requirements"][0].update(status="謎の状態")),
    ("ref", lambda q: q["requirements"][0].update(related=["REQ-999"])),
    ("evidence", lambda q: q["requirements"][0]["evidence"].append({"source_id": "SRC-999"})),
    ("missing", lambda q: q.pop("decisions")),
    ("domain", lambda q: q.update(domains=["x"])),
    ("name", lambda q: q.update(name="")),
])
def test_invalid_json_rejected(built, name, fn):
    with pytest.raises(jsonio.LoadError):
        jsonio.loads(corrupt(built["d1"], fn))


def test_broken_json_text():
    with pytest.raises(jsonio.LoadError):
        jsonio.loads(b"{broken")


def test_demo_json_resumes_as_normal_project(built):
    q = jsonio.loads(jsonio.dumps(built["d1"]))
    assert q["is_demo"] is False and q["demo"] is None and q["from_demo"] is True


# ---- デモ ----
@pytest.mark.parametrize("demo", DEMOS)
@pytest.mark.parametrize("stage", [1, 2, 3, 4])
def test_all_demo_evidence_verified(demo, stage):
    assert ev.verify_all(builder.build(demo, stage)) == []


def test_demos_are_differentiated(built):
    assert builder.build("d1", 1)["domains"] != built["d2"]["domains"] != built["d3"]["domains"]
    kinds = {d: {s["file_kind"] for s in built[d]["sources"]} for d in DEMOS}
    assert "pdf" in kinds["d1"] and "pptx" in kinds["d2"] and "xlsx" in kinds["d3"]
    assert built["d3"]["recordings"][0]["method"] == "prepared" and built["d1"]["recordings"][0]["method"] == "subtitle"
    titles = [{r["title"] for r in built[d]["requirements"]} for d in DEMOS]
    assert not (titles[0] & titles[1]) and not (titles[1] & titles[2])


@pytest.mark.parametrize("demo", DEMOS)
def test_demo_covers_main_features(built, demo):
    p = built[demo]
    for key in ("sources", "questions", "candidates", "requirements", "issues", "scenarios", "decisions", "changes", "conflicts", "risks", "history", "baselines", "shared_docs"):
        assert p[key], key
    assert {d["doc_type"] for d in p["shared_docs"]} == {"meeting", "change", "spec"}
    assert any(c["state"] != "候補" for c in p["candidates"])
    assert any(r.get("acceptance") for r in p["requirements"])
    assert any(r["status"] == "合意済み" for r in p["requirements"])
    assert any(r["scope"] == "次回以降" for r in p["requirements"])
    assert any(s["kind"] == "例外" for s in p["scenarios"])


def test_d1_expected_story(built):
    p = built["d1"]
    assert any(d["adopted"] == "C" and d["state"] == "合意済み" for d in p["decisions"])
    assert any(d["state"] == "保留" for d in p["decisions"])
    assert any(h["outcome"] == "却下" for h in p["history"])
    assert any(c["state"] == "却下" and c["unsupported_numbers"] for c in p["candidates"])


def test_d2_expected_story(built):
    p = built["d2"]
    assert any(m["status"] == "未計測" for r in p["requirements"] for m in r["measures"])
    assert any(w for s in p["sources"] for w in s["warnings"] if "理解していません" in w)
    assert next(s for s in p["sources"] if s["file_kind"] == "pptx")["supplement"]


def test_d3_proposal_is_not_agreed_at_meeting_stage():
    p = builder.build("d3", 2)
    r = next(x for x in p["requirements"] if x["title"] == "保守会社の遠隔保守")
    assert r["status"] == "提案" and p["decisions"][0]["state"] == "確認待ち"
    speakers = {s["speaker"] for s in p["recordings"][0]["segments"]}
    assert "岡田" in speakers


def test_d3_video_exists_and_transcript_matches():
    from definereq.media import probe

    rec = builder.build("d3", 2)["recordings"][0]
    info = probe.probe(str(config.DEMO_FILES / rec["video_file"]))
    assert abs(info.duration - rec["segments"][-1]["end"]) < 3


def test_d1_final_speaker_left_unconfirmed():
    segs = builder.build("d1", 2)["recordings"][0]["segments"]
    assert segs[-1]["speaker_status"] == "未確認"


def test_stages_progress():
    counts = [len(builder.build("d1", s)["requirements"]) for s in (1, 2, 3, 4)]
    assert counts[0] == 0 < counts[1] <= counts[2] <= counts[3]
    assert not builder.build("d1", 1)["decisions"] and builder.build("d1", 4)["decisions"]


def test_demo_prepared_results_are_labeled_and_free(built):
    for p in built.values():
        assert p["ai_runs"] and all(r["source"] == "準備済み" and r["cost_jpy"] == 0 for r in p["ai_runs"])


def test_demo_edit_marks_prepared_result_stale():
    p = builder.build("d2", 1)
    run = p["ai_runs"][0]
    assert ai.run_status(p, run) == "最新"
    p["sources"][1]["units"][0]["text"] = "編集した内容"
    assert "古い結果" in ai.run_status(p, run)


def test_demo_copies_are_isolated():
    a = builder.build("d1", 4)
    b = builder.build("d1", 4)
    a["requirements"][0]["title"] = "利用者Aの編集"
    assert b["requirements"][0]["title"] != "利用者Aの編集"
    assert a["id"] != b["id"] or a is not b


def test_demo_runs_without_keys_or_network(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    import definereq.ai.client as c

    monkeypatch.setattr(c, "ClaudeClient", lambda: pytest.fail("デモでAPIを呼びました"))
    assert builder.build("d2", 4)["requirements"]


def test_tour_covers_all_stages():
    for d in builder.catalog():
        assert 6 <= len(d["tour"]) <= 9
        assert {s["stage"] for s in d["tour"]} == {1, 2, 3, 4}


def test_sources_contain_no_real_secrets_or_keys():
    pattern = re.compile(r"sk-ant-[A-Za-z0-9]|sk-[A-Za-z0-9]{20}|hf_[A-Za-z0-9]{20}|postgres(ql)?://[^\"'\s]+:[^\"'\s]+@(?!127)")
    for path in list(ROOT.glob("definereq/**/*.py")) + list(ROOT.glob("*.*")):
        if path.suffix in (".py", ".toml", ".md", ".txt"):
            assert not pattern.search(path.read_text(encoding="utf-8", errors="ignore")), path


def test_backlog_consistent_in_demo(built):
    b = checks.backlog(built["d2"])
    assert b["unique_total"] <= b["category_total"]
