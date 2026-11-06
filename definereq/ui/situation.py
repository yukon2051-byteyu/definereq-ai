"""状況案内の共通部品。デモと実案件で同じ見た目の枠を使う。

- デモ：案件の前提、デモ用の役割、現在の場面を示す
- 実案件：プログラムの判定（logic/guidance.py）を示し、必要なときだけAIの補足を付ける

案内は表示するだけで、案件の内容を変更しない。閉じても作業でき、再表示できる。
"""
from __future__ import annotations

import streamlit as st

from .. import config
from ..ai import guidance as ai_guidance
from ..ai import tasks as ai_tasks
from ..ai.client import AIError
from ..logic import guidance as gd
from ..usage import gate
from ..usage.ledger import BudgetExceeded, LedgerUnavailable
from . import state
from .ai_panel import current_code
from .components import chip, esc, ok_rerun, touch

STAGE_CHOICES = {None: "まだ分からない", "before_first": "はい、初回会議の前です", "after_first": "いいえ、会議は実施済みです"}


def frame(tag: str, rows: list[tuple[str, str]], lead: str = "", kind: str = "demo") -> str:
    """案内の枠のHTML。文字は全てエスケープする。"""
    body = "".join(f'<div class="dr-sit-row"><b>{esc(k)}</b><span>{esc(v)}</span></div>' for k, v in rows)
    intro = f'<p class="dr-sit-lead">{esc(lead)}</p>' if lead else ""
    return f'<div class="dr-sit dr-sit-{kind}"><div class="dr-sit-tag">{esc(tag)}</div>{intro}{body}</div>'


def demo_banner(name: str, intro: dict, step: dict, first: bool, move: str | None, background: list[tuple[str, str]]) -> None:
    """デモの状況案内。背景は最初の画面の本文で説明し、ここでは時点と行うことだけを短く示す。"""
    if first:
        st.html(frame(f"デモ体験中｜{name}", [], f"あなたは、{intro['role']}です（デモ用の役割）。"))
        return
    st.html(frame(f"{name}｜{step['scene']}", [], " ".join(x for x in (move, step["check"]) if x)))
    with st.expander("案件の背景を確認"):  # 開いても画面は移動しないため、同じ場面のまま確認できる
        for label, text in background:
            st.markdown(f"**{label}**")
            st.write(text)


def _advice_html(a: gd.Advice) -> str:
    return frame(f"現在：{a.title}", [("現在の状況", a.situation), ("今、確認するとよいこと", a.todo), ("案内の理由", a.reason)], kind="work")


def _go(a: gd.Advice, page: str, key: str) -> None:
    if a.page == page:
        return
    if st.button(a.button, key=key, type="primary"):
        st.session_state["resumed"] = False
        state.goto(a.page)


def _note_items(note: dict) -> None:
    for it in note["items"]:
        flags = chip("根拠の確認が必要", "warn") if it.get("no_evidence") else ""
        if it.get("unsupported_numbers"):
            flags += chip("資料にない数値あり", "warn")
        ask = f'<div class="dr-meta">確認相手の候補：{esc(it["ask"])}</div>' if it.get("ask") else ""
        detail = f'<div class="dr-g-sub">{esc(it["detail"])}</div>' if it.get("detail") else ""
        quotes = "".join(f'<div class="dr-meta">「{esc(str(e["quote"]))}」 {esc(str(e["where"]))}</div>' for e in it.get("evidence", []))
        st.html(f'<div class="dr-ai-note"><div class="dr-v-lab">{esc(str(it.get("kind") or "補足"))}</div><div class="dr-ai-t">{esc(it["text"])}</div>{detail}{ask}{quotes}<div class="dr-chips">{flags}</div></div>')


