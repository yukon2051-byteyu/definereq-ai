"""DefineReq_AI の入口。

起動：streamlit run app.py
APIキーがなくてもトップページと3件のデモは動く（有料機能の設定不備で全体を止めない）。
"""
from __future__ import annotations

import streamlit as st

from definereq.ui import home, shell, state
from definereq.ui.theme import CSS

st.set_page_config(page_title="DefineReq_AI", page_icon="📐", layout="wide",
                   initial_sidebar_state="auto" if state.current() else "collapsed")
st.html(CSS)

project = state.current()
try:
    if project is None:
        home.render()
    else:
        shell.render(project)
except st.errors.StreamlitAPIException:
    raise
except Exception as e:  # 想定外の失敗でも案件データを失わないよう、案内を出して操作を続けられるようにする
    if type(e).__name__ in ("RerunException", "StopException"):
        raise
    st.error("画面の表示で問題が発生しました。入力した案件は保持されています。別の画面へ移動してください。")
    st.caption(type(e).__name__)
