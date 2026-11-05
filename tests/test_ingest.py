"""資料読込：位置の保持、PowerPoint、異常なファイル。"""
import io
import zipfile

import pytest

from definereq import config
from definereq.ingest import formats as f
from definereq.ingest import registry
from definereq.ingest.safety import IngestError, check_zip, safe_filename

FILES = config.DEMO_FILES


def read(name):
    return f.parse_file(name, (FILES / name).read_bytes())[1]


def test_text_lines_and_shift_jis():
    _, p = f.parse_file("a.txt", "一行目\n\n三行目".encode("cp932"))
    assert [u["locator"] for u in p.units] == ["1行目", "3行目"]
    assert any("Shift_JIS" in w for w in p.warnings)


def test_pdf_page_location_and_article_split():
    p = read("d1_経費申請規程.pdf")
    assert {u["locator"] for u in p.units} == {"p.1"}
    assert any("第5条" in u["text"] and "第6条" not in u["text"] for u in p.units)


def test_docx_heading_paragraph_and_table():
    p = read("d1_第1回議事録.docx")
    assert any("見出し「発言要旨」 第1段落" == u["locator"] for u in p.units)
    assert any("表1" in u["locator"] for u in p.units)


def test_xlsx_sheet_and_cell():
    p = read("d2_現状の処理量.xlsx")
    assert any(u["locator"].startswith("シート「提出の実績」 A2") for u in p.units)


def test_xlsx_formula_not_executed_and_hidden_sheet_skipped():
    from openpyxl import Workbook

    wb = Workbook()
    wb.active["A1"] = "=1+1"
    hidden = wb.create_sheet("秘密")
    hidden["A1"] = "見せない"
    hidden.sheet_state = "hidden"
    buf = io.BytesIO()
    wb.save(buf)
    _, p = f.parse_file("x.xlsx", buf.getvalue())
    assert not any("見せない" in u["text"] for u in p.units)
    assert any("非表示" in w for w in p.warnings)


def test_pptx_slide_table_group_and_notes_default_excluded():
    p = read("d2_移行計画案.pptx")
    loc = [u["locator"] for u in p.units]
    assert any("スライド2" in x and "表" in x for x in loc)
    assert any("グループ" in x and u["text"] == "締め後の数字は固定する" for x, u in zip(loc, p.units))
    notes = [u for u in p.units if "発表者ノート" in u["locator"]]
    assert notes and all(u["target"] is False for u in notes)


def test_pptx_marks_diagrams_as_not_understood():
    p = read("d2_移行計画案.pptx")
    assert any("理解していません" in w for w in p.warnings)
    assert any(s["not_understood"] for s in p.extra["slides"])


def test_vtt_time_and_speaker_label():
    segs = f.parse_subtitles((FILES / "d1_第2回字幕.vtt").read_text(encoding="utf-8"))
    assert segs[0]["speaker_label"] == "佐藤" and segs[0]["start"] == 3.0


def test_srt_comma_time():
    segs = f.parse_subtitles("1\n00:00:01,500 --> 00:00:02,000\n田中: 発言\n")
    assert segs == [{"start": 1.5, "end": 2.0, "speaker_label": "田中", "text": "発言"}]


@pytest.mark.parametrize("name,msg", [("a.doc", ".docx"), ("a.xlsm", "マクロ"), ("a.exe", "未対応")])
def test_unsupported_formats(name, msg):
    with pytest.raises(IngestError, match=msg):
        f.parse_file(name, b"x")


def test_empty_file():
    with pytest.raises(IngestError, match="空"):
        f.parse_file("a.txt", b"")


def test_broken_office_file():
    with pytest.raises(IngestError):
        f.parse_file("a.docx", b"not a zip")


def test_garbled_warning():
    _, p = f.parse_file("a.txt", ("\ufffd" * 50).encode("utf-8"))
    assert any("文字化け" in w for w in p.warnings)


def test_zip_bomb_rejected(monkeypatch):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("big.xml", b"0" * (30 * 1024 * 1024))
    with pytest.raises(IngestError, match="圧縮率"):
        check_zip(buf.getvalue())


@pytest.mark.parametrize("raw,want", [("../../etc/passwd", "passwd"), ("C:\\x\\y.pdf", "y.pdf"), ("a<b>.txt", "a_b_.txt"), ("", "無題")])
def test_safe_filename(raw, want):
    assert safe_filename(raw) == want


def test_reimport_increases_version_and_keeps_old(project):
    a = registry.ingest_bytes(project, "a.txt", "旧本文".encode())
    b = registry.ingest_bytes(project, "a.txt", "新本文".encode())
    assert b["version"] == 2 and a["superseded_by"] == b["id"]
    assert [u["text"] for u in registry.target_units(project)] == ["新本文"]


def test_excluded_unit_not_in_targets(project):
    s = registry.ingest_bytes(project, "a.txt", "一\n二".encode())
    registry.set_unit_target(project, s["id"], {s["units"][0]["id"]}, False)
    assert [u["text"] for u in registry.target_units(project)] == ["二"]
