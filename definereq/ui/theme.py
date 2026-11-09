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
.dr-g-cols2{grid-template-columns:1fr 1fr}
.dr-g-prog{display:flex;flex-wrap:wrap;gap:4px 14px;align-items:baseline;font-size:14px;color:var(--muted);margin-bottom:2px}
.dr-g-prog b{color:#B8290A;font-weight:900}
.dr-g-h{font-size:30px;font-weight:900;line-height:1.4;margin:0 0 6px;padding:0;color:var(--ink)}
.dr-g-lead{font-size:17px;line-height:1.7;margin:6px 0 0;color:#3C3E44}
.dr-key{font-size:21px;font-weight:900;line-height:1.55;color:var(--ink)}
.dr-g-body{font-size:17px;line-height:1.7;color:#2F3036;margin-top:6px}
.dr-g-sub{font-size:16px;line-height:1.7;color:#2F3036}
.dr-meta{font-size:14px;line-height:1.6;color:#4A4C53;margin-top:6px}
.dr-meta-i{display:block;font-size:14px;color:#4A4C53}
.dr-v-lab{font-size:14px;font-weight:700;color:#4A4C53;margin-bottom:4px}
.dr-sp-top{margin-top:18px}
.dr-v-grid{display:grid;grid-template-columns:1fr 36px 1fr;align-items:stretch;gap:8px}
.dr-v-box{padding:12px 16px;background:#F7F5F1;border-radius:6px}
.dr-v-mid{display:flex;align-items:center;justify-content:center;font-size:22px;color:var(--muted)}
.dr-v-below{margin-top:16px;padding-left:14px;border-left:4px solid transparent;border-image:linear-gradient(180deg,var(--c-orange),var(--c-magenta),var(--c-purple)) 1}
.dr-sp{padding:12px 16px;background:#F7F5F1;border-radius:6px}
.dr-win{padding:12px 16px;border-left:5px solid transparent;border-image:linear-gradient(180deg,var(--c-orange),var(--c-magenta),var(--c-purple)) 1;background:#FBFAF7}
.dr-pend{padding:12px 16px;border-left:5px solid #B7B5AE;background:#F7F5F1}
.dr-t-wrap{overflow-x:auto;margin-top:12px}
.dr-t{width:100%;border-collapse:collapse;font-size:15px;line-height:1.6;color:var(--ink)}
.dr-t th{text-align:left;font-size:14px;font-weight:700;color:var(--muted);padding:6px 10px;border-bottom:2px solid var(--line)}
.dr-t td{padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
.dr-t-win td{background:#F7F5F1;font-weight:700}
.dr-f{display:grid;gap:10px}
.dr-f-3{grid-template-columns:repeat(3,1fr)}
.dr-f-2{grid-template-columns:repeat(2,1fr)}
.dr-f-col{padding:12px 14px;background:#F7F5F1;border-radius:6px}
.dr-f-text{font-size:17px;font-weight:700;line-height:1.7;color:var(--ink)}
.dr-add{text-decoration:none;background:#E7F4ED;border-bottom:2px solid #1C7A4D;padding:1px 2px}
.dr-del{background:#FBE9E7;color:#7A1C15;padding:1px 2px}
.dr-add small,.dr-del small{font-size:11px;font-weight:900;margin-right:4px;text-decoration:none;display:inline-block}
.dr-add small{color:#1C7A4D}
.dr-del small{color:#B3261E}
.dr-c{margin-top:2px}
.dr-c-row{padding:8px 0;border-top:1px solid var(--line)}
.dr-c-row:first-child{border-top:none}
.dr-m-row{display:grid;grid-template-columns:1fr 30px 1fr;gap:10px;align-items:center;padding:10px 0;border-top:1px solid var(--line)}
.dr-m-row:first-child{border-top:none;padding-top:0}
.dr-m-arrow{font-size:20px;color:var(--muted);text-align:center}
.dr-tl ul{list-style:none;margin:0;padding:0}
.dr-tl li{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center;padding:6px 0;border-top:1px solid var(--line)}
.dr-tl-d{font-size:14px;font-weight:700;color:var(--muted);min-width:96px}
.dr-open{display:flex;flex-wrap:wrap;gap:6px 36px;padding-top:4px}
.dr-open-g{min-width:220px;flex:1 1 280px}
.dr-help{border-left:3px solid #8E8C85;padding:4px 14px;margin-top:6px}
.dr-help dl{display:grid;grid-template-columns:210px 1fr;gap:2px 12px;margin:0;font-size:15px;line-height:1.6;color:#2F3036}
.dr-help dt{font-weight:700;color:#4A4C53}
.dr-help dd{margin:0}
.dr-state{display:grid;grid-template-columns:120px 1fr;gap:1px 10px;margin:6px 0 0;font-size:15px;line-height:1.6;color:#2F3036}
.dr-state dt{font-weight:700;color:#4A4C53}
.dr-state dd{margin:0}
.dr-g-list{margin:0;padding-left:20px;font-size:17px;line-height:1.7;color:var(--ink)}
.dr-key-list{margin:0;padding-left:22px;font-size:18px;font-weight:700;line-height:1.7;color:var(--ink)}
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
.dr-sub span{display:block}
.dr-label{font-size:13px;font-weight:700;color:var(--muted);margin-top:8px}
.dr-cta{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}
.dr-btn{display:inline-block;padding:11px 22px;border-radius:4px;font-size:15px;font-weight:700;text-decoration:none;line-height:1.3}
.dr-btn-p,.dr-btn-p:visited{background:#D9330F;color:#fff}
.dr-btn-p:hover{background:#B8290A;color:#fff}
.dr-btn-s,.dr-btn-s:visited{background:#fff;color:var(--ink);border:1px solid #CFCDC6}
.dr-btn-s:hover{border-color:#D9330F;color:#B8290A}
.dr-note{font-size:12.5px;color:var(--muted);margin-top:10px}
.dr-jp{font-size:18px;font-weight:900;color:#F03629;margin-top:12px}
.dr-sec{font-size:24px;font-weight:900;line-height:1.3;margin:16px 0 0;color:var(--ink);padding:0;scroll-margin-top:16px}
.dr-sec-l{font-size:14px;color:var(--muted);margin:6px 0 0;line-height:1.6}
.dr-steps{display:grid;grid-template-columns:repeat(5,1fr);gap:4px;counter-reset:s}
.dr-step{counter-increment:s;font-size:13px;line-height:1.5;color:#2F3036;padding:10px 32px 10px 30px;clip-path:polygon(0 0,calc(100% - 22px) 0,100% 50%,calc(100% - 22px) 100%,0 100%,18px 50%)}
.dr-step:nth-child(1){padding-left:16px;clip-path:polygon(0 0,calc(100% - 22px) 0,100% 50%,calc(100% - 22px) 100%,0 100%)}
.dr-step:before{content:counter(s,decimal-leading-zero);display:block;font-size:22px;font-weight:900;line-height:1.15}
.dr-step b{display:block;font-size:15px;font-weight:900;color:var(--ink);line-height:1.4;margin:0 0 1px}
.dr-tiny{font-size:12px;color:var(--muted);line-height:1.7}
.dr-demo-n{display:flex;justify-content:space-between;align-items:center;gap:6px;font-size:12px;font-weight:900;color:#B8290A;min-height:24px}
.dr-demo-n .dr-chip{white-space:nowrap}
.dr-demo-t{font-size:17px;font-weight:900;line-height:1.45;color:var(--ink);margin-top:2px}
.dr-demo-l{font-size:12.5px;font-weight:700;color:#4A4C53;margin-top:8px}
.dr-demo-s{font-size:14px;line-height:1.65;color:#2F3036}
.dr-high{background:#FBF3E8;border:1px solid #EBD9BE;border-radius:4px;padding:8px 12px;margin-top:10px;font-size:14px;line-height:1.6;color:#2F3036}
.dr-high b{display:block;font-weight:900;color:#7A3A00;font-size:13.5px}
.dr-high ul{margin:2px 0 0;padding-left:18px}
/* 状況案内（デモと実案件で共通） */
.dr-sit{border:1px solid var(--line);border-left:4px solid #D9330F;background:#FCFBF8;border-radius:0 4px 4px 0;padding:8px 14px;margin-bottom:4px}
.dr-sit-work{border-left-color:#2A5DB0;background:#F7F9FC}
.dr-sit-tag{font-size:15px;font-weight:900;color:#B8290A;line-height:1.5}
.dr-sit-work .dr-sit-tag{color:#1F4A8F}
.dr-sit-lead{font-size:16px;line-height:1.7;color:var(--ink);margin:2px 0 2px;max-width:48em}
.dr-story{display:grid;grid-template-columns:1fr 1fr;gap:0 36px;margin-top:0}
.dr-story section{margin-top:14px}
.dr-story h2{font-size:16px;font-weight:900;color:#B8290A;line-height:1.4;margin:0 0 2px;padding:0}
.dr-story p{font-size:18px;line-height:1.75;color:var(--ink);margin:0}
.dr-story ul{list-style:none;margin:0;padding:0}
.dr-story li{font-size:17px;line-height:1.65;color:var(--ink);margin-top:4px}
.dr-story li b{display:block;font-size:15px;font-weight:900}
.dr-story-issue{border-left:4px solid #D9330F;background:#FBF3E8;padding:10px 16px}
.dr-sit-row{display:grid;grid-template-columns:170px 1fr;gap:2px 10px;font-size:15px;line-height:1.6;color:#2F3036;padding-top:2px}
.dr-sit-row b{font-weight:700;color:#4A4C53}
/* 最終画面 */
.dr-sit.dr-end{border:1px solid #BFDFCC;border-left:5px solid #1C7A4D;background:#F1F9F4;border-radius:0 4px 4px 0;padding:12px 16px}
.dr-end .dr-sit-tag{color:#14613C;font-weight:700;font-size:12.5px}
.dr-end-h.dr-g-h{font-size:22px;color:#14613C;margin:2px 0}
.dr-end p{margin:4px 0 0;font-size:15px;line-height:1.65;color:var(--ink)}
.dr-end p.dr-end-n{font-size:14px;color:#3C3E44}
.dr-end-sec{font-size:17px;font-weight:900;line-height:1.4;margin:14px 0 4px;padding:0;color:var(--ink)}
.dr-end-g{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.dr-doc-t{font-size:16px;font-weight:900;color:var(--ink);line-height:1.4}
.dr-doc-m{font-size:12.5px;color:#4A4C53;margin-top:1px}
.dr-doc-b{font-size:14px;line-height:1.6;color:#2F3036;margin-top:4px}
.st-key-doc_spec{background:#FBF3E8;border-left:4px solid #D9330F}
.dr-cand{padding:2px 0}
.dr-setup-h{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:17px;color:var(--ink)}
.dr-setup-h b{font-weight:900}
.dr-setup-t{font-size:14.5px;line-height:1.65;color:#2F3036;margin-top:4px}
.dr-anchor{scroll-margin-top:70px;height:0}
/* デモ一覧：このデモで分かること（背景より強く見せる）と、共通の説明 */
.dr-take{margin-top:10px;padding:8px 12px;border-left:4px solid #D9330F;background:#FBF3E8}
.dr-take .dr-demo-l{margin-top:0;color:#7A3A00}
.dr-take b{display:block;font-size:16.5px;font-weight:900;line-height:1.5;color:var(--ink)}
.dr-demo-common{display:flex;flex-wrap:wrap;gap:6px 8px;margin:2px 0 10px}
.dr-demo-common span{font-size:13px;font-weight:700;color:#45474D;background:#EFEFF2;border-radius:999px;padding:2px 12px}
/* デモの大きな区分と現在地 */
.dr-ph{display:flex;flex-wrap:wrap;align-items:center;gap:6px 16px;margin:2px 0 6px}
.dr-ph ol{display:flex;gap:4px;list-style:none;margin:0;padding:0}
.dr-ph li{display:flex;align-items:center;gap:6px;font-size:13.5px;font-weight:700;color:#6B6D73;background:#F3F2EF;padding:3px 12px 3px 6px;border-radius:999px;white-space:nowrap}
.dr-ph li b{display:inline-grid;place-items:center;width:20px;height:20px;border-radius:50%;background:#DADBDF;color:#45474D;font-size:12px}
.dr-ph li.done{color:#45474D}
.dr-ph li.on{background:#FBE7DF;color:#8F2408}
.dr-ph li.on b{background:#D9330F;color:#fff}
.dr-ph-now{font-size:14px;color:var(--muted)}
.dr-ph-now span{margin-left:12px}
.dr-g-focus{margin:4px 0 0;font-size:16px;line-height:1.6;color:var(--ink)}
.dr-g-focus b{font-size:13.5px;color:#B8290A;margin-right:10px}
/* デモの冒頭：立場の異なる主張と今回の論点 */
.dr-q{margin-top:6px}
.dr-q-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.dr-q-box{padding:12px 16px;background:#F7F5F1;border-radius:6px}
.dr-q-lab{display:flex;gap:10px;align-items:baseline;font-size:15px;font-weight:900;color:#B8290A;margin-bottom:4px}
.dr-q-lab span{font-size:13px;font-weight:700;color:#4A4C53}
.dr-q-focus{margin-top:10px;padding:10px 16px;border-left:5px solid #D9330F;background:#FBF3E8}
.dr-q-t{font-size:22px;font-weight:900;line-height:1.5;color:var(--ink)}
.st-key-tour_start,.st-key-tour_end_next{gap:10px;flex-wrap:wrap;margin:6px 0}
/* 判断の画面：採用案 → 理由 → 根拠 → 比較 */
.dr-vd section{margin-top:12px}
.dr-vd-win{padding:12px 16px;border-left:5px solid #1C7A4D;background:#F1F9F4}
.dr-vd-t{font-size:24px;font-weight:900;line-height:1.45;color:var(--ink)}
.dr-vd-list{list-style:none;margin:0;padding:0}
.dr-vd-list li,.dr-vd-skip{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px;padding:6px 0;border-bottom:1px solid var(--line)}
.dr-vd-skip{border-bottom:0;opacity:.9}
.dr-key-s{font-size:16px;font-weight:700;line-height:1.6;color:var(--ink)}
.dr-t-h{margin-top:14px}
.dr-t-cmp td:nth-child(3){min-width:16em}
.dr-t-cmp .dr-t-win td{background:#F1F9F4;font-weight:400}
.dr-t-cmp .dr-t-win td:first-child b::after{content:"（採用）";font-size:13px;color:#1C7A4D;margin-left:4px}
/* 判断後の仕様の要約 */
.dr-cs-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}
.dr-cs-grid>div{padding:10px 14px;border-radius:6px;background:#F7F5F1}
.dr-cs-after{background:#F1F9F4 !important;border-left:4px solid #1C7A4D}
.dr-cs-keep{background:#EEF2FA !important;border-left:4px solid #2A5DB0}
.dr-cs-scope{margin-top:8px;font-size:15px;line-height:1.65;color:var(--ink)}
.dr-cs-flow{display:grid;grid-template-columns:1fr 24px 1fr 24px 1fr;align-items:stretch;gap:6px;margin-top:10px}
.dr-cs-step{padding:8px 12px;border:1px solid var(--line);border-radius:6px}
.dr-cs-arrow{display:grid;place-items:center;color:#B8290A;font-weight:900}
.dr-cs-next{margin:6px 0 4px}
/* 終了画面：体験の終了と、案件に残る項目を分ける */
.dr-end-row{display:grid;grid-template-columns:3fr 2fr;gap:10px;margin-top:8px}
.dr-end-box{background:#fff;border:1px solid #D7EBDD;border-radius:4px;padding:8px 12px}
.dr-end-left{border-color:#EBD9BE;background:#FFFBF4}
.dr-end-n{font-size:24px;font-weight:900;color:#8A4B00;line-height:1.3}
/* 次にすること（準備画面と、資料の登録直後） */
.st-key-setup_next,.st-key-src_next{border-left:4px solid #D9330F !important;background:#FFFBF7}
.dr-next{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline;font-size:15px;line-height:1.6;color:var(--ink)}
.dr-next b{font-size:15px;font-weight:900;color:#B8290A}
/* 背景・資料の画面：見出しの下の短い案内、登録する種類、準備画面の補助の操作 */
.dr-brief{font-size:13.5px;line-height:1.6;color:#2F3036;border-left:3px solid #2A5DB0;padding:2px 0 2px 10px;margin:2px 0 4px}
.dr-brief b{color:#1F4A8F;margin-right:10px}
.dr-kind{font-size:13.5px;color:#45474D}
.dr-kind b{display:inline-block;margin-left:8px;padding:1px 10px;border-radius:999px;background:#E8EFFA;color:#1F4A8F;font-weight:800}
.st-key-dr_topnav{gap:8px}
.st-key-setup_resume{padding:4px 2px 0;border-top:1px solid var(--line)}
.dr-resume-t{font-size:13px;line-height:1.65;color:var(--muted)}
.dr-resume-t b{display:block;color:#45474D;font-size:13.5px;margin-bottom:2px}
/* トップで選んだ入口（新規作成か再開か）の欄を強調する。URLの#で判定するため、パスワード確定後も続く */
.st-key-home_new [data-testid="stColumn"]:has(#dr-new-create:target),.st-key-home_new [data-testid="stColumn"]:has(#dr-resume:target){outline:2px solid #D9330F;outline-offset:6px;border-radius:4px;background:#FFF8F3}
.dr-ai-note{border-left:3px solid #2A5DB0;background:#F7F9FC;padding:6px 12px;margin:4px 0}
.dr-ai-t{font-size:14.5px;font-weight:700;line-height:1.6;color:var(--ink)}
button:focus-visible,a:focus-visible{outline:2px solid #2A5DB0;outline-offset:2px}
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
 .dr-g-h{font-size:24px}
 .dr-story{grid-template-columns:1fr}
 .dr-story p,.dr-story li{font-size:17px}
 .stMainBlockContainer:has(.dr-sit){padding-top:3.8rem}
 .dr-key{font-size:19px}
 .dr-dl,.dr-v-grid,.dr-f-3,.dr-f-2,.dr-m-row,.dr-end-g,.dr-sit-row,.dr-help dl{grid-template-columns:1fr;gap:6px}
 .dr-help dl{gap:0}
 .dr-help dd{margin-bottom:4px}
 .dr-sit-row{gap:0;padding-top:4px}
 .dr-t-cards thead{display:none}
 .dr-t-cards,.dr-t-cards tbody,.dr-t-cards tr,.dr-t-cards td{display:block;width:100%}
 .dr-t-cards tr{border:1px solid var(--line);border-radius:4px;margin-bottom:8px;padding:4px 0}
 .dr-t-cards td{border-bottom:none;padding:3px 10px}
 .dr-t-cards td:before{content:attr(data-label);display:block;font-size:12px;font-weight:700;color:#4A4C53}
 .dr-v-mid,.dr-m-arrow{display:none}
}
.stMainBlockContainer{padding-top:1.6rem}
/* 画面先頭へ戻す埋め込み枠は高さを持たせない（有無で本文の位置が動かないように） */
[data-testid="stMain"] .stElementContainer:has(>.stIFrame){position:absolute;height:0;overflow:hidden}
/* デモの案内欄の上端を、サイドバーのロゴの図形の上端（ボタンの上端＋8px）に揃える */
@media (min-width:761px){.stMainBlockContainer:has(.dr-sit-demo),.stMainBlockContainer:has(.dr-end){padding-top:calc(1mm + 1cm + 8px)}}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"]{padding-top:calc(1mm + 1cm)}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{gap:.12rem}
[data-testid="stSidebar"] .stCaption{margin-top:.55rem}
[data-testid="stSidebar"] .stButton button{justify-content:flex-start;text-align:left;border:none;background:transparent;color:#F5F5F7;padding:2px 10px;min-height:30px}
[data-testid="stSidebar"] .stButton button>div{justify-content:flex-start;width:100%}
[data-testid="stSidebar"] .stButton button p{text-align:left;font-size:13.5px}
[data-testid="stSidebar"] .stButton button:hover{background:#26262B;color:#fff}
[data-testid="stSidebar"] .stButton button[kind="primary"]{background:#fff;color:#161618}
[data-testid="stSidebar"] .stButton button[kind="primary"] p{font-weight:700;color:#161618}
/* サイドバーのロゴ（トップへのリンク） */
[data-testid="stSidebarHeader"]{position:absolute;top:0;right:0;z-index:2;width:auto;height:auto;min-height:0;padding:calc(6px + 1mm + 1cm) 12px 0}
[data-testid="stSidebar"] .st-key-nav_logo button{background:url("__MARK_DARK__") 8px center/24px 24px no-repeat transparent;padding:2px 10px 2px 42px;min-height:40px}
[data-testid="stSidebar"] .st-key-nav_logo button:hover,[data-testid="stSidebar"] .st-key-nav_logo button:focus,[data-testid="stSidebar"] .st-key-nav_logo button:active{background:url("__MARK_DARK__") 8px center/24px 24px no-repeat #26262B}
[data-testid="stSidebar"] .st-key-nav_logo button p{font-size:17px;font-weight:900;color:#fff;letter-spacing:.01em}
[data-testid="stSidebar"] .st-key-nav_logo{margin-bottom:8px}
/* 作業のメニュー：上位は太字、選んだ作業の機能は字下げする */
[data-testid="stSidebar"] [class*="st-key-nav_group_"] button p{font-weight:700;font-size:14px}
[data-testid="stSidebar"] [class*="st-key-nav_sub_"]{padding-left:12px;margin-bottom:4px}
[data-testid="stSidebar"] [class*="st-key-nav_sub_"] button p{font-size:13.5px}
[data-testid="stSidebar"] [data-testid="stExpander"] details{border-color:#3A3A40}
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
