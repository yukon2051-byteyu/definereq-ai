"""作業画面の枠（案件・分野・基準版・作業位置の表示、メニュー、デモの案内）。"""
from __future__ import annotations

import streamlit as st

from .. import project as pj
from ..demos.builder import STAGES
from ..logic import guidance as gd
from ..schema import DOMAINS
from . import guide, situation, state
from .readonly import HIDE_CSS
from .components import esc, save_controls, show_flash
from .pages import decide, materials, organize, prepare, trace

# 上位は作業単位の5つ。機能は削除せず、選んだ作業の下に並べる
GROUPS = [
    ("案件ホーム", [("setup", "案件の準備", prepare.setup), ("overview", "現在の状況", prepare.overview), ("profile", "背景・目的・関係者", prepare.profile)]),
    ("会議の準備", [("prep", "質問・議題", prepare.prep), ("meetings", "会議", prepare.meetings)]),
    ("記録を取り込む", [("records", "会議の記録を整理", materials.records), ("sources", "資料・議事録", materials.sources), ("recordings", "録画・発言", materials.recordings)]),
    ("要件を整理・判断", [("candidates", "AI候補の確認", organize.candidates), ("requirements", "要件", organize.requirements), ("refine", "具体化・受入条件", organize.refine), ("decisions", "決定・合意", decide.decisions),
                  ("nfr", "非機能の確認", organize.nfr), ("scope", "範囲・優先順位", organize.scope), ("scenarios", "シナリオ", organize.scenarios), ("issues", "意見調整", decide.issues),
                  ("conflicts", "矛盾", decide.conflicts), ("risks", "リスク", decide.risks)]),
    ("共有・変更管理", [("share", "確認資料・要件定義書", trace.share_page), ("changes", "追加要望と影響", decide.changes), ("trail", "変更履歴", trace.trail), ("why", "なぜこの仕様か", trace.why),
                 ("baseline", "基準版・再確認", decide.baseline), ("usage", "AI・費用", trace.usage)]),
]
PAGES = {key: (label, fn) for _, items in GROUPS for key, label, fn in items}
# 使う頻度の低い機能は「詳細メニュー」にまとめる。関連する作業の画面からも移動できる
ADVANCED = {"refine", "nfr", "scope", "scenarios", "issues", "conflicts", "risks", "baseline", "usage"}

# 各画面の次の行動（移動先）
NEXT = {"setup": ("背景・目的・関係者を入力します", "profile"), "records": ("候補を確認して要件を整理します", "requirements"), "overview": ("残件のもとになる要件を確認します", "requirements"), "profile": ("会議の質問を準備します", "prep"), "meetings": ("次の会議の質問を準備します", "prep"), "prep": ("会議の資料を登録します", "sources"),
        "sources": ("録画と発言を確認します", "recordings"), "recordings": ("資料と発言から候補を整理します", "candidates"), "candidates": ("採用した内容を要件で確認します", "requirements"),
        "requirements": ("曖昧な要件を具体化します", "refine"), "refine": ("非機能を確認します", "nfr"), "nfr": ("今回の範囲を決めます", "scope"),
        "scope": ("通常と例外の流れを確認します", "scenarios"), "scenarios": ("意見の違いを整理します", "issues"), "issues": ("判断を記録します", "decisions"),
        "decisions": ("確認資料を出力します", "share"), "share": ("追加要望の影響を調べます", "changes"), "changes": ("矛盾の候補を確認します", "conflicts"),
        "conflicts": ("リスクを確認します", "risks"), "risks": ("基準版との差を確認します", "baseline"), "baseline": ("仕様の変遷を確認します", "trail"),
        "trail": ("仕様の理由を確認します", "why"), "why": ("残件を確認します", "overview"), "usage": ("残件を確認します", "overview")}


def sidebar(p: dict) -> None:
    with st.sidebar:
        if st.button("DefineReq_AI", key="nav_logo", width="stretch"):
            state.go_home()
        st.markdown(f"**{p['name']}**")
        st.caption("・".join(DOMAINS[d] for d in p["domains"]))
        if st.button("← トップへ戻る", key="nav_home"):
            state.go_home()
        if not p.get("is_demo"):
            save_controls(p, "save_side")
        if p.get("demo") and st.session_state.get("tour_on"):
            guide.sidebar(p)  # 案内中は工程の一覧だけにする
            return
        current = st.session_state.get("page", "overview")

        def nav(key: str, label: str) -> None:
            if st.button(label, key=f"nav_{key}", type="primary" if key == current else "secondary", width="stretch"):
                st.session_state["tour_on"] = False
                state.goto(key)

        for n, (group, items) in enumerate(GROUPS):
            active = current in {k for k, _, _ in items}
            if st.button(group, key=f"nav_group_{n}", type="tertiary" if active else "secondary", width="stretch"):
                st.session_state["tour_on"] = False
                state.goto(items[0][0])
            if active:  # 選んだ作業の機能だけを表示する
                with st.container(key=f"nav_sub_{n}"):
                    for key, label, _ in items:
                        if key not in ADVANCED:
                            nav(key, label)
                    more = [x for x in items if x[0] in ADVANCED]
                    if more:
                        with st.expander("詳細メニュー", expanded=current in ADVANCED):
                            for key, label, _ in more:
                                nav(key, label)
        if p.get("demo"):
            st.divider()
            if st.button("機能対応表", key="nav_map", width="stretch"):
                state.goto("demo_map")
            if st.button("案内を最初から見る", key="nav_tour", width="stretch"):
                state.open_demo(p["demo"]["id"], tour=True)


