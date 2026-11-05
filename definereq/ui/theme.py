"""見た目の共通定義。

色と文字は公式テーマ（.streamlit/config.toml）を基本とし、CSSは独自部品（dr-*）の範囲に限定する。
Streamlit の標準部品のフォントは上書きしない（アイコンを壊さないため）。

参考：Filament X Frontier のビジュアル（太いゴシック、橙→赤→マゼンタの階調、はみ出す大きな幾何形状、広い余白）。
ロゴのX形状や画像は流用せず、「根拠から判断へ渡る斜めの帯」を独自の図形にしている。
"""
from __future__ import annotations

import base64

CSS = """
<style>
:root{--ink:#161618;--muted:#5A5C63;--line:#E2E3E7;--panel:#F5F5F7;--g1:#FF7A00;--g2:#F23A1E;--g3:#E0117F}
.dr-chips{display:flex;flex-wrap:wrap;gap:6px;margin:2px 0 8px}
.dr-chip{display:inline-block;padding:2px 9px;border-radius:3px;font-size:12px;font-weight:700;line-height:1.7;white-space:nowrap}
.dr-head{margin:0 0 14px;padding-left:14px;border-left:6px solid;border-image:linear-gradient(180deg,var(--g1),var(--g2),var(--g3)) 1}
.dr-eyebrow{font-size:12px;font-weight:700;color:var(--muted);letter-spacing:.06em}
.dr-title{font-size:27px;font-weight:900;line-height:1.3;margin:0;padding:0;color:var(--ink)}
.dr-lead{font-size:14px;color:var(--muted);margin:4px 0 0;line-height:1.7}
.dr-card{border:1px solid var(--line);border-radius:4px;padding:14px 16px;background:#fff;height:100%}
.dr-card-t{font-weight:900;font-size:15px;color:var(--ink)}
.dr-card-b{font-size:13.5px;color:var(--muted);line-height:1.75;margin-top:4px}
.dr-card-f{margin-top:6px}
.dr-ev{border-left:3px solid var(--g2);background:var(--panel);padding:8px 12px;margin:6px 0;border-radius:0 3px 3px 0}
.dr-ev-q{font-size:13.5px;line-height:1.7;color:var(--ink)}
.dr-ev-w{font-size:12px;color:var(--muted);margin-top:2px}
.dr-flow{display:grid;grid-template-columns:repeat(4,1fr);gap:0;border:1px solid var(--line);border-radius:4px;overflow:hidden;margin:6px 0 12px}
.dr-flow-c{padding:10px 12px;border-right:1px solid var(--line);background:#fff}
.dr-flow-c:last-child{border-right:none}
.dr-flow-l{font-size:11px;font-weight:900;color:#B8290A;letter-spacing:.04em}
.dr-flow-v{font-size:13px;line-height:1.6;color:var(--ink);margin-top:2px}
.dr-bar{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;padding:8px 12px;background:var(--panel);border-radius:4px;font-size:13px;margin-bottom:10px;color:var(--ink)}
.dr-bar b{font-weight:900}
.dr-stat{border-top:3px solid var(--ink);padding-top:6px}
.dr-stat-n{font-size:30px;font-weight:900;line-height:1.2;color:var(--ink)}
.dr-stat-l{font-size:12.5px;color:var(--muted)}
/* トップページ */
.dr-hero{position:relative;overflow:hidden;background:#fff;padding:54px 0 60px;min-height:440px}
.dr-hero-shape{position:absolute;right:0;top:0;bottom:0;width:52%;background:url("__HERO__") right center/cover no-repeat;pointer-events:none}
.dr-markimg{display:inline-block;width:26px;height:26px;background:url("__MARK__") center/contain no-repeat}
.dr-hero-in{position:relative;max-width:640px}
.dr-mark{display:flex;align-items:center;gap:10px;font-weight:900;font-size:17px;color:var(--ink);letter-spacing:.01em}
.dr-kana{font-size:12px;font-weight:500;color:var(--muted)}
.dr-h1{font-size:42px;line-height:1.32;font-weight:900;margin:26px 0 0;color:var(--ink);letter-spacing:-.01em;padding:0}
.dr-h1 span{display:inline-block}
.dr-sub{font-size:15px;line-height:1.95;color:#3C3E44;margin:18px 0 0;max-width:600px}
.dr-jp{font-size:13px;font-weight:700;color:#B8290A;margin-top:12px}
.dr-sec{font-size:24px;font-weight:900;margin:44px 0 4px;color:var(--ink);padding:0}
.dr-sec-l{font-size:14px;color:var(--muted);margin:0 0 14px;line-height:1.7}
.dr-dom{display:grid;grid-template-columns:repeat(4,1fr);gap:0;border-top:3px solid var(--ink)}
.dr-dom div{padding:14px 14px 16px 0;font-size:13px;line-height:1.7;color:var(--muted)}
.dr-dom b{display:block;font-size:17px;font-weight:900;color:var(--ink);margin-bottom:2px}
.dr-steps{display:grid;grid-template-columns:repeat(5,1fr);gap:14px 18px;counter-reset:s}
.dr-step{counter-increment:s;font-size:13px;line-height:1.65;color:#3C3E44}
.dr-step:before{content:counter(s,decimal-leading-zero);display:block;font-size:26px;font-weight:900;background:linear-gradient(90deg,var(--g1),var(--g2),var(--g3));-webkit-background-clip:text;background-clip:text;color:transparent;line-height:1.2}
.dr-prev{border:1px solid var(--line);border-radius:6px;overflow:hidden}
.dr-prev-h{background:var(--ink);color:#fff;padding:8px 14px;font-size:12.5px;font-weight:700}
.dr-prev table{width:100%;border-collapse:collapse;font-size:13px}
.dr-prev th{text-align:left;background:var(--panel);padding:7px 12px;font-weight:700;color:var(--muted);font-size:12px}
.dr-prev td{padding:8px 12px;border-top:1px solid var(--line);vertical-align:top;color:var(--ink)}
.dr-tiny{font-size:12px;color:var(--muted);line-height:1.7}
.dr-demo-n{font-size:12px;font-weight:900;color:#B8290A}
@media (max-width:760px){
 .dr-hero{padding:28px 0 36px;min-height:0}
 .dr-hero-shape{width:70%;opacity:.16}
 .dr-h1{font-size:29px}
 .dr-dom{grid-template-columns:repeat(2,1fr)}
 .dr-steps{grid-template-columns:repeat(2,1fr)}
 .dr-flow{grid-template-columns:1fr 1fr}
 .dr-flow-c{border-bottom:1px solid var(--line)}
 .dr-title{font-size:22px}
 .dr-prev{overflow-x:auto}
 .dr-prev table{min-width:520px}
}
.stMainBlockContainer{padding-top:1.6rem}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]{padding-top:.4rem}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:.12rem}
[data-testid="stSidebar"] .stCaption{margin-top:.55rem}
[data-testid="stSidebar"] .stButton button{justify-content:flex-start;text-align:left;border:none;background:transparent;color:#F5F5F7;padding:2px 10px;min-height:30px}
[data-testid="stSidebar"] .stButton button>div{justify-content:flex-start;width:100%}
[data-testid="stSidebar"] .stButton button p{text-align:left;font-size:13.5px}
[data-testid="stSidebar"] .stButton button:hover{background:#26262B;color:#fff}
[data-testid="stSidebar"] .stButton button[kind="primary"]{background:#fff;color:#161618}
[data-testid="stSidebar"] .stButton button[kind="primary"] p{font-weight:700;color:#161618}
</style>
"""

