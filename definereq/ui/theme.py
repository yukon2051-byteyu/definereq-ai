"""見た目の共通定義。

色と文字は公式テーマ（.streamlit/config.toml）を基本とし、CSSは独自部品（dr-*）の範囲に限定する。
Streamlit の標準部品のフォントは上書きしない（アイコンを壊さないため）。

参考：Filament X Frontier のビジュアル（太いゴシック、橙→赤→マゼンタの階調、はみ出す大きな幾何形状、広い余白）。
ロゴのX形状や画像は流用せず、「根拠から判断へ渡る斜めの帯」を独自の図形にしている。
"""
from __future__ import annotations

import base64

# 色の定義元。ヒーローの図形（SVG）とCSS変数の両方へ流し込む
# 図形はCSS変数を読めないため、ここで一元管理する
PALETTE = {"orange": "#FF7A00", "coral": "#F23A1E", "pink": "#EE2A6C", "magenta": "#E0117F", "purple": "#A41EF5"}
# 工程の番号の色（淡い背景の上で読める濃さ）
DEEP = {"orange": "#A84A00", "coral": "#B92A12", "pink": "#B3164C", "magenta": "#AE0C62", "purple": "#7E12C4"}
# 白で薄める割合。紫は同じ割合だと暗く見えるため少し低くして、5枚の明るさをそろえる
TINT = {"orange": .24, "coral": .22, "pink": .22, "magenta": .22, "purple": .20}


def mix(a: str, b: str, ratio: float = .5) -> str:
    """2色を混ぜる（ratio は a の割合）。"""
    pa, pb = (tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (a, b))
    return "#" + "".join(f"{round(x * ratio + y * (1 - ratio)):02X}" for x, y in zip(pa, pb))


def palette_css() -> str:
    """CSS変数と、5工程で一続きになる背景を作る。"""
    names = list(PALETTE)
    tints = [mix(PALETTE[n], "#FFFFFF", TINT[n]) for n in names]
    lines = [":root{" + "".join(f"--c-{n}:{PALETTE[n]};--deep-{n}:{DEEP[n]};" for n in names)
             + "".join(f"--t{i}:{t};" for i, t in enumerate(tints, 1)) + "--flow-dir:90deg}"]
    for i, n in enumerate(names, 1):
        start = f"--t{i}" if i == 1 else None
        left = f"var(--t{i})" if start else mix(tints[i - 2], tints[i - 1])
        right = f"var(--t{i})" if i == len(names) else mix(tints[i - 1], tints[i])
        lines.append(f".dr-step:nth-child({i}){{background:linear-gradient(var(--flow-dir),{left},var(--t{i}),{right})}}")
        lines.append(f".dr-step:nth-child({i}):before{{color:var(--deep-{n})}}")
    return "\n".join(lines)


