"""案内付きデモの画面。

各画面の主題を1つに絞り、内容の関係に合う配置で見せる。
対立は左右比較、変更は前後の並び、判断は採用案を大きく、経緯は時系列で示す。
原文・ID・資料の位置は開閉式の補足へ置く。
最上段の状況案内は、案件の前提と現在の場面を示す（ガイドの何画面目かとは別の情報）。
"""
from __future__ import annotations

import streamlit as st

from .. import project as pj
from ..demos import guide
from ..demos.builder import STAGES
from ..project import display
from . import artifacts, situation, state
from .components import STATUS_TONE, chip, esc, play_at


def tag(text: str) -> str:
    return chip(text, STATUS_TONE.get(text, "plain"))


def _say(side: dict) -> str:
    return f"「{side['text']}」" if side["quoted"] else side["text"]


def _versus(c: dict) -> None:
    def box(side: dict) -> str:
        return f'<div class="dr-v-box"><div class="dr-v-lab">{esc(side["label"])}</div><div class="dr-key">{esc(_say(side))}</div></div>'

    below = ""
    if c.get("below"):
        below = f'<div class="dr-v-below"><div class="dr-v-lab">{esc(c["below"][0])}</div><div class="dr-g-body">{esc(c["below"][1])}</div></div>'
    st.html(f'<div class="dr-v"><div class="dr-v-grid">{box(c["left"])}<div class="dr-v-mid">⇔</div>{box(c["right"])}</div>{below}</div>')


def _speech(p: dict, c: dict, key: str) -> None:
    chips = tag(c["kind"]) + chip(f"話者確認：{c['speaker_check']}", "ok" if c["speaker_check"] == "確認済み" else "warn") \
        + chip(f"発言内容の確認：{c['content_check']}", "ok" if c["content_check"] == "確認済み" else "warn")
    note = f'<div class="dr-g-body">{esc(c["note"])}</div>' if c.get("note") else ""
    st.html(f'<div class="dr-sp"><div class="dr-meta">{esc(c["who_label"])}：{esc(c["who"])}　{esc(c["time"])}</div><div class="dr-key">「{esc(c["text"])}」</div><div class="dr-chips">{chips}</div>{note}</div>')
    rec = pj.get(p, "recordings", c["rec_id"])
    if rec.get("video_file"):
        play_at(rec, c["start"], key)


VERDICT_TONE = {"採用": "ok", "不採用": "bad", "保留": "warn", "未判断": "plain"}


def _decision(c: dict) -> None:
    head = ""
    if c.get("adopted"):
        reason = f'<div class="dr-g-body">{esc(c["rationale"])}</div>' if c.get("rationale") else '<div class="dr-g-body">理由の記録がありません</div>'
        confirm = f'<div class="dr-meta">確認の記録：{esc(c["confirmation"])}</div>' if c.get("confirmation") else ""
        head = (f'<div class="dr-win"><div class="dr-v-lab">採用した案</div><div class="dr-key">{esc(c["adopted"])}</div>{reason}'
                f'<div class="dr-meta">判断者：{esc(c["decider"] or "記録なし")}／確認者：{esc(c["confirmer"] or "記録なし")}／判断日：{esc(c["date"] or "記録なし")}</div>{confirm}</div>')
    else:
        head = (f'<div class="dr-pend"><div class="dr-v-lab">現在の状態</div><div class="dr-key">{esc(c["state"])}：判断は記録されていません</div>'
                f'<div class="dr-meta">判断者（予定）：{esc(c["decider"] or "記録なし")}</div></div>')
    rows = ""
    for r in c["rows"]:
        cls = ' class="dr-t-win"' if r["adopted"] else ""
        reason = "上記の採用理由のとおり" if r["adopted"] else (r["reason"] or ("判断待ち" if r["verdict"] == "未判断" else "記録なし"))
        rows += (f'<tr{cls}><td data-label="案"><b>{esc(r["label"])}</b></td><td data-label="利点">{esc(r["pros"] or "記録なし")}</td><td data-label="懸念">{esc(r["cons"] or "記録なし")}</td>'
                 f'<td data-label="採否">{chip(r["verdict"], VERDICT_TONE[r["verdict"]])}</td><td data-label="理由">{esc(reason)}</td></tr>')
    st.html(f'{head}<div class="dr-t-wrap"><table class="dr-t dr-t-cards"><thead><tr><th>案</th><th>利点</th><th>懸念</th><th>採否</th><th>理由</th></tr></thead><tbody>{rows}</tbody></table></div>')


