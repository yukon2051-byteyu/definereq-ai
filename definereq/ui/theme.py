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
.dr-hero{position:relative;overflow:hidden;background:#F3F0EA;border-radius:6px;padding:34px 44px 30px}
.dr-hero-shape{position:absolute;right:0;top:0;bottom:0;width:27%;background:url("__HERO__") right center/100% 100% no-repeat;pointer-events:none}
.dr-markimg{display:inline-block;width:26px;height:26px;background:url("__MARK__") center/contain no-repeat}
.dr-hero-in{position:relative;max-width:68%}
.dr-mark{display:flex;align-items:center;gap:10px;font-weight:900;font-size:17px;color:var(--ink);letter-spacing:.01em}
.dr-h1{font-size:clamp(34px,3.3vw,46px);line-height:1.28;font-weight:900;margin:26px 0 0;color:var(--ink);letter-spacing:-.01em;padding:0}
.dr-h1 span{display:inline-block}
.dr-sub{font-size:16px;line-height:1.75;color:#3C3E44;margin:8px 0 0}
.dr-label{font-size:13px;font-weight:700;color:var(--muted);margin-top:8px}
.dr-cta{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}
.dr-btn{display:inline-block;padding:11px 22px;border-radius:4px;font-size:15px;font-weight:700;text-decoration:none;line-height:1.3}
.dr-btn-p,.dr-btn-p:visited{background:#D9330F;color:#fff}
.dr-btn-p:hover{background:#B8290A;color:#fff}
.dr-btn-s,.dr-btn-s:visited{background:#fff;color:var(--ink);border:1px solid #CFCDC6}
.dr-btn-s:hover{border-color:#D9330F;color:#B8290A}
.dr-note{font-size:12.5px;color:var(--muted);margin-top:10px}
.dr-jp{font-size:18px;font-weight:900;color:#B8290A;margin-top:12px}
.dr-sec{font-size:24px;font-weight:900;margin:24px 0 4px;color:var(--ink);padding:0;scroll-margin-top:16px}
.dr-sec-l{font-size:14px;color:var(--muted);margin:0 0 14px;line-height:1.7}
.dr-dom{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.dr-dom div{padding:16px 16px 18px;border-radius:6px;font-size:13px;line-height:1.7;color:#4A4C52}
.dr-dom div:nth-child(1){background:#DFECFA}
.dr-dom div:nth-child(2){background:#E1F3E4}
.dr-dom div:nth-child(3){background:#FBF5D2}
.dr-dom div:nth-child(4){background:#ECEBF5}
.dr-dom b{display:block;font-size:17px;font-weight:900;color:var(--ink);margin-bottom:2px}
.dr-steps{display:grid;grid-template-columns:repeat(5,1fr);gap:4px;counter-reset:s}
.dr-step{counter-increment:s;font-size:13px;line-height:1.65;color:#2F3036;padding:16px 34px 18px 30px;clip-path:polygon(0 0,calc(100% - 22px) 0,100% 50%,calc(100% - 22px) 100%,0 100%,18px 50%)}
.dr-step:nth-child(1){background:#FFF4EA;padding-left:16px;clip-path:polygon(0 0,calc(100% - 22px) 0,100% 50%,calc(100% - 22px) 100%,0 100%)}
.dr-step:nth-child(2){background:#FFE8D6}
.dr-step:nth-child(3){background:#FFDBC8}
.dr-step:nth-child(4){background:#FDCCBF}
.dr-step:nth-child(5){background:#FAB9BE}
.dr-step:before{content:counter(s,decimal-leading-zero);display:block;font-size:24px;font-weight:900;color:#B8290A;line-height:1.2}
.dr-step b{display:block;font-size:16px;font-weight:900;color:var(--ink);margin:2px 0}
.dr-tiny{font-size:12px;color:var(--muted);line-height:1.7}
.dr-demo-n{font-size:12px;font-weight:900;color:#B8290A}
@media (max-width:760px){
 .dr-hero{padding:24px 18px 24px}
 .dr-hero-in{max-width:100%}
 .dr-cta{flex-direction:column}
 .dr-btn{text-align:center}
 .dr-hero-shape{display:none}
 .dr-h1{font-size:30px}
 .dr-jp{font-size:17px}
 .dr-dom{grid-template-columns:repeat(2,1fr)}
 .dr-steps{grid-template-columns:1fr}
 .dr-step,.dr-step:nth-child(1){clip-path:none;padding:12px 16px;border-radius:4px}
 .dr-flow{grid-template-columns:1fr 1fr}
 .dr-flow-c{border-bottom:1px solid var(--line)}
 .dr-title{font-size:22px}
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
_HERO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 350 400" preserveAspectRatio="none">
<defs><linearGradient id="g" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#FF7A00"/><stop offset=".55" stop-color="#F23A1E"/><stop offset="1" stop-color="#E0117F"/></linearGradient></defs>
<polygon points="95,400 335,0 350,0 350,75 165,400" fill="url(#g)"/>
<polygon points="215,400 350,165 350,285 285,400" fill="url(#g)"/>
<polygon points="30,345 215,40 240,40 55,345" fill="#161618"/>
<polygon points="5,215 118,30 130,30 17,215" fill="#E2E3E7"/>
</svg>"""

_MARK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 26 26">
<defs><linearGradient id="m" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#FF7A00"/><stop offset=".6" stop-color="#F23A1E"/><stop offset="1" stop-color="#E0117F"/></linearGradient></defs>
<polygon points="1,25 18,1 25,1 8,25" fill="url(#m)"/><polygon points="12,25 20,13 25,13 17,25" fill="#161618"/></svg>"""


def _uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


CSS = CSS.replace("__HERO__", _uri(_HERO_SVG)).replace("__MARK__", _uri(_MARK_SVG))
HERO_SHAPE = '<div class="dr-hero-shape"></div>'
MARK = '<span class="dr-markimg"></span>'
