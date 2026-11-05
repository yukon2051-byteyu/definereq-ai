"""概要・案件情報・会議前の準備。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ... import config
from ... import project as pj
from ...demos.builder import STAGES
from ...logic import checks
from ...project import PROFILE_FIELDS, display
from ...schema import CERTAINTY, DOMAINS, QUESTION_STATES
from .. import state
from ..ai_panel import ai_panel, ai_runs_list
from ..components import edit_block, esc, head, ok_rerun, touch


def overview(p: dict) -> None:
    head(p["name"], "残件と次の行動を確認します。完成度の点数は表示しません。", "概要")
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
        st.info("現在の登録内容から検出された残件はありません。登録されていない論点は検出できません。")

    st.subheader("次の行動")
    na = checks.next_actions(p)
    if na["actions"]:
        st.dataframe(pd.DataFrame([{"ID": a["id"], "内容": a["content"], "担当": display(a.get("owner")), "期限": display(a.get("due")), "状態": a["state"]}
                                   for a in na["actions"]]), hide_index=True, width="stretch")
    with edit_block("action"), st.form("add_action", clear_on_submit=True):
        c1, c2, c3 = st.columns([3, 1, 1])
        text = c1.text_input("行動を追加")
        owner = c2.text_input("担当（未設定可）")
        due = c3.text_input("期限（未設定可）")
        if st.form_submit_button("追加") and text.strip():
            pj.add(p, "actions", {"content": text.strip(), "owner": owner or None, "due": due or None, "related": [], "state": "未着手"})
            touch(p)
            ok_rerun("行動を追加しました")

    with st.expander("操作の記録"):
        for a in reversed(p["activity"][-30:]):
            st.caption(f"{a['at'][:16].replace('T', ' ')}　{a['message']}")


def profile(p: dict) -> None:
    head("案件情報・関係者", "確認済み・本人申告・仮説・未確認を区別して記録します。担当者や期限をAIが設定することはありません。", "準備")
    st.subheader("対象分野")
    domains = st.multiselect("分野（複合は複数選択）", list(DOMAINS), default=p["domains"], format_func=DOMAINS.get, key="pf_domains")
    traits_all = config.checkpoints()["traits"]
    suggested = checks.suggest_traits(p)
    traits = st.multiselect("業務・システムの特徴（深掘りする観点）", list(traits_all), default=p.get("traits", []), format_func=lambda k: traits_all[k]["label"], key="pf_traits")
    missing = [traits_all[k]["label"] for k in suggested if k not in p.get("traits", [])]
    if missing:
        st.caption("本文から提案された特徴（採否は人が決めます）：" + "、".join(missing))
    if st.button("分野と特徴を保存") and domains:
        p["domains"], p["traits"] = domains, traits
        touch(p)
        ok_rerun("保存しました")

    st.subheader("案件の情報")
    with st.form("profile"):
        new = {}
        for key, label in PROFILE_FIELDS.items():
            cur = p["profile"][key]
            c1, c2 = st.columns([4, 1])
            value = c1.text_area(label, value=cur["value"] or "", height=68, key=f"pf_{key}")
            cert = c2.selectbox("確かさ", CERTAINTY, index=CERTAINTY.index(cur["certainty"]), key=f"pfc_{key}")
            new[key] = {"value": value.strip() or None, "certainty": cert}
        if st.form_submit_button("保存", type="primary"):
            p["profile"].update(new)
            touch(p)
            ok_rerun("保存しました")

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


def prep(p: dict) -> None:
    head("会議前の準備", "固定の確認観点と案件の特徴を組み合わせて質問を用意します。回答済みの観点は繰り返しません。", "準備")
    pr = p["prep"]
    tabs = st.tabs(["理解と議題", "質問", "分野別の確認観点"])
    with tabs[0], st.form("prep_form"):
        understanding = st.text_area("現時点の理解", value=pr.get("understanding") or "")
        purpose = st.text_input("会議の目的", value=pr.get("purpose") or "")
        c1, c2 = st.columns(2)
        gaps = c1.text_area("不足情報（1行に1件）", value="\n".join(pr.get("gaps", [])))
        materials = c2.text_area("必要な資料・計測（1行に1件）", value="\n".join(pr.get("materials", [])))
        agenda = c1.text_area("議題（1行に1件）", value="\n".join(pr.get("agenda", [])))
        decide = c2.text_area("今回決めたいこと（1行に1件）", value="\n".join(pr.get("decide_today", [])))
        if st.form_submit_button("保存", type="primary"):
            def lines(x: str) -> list[str]:
                return [v.strip() for v in x.splitlines() if v.strip()]
            pr.update(understanding=understanding or None, purpose=purpose or None, gaps=lines(gaps), materials=lines(materials),
                      agenda=lines(agenda), decide_today=lines(decide))
            touch(p)
            ok_rerun("保存しました")
    with tabs[1]:
        qs = p["questions"]
        if qs:
            order = {"高": 0, "中": 1, "低": 2, None: 3}
            st.caption("優先順位の「高→中→低」の順に表示します。回答は会議後に記録します。")
            df = pd.DataFrame([{"ID": q["id"], "質問": q["text"], "優先": q.get("priority"), "優先する理由": q.get("why"), "確認相手": q.get("ask"),
                                "状態": q["status"], "回答": q.get("answer") or ""} for q in sorted(qs, key=lambda x: order.get(x.get("priority"), 3))])
            edited = st.data_editor(df, hide_index=True, width="stretch", disabled=["ID"],
                                    column_config={"状態": st.column_config.SelectboxColumn(options=QUESTION_STATES, required=True),
                                                   "優先": st.column_config.SelectboxColumn(options=["高", "中", "低"])}, key="q_ed")
            if st.button("質問の変更を保存"):
                for row in edited.to_dict("records"):
                    q = pj.get(p, "questions", row["ID"])
                    q.update(text=row["質問"], priority=row["優先"], why=row["優先する理由"], ask=row["確認相手"], status=row["状態"], answer=row["回答"] or None)
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