def _parts(parts: list[tuple]) -> str:
    """差分の表示。色だけでなく「追加」「削除」の文字でも示す。"""
    out = ""
    for kind, text in parts:
        if kind == "add":
            out += f'<ins class="dr-add"><small>追加</small>{esc(text)}</ins>'
        elif kind == "del":
            out += f'<del class="dr-del"><small>削除</small>{esc(text)}</del>'
        else:
            out += esc(text)
    return out


def _flow3(c: dict) -> None:
    cols = "".join(f'<div class="dr-f-col"><div class="dr-v-lab">{esc(x["label"])}</div><div class="dr-f-text">{_parts(x["parts"]) if x.get("parts") else esc(x["text"])}</div><div class="dr-chips">{tag(x["chip"])}</div></div>' for x in c["cols"])
    legend = {"partial": "変更された部分だけを示しています。", "whole": "文章の大部分が変わったため、全体を変更として示しています。"}.get(c.get("mode"))
    note = f'<div class="dr-meta">{esc(legend)}</div>' if legend else ""
    st.html(f'<div class="dr-f dr-f-{len(c["cols"])}">{cols}</div>{note}')


def _conflict(c: dict) -> None:
    rows = "".join(f'<div class="dr-c-row"><div class="dr-v-lab">{esc(a)}</div><div class="dr-g-sub">{esc(b)}</div><div class="dr-chips">{tag(str(t))}</div></div>' for a, b, t in c["rows"])
    st.html(f'<div class="dr-c">{rows}</div>')


def _convert(c: dict) -> None:
    rows = ""
    for r in c["rows"]:
        said = f'<div class="dr-g-sub">「{esc(r["said"])}」</div>' if r.get("said") else '<div class="dr-g-sub">発言の記録なし</div>'
        plain = f'<div class="dr-meta">{esc(r["help"])}</div>' if r.get("help") else ""
        items = [("値の出所", r["origin"]), ("要求値の合意", r["agreement"]), ("達成の検証", r["verify"])]
        state = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in items)
        asked = '<div class="dr-meta">AIは確認用の質問を出しただけで、数値は提示していません。</div>' if r.get("ai_asked") else ""
        rows += (f'<div class="dr-m-row"><div>{said}</div><div class="dr-m-arrow">→</div><div><div class="dr-v-lab">{esc(r["metric"])}</div><div class="dr-key">{esc(r["value"])}</div>{plain}'
                 f'<dl class="dr-state">{state}</dl>{asked}</div></div>')
    st.html(f'<div class="dr-m">{rows}</div>')


def _story(c: dict) -> None:
    """最初の画面の冒頭。立場の異なる2つの主張を横に並べ、その下に今回の論点を出す。"""
    def side(x: dict) -> str:
        return (f'<div class="dr-q-box"><div class="dr-q-lab">{esc(x["label"])}<span>{esc(x["who"])}</span></div>'
                f'<div class="dr-key">{esc(x["text"])}</div><div class="dr-meta">記録：{esc(x["quote"])}</div></div>')
    st.html(f'<div class="dr-q"><div class="dr-q-grid">{"".join(side(x) for x in c["sides"])}</div>'
            f'<div class="dr-q-focus"><div class="dr-v-lab">今回の論点</div><div class="dr-q-t">{esc(c["focus"])}</div></div></div>')


