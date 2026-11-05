"""画面の状態（利用者ごとに分離）。

st.session_state は接続ごとに別々なので、利用者間でデータは混ざらない。
デモは段階ごとに作業コピーを持ち、編集しても固定の元データは変わらない。
"""
from __future__ import annotations

import streamlit as st

from ..demos import builder


def current() -> dict | None:
    return st.session_state.get("project")


def _clear_widgets() -> None:
    keep = {"project", "page", "demo_copies", "tour_index", "tour_on", "media_paths", "access_code", "flash", "last_view"}
    for k in list(st.session_state.keys()):
        if k not in keep:
            del st.session_state[k]


def open_project(p: dict) -> None:
    _clear_widgets()
    st.session_state["project"] = p
    st.session_state["page"] = "overview"
    st.session_state["tour_on"] = False
    st.rerun()


def demo_copy(demo_id: str, stage: int) -> dict:
    copies = st.session_state.setdefault("demo_copies", {})
    key = f"{demo_id}:{stage}"
    if key not in copies:
        copies[key] = builder.build(demo_id, stage)
    return copies[key]


def open_demo(demo_id: str, tour: bool = False, stage: int | None = None) -> None:
    _clear_widgets()
    stage = stage or (1 if tour else 4)
    st.session_state["project"] = demo_copy(demo_id, stage)
    st.session_state["tour_on"] = tour
    st.session_state["tour_index"] = 0
    st.session_state["page"] = "overview"
    if tour:
        step = next(d for d in builder.catalog() if d["id"] == demo_id)["tour"][0]
        st.session_state["page"] = step["page"]
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


def reset_demo() -> None:
    """デモの作業コピーを破棄して初期状態に戻す。"""
    p = current()
    copies = st.session_state.get("demo_copies", {})
    for key in [k for k in copies if k.startswith(p["demo"]["id"] + ":")]:
        del copies[key]
    stage = p["demo"]["stage"]
    st.session_state["project"] = demo_copy(p["demo"]["id"], stage)
    _clear_widgets()
    st.rerun()


def close_project() -> None:
    for k in ("project", "page", "tour_on", "tour_index"):
        st.session_state.pop(k, None)
    _clear_widgets()
    st.rerun()
