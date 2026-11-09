"""入力途中の内容（下書き）の保持。

Streamlit では、画面を離れると入力欄の値が消える。入力のたびに値を下書きへ写し、
同じ画面に戻ったときに下書きから入力欄を復元する。下書きは案件IDごとに分けるため、別の案件と混ざらない。
下書きは利用中のブラウザーの中だけにあり、案件には「保存」を押したときに反映する。
"""
from __future__ import annotations

import streamlit as st

from ..project import PROFILE_FIELDS


def store(project_id: str) -> dict:
    return st.session_state.setdefault("drafts", {}).setdefault(project_id, {})


def widget(project_id: str, name: str, make, label: str, saved, **kwargs):
    """下書きを持つ入力欄。make は st.text_area などの部品。"""
    draft = store(project_id)
    key = f"draft_{project_id}_{name}"
    if key not in st.session_state:  # 画面に戻ったときは下書き、なければ保存済みの値で始める
        st.session_state[key] = draft.get(name, saved)

    def keep() -> None:
        draft[name] = st.session_state[key]

    return make(label, key=key, on_change=keep, **kwargs)


def clear(project_id: str, names: list[str]) -> None:
    """保存した項目の下書きと入力欄の値を消す。次に開いたときは保存済みの値が出る。"""
    draft = store(project_id)
    for name in names:
        draft.pop(name, None)
        st.session_state.pop(f"draft_{project_id}_{name}", None)


def profile_pending(p: dict) -> bool:
    """背景・目的の下書きに、保存していない変更があるか。"""
    draft = st.session_state.get("drafts", {}).get(p["id"], {})
    for key in PROFILE_FIELDS:
        cur = p["profile"][key]
        if f"v_{key}" in draft and (draft[f"v_{key}"] or "").strip() != (cur["value"] or ""):
            return True
        if f"c_{key}" in draft and draft[f"c_{key}"] != cur["certainty"]:
            return True
    return any((draft.get(n) or "").strip() for n in ("stk_name", "term_term"))


def profile_state(p: dict) -> str:
    """背景・目的・関係者の状態。実際の案件データと下書きから求める。"""
    if profile_pending(p):
        return "未保存の変更あり"
    filled = any(v.get("value") for v in p["profile"].values()) or p["stakeholders"] or p["glossary"]
    return "入力済み" if filled else "未入力"


def records_count(p: dict) -> int:
    """取り込みが完了した資料・議事録・録画の件数。選んだだけのファイルや失敗は数えない。"""
    return sum(1 for s in p["sources"] if not s.get("superseded_by")) + len(p["recordings"])
