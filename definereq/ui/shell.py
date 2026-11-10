"""作業画面の枠（案件・分野・基準版・作業位置の表示、メニュー、デモの案内）。"""
from __future__ import annotations

import streamlit as st

from .. import project as pj
from ..demos.builder import STAGES
from ..demos import guide as demo_guide
from ..logic import guidance as gd
from ..schema import DOMAINS
from . import guide, situation, state
from .readonly import HIDE_CSS
from .components import esc, save_controls, show_flash
from .pages import decide, materials, organize, prepare, trace

# 上位は作業の工程の5つ。デモと自分の案件で同じ定義からサイドバーを描画し、工程名と機能名をそろえる
GROUPS = [
    ("案件の準備", [("setup", "準備の概要", prepare.setup), ("overview", "現在の状況", prepare.overview), ("profile", "背景・目的・関係者", prepare.profile), ("refs", "参考資料", materials.references)]),
    ("会議の準備", [("prep", "質問・議題", prepare.prep), ("meetings", "会議", prepare.meetings)]),
    ("記録の取り込み・整理", [("records", "会議の記録を整理", materials.records), ("sources", "資料・議事録", materials.sources), ("recordings", "録画・発言", materials.recordings)]),
    ("要件の確認・判断", [("candidates", "AI候補の確認", organize.candidates), ("requirements", "要件", organize.requirements), ("refine", "具体化・受入条件", organize.refine), ("decisions", "決定・合意", decide.decisions),
                  ("nfr", "非機能の確認", organize.nfr), ("scope", "範囲・優先順位", organize.scope), ("scenarios", "シナリオ", organize.scenarios), ("issues", "意見調整", decide.issues),
                  ("conflicts", "矛盾", decide.conflicts), ("risks", "リスク", decide.risks)]),
    ("共有・変更管理", [("share", "確認資料・要件定義書", trace.share_page), ("changes", "追加要望と影響", decide.changes), ("trail", "変更履歴", trace.trail), ("why", "なぜこの仕様か", trace.why),
                 ("baseline", "基準版・再確認", decide.baseline), ("usage", "AI・費用", trace.usage)]),
]
PAGES = {key: (label, fn) for _, items in GROUPS for key, label, fn in items}
GROUP_OF = {key: group for group, items in GROUPS for key, _, _ in items}
# 画面の上部に独自の状態表示と主ボタンを持つ画面。共通の状態表示（situation.headline）は出さない
CUSTOM_TOP = {"setup", "profile", "refs", "sources", "records", "candidates", "prep", "meetings"}
# 使う頻度の低い機能は「詳細メニュー」にまとめる。関連する作業の画面からも移動できる
ADVANCED = {"refine", "nfr", "scope", "scenarios", "issues", "conflicts", "risks", "baseline", "usage"}

# 各画面の次の行動（移動先）
NEXT = {"setup": ("背景・目的・関係者を入力します", "profile"), "records": ("候補を確認して要件を整理します", "requirements"), "overview": ("残件のもとになる要件を確認します", "requirements"), "profile": ("会議の質問を準備します", "prep"), "meetings": ("次の会議の質問を準備します", "prep"), "prep": ("会議の資料を登録します", "sources"), "refs": ("会議の質問を準備します", "prep"),
        "sources": ("録画と発言を確認します", "recordings"), "recordings": ("資料と発言から候補を整理します", "candidates"), "candidates": ("採用した内容を要件で確認します", "requirements"),
        "requirements": ("曖昧な要件を具体化します", "refine"), "refine": ("非機能を確認します", "nfr"), "nfr": ("今回の範囲を決めます", "scope"),
        "scope": ("通常と例外の流れを確認します", "scenarios"), "scenarios": ("意見の違いを整理します", "issues"), "issues": ("判断を記録します", "decisions"),
        "decisions": ("確認資料を出力します", "share"), "share": ("追加要望の影響を調べます", "changes"), "changes": ("矛盾の候補を確認します", "conflicts"),
        "conflicts": ("リスクを確認します", "risks"), "risks": ("基準版との差を確認します", "baseline"), "baseline": ("仕様の変遷を確認します", "trail"),
        "trail": ("仕様の理由を確認します", "why"), "why": ("残件を確認します", "overview"), "usage": ("残件を確認します", "overview")}


