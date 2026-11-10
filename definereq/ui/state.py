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
    keep = {"project", "page", "demo_copies", "tour_index", "tour_on", "media_paths", "ai_code", "flash", "last_view", "save_fp", "save_time", "show_home", "work_project",
            "demo_done", "artifact_files", "guidance_hidden", "scroll_nonce", "drafts", "home_was_valid", "resumed", "scroll_to", "guide_ai_busy", "tour_side_open"}
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
    # 新しい案件は案件の準備から始める。再開した案件は、保存時に開いていた画面へ戻る（記録がなければ案件の準備）
    last = p.pop("last_page", None) if loaded else None
    st.session_state["page"] = last if isinstance(last, str) and last.isascii() and last.isalpha() else "setup"
    st.session_state["tour_on"] = False
    st.session_state["show_home"] = False
    st.session_state["save_time"] = None
    st.session_state.pop("work_project", None)
    st.session_state["save_fp"] = pj.fingerprint(p) if loaded else None
    st.session_state["resumed"] = loaded  # 再開の案内は、作業位置を推測せず記録の範囲で出す
    st.session_state["guidance_hidden"] = False
    st.rerun()


def go_home(section: str | None = None) -> None:
    """トップへ戻る。作業中の案件は保持する。section を指定すると、その欄まで移動する。"""
    p = current()
    if section:
        st.session_state["scroll_to"] = section
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


def open_demo(demo_id: str, tour: bool = True, stage: int | None = None, start: int = 0) -> None:
    """デモを開く。start を指定すると、そのステップ（一覧の見どころへの近道）から開く。"""
    _clear_widgets()
    p = current()
    if p and not p.get("is_demo"):  # デモを見ても作業中の案件を失わない
        st.session_state["work_project"] = p
    st.session_state["show_home"] = False
    steps = guide.load(demo_id)
    stage = stage or (steps[start]["stage"] if tour else 4)
    st.session_state["project"] = demo_copy(demo_id, stage)
    st.session_state["tour_on"] = tour
    st.session_state["tour_side_open"] = set()  # デモを開いた時点では、サイドバーの工程はすべて閉じる
    st.session_state["tour_index"] = start
    st.session_state["page"] = steps[start]["page"] if tour else "overview"
    st.session_state.pop("ev_focus", None)
    if start:  # 近道で開いたときだけ、前提と「案件の背景から見る」を出す
        st.session_state["tour_via_shortcut"] = start
    else:
        st.session_state.pop("tour_via_shortcut", None)
    st.rerun()


def open_requirements(ids: list[str], reason: str, from_page: str, cat: str | None = None) -> None:
    """残件などから、関係する要件に絞って要件一覧を開く。絞り込みはこの移動のときだけ有効にする。"""
    goto_keep = {"req_focus": {"ids": ids, "reason": reason, "from": from_page, "cat": cat}}
    if len(ids) == 1:
        goto_keep["rq_sel"] = ids[0]  # 1件なら、その要件の詳細を開く
    goto("requirements", keep=goto_keep)


def goto(page: str, keep: dict | None = None) -> None:
    st.session_state.pop("src_done", None)  # 資料の登録直後の案内は、別の画面へ移ったら閉じる
    st.session_state.pop("pf_saved", None)  # 背景の保存直後の案内も同じ
    st.session_state["resumed"] = False  # 再開の通知は、作業を始めたら閉じる
    st.session_state.pop("req_focus", None)  # 残件から開いたときの絞り込みは、その移動のときだけ
    st.session_state.pop("cand_done", None)  # 候補を採用した直後の案内は、別の画面へ移ったら閉じる
    st.session_state.pop("refs_from", None)  # 質問・議題から参考資料を開いた印（戻り先）は、その移動のときだけ
    st.session_state.pop("rec_new", None)  # 今回登録した議事録の印は、議事録の登録直後の移動のときだけ
    st.session_state.pop("rec_meeting", None)  # 会議の画面から選んだ会議（記録の整理で関連付ける会議の初期値）
    st.session_state.pop("prep_saved", None)  # 質問・議題の反映直後の案内
    st.session_state.pop("mtg_done", None)  # 会議の登録直後の案内
    for k, v in (keep or {}).items():
        st.session_state[k] = v
    st.session_state["page"] = page
    st.rerun()


def goto_minutes() -> None:
    """会議の記録を整理する画面へ移動する。取込みからAIの整理までを1画面で行う。"""
    goto("records")


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
