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

# これから確認する内容で、事実の主張ではない種類。根拠がないのが普通なので注意を出さない
PLANNING_KINDS = {"質問", "議題", "必要資料", "今回決めたいこと", "不足情報"}
STATE_FILTER = {"すべて": None, "未処理": ("候補", "要再確認"), "採用": ("採用", "修正して採用"), "却下": ("却下",)}
# 候補を確定したときに登録される場所（logic/intake.py の反映先と同じ）。AIの候補と、人が確定した内容を区別して示す
DESTINATION = {"requirement": "要件一覧（下書き）", "decision": "判断記録の下書き（決定・合意）", "confirm": "確認事項（質問・議題）", "question": "会議の質問（質問・議題）",
               "agenda": "議題（質問・議題）", "material": "資料の依頼事項（質問・議題）", "decide_today": "今回決めたいこと（質問・議題）", "action": "確認・依頼事項（現在の状況）",
               "risk": "リスク一覧", "issue": "意見調整", "profile": "案件情報（背景・目的・関係者）", "note": "記録のみ"}


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
    st.caption(f"この操作で要件の下書きを登録します（合意にはなりません）。分類は{s['basis']}です。確認してから採用してください。分からない項目は空欄のままで構いません。")
    domains, kinds = [None, *DOMAINS], [None, *REQ_KINDS]
    parts = intake.split_proposal(c["text"])
    split = bool(parts) and st.toggle("複数の要件に分けて採用する", value=True, key=f"split_{c['id']}", help="原文の範囲で分けた案です。分類は1件ずつ確認できます。")
    rows = intake.split_details(p, c, parts) if split else [{**s, "text": c["text"]}]
    if split and c.get("detail"):
        st.caption(f"元の候補の補足：{c['detail']}")

    def row(n: int, item: dict) -> dict:
        text = st.text_area(f"要件{n + 1}の本文", item["text"], key=f"cr_t_{c['id']}_{n}", height=68) if split else item["text"]
        c1, c2 = st.columns(2)
        domain = c1.selectbox(f"分野（要件{n + 1}）", domains, index=domains.index(item["domain"]), format_func=lambda d: "未分類のまま" if d is None else DOMAINS[d], key=f"cr_d_{c['id']}_{n}")
        kind = c2.selectbox(f"要件の種類（要件{n + 1}）", kinds, index=kinds.index(item["kind"]), format_func=lambda k: k or "未分類のまま", key=f"cr_k_{c['id']}_{n}")
        target = st.text_input(f"対象業務・利用者（要件{n + 1}）", item.get("target") or "", key=f"cr_u_{c['id']}_{n}")
        data_io = st.text_input(f"入出力・連携（要件{n + 1}）", item.get("data_io") or "", key=f"cr_i_{c['id']}_{n}")
        open_items = st.text_input(f"未確認事項（要件{n + 1}）", item.get("open_items") or "", key=f"cr_o_{c['id']}_{n}")
        return {"text": text, "domain": domain, "kind": kind, "target": target, "data_io": data_io, "open_items": open_items, "background": s["background"]}

    with st.form(f"cand_req_{c['id']}_{len(rows)}"):
        values = [row(n, item) for n, item in enumerate(rows)]
        if st.form_submit_button("この内容で採用", type="primary"):
            created = guard(intake.adopt_requirement, p, c["id"], None, values, "利用者", meeting)
            if created:  # 登録できたときだけ、採用した候補の近くに結果と次の操作を出す
                touch(p)
                st.session_state.pop("cand_open", None)
                st.session_state["cand_done"] = {"cand": c["id"], "reqs": [r["id"] for r in created]}
                st.session_state["cand_focus"] = c["id"]  # 採用した候補は一覧の後ろへ移るため、結果の位置へ移動する
                st.rerun()


