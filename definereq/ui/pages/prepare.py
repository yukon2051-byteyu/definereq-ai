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
from .. import drafts, situation
from ..components import main_type, chip, definition, edit_block, esc, guard, head, ok_rerun, save_controls, select_item, touch


def setup(p: dict) -> None:
    """案件の準備。背景と資料はどちらからでも始められ、あとから追加・編集できる。"""
    head("準備の概要", "背景の入力と資料の取り込みは、どちらからでも始められます。あとから追加・編集できます。", "案件ホーム")
    pstate = drafts.profile_state(p)
    count = drafts.references_count(p)  # 参考資料の件数（議事録は数えない）
    rstate = f"登録済み {count}件" if count else "未登録"
    tone = {"未入力": "plain", "入力済み": "ok", "未保存の変更あり": "warn"}
    cards = (("背景・目的・関係者", "案件の背景、困りごと、目的、関係者を記録します。分からない項目は空欄で構いません。", chip(pstate, tone[pstate]),
              "背景・目的・関係者を入力" if pstate == "未入力" else "背景・目的・関係者を編集", "profile", "setup_profile"),
             ("参考資料", "現行のルール・運用資料・要望書など、会議の前に読む資料を登録します。Word・Excel・PDF・テキストに対応しています。", chip(rstate, "ok" if count else "plain"),
              "参考資料を確認・追加する" if count else "参考資料を登録する", "refs", "setup_refs"))
    cols = st.columns(2)
    for col, (title, text, badge, label, page, key) in zip(cols, cards):
        with col, st.container(border=True, height="stretch"):
            st.html(f'<div class="dr-setup-h"><b>{esc(title)}</b>{badge}</div><div class="dr-setup-t">{esc(text)}</div>')
            st.space("stretch")
            if st.button(label, key=key, width="stretch"):
                state.goto(page)
    if not p.get("is_demo"):  # 会議がすでに終わっている人は、工程3の議事録の登録へ直接進める
        if st.button("すでに議事録がある場合は、議事録を取り込む →", key="setup_minutes", type="tertiary"):
            state.goto("sources")
    if not p.get("is_demo") and not gd.setup_next(p).get("empty"):  # 何も登録していないときは、上の2枚のカードが開始の操作
        st.caption("上の2つは、背景や資料をあとから追加・編集するときの入口です。")
        next_block(p, "setup_next")
    if not p.get("is_demo"):  # 続きの作業に備える補助の操作。「次にすること」より下に、控えめに置く
        with st.container(key="setup_resume"):
            st.html('<div class="dr-resume-t"><b>続きの作業に備える</b>' + esc(RESUME_NOTE) + "</div>")
            save_controls(p, "save_setup", note=False)


# 再開用ファイルの説明。jsonio.dumps は案件データ（取り込んだ資料の本文を含む）を書き出し、元のファイルと保存前の下書きは含まない
RESUME_NOTE = ("別の日に続ける場合は、再開用ファイルをダウンロードしてください。元のWord・PDFファイルは含まれません。"
               "各画面の「保存」は、いま開いている案件への反映です。再開用ファイルは、ブラウザーを閉じた後に案件を復元するためのものです（保存していない下書きは含まれません）。")


def next_block(p: dict, key: str, lead: str = "次にすること") -> None:
    """案件の状態に合う次の作業。主ボタン1つで既存の作業画面を直接開き、ほかに進める作業は控えめに出す。

    ボタンは画面を開くだけで、AIの実行は移動先の画面の操作で行う。
    """
    nx = gd.setup_next(p)
    with st.container(border=True, key=key):
        st.html(f'<div class="dr-next"><b>{esc(lead)}</b><span class="dr-next-s">{esc(nx["status"])}</span></div>'
                f'<div class="dr-meta">{esc(nx["reason"])}' + (f'　{esc(nx["detail"])}' if nx.get("detail") else "") + "</div>")
        with st.container(horizontal=True, vertical_alignment="center"):
            if st.button(f"{nx['label']} →", key=f"{key}_go", type="primary"):
                state.goto(nx["page"])
            where = st.session_state.get("_page_names", {}).get(nx["page"])
            if where:
                st.caption(f"行き先：{where[0]} › {where[1]}")
            for n, (label, page) in enumerate(nx["alts"]):
                if st.button(f"ほかの作業：{label}", key=f"{key}_alt_{n}", type="tertiary"):
                    state.goto(page)