def _story_more(c: dict) -> None:
    """紙・Excelでの運用や、そのほかの関係者などの詳しい背景。必要なときに開く。"""
    with st.expander("案件の詳しい背景（現在の業務・困りごと・関係者）"):
        rows = "".join(f'<section><h2>{esc(label)}</h2><p>{esc(text)}</p></section>' for label, text in c["rows"])
        people = "".join(f"<li><b>{esc(who)}</b><span>{esc(what)}</span></li>" for who, what in c["people"])
        st.html(f'<div class="dr-story"><div>{rows}</div><div><section><h2>関係者が重視すること</h2><ul>{people}</ul></section>'
                f'<section class="dr-story-issue"><h2>検討中の論点</h2><p>{esc(c["issue"])}</p></section>'
                f'<section><h2>このデモで確認すること</h2><p>{esc(c["demo"])}</p></section></div></div>')


def _verdict_top(c: dict) -> None:
    """判断画面の上部：採用した案と理由1文、根拠の短い要約。関係者による判断であることを示す。"""
    who = f'判断者：{esc(c["decider"] or "記録なし")}／確認者：{esc(c["confirmer"] or "記録なし")}／判断日：{esc(c["date"] or "記録なし")}'
    kinds = [b["kind"] for b in c["basis"]]
    parts = []
    if "本人確認済みの記録" in kinds:
        parts.append(f"本人の確認メール（{c['mail_name']}）で判断を確認")
    speech = kinds.count("発言（話者確認済み）")
    if speech:
        parts.append(f"話者確認済みの発言{speech}件を参照")
    summary = "根拠：" + "・".join(parts) if parts else "根拠の記録がありません"
    st.html(f'<div class="dr-vd"><section class="dr-vd-win"><div class="dr-v-lab">採用した案</div><div class="dr-vd-t">{esc(c["adopted"])}を採用</div>'
            f'<div class="dr-g-body">{esc(c["rationale"] or "理由の記録がありません")}</div>'
            f'<div class="dr-chips">{chip("関係者による判断", "ok")}<span class="dr-meta">{who}</span></div>'
            f'<div class="dr-vd-sum">{esc(summary)}</div></section></div>')


def _verdict_basis(c: dict) -> None:
    """根拠の詳細：引用の全文と種類、判断に使っていない（話者未確認の）発言、確認の経緯。"""
    tone = {"本人確認済みの記録": "ok", "発言（話者確認済み）": "info", "資料": "plain"}
    basis = "".join(f'<li>{chip(b["kind"], tone.get(b["kind"], "warn"))}<span class="dr-key-s">「{esc(b["quote"])}」</span><span class="dr-meta">{esc(b["where"])}</span></li>' for b in c["basis"])
    skipped = (f'<div class="dr-vd-skip">{chip("判断に使っていない発言（話者未確認）", "warn")}<span class="dr-key-s">「{esc(c["skipped"]["text"])}」</span>'
               f'<span class="dr-meta">{esc(c["skipped"]["where"])}</span></div>')
    note = f'<div class="dr-meta">{esc(c["confirmation"])}</div>' if c.get("confirmation") else ""
    st.html(f'<div class="dr-vd"><ul class="dr-vd-list">{basis}</ul>{skipped}{note}</div>')


def _options_table(c: dict, heading: str = "") -> None:
    """案の比較。採用した行は「採用」の文字と控えめな背景色で示す。"""
    rows = ""
    for r in c["rows"]:
        cls = ' class="dr-t-win"' if r["adopted"] else ""
        reason = "採用理由のとおり" if r["adopted"] else (r["reason"] or ("判断待ち" if r["verdict"] == "未判断" else "記録なし"))
        rows += (f'<tr{cls}><td data-label="案"><b>{esc(r["label"])}</b></td><td data-label="採否">{chip(r["verdict"], VERDICT_TONE[r["verdict"]])}</td>'
                 f'<td data-label="理由">{esc(reason)}</td><td data-label="利点">{esc(r["pros"] or "記録なし")}</td><td data-label="懸念">{esc(r["cons"] or "記録なし")}</td></tr>')
    title = f'<div class="dr-v-lab dr-t-h">{esc(heading)}</div>' if heading else ""
    st.html(f'{title}<div class="dr-t-wrap"><table class="dr-t dr-t-cards dr-t-cmp"><thead><tr><th>案</th><th>採否</th><th>理由</th><th>利点</th><th>懸念</th></tr></thead><tbody>{rows}</tbody></table></div>')


