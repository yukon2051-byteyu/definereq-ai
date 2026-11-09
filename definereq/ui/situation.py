"""状況案内の共通部品。デモと実案件で同じ見た目の枠を使う。

- デモ：案件の前提、デモ用の役割、現在の場面を示す
- 実案件：プログラムの判定（logic/guidance.py）を示し、必要なときだけAIの補足を付ける

案内は表示するだけで、案件の内容を変更しない。閉じても作業でき、再表示できる。
"""
from __future__ import annotations

import streamlit as st

from .. import config
from ..ai import guidance as ai_guidance
from ..ai import tasks as ai_tasks
from ..ai.client import AIError
from ..logic import guidance as gd
from ..usage import gate
from ..usage.ledger import BudgetExceeded, LedgerUnavailable
from . import state
from .ai_panel import current_code
from .components import chip, esc, ok_rerun, touch

def frame(tag: str, rows: list[tuple[str, str]], lead: str = "", kind: str = "demo") -> str:
    """案内の枠のHTML。文字は全てエスケープする。"""
    body = "".join(f'<div class="dr-sit-row"><b>{esc(k)}</b><span>{esc(v)}</span></div>' for k, v in rows)
    intro = f'<p class="dr-sit-lead">{esc(lead)}</p>' if lead else ""
    return f'<div class="dr-sit dr-sit-{kind}"><div class="dr-sit-tag">{esc(tag)}</div>{intro}{body}</div>'


NOTE = "このガイドは、記録された内容を時系列で表示しています。画面を移動しても、判断や合意は発生しません。判断と合意は関係者が行ったものです。"


def demo_banner(name: str, intro: dict, step: dict, first: bool, when: str | None, point: str, background: list[tuple[str, str]]) -> None:
    """デモの状況案内。背景は最初の画面の本文で説明し、ここでは時点と行うことだけを短く示す。"""
    if first:
        st.html(frame(f"デモ体験中｜{name}", [], f"あなたは、{intro['role']}です（デモ用の役割）。"))
        return
    st.html(frame(f"{name}｜{step['scene']}" + (f"（{when}）" if when else ""), [], point))
    with st.expander("案件の背景を確認"):  # 開いても画面は移動しないため、同じ場面のまま確認できる
        for label, text in background:
            st.markdown(f"**{label}**")
            st.write(text)
        st.caption(NOTE)


def _short(a: gd.Advice) -> str:
    return a.short or f"{a.title}。{a.todo}"


def _advice_html(a: gd.Advice, open_detail: bool) -> str:
    """閉じても残すのは短い文。詳しい説明と、おすすめする理由だけを開閉する。"""
    rows = [("現在の状況", a.situation), ("今、確認するとよいこと", a.todo), ("この操作をおすすめする理由", a.reason)] if open_detail else []
    return frame(f"現在の状況と次にすること｜{a.title}", rows, _short(a), kind="work")


def _move(label: str, target: str) -> None:
    """議事録を取り込むボタンは、資料の種類を議事録にして移動する。"""
    state.goto(target)


def _here(a: gd.Advice, page: str) -> bool:
    """次の操作をこの画面で行えるか。候補の確認は2つの画面でできる。"""
    return a.page == page or (a.id == "candidates" and page == "candidates")


def _go(a: gd.Advice, page: str, key: str) -> None:
    if _here(a, page):
        return
    if st.button(a.button, key=key):  # 画面の下の案内は補助の操作
        st.session_state["resumed"] = False
        _move(a.button, a.page)