def top_nav(back_key: str, cross: tuple[str, str, str]) -> None:
    """本文の最上部の移動。左メニューを閉じていても、準備の画面と、背景・資料の間を移動できる。"""
    with st.container(key="dr_topnav", horizontal=True, horizontal_alignment="distribute"):
        if st.button("← 準備の概要に戻る", key=back_key, type="tertiary"):
            state.goto("setup")
        label, page, key = cross
        if st.button(label, key=key, type="secondary"):
            state.goto(page)


def note_slot(name: str) -> None:
    """操作の結果を、その操作の近くに表示する。表示は次の再描画で消える。"""
    msg = st.session_state.pop(f"msg_{name}", None)
    if msg:
        (st.error if msg[0] == "error" else st.success)(msg[1])


def done(name: str, text: str, kind: str = "ok") -> None:
    st.session_state[f"msg_{name}"] = (kind, text)
    st.rerun()


def _related_links(p: dict, items: list[dict], cat: str) -> None:
    """残件ごとに、関係する要件を開く操作。関係は登録済みのIDの参照だけで判定する。0件なら出さない（一覧は補助の操作から開く）。"""
    seen = set()
    for k, i in enumerate(items):
        if i["target"] in seen:
            continue
        seen.add(i["target"])
        ids = checks.related_requirements(p, i["target"])
        if not ids:
            continue
        c1, c2 = st.columns([3, 2])
        c1.caption(f"{i['target']}：{i['content']}")
        label = "この残件に関係する要件を見る" + (f"（{len(ids)}件）" if len(ids) > 1 else "")
        if c2.button(label, key=f"bl_req_{cat}_{k}", type="tertiary"):
            state.open_requirements(ids, i["content"], "overview", cat)


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
    for k, x in enumerate([*acts, *confirm]):  # 確認・依頼の結果が、どの要件の判断に役立つか
        ids = checks.related_requirements(p, x["id"])
        if ids:
            c1, c2 = st.columns([3, 2])
            c1.caption(f"{x['id']}：{x.get('content') or x.get('text')} → 関係する要件 {'、'.join(ids)}")
            if c2.button("この残件に関係する要件を見る" + (f"（{len(ids)}件）" if len(ids) > 1 else ""), key=f"todo_req_{k}", type="tertiary"):
                state.open_requirements(ids, x.get("content") or x.get("text"), "overview", None)
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
        setup(p)
        return
    head(p["name"], "現在の状況と、確認・依頼することをまとめています。" if not p.get("is_demo") else "残件と次の行動を確認します。完成度の点数は表示しません。", "案件ホーム")
    bl = checks.backlog(p)
    stats = [("要件", sum(1 for r in p["requirements"] if r["status"] not in ("廃止", "却下"))),
             ("合意済み", sum(1 for r in p["requirements"] if r["status"] == "合意済み")),
             ("残件（対象の数）", bl["unique_total"]),
             ("未解消の矛盾候補", sum(1 for c in p["conflicts"] if c["state"] in ("未確認", "確認中")))]
    # 登録が進むまでは0件の指標と残件の欄を出さない
    if p.get("is_demo") or any(n for _, n in stats):
        for col, (label, n) in zip(st.columns(4), stats):
            col.html(f'<div class="dr-stat"><div class="dr-stat-n">{n}</div><div class="dr-stat-l">{esc(label)}</div></div>')
    if bl["category_total"] != bl["unique_total"]:
        st.caption(f"分類別の合計は {bl['category_total']} 件です。1つの対象が複数の分類に入ることがあるため、重複を除いた対象の数は {bl['unique_total']} 件です。")

    if bl["unique_total"] or phase == "clear" or p.get("is_demo"):
        _backlog(p, bl, phase)
    _todo_list(p)

    with st.expander("操作の記録"):
        for a in reversed(p["activity"][-30:]):
            st.caption(f"{a['at'][:16].replace('T', ' ')}　{a['message']}")


