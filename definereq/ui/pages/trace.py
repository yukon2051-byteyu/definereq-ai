"""仕様の変遷・なぜこの仕様か・共有資料と出力・AIと費用。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from ... import config
from ... import project as pj
from ...demos import builder
from ...export import excelx, jsonio, share, wordx
from ...logic import agreement as ag
from ...logic import continuity
from ...logic import why as whylogic
from ...project import display
from ...schema import DOC_TYPES
from ...usage import gate
from ...usage.ledger import LedgerUnavailable
from .. import artifacts, state
from ..ai_panel import current_code
from ..components import main_type, chip, chips, edit_block, esc, evidence_block, head, ok_rerun, save_controls, select_item, touch


def trail(p: dict) -> None:
    head("仕様の変遷", "現在の要件と経緯を確認します。不明な日付は記録日時で代用しません。過去を上書きせず、訂正は履歴を追加します。", "経緯")
    target = st.selectbox("要件で絞り込む", [None, *[r["id"] for r in p["requirements"]]], format_func=lambda i: "全ての要件" if i is None else pj.label_of(p, i), key="tr_sel")
    related = pj.lineage(p, target) if target else None
    items = [h for h in p["history"] if related is None or h.get("requirement_id") in related]
    corrected = {h.get("corrects") for h in p["history"] if h.get("corrects")}
    if target:
        r = pj.require(p, "requirements", target)
        chips(r["status"], f"v{r['version']}")
        st.write(f"**現在の条件**：{r['body']}")
        if len(related) > 1:
            st.caption("分割・統合の系譜：" + " / ".join(related))
    if not items:
        st.info("履歴はまだありません。")
    for h in sorted(items, key=lambda x: x.get("decided_on") or x.get("recorded_at") or ""):
        with st.container(border=True):
            flags = chip(h["outcome"]) + (chip("訂正済み", "plain") if h["id"] in corrected else "") + (chip(f"{h['corrects']} の訂正", "warn") if h.get("corrects") else "")
            st.html(f"<div>{chip(h['id'], 'plain')} {chip(h.get('requirement_id') or '要件なし', 'plain')} {flags}</div>")
            st.markdown(f"**{h.get('trigger')}**")
            if h.get("before") or h.get("after"):
                c1, c2 = st.columns(2)
                c1.caption("変更前")
                c1.write(h.get("before") or "（なし）")
                c2.caption("変更後")
                c2.write(h.get("after") or "（なし）")
            if h.get("options"):
                st.caption("比較した案：" + "、".join(h["options"]))
            st.write(f"理由：{h.get('rationale') or whylogic.NO_REASON}")
            st.caption(f"会議：{continuity.label(p, h.get('meeting_id'))}")
            st.caption(f"会議日：{display(h.get('meeting_date'))}／提案日：{display(h.get('proposed_on'))}／判断日：{display(h.get('decided_on'))}／適用日：{display(h.get('applied_on'))}／"
                       f"記録日時：{(h.get('recorded_at') or '')[:16].replace('T', ' ')}／判断者：{display(h.get('decider'))}／確認者：{display(h.get('confirmer'))}")
            for i, e in enumerate(h.get("evidence") or []):
                evidence_block(p, e, f"his_{h['id']}_{i}")
    with edit_block("cor"), st.expander("履歴を訂正する（元の記録は残ります）"):
        hid = st.selectbox("訂正する履歴", [h["id"] for h in p["history"]], key="cor_id", index=None)
        new_reason = st.text_input("訂正後の理由", key="cor_r")
        new_date = st.text_input("訂正後の判断日（変更しない場合は空欄）", key="cor_d")
        why_ = st.text_input("訂正の理由", key="cor_w")
        if st.button("訂正を追加") and hid and why_.strip():
            fields = {"rationale": new_reason or pj.require(p, "history", hid).get("rationale")}
            if new_date:
                fields["decided_on"] = new_date
            ag.correct_history(p, hid, fields, why_)
            touch(p)
            ok_rerun("訂正を追加しました")


EXAMPLES = {"d1": ["なぜ再申請なのか", "代理承認はどうなったのか", "なぜ部長の承認が必要なのか"],
            "d2": ["なぜ復旧は4時間以内なのか", "なぜ保存期間は3年なのか", "締め後の数字はなぜ固定なのか"],
            "d3": ["なぜ遠隔保守を今回やらないのか", "なぜ外部接続は禁止なのか", "なぜ回線を二重化するのか"]}


def why(p: dict) -> None:
    head("なぜこの仕様か", "登録済みの情報だけから回答します。理由がなければ「理由の記録がありません」と答えます。他の案件は参照しません。AIは使わず、料金は発生しません。", "経緯")
    samples = EXAMPLES.get((p.get("demo") or {}).get("id"), [])
    if samples:
        cols = st.columns(len(samples))
        for c, q in zip(cols, samples):
            if c.button(q, key=f"ex_{q}", width="stretch"):
                st.session_state["why_q"] = q
    q = st.text_input("質問", key="why_q", placeholder="例：なぜこの方式にしたのか／REQ-001 の理由は？")
    if not q:
        return
    a = whylogic.answer(p, q)
    if a["status"] == "not_found":
        st.warning(a["message"])
        st.caption(a["note"])
        return
    if a["status"] == "ambiguous":
        st.warning(a["message"])
        for c in a["candidates"]:
            st.write(f"・{c['id']} {c['title']}（{c['status']}）")
        st.caption("要件ID（例：REQ-001）を含めて質問してください。")
        return
    if a["status"] != "answered":
        return
    st.markdown(f"**対象**：{a['target']['id']} {a['target']['title']}")
    cur = a["current"]
    chips(cur["status"], f"現行 v{cur['version']}", cur.get("scope") or "")
    if cur.get("notice"):
        st.warning(cur["notice"])
    st.markdown(f"**現在の条件**　{cur['body']}")
    if a["reason_recorded"]:
        st.success(f"採用理由：{a['reason']}")
    else:
        st.warning(whylogic.NO_REASON)
    for d in a["decisions"]:
        with st.container(border=True):
            st.markdown(f"**決定時点** {d['id']} {d['topic']}")
            st.caption(f"判断日：{d['date'] or '記録なし'}／判断者：{d['decider'] or '記録なし'}／確認者：{d['confirmer'] or '記録なし'}")
            st.write(f"採用：{d['adopted'] or '未定'}")
            if d.get("reason"):
                st.write(f"この判断の理由：{d['reason']}")
            if d.get("confirmation"):
                st.caption(f"確認の記録：{d['confirmation']}")
            for o in d["options"]:
                if not o["adopted"]:
                    st.caption(f"比較した案：{o['label']}／不採用の理由：{o['rejected_reason'] or whylogic.NO_REASON}")
            for c in d["citations"]:
                st.html(f'<div class="dr-ev"><div class="dr-ev-q">「{esc(str(c["text"]))}」</div><div class="dr-ev-w">{esc(c["where"])}</div></div>')
    for d in a["not_agreed"]:
        st.caption(f"合意していない判断：{d['id']} {d['topic']}（{d['state']}）。理由として採用していません。")
    if a["past_versions"]:
        with st.expander(f"過去の版（現行ではありません）　{len(a['past_versions'])}件", expanded=a["wants_past"]):
            for v in a["past_versions"]:
                st.write(f"v{v['version']}（{v['status']}）：{v['body']}")
                st.caption(f"変更の理由：{v['change_reason'] or whylogic.NO_REASON}")
    if a["history"]:
        with st.expander("変更の経緯"):
            for h in a["history"]:
                st.write(f"{h['date'] or '判断日の記録なし'}　{h['outcome']}　{h['trigger']}　{continuity.label(p, h['meeting'])}")
                st.caption(h["rationale"] or whylogic.NO_REASON)
    if a["evidence"]:
        st.markdown("**要件の根拠**")
        for c in a["evidence"]:
            st.html(f'<div class="dr-ev"><div class="dr-ev-q">「{esc(str(c["text"]))}」</div><div class="dr-ev-w">{esc(c["where"])}</div></div>')


def _precheck(p: dict, check: dict) -> None:
    """要件定義書の出力前確認。不足があっても下書きとして出力できる。"""
    with st.container(border=True):
        st.markdown("**要件定義書の出力前確認**")
        rows = "".join(f"<li>{esc(label)}：{n}件</li>" for label, n, _ in check["rows"])
        if check["missing_profile"]:
            rows += f"<li>{esc('・'.join(check['missing_profile']))}が未設定（案件情報を参照します）</li>"
        st.html(f'<ul class="dr-g-list">{rows}</ul>')
        o = check["open"]
        st.markdown(f"**未決事項**　登録{o['registered']}件／掲載{len(o['included'])}件／除外{len(o['excluded'])}件" + (f"／同じ内容をまとめた{o['merged']}件" if o["merged"] else ""))
        for item in o["excluded"]:
            st.caption(f"除外：{item['id']} {item['content']}（{item['reason']}）")
        st.caption("未採用のAI候補は文書に含まれません。質問・宿題・未回答は、候補の画面から反映すると「未決事項」に記載されます。")
        with st.expander(f"出力対象の要件と版（{len(check['targets'])}件）"):
            for t in check["targets"]:
                st.write(t)
        c1, c2, c3 = st.columns(3)
        if c1.button("不足項目を確認する", key="go_check_reqs", width="stretch"):
            state.goto("requirements")
        if check["pending_candidates"] and c2.button("未処理の候補を確認する", key="go_check_cands", width="stretch"):
            state.goto("candidates")
        if check["missing_profile"] and c3.button("案件情報を確認する", key="go_check_prof", width="stretch"):
            state.goto("profile")


def share_page(p: dict) -> None:
    head("確認資料・要件定義書", "出力の前に対象と不足を確認します。内部メモは既定で対象外です。録画の全文や発言は自動で掲載しません。送付しても合意にはなりません。", "共有・変更管理")
    tabs = st.tabs(["確認資料・要件定義書", "回答の記録", "Excel・JSON"], key="share_tabs")
    with tabs[0]:
        doc_type = st.radio("資料の種類", list(DOC_TYPES), format_func=DOC_TYPES.get, horizontal=True, key="sh_type")
        opt = share.Options(doc_type=doc_type)
        if doc_type == "change":
            if p["changes"]:
                opt.change_id = st.selectbox("追加要望", [c["id"] for c in p["changes"]], format_func=lambda i: pj.label_of(p, i), key="sh_chg")
            else:
                st.info("追加要望は登録されていません。")
        c1, c2 = st.columns(2)
        opt.include_drafts = c1.toggle("下書きの要件を含める", value=True, key="sh_dr")
        opt.include_internal = c2.toggle("内部メモを含める（社外共有は不可）", value=False, key="sh_in")
        if opt.include_internal:
            st.warning("内部メモが含まれます。社外へ送付しないでください。")
        quotes = share.quotable(p)
        keys = st.multiselect("掲載する引用を選ぶ（既定は掲載なし）", [q["key"] for q in quotes],
                              format_func=lambda k: (lambda q: f"{q['item']}：{str(q['quote'])[:34]}（{q['where']}）")(next(x for x in quotes if x["key"] == k)), key="sh_q")
        opt.quote_keys = set(keys)
        ids = [r["id"] for r in p["requirements"]]
        opt.exclude_ids = set(st.multiselect("対象から外す要件", ids, format_func=lambda i: pj.label_of(p, i), key="sh_ex"))
        with st.expander("内容を確認する", expanded=False):
            artifacts.preview(share.build(p, opt))
        check = share.precheck(p, opt) if doc_type == "spec" else None
        if check:
            _precheck(p, check)
        label = "下書きとしてWordを作成する" if check and check["is_draft"] else f"{DOC_TYPES[doc_type]}を作成する（Word）"
        if st.button(label, type=main_type(), key="share_word"):
            title = DOC_TYPES[doc_type]
            if p.get("is_demo"):  # 閲覧専用では発行の記録を増やさない。発行済みの資料と同じ版で出力する
                doc = share.latest_doc(p, doc_type) or {"id": "DEMO", "version": 1, "issued_at": pj.now_iso()}
            else:
                doc = share.register_doc(p, opt, title)
            st.session_state["word"] = {"data": wordx.render(p, opt, doc["id"], doc["version"], doc["issued_at"]), "name": wordx.filename(p, doc_type, doc["version"]), "id": doc["id"], "title": title}
            touch(p)
        w = st.session_state.get("word")
        if w:
            st.success(f"{w['title']}を作成しました。下のボタンからダウンロードしてください。")
            st.download_button(f"{w['title']}をダウンロード（Word）", w["data"], file_name=w["name"], mime=artifacts.WORD, key="dl_word", on_click="ignore", type=main_type())
            st.caption("PDFが必要な場合は、Wordで開いて「名前を付けて保存」からPDFを選んでください。")
            if not p.get("is_demo"):  # 作業の区切り：戻り先と、続きに備える再開用ファイル
                with st.container(border=True, key="share_after"):
                    st.markdown("**資料を作成した後**")
                    if st.button("現在の状況へ戻る", key="share_back_ov", type="secondary"):
                        state.goto("overview")
                    save_controls(p, "save_share_after", note=False)
            c1, c2 = st.columns(2)
            if c1.button("未確認事項を確認する", key="go_overview_open", width="stretch"):
                state.goto("overview")
            if c2.button("案件ホームへ戻る", key="go_home_after", width="stretch"):
                state.goto("overview")
        st.markdown("**作成済みの資料**")
        st.dataframe(pd.DataFrame([{"ID": d["id"], "名称": d["title"], "版": d["version"], "発行日時": d["issued_at"][:16].replace("T", " "), "範囲": d["scope_note"], "送付": "送付済み" if d["sent"] else "未送付"} for d in p["shared_docs"]],
                                  columns=["ID", "名称", "版", "発行日時", "範囲", "送付"]), hide_index=True, width="stretch")
        if p["shared_docs"] and not p.get("is_demo"):
            c1, c2 = st.columns([3, 1])
            sent_id = c1.selectbox("送付の記録", [d["id"] for d in p["shared_docs"]], format_func=lambda i: pj.label_of(p, i), key="sent_sel")
            if c2.button("送付済みにする", key="sent_b"):
                pj.require(p, "shared_docs", sent_id)["sent"] = True
                touch(p)
                ok_rerun("記録しました（送付しても合意にはなりません）")
    with tabs[1]:
        st.caption("回答は資料の版と項目IDに関連付けて記録します。回答しても自動で合意にはなりません。")
        st.dataframe(pd.DataFrame([{"ID": r["id"], "資料": r["doc_id"], "版": r["doc_version"], "項目": r["item_id"], "回答": r["content"], "回答者": display(r.get("respondent")), "回答日": display(r.get("answered_on"))} for r in p["responses"]],
                                  columns=["ID", "資料", "版", "項目", "回答", "回答者", "回答日"]), hide_index=True, width="stretch")
        if p["shared_docs"]:
            with edit_block("res"), st.form("add_res", clear_on_submit=True):
                doc = st.selectbox("資料", [d["id"] for d in p["shared_docs"]])
                item = st.text_input("項目ID（例：REQ-001）")
                content = st.text_area("回答")
                who, when = st.text_input("回答者"), st.text_input("回答日")
                if st.form_submit_button("回答を記録") and item.strip() and content.strip():
                    share.record_response(p, doc, item.strip(), content.strip(), who or None, when or None)
                    touch(p)
                    ok_rerun("記録しました")
    with tabs[2]:
        include = st.toggle("Excelに内部メモを含める（社外共有は不可）", value=False, key="xl_in")
        st.download_button("Excelをダウンロード（要件・質問・残件・リスク・履歴）", excelx.render(p, include), file_name=excelx.filename(p, pj.today()), key="dl_xl", on_click="ignore",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        if p.get("is_demo"):
            st.download_button("案件JSONをダウンロード", jsonio.dumps(p), file_name=f"{pj.today()}_DefineReq_{p['id']}.json", mime="application/json")
        else:
            save_controls(p, "save_share")
        st.caption("JSONには資料の本文と文字起こしが含まれます。元ファイルは含みません。取り扱いに注意してください。案件はアプリ利用中のみ保持されます。続きを行うときは、トップの「保存した案件から再開する」で読み込みます。")


def usage(p: dict) -> None:
    head("AI・費用", "有料処理の状態を確認します。デモと無料の機能は、ここの設定がなくても動きます。", "管理")
    st.markdown(f"""