# 独自の図形：根拠（細い線）から判断（太い帯）へ渡る斜めの帯。
# st.html は SVG 要素を取り除くため、CSS の背景画像として埋め込む
_HERO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 760" preserveAspectRatio="xMaxYMid slice">
<defs><linearGradient id="g" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#FF7A00"/><stop offset=".55" stop-color="#F23A1E"/><stop offset="1" stop-color="#E0117F"/></linearGradient></defs>
<polygon points="330,760 700,250 700,520 520,760" fill="url(#g)"/>
<polygon points="120,760 700,-40 700,120 300,760" fill="url(#g)" opacity=".92"/>
<polygon points="20,620 360,150 400,150 60,620" fill="#161618"/>
<polygon points="0,470 240,140 256,140 16,470" fill="#E2E3E7"/>
</svg>"""

_MARK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 26 26">
<defs><linearGradient id="m" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#FF7A00"/><stop offset=".6" stop-color="#F23A1E"/><stop offset="1" stop-color="#E0117F"/></linearGradient></defs>
<polygon points="1,25 18,1 25,1 8,25" fill="url(#m)"/><polygon points="12,25 20,13 25,13 17,25" fill="#161618"/></svg>"""


def _uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


CSS = CSS.replace("__HERO__", _uri(_HERO_SVG)).replace("__MARK__", _uri(_MARK_SVG))
HERO_SHAPE = '<div class="dr-hero-shape"></div>'
MARK = '<span class="dr-markimg"></span>'