def _decision_form(p: dict, c: dict, meeting: str | None) -> None:
    """決定の候補の確認欄。開いただけではデータを変えない。「判断記録の下書きを作成」で1回だけ作成する（合意にはならない）。

    選んだ要件との関係に合わせて、作成される内容を確定の前に示す。
    """
    choices = {"link": "既存の要件に関連付ける", "new": "決定の内容から新しい要件の下書きを作る", "none": "要件を伴わない判断として記録する"}
    with st.container(border=True, key=f"cand_dec_{c['id']}"):
        how = st.radio("要件との関係", list(choices), format_func=choices.get, key=f"cd_h_{c['id']}", index=0 if p["requirements"] else 1)
        linked: list[str] = []
        if how == "link":
            reqs = [r["id"] for r in p["requirements"]]
            linked = st.multiselect("関連付ける要件", reqs, format_func=lambda i: pj.label_of(p, i), key=f"cd_r_{c['id']}")
        if how == "new":
            plan = "判断記録と要件の下書きを作成します。"
        elif how == "link" and linked:
            plan = f"判断記録の下書きを作成し、{'、'.join(linked)} に関連付けます（要件の内容は変更しません）。"
        elif how == "link":
            plan = "判断記録の下書きを作成します。関連付ける要件を選んでいないため、要件には関連付けません。"
        else:
            plan = "判断記録の下書きだけを作成します（要件は作成しません）。"
        st.html(f'<div class="dr-kind">作成する内容<b>{esc(plan)}</b></div>')
        st.caption("この操作で判断記録の下書きを作成します。正式な判断・合意にはなりません。合意は「決定・合意」で、判断者・判断日・採用案を人が記録して確定します。")
        if st.button("判断記録の下書きを作成", type="primary", key=f"cd_go_{c['id']}"):
            label = guard(intake.apply, p, c["id"], meeting_id=meeting, link_requirements=linked, new_requirement=how == "new")
            if label:  # 既存の登録処理（候補の状態で二重登録を防ぐ）で作成できたときだけ、結果を候補の近くに出す
                touch(p)
                st.session_state.pop("cand_open", None)
                items = c.get("resolved_items") or []
                decision = next((i for i in items if i.startswith("DEC")), None)
                new_reqs = [i for i in items if i.startswith("REQ")] if how == "new" else []
                st.session_state["cand_done"] = {"cand": c["id"], "kind": "decision", "decision": decision, "reqs": new_reqs, "linked": linked}
                st.session_state["cand_focus"] = c["id"]  # 確定した候補は一覧の後ろへ移るため、結果の位置へ移動する
                st.rerun()


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
        owner, due, ask = intake.KEEP, intake.KEEP, intake.KEEP
        if route.kind == "action":  # 担当・確認相手・期限は別の項目。入力した値をそのまま保存する
            a, b, d = st.columns(3)
            owner = a.text_input("担当（未設定可）", intake.owner_of(c) or "", key=f"own_{c['id']}")
            ask = b.text_input("確認相手（未設定可）", ai.person_name(c.get("ask")) or "", key=f"ask_{c['id']}")
            due = d.text_input("期限（未設定可）", c.get("due") or "", key=f"due_{c['id']}")
        b1, b2, b3, b4 = st.columns([3, 2, 1, 2])
        if route.kind == "requirement":
            if b1.button(route.button, key=f"go_req_{c['id']}", width="stretch"):
                st.session_state["cand_open"] = c["id"]
                st.rerun()
        elif route.kind == "decision":
            if b1.button(route.button, key=f"go_dec_{c['id']}", width="stretch"):
                st.session_state["cand_open"] = c["id"]
                st.rerun()
        elif route.kind == "profile":
            if b1.button(route.button, key=f"go_prof_{c['id']}", width="stretch"):
                st.session_state["page"] = "profile"
                st.rerun()
        elif route.kind == "note":
            if b1.button(route.button, key=f"keep_{c['id']}", width="stretch"):
                c.update(state="採用", resolved_label="記録のみ")
                touch(p)
                ok_rerun("記録として残しました")
        elif b1.button(route.button, key=f"apply_{c['id']}", width="stretch"):
            label = guard(intake.apply, p, c["id"], owner, due, "利用者", meeting, ask)
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
            (_decision_form if route.kind == "decision" else _adopt_form)(p, c, meeting)
        if route.kind == "requirement" and st.toggle("既存の要件への補足などに振り分ける", key=f"adv_{c['id']}"):
            _advanced(p, c, meeting)