def _actions(main: gd.Advice | None, page: str, hidden: bool) -> None:
    """次の操作は、説明を閉じても常に表示する。"""
    alts = [x for x in (main.alt if main else []) if x[1] != page]
    cols = st.columns([3] * (1 + len(alts)) + [2])
    with cols[0]:
        if main:
            if _here(main, page):
                st.caption("この画面で作業できます。")
            _go(main, page, "guide_go")
    for n, (label, target) in enumerate(alts):
        if cols[n + 1].button(label, key=f"guide_alt_{n}"):
            st.session_state["resumed"] = False
            _move(label, target)
    if hidden:
        if cols[-1].button("詳しい説明を表示", key="guide_show", type="tertiary", width="stretch"):
            st.session_state["guidance_hidden"] = False
            st.rerun()
    elif cols[-1].button("詳しい説明を閉じる", key="guide_hide", type="tertiary", width="stretch"):
        st.session_state["guidance_hidden"] = True
        st.rerun()


def _note_items(note: dict) -> None:
    for it in note["items"]:
        flags = chip("根拠の確認が必要", "warn") if it.get("no_evidence") else ""
        if it.get("unsupported_numbers"):
            flags += chip("資料にない数値あり", "warn")
        ask = f'<div class="dr-meta">確認相手の候補：{esc(it["ask"])}</div>' if it.get("ask") else ""
        detail = f'<div class="dr-g-sub">{esc(it["detail"])}</div>' if it.get("detail") else ""
        quotes = "".join(f'<div class="dr-meta">「{esc(str(e["quote"]))}」 {esc(str(e["where"]))}</div>' for e in it.get("evidence", []))
        st.html(f'<div class="dr-ai-note"><div class="dr-v-lab">{esc(str(it.get("kind") or "補足"))}</div><div class="dr-ai-t">{esc(it["text"])}</div>{detail}{ask}{quotes}<div class="dr-chips">{flags}</div></div>')


def _ai_block(p: dict, a: gd.Advice) -> None:
    fp = gd.state_fingerprint(p)
    note = ai_guidance.current_note(p, fp, a.id)
    if note:
        st.caption(f"AIの提案（{note['generated_at'][:16].replace('T', ' ')} 作成）。人が判断してください。上の説明は登録データに基づく状態の説明です。")
        _note_items(note)
    old = ai_guidance.stale_notes(p, fp)
    if old:
        with st.expander("以前のAI補足（案件の状態が変わったため、現在の内容ではありません）"):
            st.caption(f"作成：{old[-1]['generated_at'][:16].replace('T', ' ')}／対象：{old[-1].get('advice_title') or '記録なし'}")
            _note_items(old[-1])
    if note:
        return
    with st.expander("AIに補足してもらう（ボタンを押したときだけ実行）"):
        code = current_code()
        rd = gate.readiness(code if code else None)
        if not rd.ai:
            st.caption("今はAIを使えません。この説明は登録データからプログラムが判定しているため、そのまま作業を続けられます。")
            for reason in rd.reasons:
                st.caption(reason)
            return
        context = ai_guidance.build_context(p, a)
        st.caption(f"送信先：Anthropic（モデル {config.ai_model()}）／送信量：{len(context):,}文字／費用見込み：最大 約{ai_tasks.estimate(context, ai_guidance.MAX_OUTPUT_TOKENS):,.0f}円。"
                   "内部メモは送信しません。結果は提案として表示し、要件や判断は変更しません。")
        busy = st.session_state.get("guide_ai_busy", False)
        if st.button("AIで補足を作成", key="guide_ai", disabled=busy):
            st.session_state["guide_ai_busy"] = True
            try:
                with st.spinner("AIが補足を作成しています。"):
                    ai_guidance.run(p, a, code, rd.ledger)
            except (AIError, BudgetExceeded, LedgerUnavailable) as e:
                st.warning(f"AIの補足を作成できませんでした。{e} 通常の操作はそのまま続けられます。")
                return
            except Exception:
                st.warning("AIの補足を作成できませんでした。時間をおいて再度お試しください。通常の操作はそのまま続けられます。")
                return
            finally:
                st.session_state["guide_ai_busy"] = False
            touch(p)
            ok_rerun("AIの補足を作成しました")