def sidebar(p: dict) -> None:
    """サイドバー：案件名 → モード固有の情報と操作 → 共通の工程メニュー。

    工程メニューはデモと自分の案件で同じ定義（GROUPS）から描画する。
    デモの案内中は、ステップを進めても工程を自動では開かない（開いた時点ではすべて閉じ、利用者が開閉した状態を保つ）。
    現在地は本文上部の「デモステップ N/8」で伝える。機能画面を開いたときだけ、その工程を開いてページを選択表示し、
    本文の「← デモステップ」で戻ると、選択表示を外して案内中の開閉状態に戻る。
    """
    tour = bool(p.get("demo")) and st.session_state.get("tour_on")
    with st.sidebar:
        if st.button("DefineReq_AI", key="nav_logo", width="stretch"):
            state.go_home()
        st.markdown(f"**{p['name']}**")
        st.caption("・".join(DOMAINS[d] for d in p["domains"]))
        if st.button("← トップへ戻る", key="nav_home"):
            state.go_home()
        # モード固有の情報と操作（共通の工程メニューとは分ける）
        with st.container(key="nav_mode"):
            if p.get("demo"):
                st.caption("デモ：閲覧専用・架空データ")
                if st.button("デモを最初から見る", key="nav_tour", width="stretch"):  # ステップ1からやり直す
                    state.open_demo(p["demo"]["id"], tour=True)
                if st.button("機能対応表", key="nav_map", width="stretch"):
                    st.session_state["tour_on"] = False
                    state.goto("demo_map")
            elif not p.get("is_demo"):
                save_controls(p, "save_side")
        current = None if tour else st.session_state.get("page", "overview")
        # 案内中に利用者が開いた工程（デモを開いた時点では空。機能画面へ行って戻っても変わらない）
        opened: set = st.session_state.setdefault("tour_side_open", set())

        def open_page(key: str) -> None:
            if tour:  # デモの案内中に機能を開くと、本文に元のステップへ戻る操作が出る
                guide.open_detail(key)
            st.session_state["tour_on"] = False
            state.goto(key)

        def nav(key: str, label: str) -> None:
            if st.button(label, key=f"nav_{key}", type="primary" if key == current else "secondary", width="stretch"):
                open_page(key)

        st.caption("工程")
        for n, (group, items) in enumerate(GROUPS):
            active = (n in opened) if tour else group == GROUP_OF.get(current)
            if st.button(f"{n + 1}. {group}", key=f"nav_group_{n}", type="tertiary" if active and not tour else "secondary", width="stretch"):
                if tour:  # 案内中は工程名で開閉するだけ（ステップの位置は変えない）
                    opened.symmetric_difference_update({n})
                    st.rerun()
                open_page(items[0][0])
            if active:  # 開いている工程の機能だけを表示する
                with st.container(key=f"nav_sub_{n}"):
                    for key, label, _ in items:
                        if key not in ADVANCED:
                            nav(key, label)
                    more = [x for x in items if x[0] in ADVANCED]
                    if more:
                        with st.expander("詳細メニュー", expanded=current in ADVANCED):
                            for key, label, _ in more:
                                nav(key, label)


def context_bar(p: dict, page_label: str) -> None:
    parts = [f"<b>{esc(p['name'])}</b>", esc("・".join(DOMAINS[d] for d in p["domains"])), f"作業位置：{esc(page_label)}"]
    if p["baselines"]:
        parts.insert(2, f"基準版：{esc(p['baselines'][-1]['label'])}")
    if p.get("demo"):
        parts.append(f"表示中のデータ：{esc(guide.data_time(p['demo']['stage']))}")  # デモ本編のステップとは別
        parts.append("閲覧専用・架空データ")
    st.html('<div class="dr-bar">' + "".join(f"<span>{x}</span>" for x in parts) + "</div>")