def _after_adopt(p: dict, c: dict) -> None:
    """採用した直後：結果と、続ける操作（次の未確認候補へ）・採用結果への導線（登録した要件を開く）。"""
    from . import state

    done = st.session_state.get("cand_done")
    if not done or done["cand"] != c["id"]:
        return
    ids = [i for i in done["reqs"] if pj.get(p, "requirements", i)]
    if done.get("kind") == "decision":
        _after_decision(p, c, done, ids)
        return
    st.success(f"要件を下書きとして登録しました（{'、'.join(ids)}）。合意は「決定・合意」で人が記録します。")
    order = st.session_state.get("_cand_order", [])
    waiting = [i for i in order if (pj.get(p, "candidates", i) or {}).get("state") in ("候補", "要再確認")]
    after = order[order.index(c["id"]) + 1:] if c["id"] in order else []
    nxt = next((i for i in after if i in waiting), waiting[0] if waiting else None)  # 画面の表示順で次の確認待ち
    reason = f"会議記録の候補「{c['text'][:24]}」から登録した要件"
    with st.container(horizontal=True, key=f"cand_after_{c['id']}"):
        if nxt:
            if st.button("次の未確認候補へ", key="cand_next", type="primary"):
                st.session_state.pop("cand_done", None)
                st.session_state["cand_focus"] = nxt
                st.rerun()
            if st.button("登録した要件を開く", key="cand_open_reqs"):
                state.open_requirements(ids, reason, "candidates")
        else:
            if st.button("登録した要件を開く", key="cand_open_reqs", type="primary"):
                state.open_requirements(ids, reason, "candidates")
            if st.button("要件一覧を開く", key="cand_all_reqs"):
                state.goto("requirements")


def _next_waiting(c: dict, p: dict) -> str | None:
    """画面の表示順で、この候補の次にある確認待ちの候補。"""
    order = st.session_state.get("_cand_order", [])
    waiting = [i for i in order if (pj.get(p, "candidates", i) or {}).get("state") in ("候補", "要再確認")]
    after = order[order.index(c["id"]) + 1:] if c["id"] in order else []
    return next((i for i in after if i in waiting), waiting[0] if waiting else None)


def _after_decision(p: dict, c: dict, done: dict, new_reqs: list[str]) -> None:
    """判断記録の下書きを作った直後：実際に作成したものと、開く操作。自動では移動しない。"""
    from . import state

    dec = done.get("decision")
    made = [f"判断記録の下書き {dec}"] + ([f"要件の下書き {'、'.join(new_reqs)}"] if new_reqs else [])
    linked = f"（{'、'.join(done['linked'])} に関連付け）" if done.get("linked") else ""
    st.success(f"{'と'.join(made)}を作成しました{linked}。合意は「決定・合意」で判断者・判断日・採用案を記録して確定します。")
    nxt = _next_waiting(c, p)
    with st.container(horizontal=True, key=f"cand_after_{c['id']}"):
        if dec and st.button("決定・合意で下書きを開く", key="cand_open_dec", type="primary"):
            state.goto("decisions", keep={"dc_sel": dec})
        if new_reqs and st.button("要件の下書きを開く", key="cand_open_reqs"):
            state.open_requirements(new_reqs, f"会議記録の候補「{c['text'][:24]}」から作成した要件の下書き", "candidates")
        if nxt and st.button("次の未確認候補へ", key="cand_next", type="tertiary"):
            st.session_state.pop("cand_done", None)
            st.session_state["cand_focus"] = nxt
            st.rerun()


