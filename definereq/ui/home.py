"""トップページ。プレビューは実際のデモ案件のデータから作る（架空の実績は載せない）。"""
from __future__ import annotations

import streamlit as st

from .. import project as pj
from ..demos import builder
from ..export import jsonio
from ..schema import DOMAINS
from . import state
from .components import chip, esc, guard
from .theme import HERO_SHAPE, MARK

LEAD = ("事前情報からヒアリングを準備し、Web会議の録画や議事録から要望・決定・未決事項を整理します。"
        "業務アプリ、インフラ、ネットワークの要件について、見落とし、仕様の矛盾、追加要望の影響を確認し、"
        "関係者との認識合わせ、要件定義書の作成、仕様変更の経緯の追跡まで支援します。")
FLOW = ["案件の分野・要望・事前資料を登録", "不足情報・議題・事前質問を整理", "録画・議事録・追加資料を登録", "要望・決定・未決事項を抽出",
        "例外・非機能・矛盾・意見の違いを確認", "関係者が判断し、要件を確定", "確認資料と要件定義書を出力", "追加要望の影響と矛盾を調査",
        "判断と変更を記録し、関連文書を更新", "「なぜこの仕様か」を根拠付きで確認"]
DOM_NOTE = {"app": "業務・機能・データ・画面・連携", "infra": "性能・容量・可用性・復旧・運用", "network": "接続・通信・分離・認証・障害"}


def render() -> None:
    st.html(f"""<div class="dr-hero">{HERO_SHAPE}<div class="dr-hero-in">
<div class="dr-mark">{MARK}<span>DefineReq_AI</span> <span class="dr-kana">ディファインレック・エーアイ</span></div>
<h1 class="dr-h1"><span>「何を聞くか」から</span><span>「なぜこの仕様か」まで。</span><span>会議と変更の根拠をつなぐ、</span><span>要件定義支援AI。</span></h1>
<div class="dr-jp">AI要件定義・変更経緯管理システム</div>
<p class="dr-sub">{esc(LEAD)}</p></div></div>""")

    st.html('<h2 class="dr-sec">3件のデモを試す</h2><p class="dr-sec-l">APIキーや登録なしで、全機能を操作できます。データは全て架空です。AIの結果は事前に用意したもので、料金は発生しません。</p>')
    cols = st.columns(3)
    for i, (col, d) in enumerate(zip(cols, builder.catalog()), 1):
        with col, st.container(border=True):
            st.html(f'<div class="dr-demo-n">DEMO {i}　{esc("＋".join(DOMAINS[x] for x in d["domains"]))}</div>')
            st.markdown(f"**{d['name']}**")
            st.caption(d["lead"])
            st.caption(f"見どころ：{d['strength']}")
            if st.button("3分の案内で見る", key=f"tour_{d['id']}", type="primary", width="stretch"):
                state.open_demo(d["id"], tour=True)
            if st.button("自由に操作する", key=f"free_{d['id']}", width="stretch"):
                state.open_demo(d["id"], tour=False)

    st.html('<h2 class="dr-sec">新しい案件を始める</h2>')
    left, right = st.columns(2)
    with left, st.container(border=True):
        st.markdown("**新規案件**")
        name = st.text_input("案件名", placeholder="例：勤怠システムの更新", key="new_name")
        domains = st.multiselect("対象分野（複合は複数選択）", list(DOMAINS), format_func=DOMAINS.get, default=["app"], key="new_dom")
        st.caption("入力した内容はこの画面の利用中のみ保持されます。作業の前後にJSONで保存してください。")
        if st.button("案件を作成", type="primary"):
            created = guard(pj.new_project, name, domains)
            if created:
                state.open_project(created)
    with right, st.container(border=True):
        st.markdown("**保存した案件を開く**")
        up = st.file_uploader("案件JSON", type=["json"], key="home_json")
        if up is not None and st.button("読み込む"):
            try:
                state.open_project(jsonio.loads(up.getvalue()))
            except jsonio.LoadError as e:
                st.error("読み込めませんでした。作業中のデータは変更していません。")
                for msg in e.errors[:6]:
                    st.caption(msg)

    st.html('<h2 class="dr-sec">対応する分野</h2><p class="dr-sec-l">分野に応じて、質問・確認観点・文書の章立てが切り替わります。</p>')
    dom = "".join(f"<div><b>{esc(DOMAINS[k])}</b>{esc(DOM_NOTE[k])}</div>" for k in DOMAINS)
    st.html(f'<div class="dr-dom">{dom}<div><b>複合</b>共通と分野別を分け、重複をまとめる</div></div>')

    st.html('<h2 class="dr-sec">利用の流れ</h2><p class="dr-sec-l">AIは候補を作り、プログラムが記録と照合を行い、人が判断します。AIの出力だけで要件や合意は確定しません。</p>')
    st.html('<div class="dr-steps">' + "".join(f'<div class="dr-step">{esc(t)}</div>' for t in FLOW) + "</div>")

    st.html('<h2 class="dr-sec">画面の例</h2><p class="dr-sec-l">下の表は、デモ1「申請・承認アプリの刷新」の実データから表示しています。</p>')
    st.html(_preview())
    st.html('<p class="dr-tiny" style="margin-top:36px">要件定義の完全性や正しさを保証するものではありません。人が確認・判断するための根拠と残件を示します。'
            '公開環境の無料CPUは利用がないと休止するため、開くまでに時間がかかることがあります。</p>')


@st.cache_data(show_spinner=False)
def _preview() -> str:
    p = builder.build("d1", 4)
    rows = ""
    for r in p["requirements"][:5]:
        rows += (f"<tr><td>{esc(r['id'])}</td><td>{esc(r['title'])}</td><td>{chip(r['scope'] or '未設定')}</td>"
                 f"<td>{chip(r['status'])}</td><td>{len(r['evidence'])}件</td></tr>")
    return (f'<div class="dr-prev"><div class="dr-prev-h">要件一覧　{esc(p["name"])}</div><table><thead><tr><th>ID</th><th>要件</th><th>範囲</th>'
            f"<th>状態</th><th>根拠</th></tr></thead><tbody>{rows}</tbody></table></div>")