def _backlog(p: dict, bl: dict, phase: str) -> None:
    """残件の一覧。確認した結果として0件の場合は、完了と誤解されないように説明する。"""
    st.subheader("残件")
    if p["requirements"] and st.button("この案件の要件一覧を見る", key="bl_all_reqs", type="tertiary"):  # 見返すための補助
        state.goto("requirements")
    opened = st.session_state.pop("backlog_open", None)  # 要件から戻ったときは、開いていた区分を開く
    for cat, items in bl["categories"].items():
        if not items:
            continue
        with st.expander(f"{cat}　{len(items)}件", expanded=cat == opened):
            _related_links(p, items, cat)
            rows = [{"対象": i["target"], "内容": i["content"], "行動": i["action"], "確認相手": display(i.get("ask")),
                     "期限": display(i.get("due")), "状態": i["state"]} for i in items]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            if st.button("対象の画面へ移動", key=f"go_{cat}"):
                state.goto(items[0]["page"])
    if not bl["unique_total"]:
        st.info("確認した範囲では、残件は検出されていません。登録されていない論点は検出できず、案件全体の確認が完了したことを示すものではありません。")


def profile(p: dict) -> None:
    demo = p.get("is_demo")
    if not demo:
        top_nav("go_setup_top", ("参考資料へ", "refs", "go_sources_top"))
    head("背景・目的・関係者", "案件の背景・目的・課題を記録します。分からない項目は空欄のまま進められます。" if not demo else
         "確認済み・本人申告・仮説・未確認を区別して記録します。要件定義書の背景と目的はここを参照します。", "案件ホーム")
    # 編集中は「案件情報を保存」を主な操作にするため、上部に別の工程を勧める案内は出さない（詳しい案内は画面の下）
    guide = None if demo else gd.assess(p, "profile", st.session_state.get("resumed", False))
    if demo:
        definition([(label, p["profile"][key]["value"]) for key, label in PROFILE_FIELDS.items()])
    _profile_form(p)
    _reflect_panel(p)
    _stakeholders(p)
    _glossary(p)
    _domains(p)
    if guide:
        situation.details(p, "profile", guide, skip={"setup", "sources", "profile"})


MAIN_FIELDS = ("background", "purpose", "problem")  # 最初に見せる項目


def _profile_form(p: dict) -> None:
    """背景・目的などの欄。入力途中の内容は下書きとして残り、ボタンを押したときだけ案件に反映する。"""
    with edit_block("profile"), st.container(border=True, key="pf_form"):
        st.markdown("**案件情報**")
        st.caption("分かる項目だけで進められます。空欄のままでも保存できます。入力途中の内容は、ほかの画面へ移っても残ります。")
        new = {}

        def field(key: str, label: str) -> None:
            cur = p["profile"][key]
            c1, c2 = st.columns([4, 1])
            value = drafts.widget(p["id"], f"v_{key}", c1.text_area, label, cur["value"] or "", height=68)
            cert = drafts.widget(p["id"], f"c_{key}", c2.selectbox, "確かさ", cur["certainty"], options=CERTAINTY)
            new[key] = {"value": (value or "").strip() or None, "certainty": cert}

        for key in MAIN_FIELDS:  # 背景・目的・課題を先に見せ、すぐ下に保存の操作を置く
            field(key, PROFILE_FIELDS[key])
        rest = [k for k in PROFILE_FIELDS if k not in MAIN_FIELDS]
        filled = sum(1 for k in rest if p["profile"][k]["value"])
        # 任意の項目は折りたたむ。閉じていても入力欄は描画されるため、保存済みの値や編集中の内容は残る
        with st.expander(f"案件情報を詳しく入力（{'・'.join(PROFILE_FIELDS[k] for k in ('scope_in', 'constraints', 'timeline', 'budget'))}など{len(rest)}項目" + (f"、入力済み{filled}項目" if filled else "") + "）"):
            st.caption("「確かさ」は、確認済み・本人申告・仮説・未確認から選びます。")
            for key in rest:
                field(key, PROFILE_FIELDS[key])
        # ボタンより上には、入力中に表示が変わる部品を置かない。
        # 入力欄の確定（フォーカスが外れたとき）で上の表示が増えると、押している最中にボタンが下へずれ、クリックが成立しないため
        st.caption("背景・目的・課題など、この欄の入力を案件に反映します。関係者と用語は、それぞれの「追加」で反映します。")
        go_label, go_page = _after_save(p)
        saved = st.session_state.get("pf_saved")
        # 保存した直後（未保存の変更なし）は「次へ」を主ボタンにし、保存は補助の見た目にする
        just_saved = bool(saved and saved["project"] == p["id"] and not drafts.profile_fields_pending(p))
        b1, b2 = st.columns(2)
        save_now = b1.button("案件情報を保存", type="secondary" if just_saved else "primary", key="pf_save", width="stretch")
        where = st.session_state.get("_page_names", {}).get(go_page, ("", go_label))[1]
        save_go = b2.button(f"保存して{where}へ進む", key="pf_save_go", width="stretch")  # 処理（保存）と行き先の両方を示す
        if save_now or save_go:
            error = _save_profile(p, new)
            if error:  # 入力内容は下書きに残したまま、理由をボタンの近くに出す
                st.error(f"案件情報を保存できませんでした。{error} 入力内容はそのまま残っています。")
            elif save_go:  # 保存を確認してから移動する
                st.session_state["flash"] = "案件情報を保存しました"
                state.goto(go_page)
            else:  # 保存の結果と次の操作は、別の画面へ移るまで残す（押す前に消えるとクリックが届かないため）
                st.session_state["pf_saved"] = {"project": p["id"], "time": pj.now_iso()[11:16]}
                st.rerun()
        if drafts.profile_fields_pending(p):
            st.caption("保存していない変更があります。")
        elif saved and saved["project"] == p["id"]:
            label, page = _after_save(p)
            with st.container(key="pf_saved_box"):
                st.success(f"案件情報を保存しました（{saved['time']}）。")
                with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="right"):  # 「次へ」は右端
                    if not drafts.references_count(p) and st.button("参考資料を登録する", key="pf_refs"):
                        state.goto("refs")
                    if st.button(f"次へ：{label} →", key="pf_next_go", type="primary"):
                        state.goto(page)


