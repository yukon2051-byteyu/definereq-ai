"""AI候補の一覧。生成した画面で本文と次の操作を確認できるようにする。

種類ごとにまとめ、候補の意味に合うボタンを出す。大量の候補に同じフォームを繰り返さない。
過去の候補は削除せず、最新の解析結果と区別して表示する。
"""
from __future__ import annotations

import streamlit as st

from ..ai import tasks as ai
from .. import project as pj
from ..logic import continuity, intake
from ..schema import CANDIDATE_INTAKE, DOMAINS, REQ_KINDS
from .components import chip, edit_block, esc, evidence_block, guard, ok_rerun, touch

STATE_FILTER = {"未処理": ("候補", "要再確認"), "採用": ("採用", "修正して採用"), "却下": ("却下",), "すべて": None}


def _run_state(p: dict, c: dict) -> str:
    """候補が最新の解析結果かどうか。入力が変わった後の結果を最新として見せない。"""
    run = pj.get(p, "ai_runs", c.get("origin_run"))
    if not run:
        return "解析の記録なし"
    newer = [r for r in p["ai_runs"] if r["task"] == run["task"] and r["ran_at"] > run["ran_at"]]
    if newer:
        return "過去の解析"
    return "最新の解析" if ai.run_status(p, run) == "最新" else "入力の更新前の解析"


def _adopt_form(p: dict, c: dict, meeting: str | None) -> None:
    """要件へ採用する前の確認。推測は推測として示し、必須にしない。"""
    s = intake.suggest(p, c)
    st.caption(f"分類は{s['basis']}です。確認してから採用してください。分からない項目は空欄のままで構いません。")
    domains, kinds = [None, *DOMAINS], [None, *REQ_KINDS]
    with st.form(f"cand_req_{c['id']}"):
        c1, c2 = st.columns(2)
        domain = c1.selectbox("分野", domains, index=domains.index(s["domain"]), format_func=lambda d: "未分類のまま" if d is None else DOMAINS[d])
        kind = c2.selectbox("要件の種類", kinds, index=kinds.index(s["kind"]), format_func=lambda k: k or "未分類のまま")
        target = st.text_input("対象業務・利用者", s["target"] or "")
        data_io = st.text_input("入出力・連携", s["data_io"] or "")
        open_items = st.text_input("未確認事項", s["open_items"] or "")
        parts = intake.split_proposal(c["text"])
        split_text = ""
        if parts:
            st.caption("複数の動作を含む可能性があります。分けて採用する場合は、下の分割案を確認してください（原文の範囲で分けています）。")
            split_text = st.text_area("分割案（1行に1件。空欄なら分割しません）", "\n".join(parts))
        if st.form_submit_button("この内容で要件に採用", type="primary"):
            fields = {"domain": domain, "kind": kind, "target": target, "data_io": data_io, "open_items": open_items, "background": s["background"]}
            created = guard(intake.adopt_requirement, p, c["id"], fields, split_text.splitlines() if split_text.strip() else None, "利用者", meeting)
            if created:
                touch(p)
                st.session_state.pop("cand_open", None)
                ok_rerun("、".join(r["id"] for r in created) + " を要件（下書き）として採用しました")


def _advanced(p: dict, c: dict, meeting: str | None) -> None:
    """既存要件への補足・変更候補への振り分け。通常は使わない詳細操作。"""
    kind = st.selectbox("振り分け", CANDIDATE_INTAKE, key=f"ik_{c['id']}", index=2)
    reqs = [r["id"] for r in p["requirements"]]
    target = st.selectbox("対象の要件（補足・変更候補）", reqs, key=f"it_{c['id']}", index=None, format_func=lambda i: pj.label_of(p, i))
    st.caption("補足と変更候補は追加要望として受け付けます。合意済みの要件は書き換えません。")
    if st.button("この内容で振り分ける", key=f"adopt_{c['id']}"):
        item = guard(continuity.intake_candidate, p, c["id"], kind, target, meeting)
        if item:
            touch(p)
            ok_rerun(f"{item['id']} を作成しました")