def _stage_question(p: dict) -> None:
    """作業の段階は利用者が選び直せる。選んだ段階はAIが変更しない。"""
    current = gd.user_stage(p)
    keys = list(gd.STAGE_LABELS)
    # 見出しに現在の段階を入れる。選び直すと見出しが変わり、欄が閉じて本文が上に戻る
    with st.expander(f"作業の段階を選び直す（現在：{gd.STAGE_LABELS.get(current, gd.STAGE_LABELS[None])}）"):
        st.caption("選ぶと、その作業の画面へ移動します。")
        choice = st.radio("今の作業", keys, index=keys.index(current) if current in keys else 0, format_func=gd.STAGE_LABELS.get, key="guide_stage")
    if choice != current:
        gd.guidance_store(p)["user_stage"] = choice
        target = gd.STAGE_PAGES.get(choice)
        if target:
            state.goto(target)
        st.rerun()


# 「要件の確認・判断」の工程の画面
DECIDE_PAGES = {"requirements", "refine", "decisions", "nfr", "scope", "scenarios", "issues", "conflicts", "risks"}


def resume_summary(p: dict) -> str:
    """再開した案件で、次に進める作業を1文で示す（例：AI候補が6件確認待ちです）。"""
    cands, waiting = gd.requirement_candidates(p), gd.unanalyzed_minutes(p)
    if waiting:
        return f"未整理の議事録が{len(waiting)}件あります"
    if cands:
        return f"AI候補が{len(cands)}件確認待ちです"
    return f"要件{len(p['requirements'])}件・判断{len(p['decisions'])}件を復元しました"


def resume_line(p: dict, page: str) -> bool:
    """保存した案件を再開した直後の1行の通知。保存日時と件数の内訳は開閉式にする。表示したら True。"""
    if not st.session_state.get("resumed"):
        return False
    st.html(f'<div class="dr-now dr-resume"><b>案件を再開しました</b><span>{esc(resume_summary(p))}</span></div>')
    from ..export import jsonio

    with st.expander("再開したファイルの内容（保存日時・件数の内訳）"):
        when = (p.get("exported_at") or "")[:16].replace("T", " ") or "記録なし"
        st.caption(f"保存用ファイルの作成：{when}")
        st.caption("／".join(f"{k}：{v}" for k, v in jsonio.summary(p).items()))
    return True


def headline(p: dict, page: str) -> None:
    """見出しの直後に出す、状態の1行と主ボタン。主ボタンは、その状態で進める操作を1つだけ強調する。

    判定は案件データからプログラムが行う（logic/guidance.py）。前の工程や別の作業は補助のリンクにする。
    再開した直後は、復元した案件で次に行える作業を優先する。
    """
    resumed = resume_line(p, page)
    if resumed:
        nx = gd.setup_next(p)
        label, target, alts = nx["label"], nx["page"], [] if page == "overview" else [("残件を確認する", "overview")]
        state_text = None
    else:
        result = gd.assess(p, page, False)
        a = result["main"]
        if a is None:  # この画面に関係する項目がないときも、案件の状態から次に行える作業を主ボタンで出す
            nx = gd.setup_next(p)
            label, target, alts = nx["label"], nx["page"], []
            state_text = ("この画面で対応が必要な項目は検出されていません", f"次に行える作業：{nx['label']}（登録されていない論点は検出できません）")
        else:
            label, target, alts = a.button, a.page, [x for x in a.alt if x[1] != page]
            state_text = (a.title, a.short or a.situation)
        if page in DECIDE_PAGES and p["requirements"] and target != "share":  # 要件があれば、いつでも資料の作成へ進める
            alts = [*alts, ("確認資料・要件定義書を作る", "share")]
    if state_text:
        st.html(f'<div class="dr-now"><b>{esc(state_text[0])}</b><span>{esc(state_text[1])}</span></div>')
    st.session_state["_main_elsewhere"] = bool(target and target != page)
    pending = [r["id"] for r in p["requirements"] if r["status"] in ("提案", "確認待ち")] if target == "requirements" else []
    if pending:  # 合意待ちの要件を処理する段階では、その要件に絞って開く
        label = "確認待ちの要件を見る"
    with st.container(horizontal=True, vertical_alignment="center", key="head_next"):
        if target and target != page:
            if st.button(f"{label} →", key="guide_go", type="primary"):
                st.session_state["resumed"] = False
                if pending:
                    state.open_requirements(pending, "合意待ちの要件", page)
                state.goto(target)
            where = st.session_state.get("_page_names", {}).get(target)
            if where:
                st.caption(f"行き先：{where[0]} › {where[1]}")
        elif not resumed:
            st.caption("この画面で作業します。")
        for n, (alt, to) in enumerate(alts):
            if st.button(f"ほかの作業：{alt}", key=f"guide_alt_{n}", type="tertiary"):
                st.session_state["resumed"] = False
                state.goto(to)