def _after_save(p: dict) -> tuple[str, str]:
    """案件情報を保存した後の次の操作。未整理の議事録や確認待ちの候補があればその作業、なければ会議の準備（質問・議題）。"""
    nx = gd.setup_next(p)
    if nx["page"] in ("refs", "prep"):  # 会議前の準備の段階。議事録の登録へは誘導しない
        return "質問・議題", "prep"
    return nx["label"], nx["page"]


def _save_profile(p: dict, new: dict) -> str | None:
    """案件情報を反映し、反映できたことを確かめる。問題があれば理由を返す。"""
    try:
        for key, value in new.items():  # 出所の記録は残す
            value["origin"] = p["profile"][key].get("origin")
        p["profile"].update(new)
        if any(p["profile"][k]["value"] != v["value"] for k, v in new.items()):
            return "反映後の内容を確認できませんでした。"
    except Exception:  # 想定外の失敗でも、入力を失わないようにする
        return "時間をおいて、もう一度押してください。"
    drafts.clear(p["id"], [f"{x}_{key}" for key in PROFILE_FIELDS for x in ("v", "c")])
    touch(p)
    return None


def _stakeholders(p: dict) -> None:
    st.subheader("関係者")
    df = pd.DataFrame([{"ID": s["id"], "氏名・役割": s["name"], "所属": s["org"], "立場": s["position"], "判断・確認できる範囲": s["authority"],
                        "確かさ": s["certainty"], "備考": s.get("note")} for s in p["stakeholders"]],
                      columns=["ID", "氏名・役割", "所属", "立場", "判断・確認できる範囲", "確かさ", "備考"])
    if p["stakeholders"]:
        st.dataframe(df, hide_index=True, width="stretch")
    elif not p.get("is_demo"):
        st.caption("登録された関係者はまだいません。")
    with edit_block("stk"):
        cols = st.columns(4)
        fields = {n: drafts.widget(p["id"], f"stk_{n}", col.text_input, label, "") for col, (n, label) in zip(cols, (("name", "氏名・役割"), ("org", "所属"), ("pos", "立場"), ("auth", "判断・確認できる範囲")))}
        cert = drafts.widget(p["id"], "stk_cert", st.selectbox, "確かさ（関係者）", "未確認", options=CERTAINTY)
        st.caption("「関係者を追加」を押すと、入力した1件が案件に反映されます。")
        if st.button("関係者を追加", key="pf_add_stk"):
            name = (fields["name"] or "").strip()
            if not name:
                st.error("「氏名・役割」を入力してください。")
            else:
                pj.add(p, "stakeholders", {"name": name, "org": fields["org"] or None, "position": fields["pos"] or None, "authority": fields["auth"] or None, "certainty": cert, "note": None})
                drafts.clear(p["id"], ["stk_name", "stk_org", "stk_pos", "stk_auth", "stk_cert"])
                touch(p)
                done("stk", f"関係者「{name}」を追加しました。")
        note_slot("stk")


