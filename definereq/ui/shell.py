"""作業画面の枠（案件・分野・基準版・作業位置の表示、メニュー、デモの案内）。"""
from __future__ import annotations

import streamlit as st

from ..demos.builder import STAGES, catalog
from ..schema import DOMAINS
from . import state
from .components import esc, flow, show_flash
from .pages import decide, materials, organize, prepare, trace

GROUPS = [
    ("全体", [("overview", "概要・残件", prepare.overview)]),
    ("準備", [("profile", "案件情報・関係者", prepare.profile), ("prep", "会議前の準備", prepare.prep)]),
    ("資料", [("sources", "資料", materials.sources), ("recordings", "録画・発言", materials.recordings)]),
    ("整理", [("candidates", "会議後の整理", organize.candidates), ("requirements", "要件", organize.requirements), ("refine", "具体化・受入条件", organize.refine),
              ("nfr", "非機能の確認", organize.nfr), ("scope", "範囲・優先順位", organize.scope), ("scenarios", "シナリオ", organize.scenarios)]),
    ("調整", [("issues", "意見調整", decide.issues), ("decisions", "決定・合意", decide.decisions)]),
    ("変更", [("changes", "追加要望と影響", decide.changes), ("conflicts", "矛盾", decide.conflicts), ("risks", "リスク", decide.risks), ("baseline", "基準版・再確認", decide.baseline)]),
    ("経緯", [("trail", "仕様の変遷", trace.trail), ("why", "なぜこの仕様か", trace.why)]),
    ("出力", [("share", "共有資料・出力", trace.share_page), ("usage", "AI・費用", trace.usage)]),
]
PAGES = {key: (label, fn) for _, items in GROUPS for key, label, fn in items}


def sidebar(p: dict) -> None:
    with st.sidebar:
        st.markdown(f"**{p['name']}**")
        st.caption("・".join(DOMAINS[d] for d in p["domains"]))
        if st.button("← トップへ戻る", key="nav_home"):
            state.close_project()
        current = st.session_state.get("page", "overview")
        for group, items in GROUPS:
            st.caption(group)
            for key, label, _ in items:
                if st.button(label, key=f"nav_{key}", type="primary" if key == current else "secondary", width="stretch"):
                    st.session_state["tour_on"] = False
                    state.goto(key)
        if p.get("demo"):
            st.divider()
            st.caption("デモの操作")
            if st.button("機能対応表", key="nav_map", width="stretch"):
                state.goto("demo_map")
            if st.button("案内を最初から見る", key="nav_tour", width="stretch"):
                state.open_demo(p["demo"]["id"], tour=True)
            if st.button("デモを初期状態に戻す", key="nav_reset", width="stretch"):
                state.reset_demo()


def context_bar(p: dict, page_label: str) -> None:
    base = p["baselines"][-1]["label"] if p["baselines"] else "基準版なし"
    parts = [f"<b>{esc(p['name'])}</b>", esc("・".join(DOMAINS[d] for d in p["domains"])), f"基準版：{esc(base)}", f"作業位置：{esc(page_label)}"]
    if p.get("demo"):
        parts.append(f"デモの段階：{esc(STAGES[p['demo']['stage']])}")
        parts.append("架空データ・料金なし")
        if p["demo"].get("edited"):
            parts.append("作業コピーを編集済み（古いAI結果に注意）")
    st.html('<div class="dr-bar">' + "".join(f"<span>{x}</span>" for x in parts) + "</div>")


def stage_control(p: dict) -> None:
    d = p.get("demo")
    if not d or st.session_state.get("tour_on"):
        return
    stages = list(STAGES)
    choice = st.segmented_control("デモの段階（段階ごとに別の作業コピーです）", stages, default=d["stage"], format_func=STAGES.get, key=f"stage_seg_{d['stage']}")
    if choice and choice != d["stage"]:
        state.set_stage(choice)


def tour(p: dict) -> None:
    """約3分の案内。手順ごとに入力→AI候補→人の判断→結果のつながりを示す。"""
    d = p.get("demo")
    if not d or not st.session_state.get("tour_on"):
        return
    steps = next(x for x in catalog() if x["id"] == d["id"])["tour"]
    i = min(st.session_state.get("tour_index", 0), len(steps) - 1)
    s = steps[i]
    with st.container(border=True):
        st.markdown(f"**案内 {i + 1}/{len(steps)}　{s['title']}**")
        st.progress((i + 1) / len(steps))
        flow([("入力", s["input"]), ("AI候補", s["ai"]), ("人の判断", s["human"]), ("結果", s["result"])])
        c1, c2, c3 = st.columns([1, 1, 2])
        if c1.button("前へ", disabled=i == 0, width="stretch"):
            _jump(steps, i - 1)
        if i + 1 < len(steps):
            if c2.button("次へ", type="primary", width="stretch"):
                _jump(steps, i + 1)
        elif c2.button("案内を終わる", type="primary", width="stretch"):
            st.session_state["tour_on"] = False
            st.rerun()
        if c3.button("案内を閉じて自由に操作する", width="stretch"):
            st.session_state["tour_on"] = False
            st.rerun()


def _jump(steps: list[dict], i: int) -> None:
    st.session_state["tour_index"] = i
    state.set_stage(steps[i]["stage"], steps[i]["page"])


def scroll_top_on_change(p: dict, key: str) -> None:
    """画面や段階が変わったら先頭へ戻す（案内パネルが画面外に隠れないように）。"""
    marker = f"{p['id']}:{key}:{(p.get('demo') or {}).get('stage')}"
    if st.session_state.get("last_view") != marker:
        st.session_state["last_view"] = marker
        st.html("<script>document.querySelector('[data-testid=\"stMain\"]')?.scrollTo(0, 0)</script>", unsafe_allow_javascript=True)


def render(p: dict) -> None:
    show_flash()
    sidebar(p)
    key = st.session_state.get("page", "overview")
    scroll_top_on_change(p, key)
    label = "デモの機能対応表" if key == "demo_map" else PAGES.get(key, PAGES["overview"])[0]
    context_bar(p, label)
    tour(p)
    stage_control(p)
    if key == "demo_map":
        trace.demo_map(p)
    else:
        PAGES.get(key, PAGES["overview"])[1](p)