def _change_sum(c: dict) -> None:
    """判断後の仕様の主役：変更前／変更後／引き続き守る制約の3枚と、採用理由1文。"""
    scope = f'<div class="dr-cs-scope">{esc(c["scope"])}</div>' if c.get("scope") else ""
    cols = [(f"変更前（v{c['before_v']}）", c["before"], "before", ""), (f"変更後（v{c['after_v']}）", c["after"], "after", scope), ("引き続き守る制約", c["keep"], "keep", "")]
    grid = "".join(f'<div class="dr-cs-{k}"><div class="dr-v-lab">{esc(a)}</div><div class="dr-key-s">{esc(b)}</div>{x}</div>' for a, b, k, x in cols)
    reason = f'<div class="dr-cs-why"><b>採用理由</b>{esc(c["rationale"])}</div>' if c.get("rationale") else ""
    st.html(f'<div class="dr-cs"><div class="dr-cs-grid">{grid}</div>{reason}</div>')


def _change_flow(c: dict) -> None:
    """追加要望 → 過去の判断との衝突 → 採用した対応。判断の詳細の中に置く。"""
    flow = [("追加要望", c["request"]), ("過去の判断との衝突", c["clash"]), ("採用した対応", c["adopted"])]
    steps = '<div class="dr-cs-arrow">→</div>'.join(f'<div class="dr-cs-step"><div class="dr-v-lab">{esc(a)}</div><div class="dr-g-sub">{esc(b)}</div></div>' for a, b in flow)
    st.html(f'<div class="dr-cs-flow">{steps}</div>')


def _timeline(c: dict) -> None:
    if not c["rows"]:
        return
    rows = "".join(f'<li><span class="dr-tl-d">{esc(r["date"])}</span><span class="dr-g-sub">{esc(r["event"])}</span>{tag(r["outcome"])}</li>' for r in c["rows"])
    st.html(f'<div class="dr-tl"><div class="dr-v-lab">仕様の変遷</div><ul>{rows}</ul></div>')


RENDER = {"story": _story, "versus": _versus, "decision": _decision, "flow3": _flow3, "conflict": _conflict, "convert": _convert, "timeline": _timeline}


def _more(step: dict, ctx: guide.Ctx) -> None:
    for title, lines in step["more"](ctx):
        with st.expander(title):
            for line in lines:
                st.write(line)


