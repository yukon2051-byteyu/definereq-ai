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


def _word_later(p: dict, doc: dict):
    """押したときにWordを作る（作成に数秒かかるため、画面の表示を待たせない）。別のスレッドで動くため、画面の状態は使わない。"""
    opt, did, ver, at = share.options_for(doc), doc["id"], doc["version"], doc["issued_at"]
    return lambda: wordx.render(p, opt, did, ver, at)


def _doc_card(p: dict, doc_type: str, text: str, when: str) -> None:
    title = DOC_TYPES[doc_type]
    doc = share.latest_doc(p, doc_type)
    if doc is None:
        st.html(f'<div class="dr-doc-t">{esc(title)}</div><div class="dr-g-sub">この時点では作成されていません。</div>')
        return
    st.html(f'<div class="dr-doc-t">{esc(title)}</div><div class="dr-doc-m">第{doc["version"]}版／{esc(when)}の時点／Word形式</div><div class="dr-doc-b">{esc(text)}</div>')
    # ボタンの名前に資料名を入れ、どの資料を開くかを分かるようにする。
    # 要件定義書は横に並べて優先し、幅の狭いカードは文字が切れないよう縦に並べる
    first, second = st.columns(2) if doc_type == "spec" else (st.container(), st.container())
    if first.button(f"{title}の内容を見る", key=f"tour_view_{doc_type}", width="stretch", type="primary" if doc_type == "spec" else "secondary"):
        st.session_state["doc_view"] = doc_type
        st.rerun()
    second.download_button(f"{title}をWordでダウンロード", _word_later(p, doc), file_name=wordx.filename(p, doc_type, doc["version"]), mime=WORD,
                           key=f"dl_{doc_type}", on_click="ignore", width="stretch")


def _excel_card(p: dict, when: str) -> None:
    st.html('<div class="dr-doc-t">要件一覧</div>'
            f'<div class="dr-doc-m">{esc(when)}の時点／Excel形式</div><div class="dr-doc-b">要件・質問・残件・リスク・履歴を表で確認できる資料です。</div>')
    st.download_button("要件一覧をExcelでダウンロード", lambda: excelx.render(p), file_name=excelx.filename(p, when), mime=EXCEL, key="dl_excel", on_click="ignore", width="stretch")


def spec_actions(p: dict) -> None:
    """要件定義書の全文とWord。デモの最終画面で、代表例のすぐ下に置く（全文は押した位置のすぐ下に出す）。"""
    doc = share.latest_doc(p, "spec")
    if doc is None:
        st.caption("この時点では要件定義書は作成されていません。")
        return
    with st.container(horizontal=True, key="spec_actions"):
        if st.button("要件定義書の全文を見る", key="tour_view_spec", type="primary"):
            st.session_state["doc_view"] = "spec"
            st.rerun()
        st.download_button("要件定義書をWordでダウンロード", _word_later(p, doc), file_name=wordx.filename(p, "spec", doc["version"]), mime=WORD,
                           key="dl_spec", on_click="ignore")
    if st.session_state.get("doc_view") == "spec":
        _viewer(p)


def cards(p: dict, spec_note: str | None = None, skip_spec: bool = False) -> None:
    """成果物のカード。要件定義書を大きく、ほかの資料を下に並べる。

    spec_note：要件定義書で見てほしい内容（デモごとの1文）。なければ資料の一般的な説明を出す。
    skip_spec：要件定義書を別の場所（spec_actions）に出したときは、カードに重ねて出さない。
    """
    when = STAGES.get((p.get("demo") or {}).get("stage"), pj.today())
    spec, *others = CARDS
    if not skip_spec:
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