def _row(p: dict, c: dict, meeting: str | None, key: str) -> None:
    run = _run_state(p, c)
    focus = st.session_state.get("cand_focus") == c["id"]
    st.html(f'<div id="cand-{esc(c["id"])}" class="dr-anchor{" dr-cand-focus" if focus else ""}"></div>')
    done = c["state"] in ("採用", "修正して採用")
    flags = (chip("採用済み", "ok") if done else chip(c["state"])) + chip(run, "ok" if run == "最新の解析" else "plain")
    if c.get("no_evidence") and c["kind"] not in PLANNING_KINDS:
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
        _after_adopt(p, c)
        target = c.get("resolved_items") or ([c["resolved_as"]] if c.get("resolved_as") else [])
        names = "、".join(pj.label_of(p, x) for x in target) or c.get("resolved_label")
        st.caption(f"反映先：{names}（人が確定した内容です）")
        if c.get("resolved_page") and st.button("反映先を確認する", key=f"go_to_{key}_{c['id']}"):
            st.session_state["page"] = c["resolved_page"]
            st.rerun()


def board(p: dict, tasks: tuple[str, ...] | None, key: str, meeting: str | None = None, heading: str = "会議記録の候補") -> None:
    """候補の一覧。tasks を指定すると、その工程で生成した候補だけを出す。"""
    by_run = {r["id"]: r["task"] for r in p["ai_runs"]}
    items = [c for c in p["candidates"] if tasks is None or by_run.get(c.get("origin_run")) in tasks]
    if not items:
        return
    open_n = sum(1 for c in items if c["state"] in ("候補", "要再確認"))
    st.markdown(f"**{heading}**　全{len(items)}件／確認待ち{open_n}件")
    skipped = sum(r.get("skipped_duplicates") or 0 for r in p["ai_runs"] if tasks is None or r["task"] in tasks)
    if skipped:
        st.caption(f"既存の候補と同じ内容だった{skipped}件は、重複として追加していません。")
    # 初期表示は「すべて」。確認待ちを先に並べ、採用した候補にも「採用済み」と反映先を出す
    view = st.segmented_control("表示", list(STATE_FILTER), default="すべて", key=f"{key}_state", required=True)
    states = STATE_FILTER.get(view or "すべて")
    shown = sorted((c for c in items if states is None or c["state"] in states), key=lambda c: c["state"] not in ("候補", "要再確認"))
    kinds_order = list(dict.fromkeys(c["kind"] for c in shown))
    st.session_state["_cand_order"] = [c["id"] for k in kinds_order for c in shown if c["kind"] == k]  # 画面の表示順
    focus = st.session_state.get("cand_focus") or (st.session_state.get("cand_done") or {}).get("cand")
    if not shown:
        st.caption("該当する候補はありません。")
    kinds = list(dict.fromkeys(c["kind"] for c in shown))
    for kind in kinds:
        group = [c for c in shown if c["kind"] == kind]
        route = intake.route_for(kind)
        waiting = sum(1 for c in group if c["state"] in ("候補", "要再確認"))
        has_focus = any(c["id"] == focus for c in group)  # 次に確認する候補・採用した候補がある区分は開く
        with st.expander(f"{kind}　{len(group)}件（確認待ち{waiting}件）→ 確定すると：{DESTINATION.get(route.kind, '記録のみ')}", expanded=len(shown) <= 12 or kind == kinds[0] or has_focus):
            for n, c in enumerate(group):
                if n:
                    st.divider()
                _row(p, c, meeting, key)
    target = st.session_state.pop("cand_focus", None)
    if target:  # 次の未確認候補、または確定した候補（結果の表示）の位置へ移動する
        st.iframe(f"<script>/*{target}-{pj.now_iso()}*/const t=()=>window.parent.document.getElementById('cand-{target}')?.scrollIntoView({{block:'start'}});setTimeout(t,200);setTimeout(t,700)</script>", height=1)
        st.session_state["cand_focus_shown"] = target