def _actions(p: dict, c: dict, meeting: str | None, key: str) -> None:
    route = intake.route_for(c["kind"])
    with edit_block(f"intake_{key}_{c['id']}"):
        owner, due = None, None
        if route.kind == "action":
            a, b = st.columns(2)
            owner = a.text_input("担当（未設定可）", c.get("ask") or "", key=f"own_{c['id']}")
            due = b.text_input("期限（未設定可）", key=f"due_{c['id']}")
        b1, b2, b3, b4 = st.columns([3, 2, 1, 2])
        if route.kind == "requirement":
            if b1.button(route.button, key=f"go_req_{c['id']}", type="primary", width="stretch"):
                st.session_state["cand_open"] = c["id"]
                st.rerun()
        elif route.kind == "profile":
            if b1.button(route.button, key=f"go_prof_{c['id']}", type="primary", width="stretch"):
                st.session_state["page"] = "profile"
                st.rerun()
        elif route.kind == "note":
            if b1.button(route.button, key=f"keep_{c['id']}", width="stretch"):
                c.update(state="採用", resolved_label="記録のみ")
                touch(p)
                ok_rerun("記録として残しました")
        elif b1.button(route.button, key=f"apply_{c['id']}", type="primary", width="stretch"):
            label = guard(intake.apply, p, c["id"], owner or None, due or None, "利用者", meeting)
            if label:
                touch(p)
                ok_rerun(f"「{label}」へ反映しました")
        if b2.button("要再確認にする", key=f"recheck_{c['id']}", width="stretch"):
            c["state"] = "要再確認"
            touch(p)
            st.rerun()
        if b3.button("却下", key=f"rej_{c['id']}", width="stretch"):
            c["state"] = "却下"
            touch(p)
            ok_rerun("却下しました")
        if st.session_state.get("cand_open") == c["id"]:
            _adopt_form(p, c, meeting)
        if route.kind == "requirement" and st.toggle("既存の要件への補足などに振り分ける", key=f"adv_{c['id']}"):
            _advanced(p, c, meeting)


def _row(p: dict, c: dict, meeting: str | None, key: str) -> None:
    run = _run_state(p, c)
    flags = chip(c["state"]) + chip(run, "ok" if run == "最新の解析" else "plain")
    if c.get("no_evidence"):
        flags += chip("根拠なし（推測）", "warn")
    if c.get("unsupported_numbers"):
        flags += chip("資料にない数値：" + "、".join(c["unsupported_numbers"]), "bad")
    if c.get("already_known"):
        flags += chip(f"登録済みの「{c['already_known']}」と重複の可能性", "warn")
    detail = f'<div class="dr-g-sub">{esc(c["detail"])}</div>' if c.get("detail") else ""
    ask = f'<div class="dr-meta">確認相手の候補：{esc(c["ask"])}</div>' if c.get("ask") and c["kind"] != "案件情報" else ""
    st.html(f'<div class="dr-cand"><div class="dr-ai-t">{esc(c["text"])}</div>{detail}{ask}<div class="dr-chips">{flags}</div></div>')
    for i, e in enumerate(c.get("evidence", [])):
        evidence_block(p, e, f"{key}_{c['id']}_{i}")
    if c["state"] in ("候補", "要再確認"):
        _actions(p, c, meeting, key)
    elif c.get("resolved_as") or c.get("resolved_label"):
        target = c.get("resolved_items") or ([c["resolved_as"]] if c.get("resolved_as") else [])
        names = "、".join(pj.label_of(p, x) for x in target) or c.get("resolved_label")
        st.caption(f"反映先：{names}")
        if c.get("resolved_page") and st.button("反映先を見る", key=f"go_to_{key}_{c['id']}"):
            st.session_state["page"] = c["resolved_page"]
            st.rerun()


def board(p: dict, tasks: tuple[str, ...] | None, key: str, meeting: str | None = None, heading: str = "AIの候補") -> None:
    """候補の一覧。tasks を指定すると、その工程で生成した候補だけを出す。"""
    by_run = {r["id"]: r["task"] for r in p["ai_runs"]}
    items = [c for c in p["candidates"] if tasks is None or by_run.get(c.get("origin_run")) in tasks]
    if not items:
        return
    open_n = sum(1 for c in items if c["state"] in ("候補", "要再確認"))
    st.markdown(f"**{heading}**　全{len(items)}件／未処理{open_n}件")
    skipped = sum(r.get("skipped_duplicates") or 0 for r in p["ai_runs"] if tasks is None or r["task"] in tasks)
    if skipped:
        st.caption(f"既存の候補と同じ内容だった{skipped}件は、重複として追加していません。")
    view = st.segmented_control("表示", list(STATE_FILTER), default="未処理" if open_n else "すべて", key=f"{key}_state", required=True)
    states = STATE_FILTER.get(view or "すべて")
    shown = [c for c in items if states is None or c["state"] in states]
    if not shown:
        st.caption("該当する候補はありません。")
    kinds = list(dict.fromkeys(c["kind"] for c in shown))
    for kind in kinds:
        group = [c for c in shown if c["kind"] == kind]
        route = intake.route_for(kind)
        with st.expander(f"{kind}　{len(group)}件" + (f"（反映先：{route.button.replace('に追加', '').replace('として採用', '').replace('として追加', '')}）" if route.kind != "note" else ""), expanded=len(shown) <= 12 or kind == kinds[0]):
            for n, c in enumerate(group):
                if n:
                    st.divider()
                _row(p, c, meeting, key)