def _glossary(p: dict) -> None:
    st.subheader("用語集")
    if p["glossary"]:
        st.dataframe(pd.DataFrame([{"用語": g["term"], "意味": g["meaning"]} for g in p["glossary"]], columns=["用語", "意味"]), hide_index=True, width="stretch")
    elif not p.get("is_demo"):
        st.caption("登録された用語はまだありません。")
    with edit_block("term"):
        c1, c2 = st.columns([1, 3])
        term = drafts.widget(p["id"], "term_term", c1.text_input, "用語", "")
        meaning = drafts.widget(p["id"], "term_meaning", c2.text_input, "意味", "")
        st.caption("「用語を追加」を押すと、入力した1件が案件に反映されます。")
        if st.button("用語を追加", key="pf_add_term"):
            word = (term or "").strip()
            if not word:
                st.error("「用語」を入力してください。")
            else:
                pj.add(p, "glossary", {"term": word, "meaning": meaning})
                drafts.clear(p["id"], ["term_term", "term_meaning"])
                touch(p)
                done("term", f"用語「{word}」を追加しました。")
        note_slot("term")


def _domains(p: dict) -> None:
    """案件作成時に選んだ対象分野と、深掘りする観点。補助的な設定のため、初期状態は折りたたむ。"""
    names = "、".join(DOMAINS[d] for d in p["domains"])
    if p.get("is_demo"):
        st.subheader("対象分野")
        st.write(names)
        return
    with edit_block("dom"), st.expander(f"対象分野と特徴を変更する（現在の分野：{names}）"):
        domains = st.multiselect("分野（複合は複数選択）", list(DOMAINS), default=p["domains"], format_func=DOMAINS.get, key="pf_domains")
        traits_all = config.checkpoints()["traits"]
        suggested = checks.suggest_traits(p)
        traits = st.multiselect("業務・システムの特徴（深掘りする観点）", list(traits_all), default=p.get("traits", []), format_func=lambda k: traits_all[k]["label"], key="pf_traits")
        missing = [traits_all[k]["label"] for k in suggested if k not in p.get("traits", [])]
        if missing:
            st.caption("本文から提案された特徴（採否は人が決めます）：" + "、".join(missing))
        if st.button("分野と特徴を案件内に反映", key="pf_dom_save"):
            if not domains:
                st.error("分野を1つ以上選んでください。")
            else:
                p["domains"], p["traits"] = domains, traits
                touch(p)
                done("dom", "分野と特徴を反映しました。")
        note_slot("dom")


PREP_FIELDS = ["prep_understanding", "prep_purpose", "prep_gaps", "prep_materials", "prep_agenda", "prep_decide"]


def _prep_form(p: dict, pr: dict) -> None:
    # 入力途中の内容は下書きに残す（参考資料の登録などで画面を離れて戻っても消えない）。案件には「案件内に反映」で反映する
    pid = p["id"]
    understanding = drafts.widget(pid, "prep_understanding", st.text_area, "現時点の理解", pr.get("understanding") or "")
    purpose = drafts.widget(pid, "prep_purpose", st.text_input, "会議の目的", pr.get("purpose") or "")
    c1, c2 = st.columns(2)
    with c1:
        gaps = drafts.widget(pid, "prep_gaps", st.text_area, "不足情報（1行に1件）", "\n".join(pr.get("gaps", [])))
    with c2:
        materials = drafts.widget(pid, "prep_materials", st.text_area, "必要な資料・計測（1行に1件）", "\n".join(pr.get("materials", [])))
    with c1:
        agenda = drafts.widget(pid, "prep_agenda", st.text_area, "議題（1行に1件）", "\n".join(pr.get("agenda", [])))
    with c2:
        decide = drafts.widget(pid, "prep_decide", st.text_area, "今回決めたいこと（1行に1件）", "\n".join(pr.get("decide_today", [])))
    go = st.session_state.pop("prep_save_and_go", False)
    # 主ボタンは1つ：未反映の入力があれば「案件内に反映」、なければ「会議へ進む」（反映の直後は結果の近く、それ以外は画面の下）
    if st.button("案件内に反映", type=main_type() if prep_pending(p) else "secondary", key="prep_save") or go:
        def lines(x: str) -> list[str]:
            return [v.strip() for v in (x or "").splitlines() if v.strip()]
        pr.update(understanding=understanding or None, purpose=purpose or None, gaps=lines(gaps), materials=lines(materials),
                  agenda=lines(agenda), decide_today=lines(decide))
        drafts.clear(pid, PREP_FIELDS)
        touch(p)
        st.session_state["prep_saved"] = {"project": pid, "time": pj.now_iso()[11:16], "scroll": True}
        if go:
            state.goto("meetings")
        st.rerun()
    saved = st.session_state.get("prep_saved")
    if saved and saved["project"] == pid and not prep_pending(p):  # 反映の結果と次の操作は、反映ボタンのすぐ下に出す
        with st.container(border=True, key="prep_saved_box"):
            st.success(f"理解と議題を案件内に反映しました（{saved['time']}）。")
            _to_meetings(p, "prep_saved_go", primary=True)
        if saved.pop("scroll", False):  # 反映の結果が画面の下に隠れないよう、1回だけ結果の位置へ移動する
            st.iframe(f"<script>/*{pj.now_iso()}*/const t=()=>window.parent.document.querySelector('.st-key-prep_saved_box')?.scrollIntoView({{block:'center'}});t();setTimeout(t,300)</script>", height=1)