def _finale(p: dict, ctx: guide.Ctx, steps: list[dict], i: int, intro: dict) -> None:
    """最終画面：体験の終了 → 案件に残る項目 → 次の選択肢 → 資料 → 決定と残件。

    体験の終了と、案件に残る未確認の項目は別の情報として並べる（体験が終わっても案件は完了していない）。
    """
    s = ctx.summary()
    total = s["todo_total"]
    shown = 3  # 要約に出す件数
    _phases(p["demo"]["id"], steps, i)
    rest = (f'<div class="dr-end-box dr-end-left"><div class="dr-v-lab">案件に残る未確認の項目</div><div class="dr-end-n">{total}件</div>'
            '<div class="dr-meta">要件定義の完了を示すものではありません。内容は下の「残っていること」で確認できます。</div></div>') if total else            ('<div class="dr-end-box"><div class="dr-v-lab">案件に残る未確認の項目</div><div class="dr-g-sub">登録された内容からは検出されていません。登録されていない論点は検出できません。</div></div>')
    st.html(f'<div class="dr-sit dr-end"><div class="dr-sit-tag">{esc(p["name"])}｜ステップ {i + 1}/{len(steps)}</div><h1 class="dr-g-h dr-end-h">✓ デモ体験はここで終了です</h1>'
            f'<div class="dr-end-row"><div class="dr-end-box"><div class="dr-v-lab">体験したこと</div><div class="dr-g-sub">{esc(intro["done"])}</div></div>{rest}</div></div>')
    # 次の選択肢は、末尾までスクロールしなくても見える位置に置く
    with st.container(key="tour_end_next", horizontal=True):
        if st.button("ほかのデモを見る", key="tour_others"):  # 終了画面の主操作は「要件定義書の内容を見る」
            state.go_home("dr-demo")
        if st.button("この案件の機能画面を詳しく見る", key="tour_end"):
            open_detail("overview")
    recap = "".join(f"<li>{esc(x)}</li>" for x in intro["recap"])
    st.html(f'<h2 class="dr-end-sec">作成されたサンプル資料を見る・ダウンロードする</h2>')
    artifacts.cards(p, spec_note=intro.get("spec_note"))

    st.html(f'<h2 class="dr-end-sec">この体験で確認できたこと</h2><ul class="dr-g-list">{recap}</ul><h2 class="dr-end-sec">決まったことと残っていること</h2>')
    left, right = st.columns(2)

    def todo_line(t: dict) -> str:
        return f"{t['text']}（確認相手：{display(t['ask'])}／期限：{display(t['due'])}）"

    def block(col, title: str, lines: list[str], empty: str, key: str) -> None:
        """要約と全件を同じ一覧から作る。省略があるときだけ、そのことを示す。"""
        n = len(lines)
        head = f'<div class="dr-v-lab">{esc(title)}：全{n}件</div>' if n else f'<div class="dr-v-lab">{esc(title)}</div>'
        body = "".join(f"<li>{esc(x)}</li>" for x in lines[:shown]) if n else ""
        more = f'<div class="dr-meta">主な{shown}件を表示しています。</div>' if n > shown else ""
        col.html(head + (f'{more}<ul class="dr-g-list">{body}</ul>' if n else f'<div class="dr-g-sub">{esc(empty)}</div>'))
        if n > shown:
            with col.expander(f"全{n}件を見る"):
                for x in lines:
                    st.write(f"・{x}")

    block(left, "決まったこと", s["decided"], "合意済みの判断はまだありません。", "decided")
    block(right, "残っていること", [todo_line(t) for t in s["todo"]], "登録された内容から検出された残件はありません。", "todo")

    c3, c4, _ = st.columns([2, 1, 2])
    if c3.button(f"前へ：{steps[i - 1]['process']}", key="tour_prev", type="tertiary"):
        jump(steps, i - 1)
    if c4.button("TOPへ戻る", key="tour_home", type="tertiary"):
        state.go_home()


def _lead(step: dict, ctx: guide.Ctx) -> str:
    lead = step.get("lead")
    text = lead(ctx) if callable(lead) else lead
    return f'<p class="dr-g-lead">{esc(text)}</p>' if text else ""


def _support(step: dict) -> None:
    """この場面でアプリが何を支援したか。AIとプログラムと人を分けて、短く示す。"""
    if step.get("support"):
        rows = "".join(f"<dt>{esc(k)}</dt><dd>{esc(v)}</dd>" for k, v in step["support"])
        st.html(f'<div class="dr-help"><div class="dr-v-lab">アプリの支援</div><dl>{rows}</dl></div>')


def _open(items: list[tuple[str, str]]) -> None:
    """残っている項目を意味ごとの見出しで示す。"""
    if not items:
        return
    groups: dict[str, list[str]] = {}
    for kind, text in items:
        groups.setdefault(kind, []).append(text)
    body = "".join(f'<div class="dr-open-g"><div class="dr-v-lab">{esc(k)}</div><ul class="dr-g-list">{"".join(f"<li>{esc(x)}</li>" for x in v)}</ul></div>' for k, v in groups.items())
    st.html(f'<div class="dr-open">{body}</div>')


