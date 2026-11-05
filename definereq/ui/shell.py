"""作業画面の枠（案件・分野・基準版・作業位置の表示、メニュー、デモの案内）。"""
from __future__ import annotations

import streamlit as st

from ..demos.builder import STAGES, catalog
from ..schema import DOMAINS
from . import state
from .readonly import HIDE_CSS
from .components import esc, flow, show_flash
from .pages import decide, materials, organize, prepare, trace

# 通常は主要な工程だけを表示し、詳しい機能は「詳細の機能」に収める
GROUPS = [
    ("全体", [("overview", "概要・残件", prepare.overview)]),
    ("準備", [("prep", "会議前の準備", prepare.prep), ("sources", "資料", materials.sources), ("recordings", "録画・発言", materials.recordings)]),
    ("整理", [("candidates", "会議後の整理", organize.candidates), ("requirements", "要件", organize.requirements)]),
    ("判断", [("decisions", "決定・合意", decide.decisions)]),
    ("共有", [("share", "共有資料・出力", trace.share_page)]),
    ("追跡", [("changes", "追加要望と影響", decide.changes), ("why", "なぜこの仕様か", trace.why)]),
]
DETAILS = [("profile", "案件情報・関係者", prepare.profile), ("refine", "具体化・受入条件", organize.refine), ("nfr", "非機能の確認", organize.nfr),
           ("scope", "範囲・優先順位", organize.scope), ("scenarios", "シナリオ", organize.scenarios), ("issues", "意見調整", decide.issues),
           ("conflicts", "矛盾", decide.conflicts), ("risks", "リスク", decide.risks), ("baseline", "基準版・再確認", decide.baseline),
           ("trail", "仕様の変遷", trace.trail), ("usage", "AI・費用", trace.usage)]
PAGES = {key: (label, fn) for _, items in GROUPS for key, label, fn in items}
PAGES.update({key: (label, fn) for key, label, fn in DETAILS})

# 各画面の次の行動（移動先）
NEXT = {"overview": ("残件のもとになる要件を確認します", "requirements"), "profile": ("会議の質問を準備します", "prep"), "prep": ("会議の資料を登録します", "sources"),
        "sources": ("録画と発言を確認します", "recordings"), "recordings": ("資料と発言から候補を整理します", "candidates"), "candidates": ("採用した内容を要件で確認します", "requirements"),
        "requirements": ("曖昧な要件を具体化します", "refine"), "refine": ("非機能を確認します", "nfr"), "nfr": ("今回の範囲を決めます", "scope"),
        "scope": ("通常と例外の流れを確認します", "scenarios"), "scenarios": ("意見の違いを整理します", "issues"), "issues": ("判断を記録します", "decisions"),
        "decisions": ("確認資料を出力します", "share"), "share": ("追加要望の影響を調べます", "changes"), "changes": ("矛盾の候補を確認します", "conflicts"),
        "conflicts": ("リスクを確認します", "risks"), "risks": ("基準版との差を確認します", "baseline"), "baseline": ("仕様の変遷を確認します", "trail"),
        "trail": ("仕様の理由を確認します", "why"), "why": ("残件を確認します", "overview"), "usage": ("残件を確認します", "overview")}


def sidebar(p: dict) -> None:
    with st.sidebar:
        st.markdown(f"**{p['name']}**")
        st.caption("・".join(DOMAINS[d] for d in p["domains"]))
        if st.button("← トップへ戻る", key="nav_home"):
            state.close_project()
        current = st.session_state.get("page", "overview")

        def nav(key: str, label: str) -> None:
            if st.button(label, key=f"nav_{key}", type="primary" if key == current else "secondary", width="stretch"):
                st.session_state["tour_on"] = False
                state.goto(key)

        for group, items in GROUPS:
            st.caption(group)
            for key, label, _ in items:
                nav(key, label)
        with st.expander("詳細の機能", expanded=current in {k for k, _, _ in DETAILS}):
            for key, label, _ in DETAILS:
                nav(key, label)
        if p.get("demo"):
            st.divider()
            if st.button("機能対応表", key="nav_map", width="stretch"):
                state.goto("demo_map")
            if st.button("案内を最初から見る", key="nav_tour", width="stretch"):
                state.open_demo(p["demo"]["id"], tour=True)


def context_bar(p: dict, page_label: str) -> None:
    base = p["baselines"][-1]["label"] if p["baselines"] else "基準版なし"
    parts = [f"<b>{esc(p['name'])}</b>", esc("・".join(DOMAINS[d] for d in p["domains"])), f"基準版：{esc(base)}", f"作業位置：{esc(page_label)}"]
    if p.get("demo"):
        parts.append(f"デモの段階：{esc(STAGES[p['demo']['stage']])}")
        parts.append("閲覧専用・架空データ")
    st.html('<div class="dr-bar">' + "".join(f"<span>{x}</span>" for x in parts) + "</div>")


def stage_control(p: dict) -> None:
    d = p.get("demo")
    if not d or st.session_state.get("tour_on"):
        return
    stages = list(STAGES)
    choice = st.segmented_control("デモの段階", stages, default=d["stage"], format_func=STAGES.get, key=f"stage_seg_{d['stage']}")
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
        if c1.button("前へ", disabled=i == 0, width="stretch", key="tour_prev"):
            _jump(steps, i - 1)
        if i + 1 < len(steps):
            if c2.button("次へ", type="primary", width="stretch", key="tour_next"):
                _jump(steps, i + 1)
        elif c2.button("案内を終わる", type="primary", width="stretch", key="tour_end"):
            st.session_state["tour_on"] = False
            st.rerun()
        if c3.button("案内を閉じて全画面を見る", width="stretch", key="tour_close"):
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


def next_step(key: str) -> None:
    """画面の下に、次にすることと移動ボタンを出す。"""
    if key not in NEXT or st.session_state.get("tour_on"):
        return
    text, target = NEXT[key]
    st.divider()
    c1, c2 = st.columns([3, 1])
    c1.markdown(f"**次にすること**　{text}")
    if c2.button(f"{PAGES[target][0]}へ", key=f"next_{key}", width="stretch"):
        state.goto(target)


def render(p: dict) -> None:
    show_flash()
    if p.get("is_demo"):
        st.html(HIDE_CSS)
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
        next_step(key if key in PAGES else "overview")
