"""トップページ（架空の実績は載せない）。"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import project as pj
from ..demos import builder
from ..export import jsonio
from ..schema import DOMAINS
from ..usage import gate
from . import state
from .components import chip, esc, guard, save_controls
from .theme import HERO_SHAPE, MARK

LEAD = "会議前の質問準備から、録画・議事録の要件整理、追加要望の影響確認まで。判断の根拠と変更の経緯をつなぎ、要件定義書の作成を支援します。"
FLOW = [("準備", "案件の分野・要望・資料を登録し、不足情報と質問を整理"),
        ("整理", "録画・議事録・資料から、要望・決定・未決事項を抽出"),
        ("判断", "例外・非機能の見落とし、矛盾、意見の違いを確認し、関係者が要件を確定"),
        ("共有", "確認資料で認識を合わせ、要件定義書を出力"),
        ("追跡", "追加要望の影響を調べて記録し、「なぜこの仕様か」を根拠付きで確認")]


SECTIONS = {"dr-demo"}  # 移動先として認める欄


def render() -> None:
    # トップ専用の入れ物。余白の指定をこの中に限定し、作業画面へ影響させない
    with st.container(key="home"):
        _sections()
    _scroll_to(st.session_state.pop("scroll_to", None))
    _keep_place()


def _keep_place() -> None:
    """パスワードを確定した直後、選んでいた入口（新規作成か再開か）へ戻す。"""
    valid = gate.check_code(st.session_state.get("home_code", ""))
    if valid and not st.session_state.get("home_was_valid"):
        st.iframe("<script>const h=window.parent.location.hash;const t=()=>{if(h==='#dr-new-create'||h==='#dr-resume'){window.parent.document.getElementById(h.slice(1))?.scrollIntoView({block:'start'})}};"
                  "t();setTimeout(t,300);setTimeout(t,900)</script>", height=1)
    st.session_state["home_was_valid"] = valid


def _scroll_to(section: str | None) -> None:
    """指定の欄まで移動する。描画に時間がかかるため数回試す。"""
    if section in SECTIONS:
        st.iframe(f"<script>const t=()=>window.parent.document.getElementById('{section}')?.scrollIntoView({{block:'start'}});t();setTimeout(t,300);setTimeout(t,900)</script>", height=1)


def _sections() -> None:
    # ヒーローのボタンはページ内リンク。再実行が起きないため、入力中の内容は消えない
    st.html(f"""<div class="dr-hero">{HERO_SHAPE}<div class="dr-hero-in">