CSS = """
<style>
__PALETTE_CSS__
:root{--ink:#161618;--muted:#5A5C63;--line:#E2E3E7;--panel:#F5F5F7;--g1:var(--c-orange);--g2:var(--c-coral);--g3:var(--c-magenta)}
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
.dr-bar{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center;padding:4px 0;font-size:12px;color:var(--muted)}
.dr-bar b{font-weight:700;color:#3C3E44}
.dr-g-prog{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline;font-size:13px;color:var(--muted)}
.dr-g-prog b{color:#B8290A;font-weight:900;font-size:14px}
.dr-g-h{font-size:26px;font-weight:900;line-height:1.35;margin:0;padding:0;color:var(--ink)}
.dr-g-lead{font-size:15px;line-height:1.7;margin:6px 0 0;color:#3C3E44}
.dr-g-focus{font-size:13px;font-weight:900;color:#B8290A;border-bottom:2px solid transparent;border-image:linear-gradient(90deg,var(--c-orange),var(--c-magenta),var(--c-purple)) 1;padding-bottom:3px}
.dr-g-focus span{font-weight:500;color:var(--muted);margin-left:10px}
.dr-g-card{background:#FAF9F6;border:1px solid var(--line);border-radius:6px;padding:12px 14px}
.dr-g-hot{border-left:4px solid var(--c-coral)}
.dr-g-title{font-size:15px;font-weight:700;color:var(--ink);line-height:1.6}
.dr-g-text{font-size:15px;line-height:1.75;color:var(--ink)}
.dr-g-sm{font-size:13px;line-height:1.65;color:#3C3E44;margin-top:2px}
.dr-g-meta{font-size:13px;color:#3C3E44;margin-bottom:2px}
.dr-g-note{font-size:13.5px;font-weight:700;color:#B8290A;margin-top:4px;line-height:1.6}
.dr-g-q{font-size:14.5px;line-height:1.75;color:var(--ink);background:#fff;border-left:3px solid #C9C7C0;padding:6px 10px;margin-top:6px}
.dr-g-q span{display:block;font-size:11px;font-weight:700;color:var(--muted)}
.dr-g-opts{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px;margin:8px 0}
.dr-g-opt{background:#fff;border:1px solid var(--line);border-radius:4px;padding:8px 10px}
.dr-g-win{border:2px solid #1C7A4D}
.dr-g-res{font-size:13px;line-height:1.6;color:#3C3E44;margin-top:4px;font-weight:700}
.dr-g-row{display:grid;grid-template-columns:180px 1fr;gap:10px;padding:8px 0;border-top:1px solid var(--line)}
.dr-g-row:first-child{border-top:none;padding-top:0}
.dr-g-rl{font-size:13px;font-weight:700;color:var(--muted)}
.dr-g-rv{font-size:14.5px;line-height:1.7;color:var(--ink)}
.dr-g-cols,.dr-g-cols2{display:grid;gap:14px;margin-top:6px}
.dr-g-cols{grid-template-columns:repeat(3,1fr)}
.dr-g-cols2{grid-template-columns:1fr 1fr}
.dr-g-col ul{margin:2px 0 0;padding-left:18px;font-size:14px;line-height:1.7;color:var(--ink)}
.dr-g-lab{font-size:12px;font-weight:900;color:var(--muted);margin-bottom:2px}
.dr-g-col2{margin-top:8px}
.dr-g-col2:first-child{margin-top:0}
.dr-dl{display:grid;grid-template-columns:180px 1fr;gap:6px 14px;font-size:14px;line-height:1.7;color:var(--ink);margin:0}
.dr-dl dt{font-weight:700;color:var(--muted)}
.dr-dl dd{margin:0}
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
.dr-ai{font-size:1.14em;font-weight:900;color:#EB2A44;position:relative;top:1mm}
.dr-comma{font-style:normal}
@media (min-width:761px){.dr-h1 span{white-space:nowrap}.dr-comma{margin-right:-.312em}}
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
.dr-sec{font-size:24px;font-weight:900;line-height:1.3;margin:16px 0 0;color:var(--ink);padding:0;scroll-margin-top:16px}
.dr-sec-l{font-size:14px;color:var(--muted);margin:6px 0 0;line-height:1.6}
.dr-steps{display:grid;grid-template-columns:repeat(5,1fr);gap:4px;counter-reset:s}
.dr-step{counter-increment:s;font-size:13px;line-height:1.5;color:#2F3036;padding:10px 32px 10px 30px;clip-path:polygon(0 0,calc(100% - 22px) 0,100% 50%,calc(100% - 22px) 100%,0 100%,18px 50%)}
.dr-step:nth-child(1){padding-left:16px;clip-path:polygon(0 0,calc(100% - 22px) 0,100% 50%,calc(100% - 22px) 100%,0 100%)}
.dr-step:before{content:counter(s,decimal-leading-zero);display:block;font-size:22px;font-weight:900;line-height:1.15}
.dr-step b{display:block;font-size:15px;font-weight:900;color:var(--ink);line-height:1.4;margin:0 0 1px}
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
 :root{--flow-dir:180deg}
 .dr-steps{grid-template-columns:1fr}
 .dr-step,.dr-step:nth-child(1){clip-path:none;padding:10px 14px;border-radius:4px}
 .dr-flow{grid-template-columns:1fr 1fr}
 .dr-flow-c{border-bottom:1px solid var(--line)}
 .dr-title{font-size:22px}
 .dr-g-h{font-size:21px}
 .dr-g-row,.dr-dl,.dr-g-cols,.dr-g-cols2{grid-template-columns:1fr;gap:4px}
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
/* サイドバーのロゴ（トップへのリンク） */
[data-testid="stSidebarHeader"]{height:auto;min-height:0;padding:6px 12px 0}
[data-testid="stSidebar"] .st-key-nav_logo button{background:url("__MARK_DARK__") 8px center/24px 24px no-repeat transparent;padding:2px 10px 2px 42px;min-height:40px}
[data-testid="stSidebar"] .st-key-nav_logo button:hover,[data-testid="stSidebar"] .st-key-nav_logo button:focus,[data-testid="stSidebar"] .st-key-nav_logo button:active{background:url("__MARK_DARK__") 8px center/24px 24px no-repeat #26262B}
[data-testid="stSidebar"] .st-key-nav_logo button p{font-size:17px;font-weight:900;color:#fff;letter-spacing:.01em}
[data-testid="stSidebar"] .st-key-nav_logo{margin-bottom:8px}
/* トップページ専用の余白。見た目の間隔は 区切り30px／説明→内容14px／カード内8px */
.st-key-home{gap:14px}
.stMainBlockContainer:has(.st-key-home){padding-bottom:32px}
.st-key-home [data-testid="stColumn"] [data-testid="stVerticalBlock"]{gap:8px}
.st-key-home [data-testid="stColumn"] p,.st-key-home_new p{margin-bottom:0}
.st-key-home [data-testid="stColumn"] [data-testid="stMarkdownContainer"],.st-key-home [data-testid="stColumn"] [data-testid="stCaptionContainer"],.st-key-home_new [data-testid="stMarkdownContainer"],.st-key-home_new [data-testid="stCaptionContainer"]{margin-bottom:0}
.st-key-home_new{gap:10px}
</style>
"""

