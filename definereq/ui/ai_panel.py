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


def ai_panel(p: dict, task_key: str, extra: str = "", recordings: bool = False, expanded: bool = False) -> None:
    task = ai.TASKS[task_key]
    if p.get("is_demo"):
        st.caption("デモではAIを実行できません。準備済みのAI候補を表示しています。")
        return
    with st.expander(f"AIで候補を作る：{task.label}", expanded=expanded):
        sources = [s for s in p["sources"] if not s.get("superseded_by")]
        chosen = st.multiselect("送信する資料", [s["id"] for s in sources], default=[s["id"] for s in sources],
                                format_func=lambda i: next(s["name"] for s in sources if s["id"] == i), key=f"ai_src_{task_key}")
        rec_ids: list[str] = []
        if p["recordings"]:
            rec_ids = st.multiselect("送信する文字起こし", [r["id"] for r in p["recordings"]], default=[r["id"] for r in p["recordings"]],
                                     format_func=lambda i: next(r["name"] for r in p["recordings"] if r["id"] == i), key=f"ai_rec_{task_key}")
        context = ai.build_context(p, task, chosen, rec_ids, extra)
        est = ai.estimate(context)
        refs = ai.reference_items(p)
        st.markdown("**AIが参照する案件の情報**")
        for group, values in refs.items():
            if values:
                st.caption(f"{group}：" + "／".join(f"{k}（{v['確かさ']}）：{v['内容']}" if isinstance(v, dict) else f"{k}：{'、'.join(v) if isinstance(v, list) else v}" for k, v in values.items()))
        if not any(refs.values()):
            st.caption("案件の情報は未登録です。案件名と対象分野、選んだ資料だけを送信します。")
        st.caption(f"送信先：Anthropic（Claude API、モデル {config.ai_model()}）／送信量：{len(context):,}文字／費用見込み：最大 約{est:,.0f}円")
        st.caption("上の案件情報と選んだ資料だけを送信します。選んでいない資料、対象外の単位（発表者ノートの初期状態など）、内部メモは送信しません。")
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
        if st.button("この内容でAIを実行", disabled=not (rd.ai and code and again), key=f"ai_go_{task_key}"):  # 折りたたみの中の実行は補助の見た目（記録の整理の実行欄だけ主ボタン）
            _run(p, task_key, code, rd, chosen, rec_ids, extra)


def _run(p: dict, task_key: str, code: str, rd, chosen: list[str], rec_ids: list[str], extra: str = "") -> None:
    """AIを実行して候補を登録する。人がボタンを押したときだけ呼ぶ。"""
    with st.spinner("AIが候補を作成しています。通常1〜2分かかります。"):
        try:
            res = ai.run_task(p, task_key, code, rd.ledger, source_ids=chosen, recording_ids=rec_ids, extra=extra)
        except (AIError, BudgetExceeded, LedgerUnavailable) as e:
            st.error(str(e))
            return
    touch(p)
    skipped = res["run"].get("skipped_duplicates") or 0
    ok_rerun(f"{len(res['candidates'])}件の候補を作成しました（約{res['cost_jpy']:,.1f}円）" + (f"。重複{skipped}件は追加していません" if skipped else ""))


def extract_runner(p: dict, src_ids: list[str], rec_ids: list[str], primary: bool = True) -> None:
    """会議の記録を整理する画面の実行欄。対象の選択と実行ボタンを先に出し、送信内容の詳細は開閉式にする。

    src_ids / rec_ids：初期状態で選ぶ記録（AIで未整理のもの）。未整理の記録が増えたら選択を作り直す。
    実行は、利用者が対象を確認してボタンを押したときだけ行う。
    """
    task = ai.TASKS["extract"]
    sources = [s for s in p["sources"] if not s.get("superseded_by")]
    basis = (tuple(src_ids), tuple(rec_ids))
    # 新しく登録した議事録を初期の選択に入れる。別の画面から戻ったとき（選択欄の値が消えたとき）も作り直す
    if st.session_state.get("ai_extract_basis") != basis or "ai_src_extract" not in st.session_state:
        st.session_state["ai_extract_basis"] = basis
        st.session_state["ai_src_extract"] = list(src_ids)
        st.session_state["ai_rec_extract"] = list(rec_ids)
    names = {s["id"]: f"{s['name']}（{s['kind']}）" for s in sources}
    chosen = st.multiselect("整理する議事録・資料", list(names), format_func=names.get, key="ai_src_extract")
    picked: list[str] = []
    if p["recordings"]:
        recs = {r["id"]: f"{r['name']}（文字起こし）" for r in p["recordings"]}
        picked = st.multiselect("整理する録画・字幕", list(recs), format_func=recs.get, key="ai_rec_extract")
    context = ai.build_context(p, task, chosen, picked, "")
    est = ai.estimate(context)
    code = current_code()
    rd = gate.readiness(code if code else None)
    too_long = len(context) > config.MAX_AI_INPUT_CHARS
    st.caption(f"送信先：Anthropic（{config.ai_model()}）／送信量：{len(context):,}文字／費用見込み：最大 約{est:,.0f}円。押すまでAIは実行しません。")
    if too_long:
        st.warning(f"入力が長すぎます（上限 {config.MAX_AI_INPUT_CHARS:,} 文字）。対象を減らしてください。")
    for reason in rd.reasons:
        if "文字起こし" not in reason:  # 議事録の整理と関係のない説明（文字起こしの設定）は出さない
            st.caption(reason)
    same = [r for r in p["ai_runs"] if r["task"] == "extract" and r["input_fingerprint"] == ai.input_fingerprint(context)]
    again = True
    if same:
        st.info(f"同じ対象の結果 {same[-1]['id']} があります。再実行せずに下の候補を利用できます。")
        again = st.checkbox("費用がかかることを理解して、もう一度実行する", key="ai_again_extract")
    ready = rd.ai and bool(code) and again and not too_long and bool(chosen or picked)
    if st.button("選択した議事録をAIで整理する", disabled=not ready, key="ai_go_extract", type="primary" if primary else "secondary"):
        _run(p, "extract", code, rd, chosen, picked)
    with st.expander("送信する内容の詳細（案件の情報・送信しないもの）"):
        refs = ai.reference_items(p)
        for group, values in refs.items():
            if values:
                st.caption(f"{group}：" + "／".join(f"{k}（{v['確かさ']}）：{v['内容']}" if isinstance(v, dict) else f"{k}：{'、'.join(v) if isinstance(v, list) else v}" for k, v in values.items()))
        st.caption("案件の情報と、選んだ記録だけを送信します。選んでいない資料、対象外の単位、内部メモは送信しません。")


def ai_runs_list(p: dict, task_key: str) -> None:
    runs = [r for r in p["ai_runs"] if r["task"] == task_key]
    if not runs:
        return
    st.markdown("**準備済みのAI候補**" if p.get("is_demo") else "**AI結果の記録**")
    for r in runs:
        status = ai.run_status(p, r)
        st.html(f"<div>{chip(r['id'], 'plain')} {chip(r['source'], 'info')} {chip(status)} {chip(str(r['items']) + '件', 'plain')}</div>")
        if status != "最新":
            st.caption("編集により入力が変わったため、この結果は最新の内容を反映していません。")