def render(p: dict) -> None:
    demo_id = p["demo"]["id"]
    steps = guide.load(demo_id)
    i = min(st.session_state.get("tour_index", 0), len(steps) - 1)
    step = steps[i]
    ctx = guide.Ctx(p)
    intro = guide.INTRO[demo_id]
    if step.get("finale"):  # 最終画面は体験の終了を最上段に示す
        st.session_state.setdefault("demo_done", set()).add(demo_id)
        _finale(p, ctx, steps, i, intro)
        return
    point = step["check"](ctx) if callable(step["check"]) else step["check"]
    situation.demo_banner(p["name"], intro, step, i == 0, step["date"](ctx) if step.get("date") else None, point, ctx.background())
    _phases(demo_id, steps, i)
    st.html(f'<h1 class="dr-g-h">{esc(step["title"])}</h1>' + _focus(demo_id, i) + _lead(step, ctx))
    if step["page"] in RECORD_PAGES:  # 記録の取り込み・整理のステップ：使った資料名と、登録内容を開く入口
        _used_materials(p)
    blocks = step["main"](ctx)
    inline = blocks[0]["type"] in ("story", "verdict", "change_sum")  # 「次へ」を本文の途中に1つだけ置く画面
    for n, block in enumerate(blocks):
        if block["type"] == "speech":
            _speech(p, block, f"guide_{i}_{n}")
            if st.button("録画・発言の画面でこの発言を見る", key=f"tour_ev_sp_{n}", type="tertiary"):
                open_detail("recordings", rec_sel=block["rec_id"], ev_focus={"source_id": block["rec_id"], "unit_id": block["seg_id"], "note": "デモのステップから開いた発言です。"})
        elif block["type"] == "story":
            _story(block)
            _start(steps, i, demo_id)  # 論点の直下に、順に見る操作と見どころへの近道を1組だけ出す
            if st.button("登録された背景・目的・関係者を見る", key="tour_profile", type="tertiary"):
                open_detail("profile")
            _story_more(block)
        elif block["type"] == "verdict":
            _verdict(block, step, steps, i)
        elif block["type"] == "change_sum":
            _change_sum(block)
            _next_inline(steps, i)
            with st.expander("判断の詳細を見る（追加要望と過去の判断の衝突、比較表、根拠、仕様の履歴）"):
                _change_flow(block)
                for m, rest in enumerate(blocks[n + 1:]):
                    RENDER[rest["type"]](rest)
                    _evidence_links(rest, f"cs{m}")
            break
        else:
            RENDER[block["type"]](block)
            _evidence_links(block, str(n))
    if step.get("media_note"):
        st.caption(step["media_note"])
    done = step["done"](ctx) if step.get("done") else None
    if done:
        st.caption(done)
    _support(step)
    _open(step["open"](ctx))
    if i == first_after_meeting(steps):  # 会議後の最初の場面で、残った確認事項をこの時点のデータで見せる
        if st.button("会議後に残った確認事項を見る", key="tour_todo_open", type="tertiary"):
            open_detail("overview")
        st.caption(f"開くと「現在の状況」に、この場面と同じ時点（{data_time(step['stage'])}）の残件が表示されます。")
    _more(step, ctx)
    count = step["count"](ctx)
    if count:  # 代表例と全件の数は、詳細の画面へ移るボタンの近くに置く
        st.caption(f"この画面の表示：{count}")
    _nav(steps, i, step, ctx, show_next=not inline)


def _phases(demo_id: str, steps: list[dict], i: int) -> None:
    """本文のデモ用ナビゲーション：現在地（例：ステップ 5/8 · 比較と判断）、ステップ一覧、見どころへの近道。

    前へ・次へは本文の要点の下に置く。サイドバーは工程と機能のメニュー（自分の案件と同じ）。
    """
    with st.container(key="tour_loc", horizontal=True, vertical_alignment="center"):
        st.html(f'<div class="dr-loc">デモステップ {i + 1}/{len(steps)} · {esc(steps[i]["process"])}</div>')
        with st.popover("ステップ一覧"):
            for n, step in enumerate(steps):
                _, phase = guide.phase_of(demo_id, n)
                if st.button(f"{n + 1}. {step['process']}", key=f"tour_go_{n}", type="secondary" if n == i else "tertiary", disabled=n == i):
                    jump(steps, n)
        if st.session_state.get("tour_via_shortcut") == i and st.button("案件の背景から見る", key="tour_from_start", type="tertiary"):
            jump(steps, 0)
    if st.session_state.get("tour_via_shortcut") == i:  # 一覧の近道で途中から開いたときだけ、その場面までの前提を1文で示す
        st.html(f'<p class="dr-premise">{esc(guide.PREMISES[demo_id])}</p>')


