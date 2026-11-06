"""概要・案件情報・会議前の準備。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ... import config
from ... import project as pj
from ...demos.builder import STAGES
from ...logic import checks, continuity, intake
from ...logic import guidance as gd
from ...project import PROFILE_FIELDS, display
from ...schema import CERTAINTY, DOMAINS, QUESTION_STATES
from .. import state
from ..ai_panel import ai_panel, ai_runs_list
from ..candidates import board
from ..components import definition, edit_block, esc, guard, head, ok_rerun, select_item, touch


QUICK_FIELDS = (("problem", "現在、何に困っていますか", "例：月末の勤怠集計に時間がかかる"), ("request", "何を変えたいですか", "例：Excel集計をWebシステムへ更新したい"),
                ("users", "誰が利用しますか", "例：社員100名と上長"), ("constraints", "分かっている制約はありますか", "例：導入時期は未確認"))


def start(p: dict) -> None:
    """新規案件の開始画面。0件の指標は出さず、最初の一歩を案内する。"""
    head(f"{p['name']}の準備を始めましょう", "まず、更新したい理由や現在の困りごとを教えてください。分かる範囲だけで大丈夫です。資料や議事録から始めることもできます。", "案件の準備")
    c1, c2 = st.columns(2)
    if c1.button("背景・困りごとを入力する", key="start_input", type="primary", width="stretch"):
        st.session_state["start_form"] = True
        st.rerun()
    if c2.button("資料・議事録から始める", key="start_records", width="stretch"):
        state.goto("sources")
    if st.session_state.get("start_form"):
        with st.form("start_profile"):
            values = {key: st.text_area(label, placeholder=hint, height=68, key=f"start_{key}") for key, label, hint in QUICK_FIELDS}
            st.caption("不明な項目は空欄のままで進められます。入力した内容は案件情報に「本人申告」として記録します。")
            if st.form_submit_button("案件内に反映", type="primary"):
                filled = {k: v.strip() for k, v in values.items() if v.strip()}
                for key, value in filled.items():
                    p["profile"][key].update(value=value, certainty="本人申告", origin="開始画面の入力")
                if filled:
                    touch(p)
                    st.session_state.pop("start_form", None)
                    ok_rerun("案件に反映しました")
                st.warning("1項目以上入力するか、資料・議事録から始めてください。")


def _todo_list(p: dict) -> None:
    """人が担当・期限を付けて管理する宿題。アプリが勧める操作（上の案内）とは別のもの。"""
    st.subheader("確認・依頼すること")
    confirm = [q for q in p["questions"] if q.get("category") == "確認事項" and q["status"] in ("未質問", "回答待ち")]
    acts = [a for a in p["actions"] if a["state"] in ("未着手", "対応中")]
    if acts:
        st.dataframe(pd.DataFrame([{"ID": a["id"], "内容": a["content"], "担当": display(a.get("owner")), "期限": display(a.get("due")), "状態": a["state"]} for a in acts]), hide_index=True, width="stretch")
    if confirm:
        st.dataframe(pd.DataFrame([{"ID": q["id"], "確認事項": q["text"], "確認相手": display(q.get("ask")), "状態": q["status"]} for q in confirm]), hide_index=True, width="stretch")
    if not acts and not confirm:
        st.caption("登録された依頼や確認事項はありません。")
    with edit_block("action"), st.form("add_action", clear_on_submit=True):
        c1, c2, c3 = st.columns([3, 1, 1])
        text = c1.text_input("依頼・確認を追加", placeholder="例：人事担当に現行の勤怠表を依頼する")
        owner = c2.text_input("担当（未設定可）")
        due = c3.text_input("期限（未設定可）")
        if st.form_submit_button("追加") and text.strip():
            pj.add(p, "actions", {"content": text.strip(), "owner": owner or None, "due": due or None, "related": [], "state": "未着手"})
            touch(p)
            ok_rerun("追加しました")


def overview(p: dict) -> None:
    phase = gd.phase(p)
    if phase == "empty" and not p.get("is_demo"):
        start(p)
        return
    head(p["name"], "現在の状況と、確認・依頼することをまとめています。" if not p.get("is_demo") else "残件と次の行動を確認します。完成度の点数は表示しません。", "案件ホーム")
    bl = checks.backlog(p)
    cols = st.columns(4)
    stats = [("要件", sum(1 for r in p["requirements"] if r["status"] not in ("廃止", "却下"))),
             ("合意済み", sum(1 for r in p["requirements"] if r["status"] == "合意済み")),
             ("残件（対象の数）", bl["unique_total"]),
             ("未解消の矛盾候補", sum(1 for c in p["conflicts"] if c["state"] in ("未確認", "確認中")))]
    for col, (label, n) in zip(cols, stats):
        col.html(f'<div class="dr-stat"><div class="dr-stat-n">{n}</div><div class="dr-stat-l">{esc(label)}</div></div>')
    st.caption(f"分類別の合計は {bl['category_total']} 件です。1つの対象が複数の分類に入ることがあるため、重複を除いた対象の数は {bl['unique_total']} 件です。")

    st.subheader("残件")
    for cat, items in bl["categories"].items():
        if not items:
            continue
        with st.expander(f"{cat}　{len(items)}件"):
            rows = [{"対象": i["target"], "内容": i["content"], "行動": i["action"], "確認相手": display(i.get("ask")),
                     "期限": display(i.get("due")), "状態": i["state"]} for i in items]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            if st.button("対象の画面へ移動", key=f"go_{cat}"):
                state.goto(items[0]["page"])
    if not bl["unique_total"]:
        if phase == "unprocessed":
            st.info("登録された情報はまだ解析していません。残件が0件でも、確認が済んだことを示すものではありません。")
        else:
            st.info("確認した範囲では、残件は検出されていません。登録されていない論点は検出できず、案件全体の確認が完了したことを示すものではありません。")

    _todo_list(p)

    with st.expander("操作の記録"):
        for a in reversed(p["activity"][-30:]):
            st.caption(f"{a['at'][:16].replace('T', ' ')}　{a['message']}")


def profile(p: dict) -> None:
    head("背景・目的・関係者", "確認済み・本人申告・仮説・未確認を区別して記録します。要件定義書の背景と目的はここを参照します。担当者や期限をAIが設定することはありません。", "案件ホーム")
    _reflect_panel(p)
    st.subheader("対象分野")
    if p.get("is_demo"):
        st.write("、".join(DOMAINS[d] for d in p["domains"]))
    with edit_block("dom"):
        domains = st.multiselect("分野（複合は複数選択）", list(DOMAINS), default=p["domains"], format_func=DOMAINS.get, key="pf_domains")
        traits_all = config.checkpoints()["traits"]
        suggested = checks.suggest_traits(p)
        traits = st.multiselect("業務・システムの特徴（深掘りする観点）", list(traits_all), default=p.get("traits", []), format_func=lambda k: traits_all[k]["label"], key="pf_traits")
        missing = [traits_all[k]["label"] for k in suggested if k not in p.get("traits", [])]
        if missing:
            st.caption("本文から提案された特徴（採否は人が決めます）：" + "、".join(missing))
        if st.button("分野と特徴を案件内に反映") and domains:
            p["domains"], p["traits"] = domains, traits
            touch(p)
            ok_rerun("保存しました")

    st.subheader("案件の情報")
    st.caption("分かる範囲だけで構いません。不明な項目は空欄のまま進めます。ここの内容は下のボタンでまとめて案件に反映します。関係者と用語は1件ずつ追加します。")
    if p.get("is_demo"):
        definition([(label, p["profile"][key]["value"]) for key, label in PROFILE_FIELDS.items()])
    with edit_block("profile"), st.form("profile"):
        new = {}
        for key, label in PROFILE_FIELDS.items():
            cur = p["profile"][key]
            c1, c2 = st.columns([4, 1])
            value = c1.text_area(label, value=cur["value"] or "", height=68, key=f"pf_{key}")
            cert = c2.selectbox("確かさ", CERTAINTY, index=CERTAINTY.index(cur["certainty"]), key=f"pfc_{key}")
            new[key] = {"value": value.strip() or None, "certainty": cert}
        st.markdown("**入力が終わったら**（下のどのボタンでも、入力内容を案件に反映します）")
        b1, b2, b3 = st.columns(3)
        save = b1.form_submit_button("案件内に反映", type="primary", width="stretch")
        to_prep = b2.form_submit_button("反映して会議を準備する", width="stretch")
        to_records = b3.form_submit_button("反映して議事録を取り込む", width="stretch")
        if save or to_prep or to_records:
            for key, value in new.items():  # 出所の記録は残す
                value["origin"] = p["profile"][key].get("origin")
            p["profile"].update(new)
            touch(p)
            if to_prep or to_records:
                st.session_state["page"] = "prep" if to_prep else "sources"
            ok_rerun("案件情報を反映しました")

    st.subheader("関係者")
    df = pd.DataFrame([{"ID": s["id"], "氏名・役割": s["name"], "所属": s["org"], "立場": s["position"], "判断・確認できる範囲": s["authority"],
                        "確かさ": s["certainty"], "備考": s.get("note")} for s in p["stakeholders"]],
                      columns=["ID", "氏名・役割", "所属", "立場", "判断・確認できる範囲", "確かさ", "備考"])
    st.dataframe(df, hide_index=True, width="stretch")
    with edit_block("stk"), st.form("add_stk", clear_on_submit=True):
        c = st.columns(4)
        name, org, pos, auth = c[0].text_input("氏名・役割"), c[1].text_input("所属"), c[2].text_input("立場"), c[3].text_input("判断・確認できる範囲")
        cert = st.selectbox("確かさ", CERTAINTY, index=3)
        if st.form_submit_button("関係者を追加") and name.strip():
            pj.add(p, "stakeholders", {"name": name.strip(), "org": org or None, "position": pos or None, "authority": auth or None, "certainty": cert, "note": None})
            touch(p)
            ok_rerun("追加しました")

    st.subheader("用語集")
    st.dataframe(pd.DataFrame([{"用語": g["term"], "意味": g["meaning"]} for g in p["glossary"]], columns=["用語", "意味"]), hide_index=True, width="stretch")
    with edit_block("term"), st.form("add_term", clear_on_submit=True):
        c1, c2 = st.columns([1, 3])
        term, meaning = c1.text_input("用語"), c2.text_input("意味")
        if st.form_submit_button("用語を追加") and term.strip():
            pj.add(p, "glossary", {"term": term.strip(), "meaning": meaning})
            touch(p)
            ok_rerun("追加しました")
    _next_block()


def _next_block() -> None:
    """ページの末尾の進み先。上のフォームの未反映の入力は、フォーム内のボタンで反映できる。"""
    with edit_block("next"):
        st.subheader("入力が終わったら")
        st.caption("案件情報の入力中は、上のフォーム内のボタンを使うと入力内容を反映して移動できます。")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**これから会議をする**")
            st.caption("質問や議題を準備します。")
            if st.button("会議を準備する", key="pf_next_prep", width="stretch"):
                state.goto("prep")
        with c2:
            st.markdown("**すでに議事録・資料がある**")
            st.caption("記録を取り込み、AIで整理します。")
            if st.button("記録を取り込む", key="pf_next_rec", width="stretch"):
                state.goto("sources")


def prep(p: dict) -> None:
    head("質問・議題", "会議で確認することを準備します。AIに候補を作ってもらい、この画面で質問や議題へ追加できます。回答済みの観点は繰り返しません。", "会議の準備")
    pr = p["prep"]
    carryover_panel(p)
    tabs = st.tabs(["理解と議題", "質問", "分野別の確認観点"], key="prep_tabs")
    if p.get("is_demo"):
        with tabs[0]:
            definition([("現時点の理解", pr.get("understanding")), ("会議の目的", pr.get("purpose")), ("不足情報", pr.get("gaps")), ("必要な資料・計測", pr.get("materials")),
                        ("議題", pr.get("agenda")), ("今回決めたいこと", pr.get("decide_today"))])
    with tabs[0], edit_block("prepf"), st.form("prep_form"):
        understanding = st.text_area("現時点の理解", value=pr.get("understanding") or "")
        purpose = st.text_input("会議の目的", value=pr.get("purpose") or "")
        c1, c2 = st.columns(2)
        gaps = c1.text_area("不足情報（1行に1件）", value="\n".join(pr.get("gaps", [])))
        materials = c2.text_area("必要な資料・計測（1行に1件）", value="\n".join(pr.get("materials", [])))
        agenda = c1.text_area("議題（1行に1件）", value="\n".join(pr.get("agenda", [])))
        decide = c2.text_area("今回決めたいこと（1行に1件）", value="\n".join(pr.get("decide_today", [])))
        if st.form_submit_button("案件内に反映", type="primary"):
            def lines(x: str) -> list[str]:
                return [v.strip() for v in x.splitlines() if v.strip()]
            pr.update(understanding=understanding or None, purpose=purpose or None, gaps=lines(gaps), materials=lines(materials),
                      agenda=lines(agenda), decide_today=lines(decide))
            touch(p)
            ok_rerun("保存しました")
    with tabs[1]:
        board(p, ("prep",), "prep_cand", heading="AIが作成した準備の候補")  # 実行した結果を最初に見せる
        qs = p["questions"]
        if qs:
            order = {"高": 0, "中": 1, "低": 2, None: 3}
            st.caption("優先順位の「高→中→低」の順に表示します。回答は会議後に記録します。")
            df = pd.DataFrame([{"ID": q["id"], "種別": q.get("category") or "質問", "質問": q["text"], "優先": q.get("priority"), "優先する理由": q.get("why"), "確認相手": q.get("ask"), "関連要件": "、".join(q.get("related_requirements") or []),
                                "状態": q["status"], "回答": q.get("answer") or ""} for q in sorted(qs, key=lambda x: order.get(x.get("priority"), 3))])
            edited = st.data_editor(df, hide_index=True, width="stretch", disabled=["ID", "種別"],
                                    column_config={"状態": st.column_config.SelectboxColumn(options=QUESTION_STATES, required=True),
                                                   "優先": st.column_config.SelectboxColumn(options=["高", "中", "低"])}, key="q_ed")
            if st.button("質問の変更を保存"):
                for row in edited.to_dict("records"):
                    q = pj.get(p, "questions", row["ID"])
                    q.update(text=row["質問"], priority=row["優先"], why=row["優先する理由"], ask=row["確認相手"], status=row["状態"], answer=row["回答"] or None,
                             related_requirements=[x.strip() for x in str(row["関連要件"] or "").replace(",", "、").split("、") if pj.get(p, "requirements", x.strip())])
                touch(p)
                ok_rerun("保存しました")
        with edit_block("addq"):
            cands = [q for q in checks.prep_questions(p) if q["perspective_id"] not in {x.get("perspective_id") for x in qs}]
            st.markdown(f"**追加できる質問候補　{len(cands)}件**（確認観点の設定から作成。AIは使っていません）")
            chosen = st.multiselect("追加する質問", range(len(cands)), format_func=lambda i: f"［{cands[i]['category']}］{cands[i]['text']}", key="add_q")
            if st.button("選んだ質問を追加") and chosen:
                for i in chosen:
                    c = cands[i]
                    pj.add(p, "questions", {"text": c["text"], "why": c["why"], "ask": c.get("ask"), "priority": None, "status": "未質問",
                                            "answer": None, "perspective_id": c["perspective_id"], "evidence": []})
                touch(p)
                ok_rerun("追加しました")
        ai_panel(p, "prep")
        ai_runs_list(p, "prep")
    with tabs[2]:
        items = checks.perspectives_for(p["domains"])
        if len(p["domains"]) > 1:
            merged = [i for i in items if len(i["merged_ids"]) > 1]
            st.caption(f"複合案件のため、重複する {len(merged)} 件の観点を1つにまとめています。")
        st.dataframe(pd.DataFrame([{"分野": "・".join("共通" if d == "common" else DOMAINS[d] for d in i["domains"]), "分類": i["category"], "確認すること": i["question"],
                                    "確認する理由": i["why"], "確認相手の例": i.get("ask"), "事前に用意": i.get("prep")} for i in items]), hide_index=True, width="stretch")
        st.caption("観点は config/checkpoints.toml で追加・変更できます。すべてを必須入力にはしていません。")


def _reflect_panel(p: dict) -> None:
    """会議準備やAI候補の内容を、人の確認のうえで案件情報へ反映する。無断で上書きしない。"""
    found = intake.profile_suggestions(p)
    if not found:
        return
    with edit_block("reflect"):
        st.subheader("案件情報へ反映できる内容")
        for s in found:
            with st.container(border=True):
                st.markdown(f"**{s['label']}**（出所：{s['origin']}）")
                st.write(s["value"])
                if s["current"]:
                    st.caption(f"現在の内容：{s['current']}")
                    c1, c2 = st.columns(2)
                    if c1.button("置き換える", key=f"pf_replace_{s['id']}"):
                        intake.apply_profile(p, s, "replace")
                        touch(p)
                        ok_rerun("案件情報を更新しました")
                    if c2.button("追記する", key=f"pf_append_{s['id']}"):
                        intake.apply_profile(p, s, "append")
                        touch(p)
                        ok_rerun("案件情報を更新しました")
                elif st.button("確認して案件情報へ反映する", key=f"pf_set_{s['id']}", type="primary"):
                    intake.apply_profile(p, s)
                    touch(p)
                    ok_rerun("案件情報へ反映しました")


def carryover_panel(p: dict) -> None:
    """前回までに残っている事項。"""
    groups = {k: v for k, v in continuity.carryover(p).items() if v}
    if not groups or not gd.has_meeting_record(p):  # 初回には引き継ぐものがない
        return
    st.subheader("前回からの引き継ぎ")
    for name, items in groups.items():
        with st.expander(f"{name}　{len(items)}件"):
            st.dataframe(pd.DataFrame([{"ID": i["id"], "内容": i["text"], "確認相手・担当": display(i["ask"]), "期限": display(i["due"]), "会議": i["meeting"]} for i in items]),
                         hide_index=True, width="stretch")


def meetings(p: dict) -> None:
    head("会議", "会議ごとに資料・発言・判断を関連付け、複数回の会議を同じ案件の続きとして記録します。", "準備")
    with edit_block("addmtg"), st.form("add_mtg", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        name, held = c1.text_input("会議名", placeholder="例：第2回打ち合わせ"), c2.text_input("開催日（不明なら空欄）")
        note = st.text_input("補足")
        if st.form_submit_button("会議を追加") and guard(continuity.add_meeting, p, name, held, note):
            touch(p)
            ok_rerun("追加しました")
    if p["meetings"]:
        st.dataframe(pd.DataFrame([{"ID": m["id"], "会議名": m["name"], "開催日": m.get("held_on") or "記録なし", "資料": len(continuity.meeting_items(p, m["id"])["資料"]) + len(continuity.meeting_items(p, m["id"])["録画"]),
                                    "判断": len(continuity.meeting_items(p, m["id"])["判断"]), "変更履歴": len(continuity.meeting_items(p, m["id"])["変更履歴"])} for m in p["meetings"]]), hide_index=True, width="stretch")
    m = select_item(p["meetings"], lambda x: continuity.label(p, x["id"]), "rq_mtg", "会議はまだありません。")
    if m:
        for name, items in continuity.meeting_items(p, m["id"]).items():
            if items:
                st.markdown(f"**{name}　{len(items)}件**")
                for text in items:
                    st.caption(text)
    carryover_panel(p)