def details_for(p: dict, page: str) -> None:
    """画面の下にまとめる詳しい案内。主ボタンと同じ移動は重ねて出さない。"""
    result = gd.assess(p, page, False)
    skip = {page, "setup"} | ({result["main"].page} if result["main"] else set())
    details(p, page, result, skip)


def brief(p: dict, page: str) -> dict:
    """入力が中心の画面では、見出しの下に短い1行だけを出す。詳しい説明は details() で画面の下にまとめる。"""
    result = gd.assess(p, page, st.session_state.get("resumed", False))
    main = result["main"]
    text = _short(main) if main else "確認した範囲では、対応が必要な項目は検出されていません。"
    st.html(f'<div class="dr-brief"><b>次にすること</b>{esc(text)}</div>')
    return result


def details(p: dict, page: str, result: dict, skip: set[str]) -> None:
    """案内の詳しい説明・作業の段階・AIの補足。初期状態はすべて折りたたむ。

    skip：この画面の上部の移動ボタンと同じ移動先。同じ操作を重複して出さない。
    """
    main = result["main"]
    st.divider()
    st.caption("案内と補助の操作")
    with st.expander("次にすることの詳しい説明"):
        if main:
            for label, text in (("現在の状況", main.situation), ("今、確認するとよいこと", main.todo), ("この操作をおすすめする理由", main.reason)):
                st.markdown(f"**{label}**")
                st.write(text)
            if main.items:
                st.caption("該当する項目：" + "／".join(main.items))
            if not _here(main, page) and main.page not in skip:
                _go(main, page, "guide_go")
        else:
            st.write("確認した範囲では、対応が必要な項目は検出されていません。登録されていない論点は検出できません。")
        others = [a for a in result["extra"] + result["rest"] if a.page not in skip]
        for n, a in enumerate(others):
            st.markdown(f"**ほかに確認すること：{a.title}**")
            st.write(a.situation)
            _go(a, page, f"guide_go_{n}")
    _stage_question(p)
    if main:
        _ai_block(p, main)


def project_panel(p: dict, page: str) -> None:
    """現在の状況と次にすること。主な内容は1件。説明を閉じても、状況の短い文と次の操作は残す。

    閉じた状態は案件を開いている間、別の画面でも続く。別の案件を開くと元に戻る。
    """
    hidden = st.session_state.get("guidance_hidden", False)
    result = gd.assess(p, page, st.session_state.get("resumed", False))
    main = result["main"]
    if main is None:
        st.html(frame("現在の状況と次にすること", [], "確認した範囲では、対応が必要な項目は検出されていません。登録されていない論点は検出できません。", kind="work"))
    else:
        st.html(_advice_html(main, not hidden))
    _actions(main, page, hidden)
    if hidden:
        return
    _stage_question(p)
    if main and main.items:
        st.caption("該当する項目：" + "／".join(main.items))
    others = result["extra"] + result["rest"]
    if others:
        with st.expander(f"ほかに確認すること（{len(others)}件）"):
            for n, a in enumerate(others):
                st.markdown(f"**{a.title}**")
                st.write(a.situation)
                st.caption(f"この操作をおすすめする理由：{a.reason}")
                _go(a, page, f"guide_go_{n}")
    if main:
        _ai_block(p, main)
