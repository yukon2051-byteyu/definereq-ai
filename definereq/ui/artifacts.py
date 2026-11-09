"""成果物の表示とダウンロード。案内の最終画面と「共有資料・出力」の画面で同じ処理を使う。

ファイルは既存の出力処理（export/wordx.py、excelx.py）で作る。AIは呼ばない。
ダウンロードしても画面を再実行しないため、案内の位置は変わらない。
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import project as pj
from ..demos.builder import STAGES
from ..export import excelx, share, wordx
from ..schema import DOC_TYPES
from .components import esc

WORD = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# 要件定義書を最初に置く
CARDS = [("spec", "合意した要件と、保留・未確認の項目を整理した資料です。"),
         ("meeting", "会議で決まったことと、次回の確認事項を整理した資料です。"),
         ("change", "追加要望の影響と、採否の判断理由を確認できる資料です。")]


def preview(sections: list[share.Section]) -> None:
    """資料の内容を画面に表示する。Wordと同じ組み立て結果を使う。"""
    for s in sections:
        st.markdown({1: "#### ", 2: "##### "}.get(s.level, "###### ") + s.heading)
        for t in s.paragraphs:
            st.write(t)
        if s.table is not None:
            if s.table["rows"]:
                st.dataframe(pd.DataFrame(s.table["rows"], columns=s.table["columns"]), hide_index=True, width="stretch")
            else:
                st.caption(s.table.get("empty") or "まだ登録されていません。")


def word_for(p: dict, doc: dict) -> dict:
    """発行済みの資料のWordファイル。同じ資料は作り直さない。"""
    cache = st.session_state.setdefault("artifact_files", {})
    key = f"{p['id']}:{doc['id']}"
    if key not in cache:
        data = wordx.render(p, share.options_for(doc), doc["id"], doc["version"], doc["issued_at"])
        cache[key] = {"data": data, "name": wordx.filename(p, doc["doc_type"], doc["version"])}
    return cache[key]


def excel_for(p: dict, when: str) -> dict:
    cache = st.session_state.setdefault("artifact_files", {})
    key = f"{p['id']}:excel"
    if key not in cache:
        cache[key] = {"data": excelx.render(p), "name": excelx.filename(p, when)}
    return cache[key]


def _failed(title: str, key: str, e: Exception) -> None:
    st.error(f"{title}のファイルを作成できませんでした（{type(e).__name__}）。下のボタンでもう一度お試しください。繰り返す場合は、機能画面の「共有資料・出力」から出力してください。")
    if st.button("もう一度作成する", key=f"tour_retry_{key}"):
        st.session_state.pop("artifact_files", None)
        st.rerun()


def _doc_card(p: dict, doc_type: str, text: str, when: str) -> None:
    title = DOC_TYPES[doc_type]
    doc = share.latest_doc(p, doc_type)
    if doc is None:
        st.html(f'<div class="dr-doc-t">{esc(title)}</div><div class="dr-g-sub">この時点では作成されていません。</div>')
        return
    st.html(f'<div class="dr-doc-t">{esc(title)}</div><div class="dr-doc-m">第{doc["version"]}版／{esc(when)}の時点／Word形式</div><div class="dr-doc-b">{esc(text)}</div>')
    try:
        f = word_for(p, doc)
    except Exception as e:  # 出力の失敗で案内の画面全体を止めない
        _failed(title, doc_type, e)
        return
    # ボタンの名前に資料名を入れ、どの資料を開くかを分かるようにする。
    # 要件定義書は横に並べて優先し、幅の狭いカードは文字が切れないよう縦に並べる
    first, second = st.columns(2) if doc_type == "spec" else (st.container(), st.container())
    if first.button(f"{title}の内容を見る", key=f"tour_view_{doc_type}", width="stretch", type="primary" if doc_type == "spec" else "secondary"):
        st.session_state["doc_view"] = doc_type
        st.rerun()
    second.download_button(f"{title}をWordでダウンロード", f["data"], file_name=f["name"], mime=WORD, key=f"dl_{doc_type}", on_click="ignore", width="stretch")


def _excel_card(p: dict, when: str) -> None:
    st.html('<div class="dr-doc-t">要件一覧</div>'
            f'<div class="dr-doc-m">{esc(when)}の時点／Excel形式</div><div class="dr-doc-b">要件・質問・残件・リスク・履歴を表で確認できる資料です。</div>')
    try:
        f = excel_for(p, when)
    except Exception as e:
        _failed("要件一覧", "excel", e)
        return
    st.download_button("要件一覧をExcelでダウンロード", f["data"], file_name=f["name"], mime=EXCEL, key="dl_excel", on_click="ignore", width="stretch")


def cards(p: dict, spec_note: str | None = None) -> None:
    """成果物のカード。要件定義書を大きく、ほかの資料を下に並べる。

    spec_note：要件定義書で見てほしい内容（デモごとの1文）。なければ資料の一般的な説明を出す。
    """
    when = STAGES.get((p.get("demo") or {}).get("stage"), pj.today())
    spec, *others = CARDS
    with st.container(border=True, key="doc_spec"):
        _doc_card(p, spec[0], spec_note or spec[1], when)
    if st.session_state.get("doc_view") == "spec":  # 押したカードのすぐ下に内容を出す
        _viewer(p)
    cols = st.columns(3)
    for col, (doc_type, text) in zip(cols, others):
        with col, st.container(border=True, height="stretch"):
            _doc_card(p, doc_type, text, when)
    with cols[2], st.container(border=True, height="stretch"):
        _excel_card(p, when)
    st.caption("PDFが必要な場合は、Wordで開いて「名前を付けて保存」からPDFを選んでください。")
    if st.session_state.get("doc_view") not in (None, "spec"):
        _viewer(p)


def _viewer(p: dict) -> None:
    viewing = st.session_state.get("doc_view")
    doc = share.latest_doc(p, viewing) if viewing else None
    if doc:
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{DOC_TYPES[viewing]}の内容（第{doc['version']}版）**")
            if c2.button("閉じる", key="tour_view_close", width="stretch"):
                st.session_state.pop("doc_view", None)
                st.rerun()
            preview(share.build(p, share.options_for(doc)))