| 項目 | 状態 |
|---|---|
| Claude API キー | {'設定済み' if config.has_ai_key() else '未設定'} |
| OpenAI API キー（文字起こし） | {'設定済み' if config.has_transcribe_key() else '未設定'} |
| AIパスワード | {'設定済み' if config.access_codes() else '未設定'} |
| 利用記録（永続DB） | {'設定済み' if (config.usage_db_url() or config.usage_hf_dataset()) else ('手元の開発用' if config.allow_local_ledger() else '未設定')} |
| AIモデル | {config.ai_model()} |
| 月額のAPI予算 | {config.monthly_budget_jpy():,}円 |
""")
    code = current_code()
    rd = gate.readiness(code if code else None)
    for r in rd.reasons:
        st.caption(r)
    if rd.ledger is not None and code and gate.check_code(code):
        try:
            s = rd.ledger.summary(code)
        except LedgerUnavailable as e:
            st.error(str(e))
            return
        a, c = s["all"], s["code"]
        st.markdown(f"**今月（{s['month']}）の利用**")
        st.write(f"全体：約{a['cost_jpy']:,.0f}円／{a['runs']}回（処理中 {a['pending']}件、失敗 {a['failed']}件）")
        st.write(f"このコード：約{c['cost_jpy']:,.0f}円／{c['runs']}回／音声{c['minutes']:.1f}分")
        st.caption("共有コードは枠も共有します。ここの金額はアプリの試算であり、請求額を保証するものではありません。")


def demo_map(p: dict) -> None:
    head("デモの機能対応表", "3件のデモが主要機能をどう使うかを示します。固定の結果は事前に用意したものです。", "デモ")
    rows = []
    for d in builder.catalog():
        for s in d["tour"]:
            rows.append({"デモ": d["name"], "段階": builder.STAGES[s["stage"]], "手順": s["title"], "入力": s["input"], "AI候補": s["ai"], "人の判断": s["human"], "結果": s["result"]})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=520)


__all__ = ["trail", "why", "share_page", "usage", "demo_map", "select_item"]
