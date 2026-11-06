"""Excel 出力（要件・質問・残件・リスク・履歴）。

数式注入の対策：= + - @ などで始まる値は文字列として書き、先頭に ' を付ける。
"""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.properties import PageSetupProperties

from .. import project as pj
from .. import schema
from ..logic import checks
from ..project import display

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r", "＝", "＋", "－", "＠")
_FILL = PatternFill("solid", fgColor="161618")
_BORDER = Border(*(Side(style="thin", color="D5D6DA") for _ in range(4)))


def safe_cell(value):
    """Excel が数式として実行しないように値を整える。"""
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    text = "".join(c for c in str(value) if c in "\t\n\r" or ord(c) >= 32)
    return "'" + text if text.startswith(_DANGEROUS) else text


def _sheet(wb: Workbook, title: str, cols: list[tuple[str, int]], rows: list[list]):
    ws = wb.create_sheet(title)
    for i, (name, width) in enumerate(cols, 1):
        c = ws.cell(row=1, column=i, value=name)
        c.font = Font(name="Yu Gothic", bold=True, color="FFFFFF", size=10)
        c.fill = _FILL
        c.alignment = Alignment(vertical="center", wrap_text=True)
        c.border = _BORDER
        ws.column_dimensions[get_column_letter(i)].width = width
    for r, row in enumerate(rows, 2):
        for i, v in enumerate(row, 1):
            cell = ws.cell(row=r, column=i)
            cell.value = safe_cell(v)
            if isinstance(cell.value, str):
                cell.data_type = "s"  # 文字列として固定
            cell.font = Font(name="Yu Gothic", size=10)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = _BORDER
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{max(1, len(rows) + 1)}"
    ws.sheet_view.showGridLines = False
    ws.oddFooter.center.text = "&P / &N"
    # 列が多いため、横向きで幅を1ページに収めて印刷する
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.print_title_rows = "1:1"
    return ws


def filename(p: dict, when: str) -> str:
    """Excelには版がないため、案件名と時点で区別する。"""
    from .wordx import safe_name

    prefix = "サンプル_" if p.get("is_demo") or p.get("from_demo") else ""
    return f"{prefix}{safe_name(p['name'])}_要件一覧_{when}.xlsx"


def render(p: dict, include_internal: bool = False) -> bytes:
    wb = Workbook()
    info = wb.active
    info.title = "表紙"
    for i, (k, v) in enumerate((("案件", p["name"]), ("案件ID", p["id"]), ("分野", "、".join(schema.DOMAINS[d] for d in p["domains"])),
                                ("出力日時", pj.now_iso()), ("形式版", p["format_version"]),
                                ("範囲", "内部メモ含む" if include_internal else "内部メモ除外"),
                                ("データ", "【サンプル】架空の案件データ。実在の組織・案件とは関係ありません" if p.get("is_demo") or p.get("from_demo") else "利用者の登録データ")), 1):
        info.cell(row=i, column=1, value=k).font = Font(name="Yu Gothic", bold=True)
        info.cell(row=i, column=2, value=safe_cell(v)).font = Font(name="Yu Gothic")
    info.column_dimensions["A"].width = 12
    info.column_dimensions["B"].width = 50

    req_cols = [("要件ID", 10), ("版", 5), ("分野", 10), ("種類", 10), ("名称", 28), ("内容", 50), ("優先", 6), ("範囲", 12),
                ("状態", 10), ("判断者", 12), ("確認相手", 12), ("期限", 11), ("受入条件数", 8), ("関連要件", 16), ("根拠数", 7)]
    if include_internal:
        req_cols.append(("内部メモ", 30))
    rows = []
    for r in p["requirements"]:
        row = [r["id"], r["version"], display(r.get("domain")), display(r.get("kind")), r["title"], r["body"],
               display(r.get("priority")), display(r.get("scope")), r["status"], display(r.get("decider")),
               display(r.get("confirm_with")), display(r.get("due")),
               len(r.get("acceptance") or []), "、".join(r.get("related") or []), len(r.get("evidence") or [])]
        if include_internal:
            row.append(r.get("internal_note") or "")
        rows.append(row)
    _sheet(wb, "要件", req_cols, rows)

    _sheet(wb, "質問", [("質問ID", 10), ("質問", 50), ("理由", 34), ("確認相手", 14), ("優先", 6), ("状態", 10), ("回答", 40)],
           [[q["id"], q["text"], display(q.get("why")), display(q.get("ask")), display(q.get("priority")), q["status"], q.get("answer") or ""]
            for q in p["questions"]])

    bl = checks.backlog(p)
    rows = [[i["category"], i["target"], i["content"], i["action"], display(i.get("ask")), display(i.get("due")), i["state"]]
            for items in bl["categories"].values() for i in items]
    ws = _sheet(wb, "残件", [("分類", 22), ("対象", 10), ("内容", 44), ("行動", 30), ("確認相手", 12), ("期限", 11), ("状態", 8)], rows)
    ws.cell(row=len(rows) + 3, column=1, value=f"分類別の合計 {bl['category_total']} 件／重複を除いた対象 {bl['unique_total']} 件")

    _sheet(wb, "リスク", [("ID", 9), ("内容", 44), ("性質", 12), ("条件", 24), ("影響", 24), ("不確かさ", 18), ("対策", 28), ("確認相手", 12), ("状態", 10)],
           [[r["id"], r["content"], display(r.get("nature")), display(r.get("condition")), display(r.get("impact")), display(r.get("uncertainty")),
             display(r.get("mitigation")), display(r.get("ask")), r["state"]] for r in p["risks"]])

    _sheet(wb, "履歴", [("ID", 9), ("要件", 9), ("変更要求", 9), ("きっかけ", 24), ("会議日", 11), ("提案日", 11), ("判断日", 11), ("適用日", 11),
                       ("記録日時", 18), ("変更前", 36), ("変更後", 36), ("結果", 8), ("理由", 36), ("判断者", 12), ("訂正元", 9)],
           [[h["id"], h.get("requirement_id") or "", h.get("change_id") or "", h.get("trigger"), display(h.get("meeting_date")), display(h.get("proposed_on")),
             display(h.get("decided_on")), display(h.get("applied_on")), h.get("recorded_at"), h.get("before") or "", h.get("after") or "",
             h["outcome"], h.get("rationale") or "理由の記録がありません", display(h.get("decider")), h.get("corrects") or ""] for h in p["history"]])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