def context_bar(p: dict, page_label: str) -> None:
    parts = [f"<b>{esc(p['name'])}</b>", esc("・".join(DOMAINS[d] for d in p["domains"])), f"作業位置：{esc(page_label)}"]
    if p["baselines"]:
        parts.insert(2, f"基準版：{esc(p['baselines'][-1]['label'])}")
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


def scroll_top_on_change(p: dict, key: str) -> None:
    """画面や段階が変わったら先頭へ戻す（案内パネルが画面外に隠れないように）。"""
    marker = f"{p['id']}:{key}:{(p.get('demo') or {}).get('stage')}:{st.session_state.get('tour_on')}:{st.session_state.get('tour_index')}:{st.session_state.get('scroll_nonce', 0)}"
    # st.html のスクリプトは初回しか実行されないため、埋め込み枠から親の画面を操作する
    script = ("const d=window.parent.document;const t=()=>{d.querySelector('[data-testid=stMain]')?.scrollTo(0,0);window.parent.scrollTo(0,0)};"
              "t();setTimeout(t,150);setTimeout(t,500);"
              # スマートフォン幅ではサイドバーが本文を覆うため、画面を移動したら閉じる
              "if(window.parent.innerWidth<=760){d.querySelector('[data-testid=stSidebarCollapseButton] button')?.click()}")
    # 枠は毎回同じ位置に置く。出したり消したりすると後ろの部品の位置がずれ、開いているタブが閉じてしまう
    # 内容が同じ間は読み直されないため、スクロールは画面が変わったときだけ動く
    # 目印は読み込んだJSONの値を含むため、ハッシュにしてからスクリプトへ入れる
    st.iframe(f"<script>/*{pj.fingerprint(marker)}*/{script}</script>", height=1)


def next_step(key: str, p: dict) -> None:
    """デモの機能画面の下に、次の画面への移動を出す。実案件は状況案内が現在の状態に合わせて案内する。"""
    if key not in NEXT or st.session_state.get("tour_on") or not p.get("is_demo"):
        return
    text, target = NEXT[key]
    st.divider()
    c1, c2 = st.columns([3, 1])
    c1.markdown(f"**次にすること**　{text}")
    if c2.button(f"{PAGES[target][0]}へ", key=f"next_{key}", width="stretch"):
        state.goto(target)


def back_to_setup(key: str) -> None:
    """自分の案件の各画面の最上部に置く戻る操作。左メニューを閉じていても、案件の準備へ戻れる。"""
    if st.button("← 案件の準備に戻る", key="go_setup_ov" if key == "overview" else f"go_setup_{key}", type="tertiary"):
        state.goto("setup")


def demo_bar(p: dict) -> None:
    """機能画面（詳細）の上部に、開いた元のステップへの戻り道を示す。戻り先の番号と名前をボタンに出す。"""
    with st.container(key="demo_back", horizontal=True, vertical_alignment="center"):
        if st.button(guide.back_label(p), key="tour_back", type="primary"):
            guide.back_to_guide(p)
        st.caption("いま見ているのは機能画面（実際の一覧と記録）です。閲覧専用のため編集はできません。編集は「あなたの案件で試す」から行えます。")


def render(p: dict) -> None:
    show_flash()
    if p.get("is_demo"):
        st.html(HIDE_CSS)
    sidebar(p)
    key = st.session_state.get("page", "overview")
    scroll_top_on_change(p, key)
    if p.get("demo") and st.session_state.get("tour_on"):
        guide.render(p)
        return
    label = "デモの機能対応表" if key == "demo_map" else PAGES.get(key, PAGES["overview"])[0]
    context_bar(p, label)
    if p.get("demo"):
        demo_bar(p)
    elif not p.get("is_demo") and key not in ("setup", "profile", "sources") and not (key == "overview" and gd.phase(p) == "empty"):
        # 自分の案件の作業画面は、同じ位置に「戻る」（案件の準備へ）と「次に進む」（状況案内の主ボタン）を置く。
        # 背景と資料の画面は入力を先に見せるため、戻る操作を各画面の見出し付近に置く。
        # 記録の整理の画面は、未整理の件数と実行ボタンを先頭に出すため、長い状況案内を画面の下にまとめる
        back_to_setup(key)
        if key != "records":
            situation.project_panel(p, key)  # 案件の準備の画面は、それ自体が進み先を示す
    stage_control(p)
    if key == "demo_map":
        trace.demo_map(p)
    else:
        PAGES.get(key, PAGES["overview"])[1](p)
        next_step(key if key in PAGES else "overview", p)