def prep_pending(p: dict) -> bool:
    """質問・議題の「理解と議題」に、案件内へ反映していない入力があるか。"""
    store = drafts.store(p["id"])
    pr = p["prep"]
    saved = {"prep_understanding": pr.get("understanding") or "", "prep_purpose": pr.get("purpose") or "", "prep_gaps": "\n".join(pr.get("gaps", [])),
             "prep_materials": "\n".join(pr.get("materials", [])), "prep_agenda": "\n".join(pr.get("agenda", [])), "prep_decide": "\n".join(pr.get("decide_today", []))}
    return any(name in store and (store[name] or "") != saved[name] for name in PREP_FIELDS)


def _to_meetings(p: dict, key: str, primary: bool, minutes: bool = True) -> None:
    """「会議へ進む」と、会議がすでに終わっている人向けの「議事録を取り込む」。"""
    with st.container(horizontal=True, vertical_alignment="center"):
        if st.button("会議へ進む →", key=key, type="primary" if primary else "secondary"):
            state.goto("meetings")
        st.caption("行き先：会議の準備 › 会議（会議を登録し、その会議の記録へ進めます）")
        if minutes and st.button("会議が終わっていれば、議事録を取り込む", key=f"{key}_minutes", type="tertiary"):
            state.goto("sources")


def _prep_footer(p: dict) -> None:
    """画面の下（どのタブを開いていても見える位置）の次の操作。反映の直後は反映結果の近くのボタンが主ボタン。"""
    st.divider()
    if prep_pending(p):  # 未反映の入力を黙って失わない（下書きは残る）。反映して進むか、編集を続けるかを選べる
        st.caption("「理解と議題」に、案件内へ反映していない入力があります。入力は下書きとして残ります。")
        with st.container(horizontal=True, vertical_alignment="center", key="prep_footer"):
            if st.button("反映して会議へ進む →", key="prep_save_go", type="secondary"):
                st.session_state["prep_save_and_go"] = True
                st.rerun()
            st.caption("編集を続ける場合は、このまま「理解と議題」で入力できます。")
        return
    saved = st.session_state.get("prep_saved")
    with st.container(key="prep_footer"):
        just = bool(saved and saved["project"] == p["id"])  # 反映の直後は、反映結果の近くの操作が主（ここは補助）
        _to_meetings(p, "prep_go_meetings", primary=not just, minutes=not just)


def _prep_entrances(p: dict) -> None:
    """会議の準備から使う資料の入口：会議前に届いた参考資料の追加（議事録の登録は画面の下の「会議へ進む」の横）。"""
    with st.container(horizontal=True, key="prep_entrances"):
        if st.button("参考資料を追加する", key="prep_add_refs", type="tertiary"):  # 登録後は「会議の準備に戻る」
            state.goto("refs", keep={"refs_from": "prep"})