def stage_control(p: dict) -> None:
    d = p.get("demo")
    if not d or st.session_state.get("tour_on"):
        return
    stages = list(STAGES)
    # デモ本編のステップ位置は変えずに、機能画面で表示するデータの時点だけを切り替える（戻るとステップの時点に戻る）
    choice = st.segmented_control("表示するデータの時点（デモのステップ位置は変わりません）", stages, default=d["stage"], format_func=STAGES.get, key=f"stage_seg_{d['stage']}")
    if choice and choice != d["stage"]:
        state.set_stage(choice)


def scroll_top_on_change(p: dict, key: str) -> None:
    """画面や段階が変わったら先頭へ戻す（案内パネルが画面外に隠れないように）。"""
    marker = f"{p['id']}:{key}:{(p.get('demo') or {}).get('stage')}:{st.session_state.get('tour_on')}:{st.session_state.get('tour_index')}:{st.session_state.get('scroll_nonce', 0)}"
    # st.html のスクリプトは初回しか実行されないため、埋め込み枠から親の画面を操作する
    # 先頭へ戻すのは、画面が切り替わった直後だけ。利用者がスクロール・クリック・キー操作をしたら、遅れて動く分を取り消す
    # （戻った直後に「次へ」まで移動して押した瞬間にページが上へ戻り、クリックが成立しないことがあったため）
    # 利用者の操作の時刻は親画面に記録する（この枠の読み込みが遅れても、それより前の操作を判定できるように）
    # S は、この枠が画面に置かれた時刻（枠の文書の開始時刻）。枠の読み込みが遅れても、置かれた後の操作を判定できる
    script = ("const w=window.parent,d=w.document,S=Math.round(performance.timeOrigin);"
              "if(!w.__drIn){w.__drIn={click:0,move:0,down:false};const c=()=>{w.__drIn.click=Date.now();w.__drIn.down=true},u=()=>{w.__drIn.down=false},m=()=>{w.__drIn.move=Date.now()};"
              "d.addEventListener('pointerdown',c,true);d.addEventListener('pointerup',u,true);d.addEventListener('pointercancel',u,true);for(const e of ['wheel','touchmove','keydown']){d.addEventListener(e,m,true)}}"
              # 画面が切り替わった後（枠が置かれた後）に利用者がスクロールやクリックをしていたら、先頭へ戻さない。
              # 枠の読み込みが利用者の操作より遅れることもあるため、ボタンを押している最中や、
              # 画面を切り替えるクリックの後にスクロールしていたときも動かさない（押した瞬間にボタンが動いてクリックが外れるのを防ぐ）
              # 前回この処理で先頭へ戻した後に位置が変わっていたら（スクロールバーや画面内移動を含む）、利用者の操作とみなす
              "let mine=null;const t=()=>{const i=w.__drIn,el=d.querySelector('[data-testid=stMain]');if(!el||i.down||i.move>S||i.click>S||i.move>i.click)return;"
              "if(mine!==null&&el.scrollTop!==mine)return;el.scrollTo(0,0);w.scrollTo(0,0);mine=el.scrollTop};"
              "t();setTimeout(t,150);setTimeout(t,500);"
              # スマートフォン幅ではサイドバーが本文を覆うため、画面を移動したら閉じる
              "if(window.parent.innerWidth<=760){d.querySelector('[data-testid=stSidebarCollapseButton] button')?.click()}")
    # 枠は毎回同じ位置に置く。出したり消したりすると後ろの部品の位置がずれ、開いているタブが閉じてしまう
    # 内容が同じ間は読み直されないため、スクロールは画面が変わったときだけ動く
    # 目印は読み込んだJSONの値を含むため、ハッシュにしてからスクリプトへ入れる
    st.iframe(f"<script>/*{pj.fingerprint(marker)}*/{script}</script>", height=1)


