"""意見調整・決定・追加要望・矛盾・リスク・基準版。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ... import project as pj
from ...logic import agreement as ag
from ...logic import baseline as bl
from ...logic import checks, continuity
from ...logic import evidence as ev
from ...project import display
from ...schema import (AGREEMENT_STATES, OPINION_NATURE, CHANGE_CLASSES, CHANGE_STATES, CONFLICT_KINDS, CONFLICT_STATES, IMPACT_AREAS, IMPACT_BASIS,
                       ISSUE_STATES, RISK_NATURE, RISK_STATES)
from ..ai_panel import ai_panel, ai_runs_list
from ..components import add_evidence_form, chip, chips, edit_block, esc, evidence_block, guard, head, meeting_select, ok_rerun, people, select_item, touch


def issues(p: dict) -> None:
    head("意見調整", "発言者ごとの立場と根拠を分け、共通の目的と対立する条件を整理します。採否は人が判断します。", "調整")
    st.dataframe(pd.DataFrame([{"ID": i["id"], "論点": i["topic"], "状態": i["state"], "判断者": display(i.get("decider"))} for i in p["issues"]], columns=["ID", "論点", "状態", "判断者"]), hide_index=True, width="stretch")
    with edit_block("addis"), st.expander("論点を追加する"), st.form("add_issue", clear_on_submit=True):
        topic = st.text_input("論点")
        if st.form_submit_button("追加") and topic.strip():
            pj.add(p, "issues", {"topic": topic.strip(), "opinions": [], "common_goal": None, "conflict_condition": None, "options": [], "decider": None, "ask": None,
                                 "extra_questions": [], "conclusion": None, "state": "未調整", "evidence": [], "related_requirements": []})
            touch(p)
            ok_rerun("追加しました")
    it = select_item(p["issues"], lambda i: f"{i['id']} {i['topic']}", "is_sel", "論点はまだありません。")
    if not it:
        return
    chips(it["state"])
    st.markdown("**意見の違い**")
    for o in it["opinions"]:
        st.html(f"<div>{chip(o['nature'], 'info')} <b>{esc(o['who'])}</b></div>")
        st.write(o["text"])
        if o.get("evidence"):
            evidence_block(p, o["evidence"], f"op_{it['id']}_{o['who']}")
    with edit_block("op"), st.form(f"op_{it['id']}", clear_on_submit=True):
        c1, c2 = st.columns([1, 1])
        who = c1.text_input("発言者・立場")
        nature = c2.selectbox("性質", OPINION_NATURE)
        text = st.text_input("意見の内容")
        srcs = [(s["id"], s["name"]) for s in p["sources"]] + [(r["id"], r["name"]) for r in p["recordings"]]
        names = dict(srcs)
        src = st.selectbox("根拠の資料（任意）", [None, *names], format_func=lambda v: names.get(v, "なし"))
        quote = st.text_input("引用（任意）")
        if st.form_submit_button("意見を追加") and who.strip() and text.strip():
            it["opinions"].append({"who": who.strip(), "nature": nature, "text": text.strip(), "evidence": ev.make(p, src, quote.strip()) if src and quote.strip() else None})
            touch(p)
            ok_rerun("追加しました")
    c1, c2 = st.columns(2)
    c1.markdown(f"**共通の目的**\n\n{display(it.get('common_goal'))}")
    c2.markdown(f"**対立する条件**\n\n{display(it.get('conflict_condition'))}")
    st.markdown(f"**選択肢**：{'、'.join(it.get('options', [])) or '未設定'}")
    st.markdown(f"**判断者**：{display(it.get('decider'))}　**確認相手**：{display(it.get('ask'))}")
    if it.get("extra_questions"):
        st.markdown("**追加の質問**")
        for q in it["extra_questions"]:
            st.write("・" + q)
    with edit_block("is"), st.form(f"is_{it['id']}"):
        state = st.selectbox("状態", ISSUE_STATES, index=ISSUE_STATES.index(it["state"]))
        goal = st.text_input("共通の目的", it.get("common_goal") or "")
        cond = st.text_input("対立する条件", it.get("conflict_condition") or "")
        opts = st.text_input("選択肢（読点区切り）", "、".join(it.get("options", [])))
        names = ["", *people(p)]
        dec = st.selectbox("判断者", names, index=names.index(it["decider"]) if it.get("decider") in names else 0)
        extra = st.text_area("追加の質問（1行に1件）", "\n".join(it.get("extra_questions", [])))
        conc = st.text_area("結論", it.get("conclusion") or "")
        if st.form_submit_button("保存"):
            it.update(state=state, common_goal=goal or None, conflict_condition=cond or None, conclusion=conc or None, decider=dec or None,
                      options=[x.strip() for x in opts.split("、") if x.strip()], extra_questions=[x.strip() for x in extra.splitlines() if x.strip()])
            touch(p)
            ok_rerun("保存しました")


def decisions(p: dict) -> None:
    head("決定・合意", "作成・発言・送付だけでは合意になりません。合意は判断者・判断日・採用案を人が記録して成立します。", "調整")
    st.info(ag.RECORD_NOTICE)
    st.dataframe(pd.DataFrame([{"ID": d["id"], "論点": d["topic"], "状態": d["state"], "判断者": display(d.get("decider")), "判断日": display(d.get("decided_on"))} for d in p["decisions"]],
                              columns=["ID", "論点", "状態", "判断者", "判断日"]), hide_index=True, width="stretch")
    with edit_block("adddc"), st.expander("判断を追加する"), st.form("add_dec", clear_on_submit=True):
        topic = st.text_input("論点")
        options = st.text_area("選択肢（1行に1件）")
        reqs = st.multiselect("関連する要件", [r["id"] for r in p["requirements"]], format_func=lambda i: pj.label_of(p, i))
        if st.form_submit_button("追加") and topic.strip():
            opts = [{"id": chr(65 + i), "label": x.strip(), "pros": None, "cons": None} for i, x in enumerate(options.splitlines()) if x.strip()]
            ag.new_decision(p, topic.strip(), opts, related_requirements=reqs)
            touch(p)
            ok_rerun("追加しました")
    d = select_item(p["decisions"], lambda x: f"{x['id']} {x['topic']}（{x['state']}）", "dc_sel", "判断はまだありません。")
    if not d:
        return
    chips(d["state"])
    if d["options"]:
        st.dataframe(pd.DataFrame([{"案": o["label"], "利点": display(o.get("pros")), "懸念": display(o.get("cons")), "結果": "採用" if o["id"] == d.get("adopted") else (d.get("rejected_reasons", {}).get(o["id"]) or "—")} for o in d["options"]]), hide_index=True, width="stretch")
    st.markdown(f"**採用理由**：{d.get('rationale') or '理由の記録がありません'}")
    if d.get("hold_reason"):
        st.markdown(f"**保留の理由**：{d['hold_reason']}")
    st.caption(f"会議：{continuity.label(p, d.get('meeting_id'))}")
    st.caption(f"判断者：{display(d.get('decider'))}／確認者：{display(d.get('confirmer'))}／判断日：{display(d.get('decided_on'))}／関連要件：{'、'.join(d.get('related_requirements', [])) or '未設定'}／関連変更：{'、'.join(d.get('related_changes', [])) or 'なし'}")
    if d.get("confirmation"):
        st.info(f"確認の記録：{d['confirmation']}")
    for i, e in enumerate(d.get("evidence", [])):
        evidence_block(p, e, f"dec_{d['id']}_{i}")
    if d["state"] == "合意済み" and any(ev.unconfirmed_speech(p, e) for e in d.get("evidence", [])):
        st.warning("話者・内容が未確認の発言を根拠に含みます。発言の確認を行ってください。")
    add_evidence_form(p, d, f"dec_{d['id']}")
    k = f"dc_{d['id']}_{d['state']}"
    labels = {o["id"]: o["label"] for o in d["options"]}
    names = ["", *people(p)]
    with edit_block("dc"), st.form(k):
        adopted = st.selectbox("採用案", [None, *labels], index=[None, *labels].index(d.get("adopted")) if d.get("adopted") in [None, *labels] else 0, format_func=lambda v: labels.get(v, "未定"))
        reason = st.text_area("採用理由", d.get("rationale") or "")
        pros = {}
        cons = {}
        for o in d["options"]:
            c1, c2 = st.columns(2)
            pros[o["id"]] = c1.text_input(f"利点：{o['label']}", o.get("pros") or "")
            cons[o["id"]] = c2.text_input(f"懸念：{o['label']}", o.get("cons") or "")
        rej = {oid: st.text_input(f"不採用の理由：{lab}", d.get("rejected_reasons", {}).get(oid) or "") for oid, lab in labels.items()}
        hold = st.text_input("保留の理由", d.get("hold_reason") or "")
        c1, c2, c3 = st.columns(3)
        decider = c1.selectbox("判断者", names, index=names.index(d["decider"]) if d.get("decider") in names else 0)
        confirmer = c2.selectbox("確認者", names, index=names.index(d["confirmer"]) if d.get("confirmer") in names else 0)
        date = c3.text_input("判断日（YYYY-MM-DD）", d.get("decided_on") or "")
        state = st.selectbox("状態", AGREEMENT_STATES, index=AGREEMENT_STATES.index(d["state"]))
        meeting = meeting_select(p, f"{k}_mtg", d.get("meeting_id"))
        if st.form_submit_button("記録する", type="primary"):
            d["meeting_id"] = meeting
            for o in d["options"]:
                o["pros"], o["cons"] = pros[o["id"]] or None, cons[o["id"]] or None
            d.update(adopted=adopted, rationale=reason or None, rejected_reasons={a: b for a, b in rej.items() if b}, hold_reason=hold or None,
                     decider=decider or None, confirmer=confirmer or None, decided_on=date or None)
            touch(p)
            if state != d["state"]:
                if guard(ag.set_state, p, d["id"], state, "human"):
                    ok_rerun("記録しました")
            else:
                ok_rerun("記録しました")


def changes(p: dict) -> None:
    head("追加要望と影響", "受付だけでは要件は変わりません。影響を調査し、合意済みの判断を結び付けて初めて反映できます。", "変更")
    st.dataframe(pd.DataFrame([{"ID": c["id"], "内容": c["content"], "要望者": display(c.get("requester")), "受付日": display(c.get("requested_at")), "分類": c["classification"], "状態": c["status"]} for c in p["changes"]],
                              columns=["ID", "内容", "要望者", "受付日", "分類", "状態"]), hide_index=True, width="stretch")
    with edit_block("addch"), st.expander("追加要望を受け付ける"), st.form("add_chg", clear_on_submit=True):
        content = st.text_area("要望の内容")
        c1, c2, c3 = st.columns(3)
        who, when, desired = c1.text_input("要望者"), c2.text_input("受付日（不明なら空欄）"), c3.text_input("希望時期")
        bg = st.text_input("背景")
        reqs = st.multiselect("関連しそうな要件", [r["id"] for r in p["requirements"]], format_func=lambda i: pj.label_of(p, i))
        meeting = meeting_select(p, "chg_mtg")
        if st.form_submit_button("受け付ける") and content.strip():
            ag.receive_change(p, content.strip(), who or None, bg or None, None, desired or None, when or None, reqs, meeting)
            touch(p)
            ok_rerun("受け付けました（要件は変更していません）")
    c = select_item(p["changes"], lambda x: f"{x['id']} {x['content'][:40]}", "ch_sel", "追加要望はまだありません。")
    if not c:
        return
    chips(c["status"], c["classification"])
    st.write(c["content"])
    st.caption(f"背景：{display(c.get('background'))}／希望時期：{display(c.get('desired_by'))}")
    for i, e in enumerate(c.get("evidence", [])):
        evidence_block(p, e, f"chg_{c['id']}_{i}")
    add_evidence_form(p, c, f"chg_{c['id']}")
    k = c["id"]
    with edit_block(f"chg{k}"):
        c1, c2 = st.columns(2)
        cls = c1.selectbox("分類", CHANGE_CLASSES, index=CHANGE_CLASSES.index(c["classification"]), key=f"cl_{k}")
        status = c2.selectbox("状態", CHANGE_STATES, index=CHANGE_STATES.index(c["status"]), key=f"cs_{k}")
        if st.button("分類と状態を保存", key=f"cb_{k}"):
            if status == "反映済み" and c["status"] != "反映済み":
                st.error("反映は下の「判断に基づいて反映する」から行ってください。")
            else:
                c.update(classification=cls, status=status)
                touch(p)
                ok_rerun("保存しました")

    st.subheader("影響の調査")
    st.caption("AI候補と確認済みの関連を区別します。")
    st.dataframe(pd.DataFrame([{"領域": i["area"], "対象": display(i.get("target")), "内容": i["note"], "根拠の区分": i["basis"]} for i in c["impacts"]], columns=["領域", "対象", "内容", "根拠の区分"]), hide_index=True, width="stretch")
    left = ag.unsurveyed_areas(c)
    if left:
        st.warning("未調査の領域：" + "、".join(left) + "。ここに表示されない影響がないとは言えません。")
    if st.button("登録された関係から影響候補を取り込む", key=f"ri_{k}", disabled=not c.get("related_requirements")):
        known = {(i["area"], i.get("target")) for i in c["impacts"]}
        for imp in checks.related_impacts(p, c["related_requirements"]):
            if (imp["area"], imp["target"]) not in known:
                ag.add_impact(p, k, imp["area"], imp["target"], imp["note"], imp["basis"])
        touch(p)
        ok_rerun("取り込みました")
    with edit_block("imp"), st.form(f"imp_{k}", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        area = c1.selectbox("領域", IMPACT_AREAS)
        basis = c2.selectbox("根拠の区分", IMPACT_BASIS)
        target = c3.text_input("対象ID")
        note = st.text_input("内容")
        if st.form_submit_button("影響を追加") and note.strip():
            ag.add_impact(p, k, area, target or None, note.strip(), basis)
            touch(p)
            ok_rerun("追加しました")
    ai_panel(p, "impact", extra=f"追加要望：{c['content']}")
    ai_runs_list(p, "impact")

    if p.get("is_demo") and c["status"] != "反映済み":
        return
    st.subheader("判断に基づいて反映する")
    related = [d for d in p["decisions"] if k in d.get("related_changes", [])]
    if c["status"] == "反映済み":
        st.success(f"反映済みです（判断 {display(c.get('decision_id'))}）。")
        return
    if not related:
        st.caption("この追加要望に関連付いた判断がありません。「決定・合意」で判断を作成し、下で関連付けてください。")
        dec_id = st.selectbox("関連付ける判断", [d["id"] for d in p["decisions"]], format_func=lambda i: pj.label_of(p, i), key=f"ld_{k}", index=None)
        if st.button("関連付ける", key=f"lb_{k}") and dec_id:
            pj.require(p, "decisions", dec_id)["related_changes"].append(k)
            touch(p)
            ok_rerun("関連付けました")
        return
    dec = st.selectbox("判断", [d["id"] for d in related], format_func=lambda i: pj.label_of(p, i), key=f"ad_{k}")
    req = st.selectbox("変更する要件", [r["id"] for r in p["requirements"]], format_func=lambda i: pj.label_of(p, i), key=f"ar_{k}", index=None)
    if req:
        body = st.text_area("変更後の本文", pj.require(p, "requirements", req)["body"], key=f"ab_{k}_{req}")
        date = st.text_input("適用日（不明なら空欄）", key=f"ao_{k}")
        if st.button("要件へ反映する", type="primary", key=f"ago_{k}"):
            if guard(ag.apply_change, p, k, dec, {req: {"body": body}}, "human", applied_on=date or None):
                touch(p)
                ok_rerun("反映しました。要件は確認待ちに戻りました。")


def conflicts(p: dict) -> None:
    head("矛盾と不確かさ", "明確な矛盾・前提確認が必要な候補・登録関係からの影響・AI推測・未調査を区別します。未検出は矛盾がないことの保証ではありません。", "変更")
    scan = checks.scan_conflicts(p)
    st.caption("調査範囲：" + scan["scope"])
    known = checks.registered_conflict_keys(p)
    fresh = [c for c in scan["candidates"] if c["key"] not in known]
    if fresh:
        st.subheader(f"新しく検出された候補　{len(fresh)}件")
        for i, c in enumerate(fresh):
            with st.container(border=True):
                st.html(chip(c["kind"]))
                st.write(f"{c['a']} {c['a_title']}　／　{c['b']} {c['b_title']}")
                st.caption(c["note"])
                if st.button("候補として登録", key=f"cf_{i}"):
                    checks.adopt_conflict(p, c)
                    touch(p)
                    ok_rerun("登録しました")
    st.subheader("登録済みの矛盾候補")
    if not p["conflicts"]:
        st.info("登録された矛盾候補はありません。")
    for c in p["conflicts"]:
        with st.container(border=True):
            st.html(f"<div>{chip(c['id'], 'plain')} {chip(c['kind'])} {chip(c['state'])}</div>")
            view = checks.conflict_view(p, c)
            left, right = st.columns(2)
            with left:
                st.markdown("**当時の指摘**")
                for side in view["sides"]:
                    st.caption(f"{side['id']}{side['detected_version']}：{side['detected_text']}")
                st.caption(c["note"])
            with right:
                st.markdown("**現在**")
                for side in view["sides"]:
                    st.caption(f"{side['id']}{side['current_version']}：{side['current_text']}" + ("（変更あり）" if side["changed"] else "（変更なし）"))
                st.caption(view["summary"])
            k = c["id"]
            with edit_block(f"cf{k}"):
                c1, c2 = st.columns([1, 1])
                kind = c1.selectbox("区分", CONFLICT_KINDS, index=CONFLICT_KINDS.index(c["kind"]), key=f"ck_{k}")
                state = c2.selectbox("状態", CONFLICT_STATES, index=CONFLICT_STATES.index(c["state"]), key=f"cs2_{k}")
                app = st.text_input("適用範囲・例外の確認結果", c.get("applicability") or "", key=f"ca_{k}")
            if c.get("applicability") and p.get("is_demo"):
                st.caption(f"適用範囲の確認：{c['applicability']}")
            if c.get("resolution"):
                st.caption(f"解消：{c['resolution']}")
            if not p.get("is_demo") and st.button("保存", key=f"cb2_{k}"):
                c.update(kind=kind, state=state, applicability=app or None)
                touch(p)
                ok_rerun("保存しました")
    ai_panel(p, "conflict")
    ai_runs_list(p, "conflict")


def risks(p: dict) -> None:
    head("リスク", "一般論と事実を分けて記録します。確率、損失額、工数は創作しません。", "変更")
    df = pd.DataFrame([{"ID": r["id"], "内容": r["content"], "性質": r.get("nature"), "条件": r.get("condition"), "影響": r.get("impact"), "不確かさ": r.get("uncertainty"), "対策": r.get("mitigation"), "確認相手": r.get("ask"), "行動": r.get("action"), "状態": r["state"]} for r in p["risks"]],
                      columns=["ID", "内容", "性質", "条件", "影響", "不確かさ", "対策", "確認相手", "行動", "状態"])
    edited = st.data_editor(df, hide_index=True, width="stretch", disabled=["ID"], key="rk_ed", column_config={
        "性質": st.column_config.SelectboxColumn(options=RISK_NATURE), "状態": st.column_config.SelectboxColumn(options=RISK_STATES, required=True)})
    if st.button("保存", type="primary", key="rk_s"):
        for row in edited.to_dict("records"):
            pj.require(p, "risks", row["ID"]).update(content=row["内容"], nature=row["性質"], condition=row["条件"], impact=row["影響"], uncertainty=row["不確かさ"], mitigation=row["対策"], ask=row["確認相手"], action=row["行動"], state=row["状態"])
        touch(p)
        ok_rerun("保存しました")
    for r in p["risks"]:
        for i, e in enumerate(r.get("evidence", [])):
            evidence_block(p, e, f"rk_{r['id']}_{i}")
    with edit_block("addrk"), st.expander("リスクを追加する"), st.form("add_risk", clear_on_submit=True):
        content = st.text_input("内容")
        nature = st.selectbox("性質", RISK_NATURE)
        if st.form_submit_button("追加") and content.strip():
            pj.add(p, "risks", {"content": content.strip(), "nature": nature, "condition": None, "impact": None, "uncertainty": None, "mitigation": None, "ask": None,
                                "action": None, "state": "未対応", "evidence": [], "related_requirements": []})
            touch(p)
            ok_rerun("追加しました")
    ai_panel(p, "risk")
    ai_runs_list(p, "risk")


def baseline(p: dict) -> None:
    head("基準版と再確認", "合意版を保存し、検討中の変更と比較します。根拠・要件・判断・受入条件が変わると、関連項目と共有資料を再確認対象にします。", "変更")
    with edit_block("bl"), st.form("add_bl", clear_on_submit=True):
        label = st.text_input("基準版の名称")
        if st.form_submit_button("現在の合意済み項目を基準版として保存") and label.strip():
            bl.create(p, label.strip())
            touch(p)
            ok_rerun("保存しました")
    b = select_item(p["baselines"], lambda x: f"{x['id']} {x['label']}（要件{len(x['requirements'])}件）", "bl_sel", "基準版はまだありません。")
    if b:
        diff = bl.compare(p, b["id"])
        st.caption(f"保存日時：{b['saved_at'][:16].replace('T', ' ')}")
        st.markdown(f"**基準版からの差分**：変更 {len(diff['changed'])}件／追加 {len(diff['added'])}件／削除 {len(diff['removed'])}件／判断の変更 {len(diff['decisions_changed'])}件")
        for c in diff["changed"]:
            with st.expander(f"{c['id']} {c['title']}（v{c['from_version']}→v{c['to_version']}・{c['status']}）"):
                for x in c["diffs"]:
                    st.markdown(f"**{x['field']}**")
                    a, b2 = st.columns(2)
                    a.caption("変更前")
                    a.write(x["before"])
                    b2.caption("変更後")
                    b2.write(x["after"])
    st.subheader("再確認の対象")
    targets = bl.reconfirm_targets(p, b["id"] if b else None)
    if targets:
        st.dataframe(pd.DataFrame([{"対象": t["id"], "理由": t["reason"]} for t in targets]), hide_index=True, width="stretch")
    else:
        st.info("現在の登録内容から検出された再確認の対象はありません。")