<div class="dr-mark">{MARK}<span>DefineReq_AI</span></div>
<h1 class="dr-h1"><span>あなたの要件定義に<i class="dr-comma">、</i></span><span>伴走する<b class="dr-ai">AI</b>を</span></h1>
<div class="dr-jp">AI要件定義・変更経緯管理システム</div>
<p class="dr-sub">{esc(LEAD)}</p>
<div class="dr-label">業務アプリ ／ インフラ ／ ネットワーク ／ 複合 に対応</div>
<div class="dr-cta"><a class="dr-btn dr-btn-p" href="#dr-demo">案内付きでデモを見る</a><a class="dr-btn dr-btn-s" href="#dr-new-create">新しい案件を始める</a><a class="dr-btn dr-btn-s" href="#dr-resume">保存した案件から再開</a></div>
<div class="dr-note">デモは登録不要・無料／AI結果は準備済みのサンプルです</div>
</div></div>""")

    st.html('<h2 class="dr-sec">利用の流れ</h2><p class="dr-sec-l">AIは候補を作り、プログラムが記録と照合を行い、人が判断します。AIの出力だけで要件や合意は確定しません。</p>')
    st.html('<div class="dr-steps">' + "".join(f'<div class="dr-step"><b>{esc(n)}</b>{esc(t)}</div>' for n, t in FLOW) + "</div>")

    st.html('<h2 id="dr-demo" class="dr-sec">3件のデモを試す</h2><p class="dr-sec-l">APIキーや登録なしで、案内に沿って見られます。最後にサンプル資料をダウンロードできます。デモは閲覧専用で、データは全て架空です。</p>')
    cols = st.columns(3)
    done = st.session_state.get("demo_done", set())
    for i, (col, d) in enumerate(zip(cols, builder.catalog()), 1):
        with col, st.container(border=True, height="stretch"):
            seen = d["id"] in done
            badge = chip("✓ 体験済み", "ok") if seen else ""
            points = "".join(f"<li>{esc(x)}</li>" for x in d["highlights"])
            st.html(f'<div class="dr-demo-n"><span>DEMO {i}　{esc("＋".join(DOMAINS[x] for x in d["domains"]))}</span>{badge}</div><div class="dr-demo-t">{esc(d["name"])}</div>'
                    f'<div class="dr-demo-l">どんな案件か</div><div class="dr-demo-s">{esc(d["summary"])}</div>'
                    f'<div class="dr-demo-l">誰が何に困っているか</div><div class="dr-demo-s">{esc(d["situation"])}</div>'
                    f'<div class="dr-high"><b>このデモの見どころ</b><ul>{points}</ul></div>')
            st.space("stretch")  # 文章の行数が違っても、ボタンと下端の線を揃える
            if st.button("もう一度見る" if seen else "案内付きでデモを見る", key=f"tour_{d['id']}", type="primary", width="stretch"):
                state.open_demo(d["id"], tour=True)

    st.html('<h2 id="dr-new" class="dr-sec">あなたの案件で試す</h2>')
    switch_ok = _current_work()
    with st.container(border=True, key="home_new"):
        code = st.text_input("AIパスワード", type="password", key="home_code")
        valid = gate.check_code(code)
        if code and not valid:
            st.warning("AIパスワードが正しくありません。")
        st.caption("案件の作成と再開にはAIパスワードが必要です。入力後にEnterキーを押してください。入力した案件はアプリ利用中のみ保持されるため、続きを行うときはJSONで保存してください。")
        left, right = st.columns(2)
        with left:
            st.html('<div id="dr-new-create" class="dr-anchor"></div>')
            st.markdown("**新しい案件を始める**")
            name = st.text_input("案件名", placeholder="例：勤怠システムの更新", key="new_name")
            domains = st.multiselect("対象分野（複合は複数選択）", list(DOMAINS), format_func=DOMAINS.get, default=["app"], key="new_dom")
            if not valid:
                st.caption("作成するには、上の「AIパスワード」を入力し、Enterキーで確定してください。")
            if st.button("案件を作成", type="primary", disabled=not (valid and switch_ok), key="create_project"):
                created = guard(pj.new_project, name, domains)
                if created:
                    st.session_state["ai_code"] = code.strip()  # AI実行の画面で使う（入力欄はここだけ）
                    state.open_project(created)
        with right:
            st.html('<div id="dr-resume" class="dr-anchor"></div>')
            st.markdown("**保存した案件から再開する**")
            if not valid:
                st.caption("再開するには、上の「AIパスワード」を入力し、Enterキーで確定してください。ファイルの選択は先にできます。")
            st.caption("前回保存した案件JSONを読み込むと、要件・未決事項・判断・変更履歴を引き継いで、次の会議の準備や整理を続けられます。")
            _resume(code, valid and switch_ok)

    st.html('<p class="dr-tiny" style="margin-top:16px">要件定義の完全性や正しさを保証するものではありません。人が確認・判断するための根拠と残件を示します。'
            '公開環境の無料CPUは利用がないと休止するため、開くまでに時間がかかることがあります。</p>')


def _current_work() -> bool:
    """作業中の案件を表示する。別の案件へ切り替えてよければ True。"""
    p = state.current()
    if not p or p.get("is_demo"):
        return True
    with st.container(border=True):
        st.markdown(f"**作業中の案件：{p['name']}**")
        if st.button("作業に戻る", key="back_work"):
            state.back_to_work()
        if not state.is_dirty(p):
            return True
        st.warning("保存用ファイルの作成後に変更があります。別の案件へ切り替える前に保存してください。")
        save_controls(p, "save_home")
        return st.checkbox("保存せずに別の案件へ切り替える", key="discard_ok")


def _resume(code: str, enabled: bool) -> None:
    up = st.file_uploader("案件JSON", type=["json"], key="home_json")
    if up is None:
        return
    try:
        loaded = jsonio.loads(up.getvalue())  # 検証に合格するまで作業中の案件には触れない
    except jsonio.LoadError as e:
        st.error("読み込めませんでした。作業中の案件は変更していません。")
        for message in e.errors[:6]:
            st.caption(message)
        st.caption(f"対処：{e.hint}")
        return
    st.dataframe(pd.DataFrame(list(jsonio.summary(loaded).items()), columns=["項目", "内容"]), hide_index=True, width="stretch")
    if loaded.get("migrated_from"):
        st.caption(f"以前の形式（版{loaded['migrated_from']}）のファイルです。現在の形式に変換して読み込みます。")
    for note in jsonio.missing_files(loaded):
        st.caption(note)
    if st.button("この案件を再開する", type="primary", disabled=not enabled, key="resume_project"):
        st.session_state["ai_code"] = code.strip()
        state.open_project(loaded, loaded=True)