def _ai_block(p: dict, a: gd.Advice) -> None:
    fp = gd.state_fingerprint(p)
    note = ai_guidance.current_note(p, fp, a.id)
    if note:
        st.caption(f"AIの提案（{note['generated_at'][:16].replace('T', ' ')} 作成）。人が判断してください。上の案内は登録データに基づく状態の説明です。")
        _note_items(note)
    old = ai_guidance.stale_notes(p, fp)
    if old:
        with st.expander("以前のAI補足（案件の状態が変わったため、現在の案内ではありません）"):
            st.caption(f"作成：{old[-1]['generated_at'][:16].replace('T', ' ')}／対象：{old[-1].get('advice_title') or '記録なし'}")
            _note_items(old[-1])
    if note:
        return
    with st.expander("AIに補足してもらう（ボタンを押したときだけ実行）"):
        code = current_code()
        rd = gate.readiness(code if code else None)
        if not rd.ai:
            st.caption("今はAIを使えません。この案内は登録データからプログラムが判定しているため、そのまま作業を続けられます。")
            for reason in rd.reasons:
                st.caption(reason)
            return
        context = ai_guidance.build_context(p, a)
        st.caption(f"送信先：Anthropic（モデル {config.ai_model()}）／送信量：{len(context):,}文字／費用見込み：最大 約{ai_tasks.estimate(context, ai_guidance.MAX_OUTPUT_TOKENS):,.0f}円。"
                   "内部メモは送信しません。結果は提案として表示し、要件や判断は変更しません。")
        busy = st.session_state.get("guide_ai_busy", False)
        if st.button("AIで補足を作成", key="guide_ai", disabled=busy):
            st.session_state["guide_ai_busy"] = True
            try:
                with st.spinner("AIが案内の補足を作成しています。"):
                    ai_guidance.run(p, a, code, rd.ledger)
            except (AIError, BudgetExceeded, LedgerUnavailable) as e:
                st.warning(f"AIの補足を作成できませんでした。{e} 通常の操作はそのまま続けられます。")
                return
            except Exception:
                st.warning("AIの補足を作成できませんでした。時間をおいて再度お試しください。通常の操作はそのまま続けられます。")
                return
            finally:
                st.session_state["guide_ai_busy"] = False
            touch(p)
            ok_rerun("AIの補足を作成しました")


def _stage_question(p: dict) -> None:
    """記録から段階を判断できないときだけ確かめる。指定は利用者の判断として保持する。"""
    current = gd.user_stage(p)
    keys = list(STAGE_CHOICES)
    choice = st.radio("初回会議の前ですか？（会議の記録がないため確認しています）", keys, index=keys.index(current), format_func=STAGE_CHOICES.get, horizontal=True, key="guide_stage")
    if choice != current:
        gd.guidance_store(p)["user_stage"] = choice
        st.rerun()


def project_panel(p: dict, page: str) -> None:
    """実案件の状況案内。主な案内は1件で、折りたたんでも作業を続けられる。"""
    if st.session_state.get("guidance_hidden"):
        if st.button("状況案内を表示", key="guide_show", type="tertiary"):
            st.session_state["guidance_hidden"] = False
            st.rerun()
        return
    result = gd.assess(p, page, st.session_state.get("resumed", False))
    main = result["main"]
    if main is None:
        st.html(frame("現在：確認が必要な項目は検出されていません", [("補足", "登録された内容からの判定です。登録されていない論点は検出できません。案件の完成や正しさを示すものではありません。")], kind="work"))
    else:
        st.html(_advice_html(main))
    c1, c2 = st.columns([3, 1])
    with c1:
        if main:
            _go(main, page, "guide_go")
    if c2.button("案内を閉じる", key="guide_hide", type="tertiary", width="stretch"):
        if main and main.id == "resume":
            st.session_state["resumed"] = False
        else:
            st.session_state["guidance_hidden"] = True
        st.rerun()
    if result["stage_question"]:
        _stage_question(p)
    if main and main.items:
        st.caption("該当する項目：" + "／".join(main.items))
    others = result["extra"] + result["rest"]
    if others:
        with st.expander(f"ほかの案内（{len(others)}件）"):
            for n, a in enumerate(others):
                st.markdown(f"**{a.title}**")
                st.write(a.situation)
                st.caption(f"案内の理由：{a.reason}")
                _go(a, page, f"guide_go_{n}")
    if main:
        _ai_block(p, main)