def prep(p: dict) -> None:
    head("質問・議題", "会議で確認することを準備します。AIに候補を作ってもらい、この画面で質問や議題へ追加できます。回答済みの観点は繰り返しません。", "会議の準備")
    pr = p["prep"]
    if not p.get("is_demo"):
        _prep_entrances(p)
    carryover_panel(p)
    tabs = st.tabs(["理解と議題", "質問", "分野別の確認観点"], key="prep_tabs")
    if p.get("is_demo"):
        with tabs[0]:
            definition([("現時点の理解", pr.get("understanding")), ("会議の目的", pr.get("purpose")), ("不足情報", pr.get("gaps")), ("必要な資料・計測", pr.get("materials")),
                        ("議題", pr.get("agenda")), ("今回決めたいこと", pr.get("decide_today"))])
    if not p.get("is_demo"):  # デモは上の表示だけ（入力欄は出さない）
        with tabs[0], edit_block("prepf"):
            _prep_form(p, pr)
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
    if not p.get("is_demo"):
        _prep_footer(p)


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
                elif st.button("確認して案件情報へ反映する", key=f"pf_set_{s['id']}"):
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


def _meeting_next(p: dict, meeting_id: str, key: str, primary: bool) -> None:
    """会議の次の操作：その会議を選んだ状態で記録の整理へ。開催前なら質問・議題へ戻って準備を続ける。"""
    with st.container(horizontal=True, vertical_alignment="center"):
        if st.button("会議の記録を整理 →", key=f"{key}_records", type="primary" if primary else "secondary"):
            state.goto("records", keep={"rec_meeting": meeting_id})
        if st.button("質問・議題に戻る", key=f"{key}_prep"):
            state.goto("prep")
    st.caption(f"「会議の記録を整理」では、議事録を「{continuity.label(p, meeting_id)}」に関連付けて登録できます。会議の前なら「質問・議題に戻る」で準備を続けられます。")


def meetings(p: dict) -> None:
    head("会議", "会議ごとに資料・発言・判断を関連付け、複数回の会議を同じ案件の続きとして記録します。", "準備")
    with edit_block("addmtg"), st.form("add_mtg", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        name, held = c1.text_input("会議名", placeholder="例：第2回打ち合わせ"), c2.text_input("開催日（不明なら空欄）")
        note = st.text_input("補足")
        if st.form_submit_button("会議を追加"):
            added = guard(continuity.add_meeting, p, name, held, note)
            if added:
                touch(p)
                st.session_state["mtg_done"] = {"project": p["id"], "id": added["id"]}
                st.session_state["rq_mtg"] = added["id"]  # 下の一覧でも、登録した会議を選んだ状態にする
                st.rerun()
    done = st.session_state.get("mtg_done")
    if done and st.session_state.get("rq_mtg") not in (None, done["id"]):  # 一覧で別の会議を選び直したら、登録直後の欄は閉じる
        st.session_state.pop("mtg_done", None)
        done = None
    if done and done["project"] == p["id"] and pj.get(p, "meetings", done["id"]):  # 登録した会議の近くに次の操作（この1組だけ）
        with st.container(border=True, key="mtg_done_box"):
            st.success(f"会議「{continuity.label(p, done['id'])}」を登録しました。")
            _meeting_next(p, done["id"], "mtg_done", primary=True)
    if p["meetings"]:
        st.dataframe(pd.DataFrame([{"ID": m["id"], "会議名": m["name"], "開催日": m.get("held_on") or "記録なし", "資料": len(continuity.meeting_items(p, m["id"])["資料"]) + len(continuity.meeting_items(p, m["id"])["録画"]),
                                    "判断": len(continuity.meeting_items(p, m["id"])["判断"]), "変更履歴": len(continuity.meeting_items(p, m["id"])["変更履歴"])} for m in p["meetings"]]), hide_index=True, width="stretch")
    m = select_item(p["meetings"], lambda x: continuity.label(p, x["id"]), "rq_mtg", "会議はまだありません。")
    just_added = bool(done and done["project"] == p["id"] and m and m["id"] == done["id"])
    if m and not p.get("is_demo") and not just_added:  # 登録直後は上の完了欄の1組だけ。開催前でも記録の入口を使える
        _meeting_next(p, m["id"], "mtg_sel", primary=True)
    elif not p["meetings"] and not p.get("is_demo"):
        if st.button("質問・議題に戻る", key="mtg_back_prep"):
            state.goto("prep")
    if m:
        for name, items in continuity.meeting_items(p, m["id"]).items():
            if items:
                st.markdown(f"**{name}　{len(items)}件**")
                for text in items:
                    st.caption(text)
    carryover_panel(p)