def step_page(p: dict) -> str:
    """案内中のステップにひもづく機能の画面。サイドバーで、対応する工程と機能を強調するために使う。"""
    steps = guide.load(p["demo"]["id"])
    return steps[min(st.session_state.get("tour_index", 0), len(steps) - 1)]["page"]


def _next_inline(steps: list[dict], i: int, label: str | None = None) -> None:
    """本文の要点のすぐ下に置く「次へ」。詳細を開いたり最後まで読んだりしなくても押せる。"""
    if st.button(label or next_label(steps, i), key="tour_next", type="primary"):
        jump(steps, i + 1)


RECORD_PAGES = {"sources", "recordings", "records"}  # 「記録の取り込み・整理」の工程の画面


def open_evidence(e: dict, note: str) -> None:
    """根拠の出典を、資料ID・発言IDで該当箇所に直接開く。戻る操作で元のステップへ戻れる。"""
    focus = {"source_id": e["source_id"], "unit_id": e.get("unit_id"), "quote": e.get("quote"), "note": note}
    if e["page"] == "recordings":
        open_detail("recordings", rec_sel=e["source_id"], ev_focus=focus)
    else:
        open_detail("sources", src_sel=e["source_id"], ev_focus=focus)


def _evidence_links(block: dict, key: str) -> None:
    """判断の根拠を開く操作。開く内容が分かる名前にし、「次へ」より控えめにする。"""
    items = (block.get("evidence") or []) if block.get("type") == "decision" else []
    if not items:
        return
    with st.container(horizontal=True, key=f"tour_evl_{key}"):
        for k, e in enumerate(items[:3]):
            if st.button(e["label"], key=f"tour_ev_{key}_{k}", type="tertiary"):
                open_evidence(e, "デモの判断の根拠として開いた箇所です。")


def _used_materials(p: dict) -> None:
    """記録の取り込み・整理のステップ：この時点で登録されている資料と記録の名前、登録内容を開く入口。"""
    names = [s["name"] for s in p["sources"] if not s.get("superseded_by")] + [r["name"] for r in p["recordings"]]
    with st.container(horizontal=True, vertical_alignment="center", key="tour_used"):
        st.caption("使用した資料：" + ("、".join(names) if names else "なし"))
        if st.button("使用した資料・議事録を見る", key="tour_used_open", type="tertiary"):
            open_detail("sources")


def _verdict(c: dict, step: dict, steps: list[dict], i: int) -> None:
    """判断の画面：採用案と理由 → 案の比較 → 次へ。根拠の引用と話者確認の経緯は開閉式にする。"""
    _verdict_top(c)
    # 根拠の出典を、採用案と理由のすぐ下から開く（資料ID・発言IDで該当箇所を開く）
    with st.container(horizontal=True, key="tour_ev_row"):
        mail = next((b for b in c["basis"] if b["kind"] == "本人確認済みの記録"), None)
        if mail and step.get("evidence_button") and st.button(step["evidence_button"], key="tour_evidence", type="tertiary"):
            open_evidence({"source_id": mail["source_id"], "unit_id": mail["unit_id"], "quote": mail["quote"], "page": "sources"}, "この判断の確認に使った記録です。")
        speech = next((b for b in c["basis"] if b["kind"] == "発言（話者確認済み）"), None)
        if speech and st.button("議事録の該当発言を見る", key="tour_ev_speech", type="tertiary"):
            open_evidence({"source_id": speech["source_id"], "unit_id": speech["unit_id"], "quote": speech["quote"], "page": "recordings"}, "この判断の根拠に使った発言（話者確認済み）です。")
    _options_table(c, "3案の比較" if len(c["rows"]) == 3 else "案の比較")
    _next_inline(steps, i)
    with st.expander("判断の根拠と経緯を見る（引用の全文、話者の確認）"):
        _verdict_basis(c)


def _focus(demo_id: str, i: int) -> str:
    """見どころの画面には、途中から入っても話が通じるよう、案件の論点を1文添える。"""
    if guide.SHORTCUTS[demo_id][0] != i:
        return ""
    return f'<p class="dr-g-focus"><b>この案件の論点</b>{esc(guide.STORIES[demo_id]["focus"])}</p>'