def next_step(key: str, p: dict) -> None:
    """デモの機能画面の下：主ボタンは「デモの続きに戻る」。関連する画面を見返す操作は補助にし、開く対象が分かる名前にする。"""
    if key not in NEXT or st.session_state.get("tour_on") or not p.get("is_demo"):
        return
    text, target = NEXT[key]
    st.divider()
    with st.container(horizontal=True, vertical_alignment="center", key="demo_next"):
        if p.get("demo") and st.button(f"デモの続きに戻る（{guide.back_label(p)[2:-3]}）", key=f"demo_resume_{key}", type="primary"):
            guide.back_to_guide(p)
        label = "この案件の要件一覧を見る" if target == "requirements" else f"{PAGES[target][0]}を見る"
        if st.button(label, key=f"next_{key}"):
            state.goto(target)


def back_to_setup(key: str) -> None:  # noqa: D401
    """自分の案件の各画面の最上部に置く戻る操作。左メニューを閉じていても、案件の準備へ戻れる。"""
    if st.button("← 準備の概要に戻る", key="go_setup_ov" if key == "overview" else f"go_setup_{key}", type="tertiary"):
        state.goto("setup")


def demo_bar(p: dict) -> None:
    """機能画面（詳細）の上部に、開いた元のステップへの戻り道を示す。戻り先の番号と名前をボタンに出す。"""
    with st.container(key="demo_back", horizontal=True, vertical_alignment="center"):
        if st.button(guide.back_label(p), key="tour_back"):  # 戻る操作は補助の見た目
            guide.back_to_guide(p)
        st.caption("いま見ているのは機能画面（実際の一覧と記録）です。閲覧専用のため編集はできません。編集は「あなたの案件で試す」から行えます。")


def render(p: dict) -> None:
    show_flash()
    if p.get("is_demo"):
        st.html(HIDE_CSS)
    sidebar(p)
    key = st.session_state.get("page", "overview")
    scroll_top_on_change(p, key)
    st.session_state["_page_names"] = {k: (GROUP_OF[k], v[0]) for k, v in PAGES.items()}  # ボタンの近くに行き先の正式名を出す
    if p.get("demo") and st.session_state.get("tour_on"):
        guide.render(p)
        return
    label = "デモの機能対応表" if key == "demo_map" else PAGES.get(key, PAGES["overview"])[0]
    context_bar(p, label)
    st.session_state["_group"] = GROUP_OF.get(key)  # 見出しの上の工程名（サイドバーと同じ名前）
    st.session_state["_demo"] = bool(p.get("is_demo"))  # デモの機能画面は、見出し付近に「デモデータ · 閲覧専用」
    st.session_state["_demo_time"] = guide.data_time(p["demo"]["stage"]) if p.get("demo") else None  # と、表示中のデータの時点
    mine = not p.get("is_demo")
    st.session_state["_main_elsewhere"] = False
    empty = key == "overview" and gd.phase(p) == "empty"
    if p.get("demo"):
        demo_bar(p)
    elif mine and key not in ("setup", "profile", "refs", "sources") and not empty:
        back_to_setup(key)  # 背景と資料の画面は、戻る操作を見出しの近くに独自に置く
    if mine and key not in CUSTOM_TOP and not empty:
        # 画面名 → 状態の1行と主ボタン の順にするため、見出しの直後に状態表示を出す（components.head が呼ぶ）
        st.session_state["_head_hook"] = lambda: situation.headline(p, key)
    elif mine:
        st.session_state["_head_hook"] = lambda: situation.resume_line(p, key)
    stage_control(p)
    if key == "demo_map":
        trace.demo_map(p)
    else:
        PAGES.get(key, PAGES["setup"] if mine else PAGES["overview"])[1](p)  # 記録された画面が無効なら案件の準備
        next_step(key if key in PAGES else "overview", p)
        if mine and key not in CUSTOM_TOP and not empty:
            situation.details_for(p, key)  # 理由・作業の段階・AIの補足は、画面の下にまとめる
    st.session_state.pop("_head_hook", None)