# 独自の図形：根拠（細い線）から判断（太い帯）へ渡る斜めの帯。
# st.html は SVG 要素を取り除くため、CSS の背景画像として埋め込む
_HERO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 350 400" preserveAspectRatio="none">
<defs><linearGradient id="g" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="__orange__"/><stop offset=".55" stop-color="__coral__"/><stop offset="1" stop-color="__magenta__"/></linearGradient></defs>
<polygon points="95,400 335,0 350,0 350,75 165,400" fill="url(#g)"/>
<polygon points="215,400 350,165 350,285 285,400" fill="url(#g)"/>
<polygon points="30,345 215,40 240,40 55,345" fill="#161618"/>
<polygon points="5,215 118,30 130,30 17,215" fill="#E2E3E7"/>
</svg>"""

_MARK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 26 26">
<defs><linearGradient id="m" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="__orange__"/><stop offset=".6" stop-color="__coral__"/><stop offset="1" stop-color="__magenta__"/></linearGradient></defs>
<polygon points="1,25 18,1 25,1 8,25" fill="url(#m)"/><polygon points="12,25 20,13 25,13 17,25" fill="#161618"/></svg>"""

# 黒いサイドバー用：黒い線だけ白にする
_MARK_DARK_SVG = _MARK_SVG.replace('fill="#161618"', 'fill="#FFFFFF"')


def _uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def _colored(svg: str) -> str:
    for name, value in PALETTE.items():
        svg = svg.replace(f"__{name}__", value)
    return svg


CSS = (CSS.replace("__PALETTE_CSS__", palette_css()).replace("__HERO__", _uri(_colored(_HERO_SVG)))
       .replace("__MARK__", _uri(_colored(_MARK_SVG))).replace("__MARK_DARK__", _uri(_colored(_MARK_DARK_SVG))))
HERO_SHAPE = '<div class="dr-hero-shape"></div>'
MARK = '<span class="dr-markimg"></span>'
