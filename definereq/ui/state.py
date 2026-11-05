"""画面の状態（利用者ごとに分離）。

st.session_state は接続ごとに別々なので、利用者間でデータは混ざらない。
デモは閲覧専用で、段階ごとに作り直した案件を表示する。
"""
from __future__ import annotations

import streamlit as st

from .. import project as pj
from ..demos import builder, guide


def current() -> dict | None:
    return st.session_state.get("project")


def _clear_widgets() -> None:
    keep = {"project", "page", "demo_copies", "tour_index", "tour_on", "media_paths", "ai_code", "flash", "last_view", "save_fp", "save_time", "show_home", "work_project"}
    for k in list(st.session_state.keys()):
        if k not in keep:
            del st.session_state[k]


def is_dirty(p: dict) -> bool:
    """保存用ファイルの作成後に変更があるか。実際にファイルが保存されたかは分からない。"""
    return st.session_state.get("save_fp") != pj.fingerprint(p)


def mark_saved(p: dict) -> None:
    st.session_state["save_fp"] = pj.fingerprint(p)
    st.session_state["save_time"] = pj.now_iso()


def open_project(p: dict, loaded: bool = False) -> None:
    _clear_widgets()
    st.session_state["project"] = p
    st.session_state["page"] = "overview"
    st.session_state["tour_on"] = False
    st.session_state["show_home"] = False
    st.session_state["save_time"] = None
    st.session_state.pop("work_project", None)
    st.session_state["save_fp"] = pj.fingerprint(p) if loaded else None
    st.rerun()


def go_home() -> None:
    """トップへ戻る。作業中の案件は保持する。"""
    p = current()
    if p and p.get("is_demo"):
        close_project()
    st.session_state["show_home"] = True
    st.rerun()


def back_to_work() -> None:
    st.session_state["show_home"] = False
    st.rerun()


def demo_copy(demo_id: str, stage: int) -> dict:
    copies = st.session_state.setdefault("demo_copies", {})
    key = f"{demo_id}:{stage}"
    if key not in copies:
        copies[key] = builder.build(demo_id, stage)
    return copies[key]


def open_demo(demo_id: str, tour: bool = True, stage: int | None = None) -> None:
    _clear_widgets()
    p = current()
    if p and not p.get("is_demo"):  # デモを見ても作業中の案件を失わない
        st.session_state["work_project"] = p
    st.session_state["show_home"] = False
    stage = stage or (guide.load(demo_id)[0]["stage"] if tour else 4)
    st.session_state["project"] = demo_copy(demo_id, stage)
    st.session_state["tour_on"] = tour
    st.session_state["tour_index"] = 0
    st.session_state["page"] = "overview"
    st.rerun()


def goto(page: str) -> None:
    st.session_state["page"] = page
    st.rerun()


def set_stage(stage: int, page: str | None = None) -> None:
    p = current()
    _clear_widgets()
    st.session_state["project"] = demo_copy(p["demo"]["id"], stage)
    if page:
        st.session_state["page"] = page
    st.rerun()


def close_project() -> None:
    work = st.session_state.pop("work_project", None)
    for k in ("project", "page", "tour_on", "tour_index"):
        st.session_state.pop(k, None)
    if work:
        st.session_state["project"] = work
        st.session_state["show_home"] = True
    else:
        st.session_state["show_home"] = False
    _clear_widgets()
    st.rerun()
