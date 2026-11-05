"""資料の読込。形式ごとに「位置付きの本文（単位＝unit）」へ変換する。

unit = {"id": "U0001", "locator": "p.3", "text": "...", "target": True}
- locator は根拠の位置（PDF:ページ / Word:見出し・段落 / Excel:シート・セル / PPT:スライド / テキスト:行 / 字幕:時刻）
- target が False の単位はAIへ送らない（例：PowerPoint の発表者ノートの初期状態）
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

from .. import config
from .safety import IngestError, check_size, check_zip, safe_filename

SUPPORTED = {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".srt", ".vtt"}
UNSUPPORTED_HINT = {
    ".doc": "旧形式の .doc は読めません。.docx に保存し直してください。",
    ".xls": "旧形式の .xls は読めません。.xlsx に保存し直してください。",
    ".ppt": "旧形式の .ppt は読めません。.pptx に保存し直してください。",
    ".xlsm": "マクロ付きファイルは読み込みません。.xlsx に保存し直してください。",
    ".pptm": "マクロ付きファイルは読み込みません。.pptx に保存し直してください。",
    ".docm": "マクロ付きファイルは読み込みません。.docx に保存し直してください。",
}


@dataclass
class Parsed:
    units: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    kind: str = "text"
    extra: dict = field(default_factory=dict)  # 形式別の補足（スライド一覧など）

    def add(self, locator: str, text: str, target: bool = True, group: str = "") -> None:
        text = (text or "").strip()
        if not text:
            return
        unit = {"id": f"U{len(self.units) + 1:04d}", "locator": locator, "text": text, "target": target}
        if group:
            unit["group"] = group
        self.units.append(unit)


def looks_garbled(text: str) -> bool:
    """文字化けの可能性を判定する（置換文字や制御文字の割合）。"""
    if not text:
        return False
    bad = sum(1 for c in text if c == "�" or (ord(c) < 32 and c not in "\n\r\t"))
    return bad / len(text) > 0.02


def decode_text(data: bytes) -> tuple[str, list[str]]:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return data.decode("utf-16"), []
        except UnicodeDecodeError:
            pass
    try:
        return data.decode("utf-8-sig"), []
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("cp932"), ["文字コードは Shift_JIS と判定しました。"]
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace"), ["文字コードを判定できず、一部が文字化けしている可能性があります。"]


def parse_text(text: str) -> Parsed:
    out = Parsed(kind="text")
    for i, line in enumerate(text.splitlines(), 1):
        out.add(f"{i}行目", line)
    return out


def parse_pdf(data: bytes) -> Parsed:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    out = Parsed(kind="pdf")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise IngestError("パスワード付きのPDFは読み込めません。")
        pages = reader.pages
        total = len(pages)
    except PdfReadError as e:
        raise IngestError("PDFを読み込めませんでした（破損の可能性）。") from e
    limit = min(total, config.MAX_PDF_PAGES)
    empty = []
    for i in range(limit):
        try:
            text = pages[i].extract_text() or ""
        except Exception:  # pypdf はページ単位で多様な例外を出すため、そのページだけ警告にする
            out.warnings.append(f"p.{i + 1} の文字を抽出できませんでした。")
            continue
        if not text.strip():
            empty.append(i + 1)
            continue
        for para in re.split(r"\n{2,}|\n(?=[・■●\d第])", text):
            out.add(f"p.{i + 1}", re.sub(r"\s*\n\s*", " ", para))
    if empty:
        out.warnings.append(f"文字のないページがあります（{', '.join(map(str, empty[:10]))}ページ）。画像のみの場合は読み取れていません。")
    if total > limit:
        out.warnings.append(f"{total}ページのうち先頭{limit}ページのみ読み込みました（省略あり）。")
    return out


def parse_docx(data: bytes) -> Parsed:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    check_zip(data)
    try:
        doc = Document(io.BytesIO(data))
    except Exception as e:  # python-docx は形式不正時に複数種の例外を出す
        raise IngestError("Wordファイルを読み込めませんでした。") from e
    out = Parsed(kind="docx")
    heading, para_no, table_no = "（見出しなし）", 0, 0
    for block in doc.iter_inner_content():
        if isinstance(block, Paragraph):
            text = block.text.strip()
            if not text:
                continue
            if (block.style.name or "").lower().startswith(("heading", "見出し", "title", "表題")):
                heading, para_no = text, 0
                out.add(f"見出し「{heading}」", text)
                continue
            para_no += 1
            out.add(f"見出し「{heading}」 第{para_no}段落", text)
        elif isinstance(block, Table):
            table_no += 1
            for r, row in enumerate(block.rows, 1):
                cells: list[str] = []
                for c in row.cells:
                    t = c.text.strip()
                    if t and (not cells or cells[-1] != t):
                        cells.append(t)
                out.add(f"見出し「{heading}」 表{table_no} {r}行目", " / ".join(cells))
    if doc.inline_shapes:
        out.warnings.append(f"画像が{len(doc.inline_shapes)}点あります。画像の内容は読み取っていません。")
    return out


def parse_xlsx(data: bytes) -> Parsed:
    from openpyxl import load_workbook
    from openpyxl.utils.exceptions import InvalidFileException

    check_zip(data)
    try:
        # data_only=True：数式は実行せず、保存済みの値だけを読む
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (InvalidFileException, KeyError, ValueError, OSError) as e:
        raise IngestError("Excelファイルを読み込めませんでした。") from e
    out = Parsed(kind="xlsx")
    for ws in wb.worksheets:
        if ws.sheet_state != "visible":
            out.warnings.append(f"非表示のシート「{ws.title}」は読み込み対象外にしました。")
            continue
        rows_read = 0
        for row in ws.iter_rows():
            rows_read += 1
            if rows_read > config.MAX_SHEET_ROWS:
                out.warnings.append(f"シート「{ws.title}」は先頭{config.MAX_SHEET_ROWS}行のみ読み込みました（省略あり）。")
                break
            cells = [(c.coordinate, c.value) for c in row if c.value is not None and str(c.value).strip()]
            if cells:
                first, last = cells[0][0], cells[-1][0]
                loc = f"シート「{ws.title}」 {first}" + (f":{last}" if last != first else "")
                out.add(loc, " / ".join(str(v).strip() for _, v in cells))
    wb.close()
    return out


def _shape_texts(shape, prefix: str, skipped: list[str]):
    """図形から文字を取り出す。グループ内も再帰的に読む。文字のない図は記録して未理解を示す。"""
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    name = shape.name or "図形"
    kind = shape.shape_type
    if kind == MSO_SHAPE_TYPE.GROUP:
        for inner in shape.shapes:
            yield from _shape_texts(inner, f"{prefix}グループ「{name}」/", skipped)
        return
    if getattr(shape, "has_table", False) and shape.has_table:
        for r, row in enumerate(shape.table.rows, 1):
            yield f"{prefix}表「{name}」{r}行目", " / ".join(c.text.strip() for c in row.cells if c.text.strip())
        return
    if getattr(shape, "has_chart", False) and shape.has_chart:
        skipped.append(f"グラフ「{name}」")
        return
    if kind == MSO_SHAPE_TYPE.PICTURE:
        skipped.append(f"画像「{name}」")
        return
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame and shape.text_frame.text.strip():
        for para in shape.text_frame.paragraphs:
            t = "".join(run.text for run in para.runs).strip()
            if t:
                yield f"{prefix}{name}", t
        return
    if kind == MSO_SHAPE_TYPE.LINE or kind == MSO_SHAPE_TYPE.FREEFORM or kind == MSO_SHAPE_TYPE.AUTO_SHAPE \
            or shape.element.tag.endswith("cxnSp"):
        skipped.append(f"図形・矢印「{name}」")
    elif "graphicFrame" in shape.element.tag:
        skipped.append(f"SmartArt等「{name}」")


def parse_pptx(data: bytes) -> Parsed:
    from pptx import Presentation

    check_zip(data)
    try:
        prs = Presentation(io.BytesIO(data))
    except Exception as e:  # python-pptx も形式不正時に複数種の例外を出す
        raise IngestError("PowerPointファイルを読み込めませんでした。") from e
    out = Parsed(kind="pptx")
    slides = []
    for no, slide in enumerate(prs.slides, 1):
        title_shape = slide.shapes.title
        title = (title_shape.text_frame.text.strip() if title_shape is not None else "") or "（タイトルなし）"
        skipped: list[str] = []
        before = len(out.units)
        for shape in slide.shapes:
            for where, text in _shape_texts(shape, "", skipped):
                out.add(f"スライド{no}「{title}」 {where}", text, group=f"slide{no}")
        notes = ""
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
        if notes:
            # ノートは初期状態で分析・送信の対象外
            out.add(f"スライド{no}「{title}」 発表者ノート", notes, target=False, group=f"slide{no}")
        slides.append({"no": no, "title": title, "units": len(out.units) - before,
                       "not_understood": skipped, "has_notes": bool(notes)})
        if skipped:
            more = " ほか" if len(skipped) > 4 else ""
            out.warnings.append(f"スライド{no}：{'、'.join(skipped[:4])}{more} は文字以外の内容を理解していません。人が補足してください。")
    out.extra["slides"] = slides
    return out


_TIME = r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})|(\d{1,2}):(\d{2})[.,](\d{1,3})"


def _to_sec(m: re.Match) -> float:
    if m.group(1) is not None:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4).ljust(3, "0")) / 1000
    return int(m.group(5)) * 60 + int(m.group(6)) + int(m.group(7).ljust(3, "0")) / 1000


def format_time(sec: float) -> str:
    s = int(sec)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse_subtitles(text: str) -> list[dict]:
    """SRT / VTT を発言区間に変換する。話者タグ（<v 名前>、「名前:」）は「ラベル」として保持する。"""
    segs: list[dict] = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n").lstrip("﻿"))
    for block in blocks:
        lines = [line for line in block.split("\n") if line.strip()]
        idx = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if idx is None:
            continue
        times = list(re.finditer(_TIME, lines[idx]))
        if len(times) < 2:
            continue
        body = " ".join(lines[idx + 1:]).strip()
        label = None
        m = re.match(r"<v\s+([^>]+)>", body)
        if m:
            label = m.group(1).strip()
        body = re.sub(r"<[^>]+>", "", body).strip()
        if label is None:
            m = re.match(r"^([^:：]{1,20})[:：]\s*(.+)$", body)
            if m:
                label, body = m.group(1).strip(), m.group(2).strip()
        if body:
            segs.append({"start": _to_sec(times[0]), "end": _to_sec(times[1]), "speaker_label": label, "text": body})
    return segs


def parse_subtitle_file(text: str) -> Parsed:
    out = Parsed(kind="subtitle")
    segs = parse_subtitles(text)
    if not segs:
        raise IngestError("字幕の時刻を読み取れませんでした。SRT または VTT 形式か確認してください。")
    for s in segs:
        prefix = f"{s['speaker_label']}: " if s["speaker_label"] else ""
        out.add(f"{format_time(s['start'])}-{format_time(s['end'])}", prefix + s["text"])
    out.extra["segments"] = segs
    return out


def parse_file(filename: str, data: bytes) -> tuple[str, Parsed]:
    """ファイルを形式に応じて読み込む。失敗時は IngestError（理由つき）。"""
    name = safe_filename(filename)
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext in UNSUPPORTED_HINT:
        raise IngestError(UNSUPPORTED_HINT[ext])
    if ext not in SUPPORTED:
        raise IngestError(f"未対応の形式です（{ext or '拡張子なし'}）。対応形式：{', '.join(sorted(SUPPORTED))}")
    check_size(data, config.MAX_DOC_MB)
    if ext == ".pdf":
        parsed = parse_pdf(data)
    elif ext == ".docx":
        parsed = parse_docx(data)
    elif ext == ".xlsx":
        parsed = parse_xlsx(data)
    elif ext == ".pptx":
        parsed = parse_pptx(data)
    else:
        text, warns = decode_text(data)
        parsed = parse_subtitle_file(text) if ext in (".srt", ".vtt") else parse_text(text)
        parsed.warnings.extend(warns)
    finalize(parsed)
    return name, parsed


def finalize(parsed: Parsed) -> None:
    """空・文字化け・省略の確認を共通で行う。"""
    if not parsed.units:
        parsed.warnings.append("文字を抽出できませんでした（空、または画像のみの可能性）。")
    total = 0
    kept = []
    for u in parsed.units:
        total += len(u["text"])
        if total > config.MAX_TEXT_CHARS:
            parsed.warnings.append(f"本文が長いため {config.MAX_TEXT_CHARS:,} 文字までを読み込みました（省略あり）。")
            break
        kept.append(u)
    parsed.units = kept
    if looks_garbled("".join(u["text"] for u in kept[:300])):
        parsed.warnings.append("文字化けの可能性があります。原文を確認してください。")
