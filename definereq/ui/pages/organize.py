"""会議後の整理・要件・具体化・非機能・範囲・シナリオ。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ... import project as pj
from ...logic import checks
from ...project import display, field_state
from ...schema import AGREEMENT_STATES, CANDIDATE_KINDS, DOMAINS, MEASURE_KINDS, MEASURE_STATUS, PRIORITIES, REQ_KINDS, SCOPE_CHOICES
from ..ai_panel import ai_panel, ai_runs_list
from ..components import add_evidence_form, chip, chips, evidence_block, flow, guard, head, ok_rerun, people, select_item, touch, tri_text


def candidates(p: dict) -> None:
    head("会議後の整理", "AIの候補を人が確認し、採用・修正・却下を決めます。候補のままでは要件や合意になりません。", "整理")
    flow([("入力", "選択した資料・発言"), ("AI候補", "要点・要望・決定候補など"), ("人の判断", "採用／修正／却下"), ("結果", "根拠付きの要件・論点")])
    ai_panel(p, "extract")
    ai_runs_list(p, "extract")
    kinds = sorted({c["kind"] for c in p["candidates"]})
    filt = st.multiselect("種類で絞り込む", kinds, key="cand_f")
    items = [c for c in p["candidates"] if not filt or c["kind"] in filt]
    if not items:
        st.info("候補はありません。")
    for c in items:
        with st.container(border=True):
            st.html(f"<div>{chip(c['id'], 'plain')} {chip(c['kind'], 'info')} {chip(c['state'])} {chip(c['origin'], 'plain')}</div>")
            st.markdown(f"**{c['text']}**")
            if c.get("detail"):
                st.caption(c["detail"])
            if c.get("unsupported_numbers"):
                st.warning("資料にない数値が含まれています：" + "、".join(c["unsupported_numbers"]) + "。創作の可能性があるため確認してください。")
            if c.get("no_evidence"):
                st.caption("確認できる根拠がありません。AIの推測として扱ってください。")
            for i, e in enumerate(c.get("evidence", [])):
                evidence_block(p, e, f"cand_{c['id']}_{i}")
            if c["state"] == "候補":
                b1, b2, b3 = st.columns(3)
                if b1.button("要件として採用", key=f"adopt_{c['id']}"):
                    r = pj.add(p, "requirements", pj.new_requirement(title=c["text"][:60], body=c["text"], evidence=c["evidence"], status="下書き", author="AI候補を人が採用"))
                    c.update(state="採用", resolved_as=r["id"])
                    touch(p)
                    ok_rerun(f"{r['id']} を作成しました")
                if b2.button("記録のみ採用", key=f"keep_{c['id']}"):
                    c["state"] = "採用"
                    touch(p)
                    ok_rerun("採用しました")
                if b3.button("却下", key=f"rej_{c['id']}"):
                    c["state"] = "却下"
                    touch(p)
                    ok_rerun("却下しました")
            elif c.get("resolved_as"):
                st.caption(f"反映先：{pj.label_of(p, c['resolved_as'])}")


def _req_label(r: dict) -> str:
    return f"{r['id']} {r['title']}（v{r['version']}・{r['status']}）"


def requirements(p: dict) -> None:
    head("要件", "段階的に入力できます。未設定と該当なしを区別します。合意済みの要件を変更すると、確認待ちに戻ります。", "整理")
    rows = [{"ID": r["id"], "名称": r["title"], "版": r["version"], "分野": DOMAINS.get(r.get("domain"), "未設定"), "種類": display(r.get("kind")), "優先": display(r.get("priority")),
             "範囲": display(r.get("scope")), "状態": r["status"], "受入条件": len(r.get("acceptance") or []), "根拠": len(r.get("evidence") or [])} for r in p["requirements"]]
    c1, c2 = st.columns(2)
    fs = c1.multiselect("状態", AGREEMENT_STATES, key="rq_fs")
    fq = c2.text_input("検索", key="rq_q")
    rows = [r for r in rows if (not fs or r["状態"] in fs) and (not fq or fq in r["名称"] or fq in r["ID"])]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    with st.expander("要件を追加する"):
        with st.form("add_req", clear_on_submit=True):
            title = st.text_input("名称")
            body = st.text_area("本文")
            if st.form_submit_button("追加", type="primary") and title.strip():
                r = pj.add(p, "requirements", pj.new_requirement(title=title.strip(), body=body.strip()))
                touch(p)
                ok_rerun(f"{r['id']} を追加しました")
    r = select_item(p["requirements"], _req_label, "rq_sel", "要件はまだありません。")
    if not r:
        return
    chips(r["status"], r.get("scope") or "未設定")
    if r.get("merged_into") or r.get("replaced_by") or r.get("split_from"):
        st.caption("系譜：" + " → ".join(pj.lineage(p, r["id"])))
    tab = st.tabs(["内容", "根拠", "編集", "版の履歴", "関係"])
    with tab[0]:
        st.markdown(f"**{r['title']}**")
        st.write(r["body"])
        for key, label in (("background", "背景・目的"), ("target", "対象業務・役割・構成要素"), ("preconditions", "前提"), ("behavior", "必要な動作・サービス条件"),
                           ("exceptions", "例外・境界"), ("data_io", "データ・入出力・通信"), ("nonfunctional", "非機能"), ("open_items", "未決")):
            st.caption(f"{label}：{display(r.get(key))}")
        st.caption(f"判断者：{display(r.get('decider'))}／確認相手：{display(r.get('confirm_with'))}／期限：{display(r.get('due'))}")
        if r.get("internal_note"):
            st.info(f"内部メモ（社外資料へ自動掲載しません）：{r['internal_note']}")
    with tab[1]:
        if not r["evidence"]:
            st.caption("根拠は登録されていません。")
        for i, e in enumerate(r["evidence"]):
            evidence_block(p, e, f"req_{r['id']}_{i}")
        add_evidence_form(p, r, f"req_{r['id']}")
    with tab[2]:
        k = f"ed_{r['id']}_{r['version']}"
        title = st.text_input("名称", r["title"], key=k + "t")
        body = st.text_area("本文", r["body"], key=k + "b")
        c1, c2, c3 = st.columns(3)
        domain = c1.selectbox("分野", [None, *DOMAINS], index=([None, *DOMAINS].index(r.get("domain"))), format_func=lambda d: "未設定" if d is None else DOMAINS[d], key=k + "d")
        kind = c2.selectbox("種類", [None, *REQ_KINDS], index=([None, *REQ_KINDS].index(r.get("kind")) if r.get("kind") in REQ_KINDS else 0), format_func=lambda v: v or "未設定", key=k + "k")
        prio = c3.selectbox("優先順位", [None, *PRIORITIES], index=[None, *PRIORITIES].index(r.get("priority")), format_func=lambda v: v or "未設定", key=k + "p")
        values = {}
        for key, label in (("background", "背景・目的"), ("target", "対象"), ("preconditions", "前提"), ("behavior", "必要な動作"), ("exceptions", "例外・境界"),
                           ("data_io", "データ・入出力"), ("nonfunctional", "非機能"), ("open_items", "未決")):
            values[key] = tri_text(label, r.get(key), f"{k}_{key}")
        names = ["", *people(p)]
        c1, c2, c3 = st.columns(3)
        decider = c1.selectbox("判断者", names, index=names.index(r["decider"]) if r.get("decider") in names else 0, key=k + "dec")
        ask = c2.selectbox("確認相手", names, index=names.index(r["confirm_with"]) if r.get("confirm_with") in names else 0, key=k + "ask")
        due = c3.text_input("期限（人が決めます）", r.get("due") or "", key=k + "due")
        note = st.text_input("内部メモ", r.get("internal_note") or "", key=k + "n")
        reason = st.text_input("変更の理由", key=k + "r")
        if st.button("変更を保存（版が上がります）", type="primary", key=k + "s"):
            pj.update_requirement(p, r["id"], {"title": title, "body": body, "domain": domain, "kind": kind, "priority": prio, "decider": decider or None,
                                               "confirm_with": ask or None, "due": due or None, "internal_note": note or None, **values}, reason=reason or None)
            touch(p)
            ok_rerun("保存しました")
        st.divider()
        new_status = st.selectbox("状態の変更", AGREEMENT_STATES, index=AGREEMENT_STATES.index(r["status"]), key=k + "st")
        st.caption("合意済みにするには、関連付いた合意済みの判断記録が必要です（「決定・合意」の画面で記録します）。")
        if st.button("状態を変更", key=k + "stb") and new_status != r["status"]:
            if guard(pj.set_requirement_status, p, r["id"], new_status, "human"):
                touch(p)
                ok_rerun("変更しました")
    with tab[3]:
        if not r["versions"]:
            st.caption("過去の版はありません。")
        for v in reversed(r["versions"]):
            st.markdown(f"**v{v.get('version')}**（{v.get('status')}）　{v.get('superseded_at', '')[:10]}")
            st.write(v.get("body"))
            st.caption(f"変更の理由：{v.get('change_reason') or '理由の記録がありません'}")
    with tab[4]:
        others = [x["id"] for x in p["requirements"] if x["id"] != r["id"]]
        rel = st.multiselect("関連する要件", others, default=[x for x in r.get("related", []) if x in others], key=f"rel_{r['id']}", format_func=lambda i: pj.label_of(p, i))
        nfr_items = {n["id"]: n["label"] for n in checks.nfr_for(p["domains"])}
        tags = st.multiselect("関連する非機能の項目", list(nfr_items), default=[x for x in r.get("nfr_tags") or [] if x in nfr_items], format_func=nfr_items.get, key=f"nt_{r['id']}")
        area = st.text_input("未決の領域（復旧・通信・責任分界など）", r.get("open_area") or "", key=f"oa_{r['id']}")
        if st.button("関連を保存", key=f"rel_b_{r['id']}"):
            r["related"], r["nfr_tags"], r["open_area"] = rel, tags, area or None
            touch(p)
            ok_rerun("保存しました")
        st.markdown("**分割・統合**（元の要件は廃止として残り、追跡できます）")
        parts = st.text_area("分割後の名称（1行に1件）", key=f"split_{r['id']}")
        reason = st.text_input("分割の理由", key=f"split_r_{r['id']}")
        if st.button("分割する", key=f"split_b_{r['id']}") and parts.strip():
            pj.split_requirement(p, r["id"], [{"title": x.strip(), "body": r["body"]} for x in parts.splitlines() if x.strip()], reason or "分割")
            touch(p)
            ok_rerun("分割しました")
        targets = st.multiselect("統合する相手", others, key=f"merge_{r['id']}")
        mt = st.text_input("統合後の名称", key=f"merge_t_{r['id']}")
        if st.button("統合する", key=f"merge_b_{r['id']}") and targets and mt.strip():
            pj.merge_requirements(p, [r["id"], *targets], mt.strip(), r["body"], "統合")
            touch(p)
            ok_rerun("統合しました")


def refine(p: dict) -> None:
    head("具体化・受入条件", "「速い」「止めない」等を測定できる条件にします。数値は人が根拠とともに登録します。", "整理")
    vague = checks.vague_requirements(p)
    if vague:
        st.subheader(f"曖昧な表現が残っている要件　{len(vague)}件")
        for v in vague:
            with st.expander(f"{v['requirement']} {v['title']}"):
                for h in v["hits"]:
                    st.markdown(f"**「{h['word']}」** を確認する質問")
                    for q in h["asks"]:
                        st.write("・" + q)
    ai_panel(p, "refine")
    ai_runs_list(p, "refine")
    r = select_item([x for x in p["requirements"] if x["status"] not in ("廃止", "却下")], _req_label, "rf_sel", "要件はまだありません。")
    if not r:
        return
    st.subheader("数値・単位・測定条件")
    st.caption("必要条件・現状の計測値・仮定・実現方式の候補・人が確定した設計制約を区別します。停止時間・復旧時間・許容データ損失は別の指標として登録してください。")
    cols = ["指標", "値", "単位", "区分", "測定条件", "根拠", "状態"]
    df = pd.DataFrame([{"指標": m.get("metric"), "値": None if m.get("value") is None else str(m.get("value")), "単位": m.get("unit"), "区分": m.get("kind"),
                        "測定条件": m.get("condition"), "根拠": m.get("basis"), "状態": m.get("status")} for m in r.get("measures", [])], columns=cols)
    edited = st.data_editor(df, hide_index=True, width="stretch", num_rows="dynamic", key=f"ms_{r['id']}_{r['version']}", column_config={
        "値": st.column_config.TextColumn(), "区分": st.column_config.SelectboxColumn(options=MEASURE_KINDS), "状態": st.column_config.SelectboxColumn(options=MEASURE_STATUS)})
    st.subheader("受入条件")
    acols = ["前提", "条件", "期待結果", "確認方法"]
    acc = [a for a in r.get("acceptance") or [] if isinstance(a, dict)]
    adf = pd.DataFrame([{"前提": a.get("given"), "条件": a.get("when"), "期待結果": a.get("then"), "確認方法": a.get("how")} for a in acc], columns=acols)
    aed = st.data_editor(adf, hide_index=True, width="stretch", num_rows="dynamic", key=f"ac_{r['id']}_{r['version']}")
    if st.button("数値と受入条件を保存", type="primary", key=f"rf_s_{r['id']}"):
        def clean(v):
            return None if v is None or (isinstance(v, float) and pd.isna(v)) or v == "" else v
        measures = [{"metric": clean(x["指標"]), "value": clean(x["値"]), "unit": clean(x["単位"]), "kind": clean(x["区分"]), "condition": clean(x["測定条件"]),
                     "basis": clean(x["根拠"]), "status": clean(x["状態"])} for x in edited.to_dict("records") if clean(x["指標"])]
        accs = [{"given": clean(x["前提"]) or "", "when": clean(x["条件"]) or "", "then": clean(x["期待結果"]) or "", "how": clean(x["確認方法"]) or ""}
                for x in aed.to_dict("records") if clean(x["期待結果"])]
        pj.update_requirement(p, r["id"], {"measures": measures, "acceptance": accs}, reason="具体化")
        touch(p)
        ok_rerun("保存しました")


def nfr(p: dict) -> None:
    head("非機能の確認", "分野に応じた項目を確認します。二重化やバックアップがあるだけでは条件達成と判断しません。", "整理")
    over = checks.overclaims(p)
    for o in over:
        st.warning(f"{o['requirement']} {o['title']}：{o['note']}")
    data = checks.nfr_overview(p)
    df = pd.DataFrame([{"項目": n["label"], "確認すること": n["question"], "状態": n["state"], "補足": n.get("note"), "関連要件": "、".join(n["requirements"]) or "未設定", "_id": n["id"]} for n in data])
    edited = st.data_editor(df, hide_index=True, width="stretch", disabled=["項目", "確認すること", "関連要件"], key="nfr_ed",
                            column_config={"_id": None, "状態": st.column_config.SelectboxColumn(options=["未確認", "確認済み", "該当なし"], required=True)})
    if st.button("確認状況を保存", type="primary"):
        for row in edited.to_dict("records"):
            p["nfr_status"][row["_id"]] = {"state": row["状態"], "note": row["補足"] or None}
        touch(p)
        ok_rerun("保存しました")
    ai_panel(p, "nfr")
    ai_runs_list(p, "nfr")


def scope(p: dict) -> None:
    head("範囲・優先順位", "今回必須・今回できれば・次回以降・対象外・判断待ちを、理由と判断者とともに記録します。追加費用や工期は創作しません。", "整理")
    active = [r for r in p["requirements"] if r["status"] not in ("廃止", "却下")]
    cols = st.columns(len(SCOPE_CHOICES))
    for c, s in zip(cols, SCOPE_CHOICES):
        c.html(f'<div class="dr-stat"><div class="dr-stat-n">{sum(1 for r in active if r.get("scope") == s)}</div><div class="dr-stat-l">{s}</div></div>')
    df = pd.DataFrame([{"ID": r["id"], "名称": r["title"], "範囲": r.get("scope"), "理由": r.get("scope_reason"), "影響": r.get("scope_impact"), "依存": "、".join(r.get("scope_depends") or []) or None,
                        "判断者": r.get("scope_decider"), "判断日": r.get("scope_decided_at")} for r in active], columns=["ID", "名称", "範囲", "理由", "影響", "依存", "判断者", "判断日"])
    edited = st.data_editor(df, hide_index=True, width="stretch", disabled=["ID", "名称"], key="sc_ed",
                            column_config={"範囲": st.column_config.SelectboxColumn(options=SCOPE_CHOICES, required=True)})
    if st.button("範囲を保存", type="primary"):
        for row in edited.to_dict("records"):
            pj.update_requirement(p, row["ID"], {"scope": row["範囲"], "scope_reason": row["理由"] or None, "scope_impact": row["影響"] or None,
                                                 "scope_depends": [x.strip() for x in (row["依存"] or "").replace(",", "、").split("、") if x.strip()],
                                                 "scope_decider": row["判断者"] or None, "scope_decided_at": row["判断日"] or None}, reason="範囲の変更")
        touch(p)
        ok_rerun("保存しました")


def scenarios(p: dict) -> None:
    head("通常・例外シナリオ", "開始条件、役割、流れ、終了、失敗、訂正、再処理を管理し、要件と結び付けます。", "整理")
    for s in p["scenarios"]:
        with st.container(border=True):
            st.html(f"<div>{chip(s['id'], 'plain')} {chip(s.get('kind', ''), 'info' if s.get('kind') == '通常' else 'warn')}</div>")
            st.markdown(f"**{s['title']}**")
            st.caption(f"開始条件：{display(s.get('start'))}")
            st.write(" → ".join(s.get("steps", [])))
            st.caption(f"終了：{display(s.get('end'))}／失敗・例外：{display(s.get('failure'))}／関連要件：{'、'.join(s.get('related_requirements', [])) or '未設定'}")
    if p["scenarios"]:
        st.dataframe(pd.DataFrame([{"ID": s["id"], "名称": s["title"], "種類": s.get("kind"), "関連要件": "、".join(s.get("related_requirements", []))} for s in p["scenarios"]]), hide_index=True, width="stretch")
    with st.expander("シナリオを追加する"), st.form("add_sc", clear_on_submit=True):
        title = st.text_input("名称")
        kind = st.selectbox("種類", ["通常", "例外"])
        start = st.text_input("開始条件")
        steps = st.text_area("流れ（1行に1手順）")
        end, failure = st.text_input("終了条件"), st.text_input("失敗時の扱い")
        reqs = st.multiselect("関連する要件", [r["id"] for r in p["requirements"]])
        if st.form_submit_button("追加") and title.strip():
            pj.add(p, "scenarios", {"title": title.strip(), "kind": kind, "start": start or None, "roles": None, "steps": [x for x in steps.splitlines() if x.strip()],
                                    "end": end or None, "failure": failure or None, "related_requirements": reqs})
            touch(p)
            ok_rerun("追加しました")
    ai_panel(p, "scenario")
    ai_runs_list(p, "scenario")


CHECKS_FIELD_STATE = field_state  # 画面の表示で「未設定／該当なし」を統一するための参照
CAND_KINDS = CANDIDATE_KINDS
