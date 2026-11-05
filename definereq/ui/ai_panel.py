"""AI実行の共通パネル。

実行前に「送信先・対象・費用見込み・残枠」を示し、人がボタンを押したときだけ実行する。
デモは有料APIを使わない。設定が足りない場合も画面は壊さず、理由を示す。
"""
from __future__ import annotations

import streamlit as st

from .. import config
from ..ai import tasks as ai
from ..ai.client import AIError
from ..usage import gate
from ..usage.ledger import BudgetExceeded, LedgerUnavailable
from .components import chip, ok_rerun, touch


def current_code() -> str:
    """トップページで入力したAIパスワード。入力欄はトップページだけに置く。"""
    return st.session_state.get("ai_code", "")


def ai_panel(p: dict, task_key: str, extra: str = "", recordings: bool = False) -> None:
    task = ai.TASKS[task_key]
    with st.expander(f"AIで候補を作る：{task.label}"):
        if p.get("is_demo"):
            st.info("デモでは有料APIを使いません。下の「AI結果の記録」に、事前に用意した結果を表示しています。自由な入力に対して新しいAI結果は作れません。")
            return
        sources = [s for s in p["sources"] if not s.get("superseded_by")]
        chosen = st.multiselect("送信する資料", [s["id"] for s in sources], default=[s["id"] for s in sources],
                                format_func=lambda i: next(s["name"] for s in sources if s["id"] == i), key=f"ai_src_{task_key}")
        rec_ids: list[str] = []
        if p["recordings"]:
            rec_ids = st.multiselect("送信する文字起こし", [r["id"] for r in p["recordings"]], default=[r["id"] for r in p["recordings"]],
                                     format_func=lambda i: next(r["name"] for r in p["recordings"] if r["id"] == i), key=f"ai_rec_{task_key}")
        context = ai.build_context(p, task, chosen, rec_ids, extra)
        est = ai.estimate(context)
        st.caption(f"送信先：Anthropic（Claude API、モデル {config.ai_model()}）／送信量：{len(context):,}文字／費用見込み：最大 約{est:,.0f}円")
        st.caption("選んでいない資料、対象外の単位（発表者ノートの初期状態など）、内部メモは送信しません。")
        code = current_code()
        rd = gate.readiness(code if code else None)
        if len(context) > config.MAX_AI_INPUT_CHARS:
            st.warning(f"入力が長すぎます（上限 {config.MAX_AI_INPUT_CHARS:,} 文字）。対象の資料を減らしてください。")
        for reason in rd.reasons:
            st.caption(reason)
        if rd.ledger is not None and code and rd.ai:
            try:
                s = rd.ledger.summary(code)
                st.caption(f"今月の残枠：全体 約{config.monthly_budget_jpy() - s['all']['cost_jpy']:,.0f}円／このコード 約{config.per_code_budget_jpy() - s['code']['cost_jpy']:,.0f}円")
            except LedgerUnavailable as e:
                st.error(str(e))
                return
        # 同じ入力の結果があれば再実行しない（二重クリックの防止と費用の節約）
        same = [r for r in p["ai_runs"] if r["task"] == task_key and r["input_fingerprint"] == ai.input_fingerprint(context)]
        again = True
        if same:
            st.info(f"同じ入力の結果 {same[-1]['id']} があります。再実行せずに候補を利用できます。")
            again = st.checkbox("費用がかかることを理解して、もう一度実行する", key=f"ai_again_{task_key}")
        if st.button("この内容でAIを実行", disabled=not (rd.ai and code and again), key=f"ai_go_{task_key}", type="primary"):
            with st.spinner("AIが候補を作成しています。通常1〜2分かかります。"):
                try:
                    res = ai.run_task(p, task_key, code, rd.ledger, source_ids=chosen, recording_ids=rec_ids, extra=extra)
                except (AIError, BudgetExceeded, LedgerUnavailable) as e:
                    st.error(str(e))
                    return
            touch(p)
            ok_rerun(f"{len(res['candidates'])}件の候補を作成しました（約{res['cost_jpy']:,.1f}円）")


def ai_runs_list(p: dict, task_key: str) -> None:
    runs = [r for r in p["ai_runs"] if r["task"] == task_key]
    if not runs:
        return
    st.markdown("**AI結果の記録**")
    for r in runs:
        status = ai.run_status(p, r)
        st.html(f"<div>{chip(r['id'], 'plain')} {chip(r['source'], 'info')} {chip(status)} {chip(str(r['items']) + '件', 'plain')}</div>")
        if status != "最新":
            st.caption("編集により入力が変わったため、この結果は最新の内容を反映していません。")
