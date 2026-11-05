"""デモを閲覧専用にする。

デモでは、入力欄を無効にし、編集のボタンを表示しない。表示の切替（項目の選択、段階、案内、質問）だけを許可する。
各画面に条件分岐を書かず、部品の呼び出しを1か所で包むことで、許可の漏れを防いでいる。
判定は利用者ごとの session_state で行うため、利用者の間で影響しない。
"""
from __future__ import annotations

import functools
import re

import streamlit as st
from streamlit.delta_generator import DeltaGenerator

# 閲覧の操作として許可する部品（key の先頭）
VIEW_WIDGET = re.compile(r"^(rq_|rf_sel|is_sel|dc_sel|ch_sel|bl_sel|src_sel|rec_sel|seg_play|cand_f|tr_sel|sh_|xl_in|why_q|play_|stage_seg)")
VIEW_BUTTON = re.compile(r"^(nav_|tour_|go_|ex_|next_|share_word)")

DISABLE = ("text_input", "text_area", "selectbox", "multiselect", "radio", "toggle", "checkbox", "slider")


def is_demo() -> bool:
    try:
        project = st.session_state.get("project")
    except Exception:  # 画面の外（テストの準備など）では対象外
        return False
    return bool(project and project.get("is_demo"))


def _patch(name: str, make) -> None:
    original = getattr(DeltaGenerator, name)
    wrapped = make(original)
    functools.update_wrapper(wrapped, original)
    setattr(DeltaGenerator, name, wrapped)
    # st.button などは起動時の部品に結び付いているため、こちらも差し替える
    setattr(st, name, lambda *a, **k: wrapped(st._main, *a, **k))


def _disable(original):
    def call(self, *args, **kwargs):
        if is_demo() and not VIEW_WIDGET.match(str(kwargs.get("key") or "")):
            kwargs["disabled"] = True
        return original(self, *args, **kwargs)
    return call


def _button(original):
    def call(self, *args, **kwargs):
        if is_demo() and not VIEW_BUTTON.match(str(kwargs.get("key") or "")):
            return False
        return original(self, *args, **kwargs)
    return call


def _data_editor(original):
    def call(self, *args, **kwargs):
        if is_demo():
            kwargs["disabled"] = True
            kwargs["num_rows"] = "fixed"
        return original(self, *args, **kwargs)
    return call


def _uploader(original):
    def call(self, *args, **kwargs):
        return None if is_demo() else original(self, *args, **kwargs)
    return call


def _submit(original):
    def call(self, *args, **kwargs):
        if is_demo():
            kwargs["disabled"] = True  # フォームの決まりで部品は必要。画面ではCSSで隠す
        return original(self, *args, **kwargs)
    return call


def install() -> None:
    if getattr(DeltaGenerator, "_definereq_readonly", False):
        return
    for name in DISABLE:
        _patch(name, _disable)
    _patch("button", _button)
    _patch("data_editor", _data_editor)
    _patch("file_uploader", _uploader)
    _patch("form_submit_button", _submit)
    DeltaGenerator._definereq_readonly = True


HIDE_CSS = """<style>
[data-testid="stFormSubmitButton"]{display:none}
[class*="st-key-edit-"]{display:none}
</style>"""
