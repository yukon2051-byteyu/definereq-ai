"""トップページ（架空の実績は載せない）。"""
from __future__ import annotations

import streamlit as st

from .. import project as pj
from ..demos import builder
from ..schema import DOMAINS
from ..usage import gate
from . import state
from .components import esc, guard
from .theme import HERO_SHAPE, MARK

LEAD = ("事前情報からヒアリングを準備し、Web会議の録画や議事録から要望・決定・未決事項を整理します。"
        "業務アプリ、インフラ、ネットワークの要件について、見落とし、仕様の矛盾、追加要望の影響を確認し、"
        "関係者との認識合わせ、要件定義書の作成、仕様変更の経緯の追跡まで支援します。")
FLOW = [("準備", "案件の分野・要望・資料を登録し、不足情報と質問を整理"),
        ("整理", "録画・議事録・資料から、要望・決定・未決事項を抽出"),
        ("判断", "例外・非機能・矛盾・意見の違いを確認し、関係者が要件を確定"),
        ("共有", "確認資料と要件定義書を出力"),
        ("追跡", "追加要望の影響を調べて記録し、「なぜこの仕様か」を根拠付きで確認")]
DOM_NOTE = {"app": "業務・機能・データ・画面・連携", "infra": "性能・容量・可用性・復旧・運用", "network": "接続・通信・分離・認証・障害"}


def render() -> None:
    st.html(f"""<div class="dr-hero">{HERO_SHAPE}<div class="dr-hero-in">
<div class="dr-mark">{MARK}<span>DefineReq_AI</span></div>
<h1 class="dr-h1"><span>あなたの要件定義に、</span><span>伴走するAI</span></h1>
<div class="dr-jp">AI要件定義・変更経緯管理システム</div>
<p class="dr-sub">{esc(LEAD)}</p></div></div>""")

    st.html('<h2 class="dr-sec">3件のデモを試す</h2><p class="dr-sec-l">APIキーや登録なしで、完成した案件の全画面を見られます。デモは閲覧専用で、データは全て架空です。</p>')
    cols = st.columns(3)
    for i, (col, d) in enumerate(zip(cols, builder.catalog()), 1):
        with col, st.container(border=True, height="stretch"):
            st.html(f'<div class="dr-demo-n">DEMO {i}　{esc("＋".join(DOMAINS[x] for x in d["domains"]))}</div>')
            st.markdown(f"**{d['name']}**")
            st.caption(d["lead"])
            st.caption(f"見どころ：{d['strength']}")
            st.space("stretch")  # 文章の行数が違っても、ボタンと下端の線を揃える
            if st.button("3分の案内で見る", key=f"tour_{d['id']}", type="primary", width="stretch"):
                state.open_demo(d["id"], tour=True)
            if st.button("全画面を見る", key=f"free_{d['id']}", width="stretch"):
                state.open_demo(d["id"], tour=False)

    st.html('<h2 class="dr-sec">あなたの案件で試す</h2>')
    with st.container(border=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("案件名", placeholder="例：勤怠システムの更新", key="new_name")
        domains = c2.multiselect("対象分野（複合は複数選択）", list(DOMAINS), format_func=DOMAINS.get, default=["app"], key="new_dom")
        code = st.text_input("AIパスワード", type="password", key="home_code")
        valid = gate.check_code(code)
        if code and not valid:
            st.warning("AIパスワードが正しくありません。")
        st.caption("案件の作成にはAIパスワードが必要です。入力後にEnterキーを押してください。入力した案件はこの画面の利用中のみ保持され、閉じると消えます。")
        if st.button("案件を作成", type="primary", disabled=not valid, key="create_project"):
            created = guard(pj.new_project, name, domains)
            if created:
                st.session_state["ai_code"] = code.strip()  # AI実行の画面で使う（入力欄はここだけ）
                state.open_project(created)

    st.html('<h2 class="dr-sec">対応する分野</h2><p class="dr-sec-l">分野に応じて、質問・確認観点・文書の章立てが切り替わります。</p>')
    dom = "".join(f"<div><b>{esc(DOMAINS[k])}</b>{esc(DOM_NOTE[k])}</div>" for k in DOMAINS)
    st.html(f'<div class="dr-dom">{dom}<div><b>複合</b>共通と分野別を分け、重複をまとめる</div></div>')

    st.html('<h2 class="dr-sec">利用の流れ</h2><p class="dr-sec-l">AIは候補を作り、プログラムが記録と照合を行い、人が判断します。AIの出力だけで要件や合意は確定しません。</p>')
    st.html('<div class="dr-steps">' + "".join(f'<div class="dr-step"><b>{esc(n)}</b>{esc(t)}</div>' for n, t in FLOW) + "</div>")

    st.html('<p class="dr-tiny" style="margin-top:36px">要件定義の完全性や正しさを保証するものではありません。人が確認・判断するための根拠と残件を示します。'
            '公開環境の無料CPUは利用がないと休止するため、開くまでに時間がかかることがあります。</p>')