def _start(steps: list[dict], i: int, demo_id: str) -> None:
    """最初の画面の進み方。順に見る人と、見どころから入りたい人の両方に対応する。"""
    # 冒頭は順番に進む操作を1つ。見どころへの近道はトップのデモ一覧に置く
    with st.container(key="tour_start", horizontal=True):
        if st.button(next_label(steps, i), key="tour_next", type="primary"):
            jump(steps, i + 1)


def open_detail(page: str, **preset) -> None:
    """機能画面（詳細）を開く。戻り先の画面番号は tour_index に残るため、詳細から元の画面へ戻れる。"""
    for k, v in preset.items():
        st.session_state[k] = v
    st.session_state["tour_on"] = False
    state.goto(page)


def back_label(p: dict) -> str:
    """詳細画面から戻るボタンの名前。実際の戻り先の画面を示す。"""
    steps = guide.load(p["demo"]["id"])
    i = min(st.session_state.get("tour_index", 0), len(steps) - 1)
    return f"← デモステップ {i + 1}/{len(steps)}『{steps[i]['process']}』に戻る"


def _nav(steps: list[dict], i: int, step: dict, ctx: guide.Ctx, show_next: bool = True) -> None:
    """画面下の移動。「次へ」を本文の途中に置いた画面では、ここに同じボタンを重ねて出さない。"""
    c1, c2, c3 = st.columns([2, 2, 3])
    if i > 0 and c1.button(f"前へ：{steps[i - 1]['process']}", key="tour_prev", width="stretch"):
        jump(steps, i - 1)
    # 機能ページを開く補助ボタン。開く内容が分かる名前にし、「次へ」と見分ける（工程番号とステップ番号は対応づけない）
    page_name = st.session_state.get("_page_names", {}).get(step["page"], ("", step["detail"](ctx)))[1]
    # ステップ1（案件の背景）からは、会議後の要件や残件へ直接は飛ばない（背景の確認は本文の補助操作で開ける）
    if i > 0 and c2.button(detail_label(page_name), key="tour_detail", type="tertiary", width="stretch"):
        open_detail(step["page"])
    if show_next and c3.button(next_label(steps, i), key="tour_next", type="primary", width="stretch"):
        jump(steps, i + 1)


def detail_label(page_name: str) -> str:
    """機能ページを開く補助ボタンの名前（例：この案件のAI候補を確認する）。画面名の「の確認」は重ねない。"""
    noun = page_name[:-3] if page_name.endswith("の確認") else page_name
    if noun.endswith("か"):  # 例：「なぜこの仕様か」
        noun = f"「{noun}」"
    return f"この案件の{noun}を確認する"


def first_after_meeting(steps: list[dict]) -> int | None:
    """会議後の時点のデータを使う、最初のステップ（ステップ1は除く）。"""
    return next((n for n, x in enumerate(steps) if n > 0 and x["stage"] == 2 and not x.get("finale")), None)


def data_time(stage: int) -> str:
    """機能画面で表示しているデータの時点の名前（デモ本編のステップとは別）。"""
    return f"{STAGES[stage]}の時点"


def next_label(steps: list[dict], i: int) -> str:
    """「次へ」のボタン名。行き先のステップの正式名（サイドバーと本文の現在地と同じ名前）を使う。"""
    return f"次へ：{steps[i + 1]['process']}"


def jump(steps: list[dict], i: int) -> None:
    st.session_state.pop("ev_focus", None)  # 根拠から開いた箇所の強調は、ステップへ戻ったら消す
    if st.session_state.get("tour_via_shortcut") != i:
        st.session_state.pop("tour_via_shortcut", None)  # 近道で開いたときだけの案内は、別のステップへ移ったら消す
    st.session_state["tour_index"] = i
    state.set_stage(steps[i]["stage"], steps[i]["page"])


def back_to_guide(p: dict) -> None:
    """機能画面から、元の工程へ戻る。"""
    steps = guide.load(p["demo"]["id"])
    i = min(st.session_state.get("tour_index", 0), len(steps) - 1)
    st.session_state["tour_on"] = True
    jump(steps, i)
