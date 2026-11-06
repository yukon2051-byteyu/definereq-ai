"""Word 出力。日本語フォント・表の列幅・ページ番号・版の表示を整える。"""
from __future__ import annotations

import io
import re

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .. import schema
from . import share

FONT = "Yu Gothic"
ACCENT = RGBColor(0xD9, 0x33, 0x0F)
INK = RGBColor(0x16, 0x16, 0x18)
MUTED = RGBColor(0x5A, 0x5C, 0x63)


def clean(text) -> str:
    """Wordが受け付けない制御文字を除く。"""
    return "".join(c for c in str(text if text is not None else "") if c in "\t\n\r" or ord(c) >= 32)


def _font(run, size=None, bold=None, color=None):
    run.font.name = FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def _shade(cell, hex_color: str):
    pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    pr.append(shd)


def _field(paragraph, code: str):
    run = paragraph.add_run()
    for tag, text in (("begin", None), (None, code), ("end", None)):
        if tag:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), tag)
        else:
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = text
        run._r.append(el)
    _font(run, 8, color=MUTED)


# 折り返すと読みにくい列の最小幅（cm）。IDや日付が途中で切れないようにする
MIN_WIDTH = {"ID": 1.8, "要件": 1.8, "対象": 1.8, "判断日": 2.2, "確認ID": 2.7, "版": 0.9, "状態": 1.6, "期限": 2.2}


def fit_widths(cols: list[str], widths: list[float], total: float) -> list[float]:
    """列幅を合計 total に合わせ、最小幅に足りない分は最も広い列から回す。"""
    out = [w * total / sum(widths) for w in widths]
    for i, name in enumerate(cols):
        need = MIN_WIDTH.get(name, 0) - out[i]
        if need > 0:
            out[i] += need
            out[out.index(max(out))] -= need
    return out


def _table(doc: Document, table: dict, total_cm: float):
    rows, cols = table.get("rows") or [], table["columns"]
    if not rows:
        p = doc.add_paragraph()
        _font(p.add_run("（該当する項目はありません）"), 9, color=MUTED)
        return
    t = doc.add_table(rows=1, cols=len(cols))
    t.style = "Table Grid"
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    widths = fit_widths(cols, table.get("widths") or [1] * len(cols), total_cm)
    for i, c in enumerate(cols):
        cell = t.rows[0].cells[i]
        cell.text = ""
        _font(cell.paragraphs[0].add_run(c), 8.5, True, RGBColor(0xFF, 0xFF, 0xFF))
        cell.paragraphs[0].paragraph_format.keep_with_next = True  # 見出し行だけがページ末に残らないようにする
        _shade(cell, "161618")
    trpr = t.rows[0]._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    trpr.append(header)
    for row in rows:
        added = t.add_row()
        no_split = OxmlElement("w:cantSplit")  # 行の途中で改ページしない
        added._tr.get_or_add_trPr().append(no_split)
        cells = added.cells
        for i, v in enumerate(row):
            cells[i].text = ""
            _font(cells[i].paragraphs[0].add_run(clean(v)), 8.5)
    # Word は表の列定義（grid）を優先するため、列とセルの両方に幅を設定する
    for i, w in enumerate(widths):
        t.columns[i].width = Cm(w)
    for row in t.rows:
        for i, w in enumerate(widths):
            row.cells[i].width = Cm(w)
    doc.add_paragraph()


def render(p: dict, opt: share.Options, doc_id: str, version: int, issued_at: str) -> bytes:
    title = schema.DOC_TYPES[opt.doc_type]
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.0)
    sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2.0)
    total = 17.0
    style = doc.styles["Normal"]
    style.font.name = FONT
    style.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    style.font.size = Pt(10)
    for level, size in ((1, 14), (2, 11.5)):
        h = doc.styles[f"Heading {level}"]
        h.font.name, h.font.size, h.font.bold = FONT, Pt(size), True
        h.font.color.rgb = INK
        h.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)

    # 見出しが表から離れて改ページされないようにする
    doc.styles["Heading 1"].paragraph_format.keep_with_next = True
    doc.styles["Heading 2"].paragraph_format.keep_with_next = True
    head = sec.header.paragraphs[0]
    sample = "【サンプル・架空案件】" if p.get("is_demo") or p.get("from_demo") else ""
    _font(head.add_run(clean(f"{sample}{p['name']}　{title}　{doc_id} 第{version}版")), 8, color=MUTED)
    foot = sec.footer.paragraphs[0]
    foot.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _field(foot, "PAGE")
    _font(foot.add_run(" / "), 8, color=MUTED)
    _field(foot, "NUMPAGES")

    para = doc.add_paragraph()
    _font(para.add_run(clean(title)), 22, True, INK)
    para = doc.add_paragraph()
    _font(para.add_run(clean(p["name"])), 12, True, ACCENT)
    meta = doc.add_paragraph()
    scope = "内部メモ含む（社外共有不可）" if opt.include_internal else "内部メモ除外"
    _font(meta.add_run(clean(f"資料ID：{doc_id}　版：第{version}版　作成日時：{issued_at[:16].replace('T', ' ')}　範囲：{scope}")), 9, color=MUTED)
    if p.get("is_demo") or p.get("from_demo"):
        note = doc.add_paragraph()
        _font(note.add_run("【サンプル】本資料は架空の案件データから作成したサンプルです。実在の組織・案件とは関係ありません。"), 9, True, ACCENT)
    note = doc.add_paragraph()
    _font(note.add_run("本資料の送付は合意を意味しません。回答欄へのご記入をお願いします。"), 9, color=MUTED)

    for s in share.build(p, opt):
        doc.add_heading(clean(s.heading), level=s.level)
        for text in s.paragraphs:
            para = doc.add_paragraph()
            _font(para.add_run(clean(text)), 10)
            para.paragraph_format.keep_with_next = bool(s.table and s.table.get("rows"))  # 説明と表を別のページに分けない
        if s.table is not None:
            _table(doc, s.table, total)
    buf = io.BytesIO()
    doc.core_properties.title = clean(title)
    doc.core_properties.author = "DefineReq_AI"
    doc.save(buf)
    return buf.getvalue()


def safe_name(text: str) -> str:
    """ファイル名に使えない文字を除く。"""
    return re.sub(r'[\\/:*?"<>|\s]+', "_", text).strip("_") or "案件"


def filename(p: dict, doc_type: str, version: int) -> str:
    """案件名・資料の種類・版が分かる名前にする。"""
    prefix = "サンプル_" if p.get("is_demo") or p.get("from_demo") else ""
    return f"{prefix}{safe_name(p['name'])}_{schema.DOC_TYPES[doc_type]}_第{version}版.docx"
