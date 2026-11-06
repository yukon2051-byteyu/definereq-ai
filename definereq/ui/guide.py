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
    """最初の画面の背景。カードに分けず、上から順に読める形にする。"""
    rows = "".join(f'<section><h2>{esc(label)}</h2><p>{esc(text)}</p></section>' for label, text in c["rows"])
    people = "".join(f"<li><b>{esc(who)}</b><span>{esc(what)}</span></li>" for who, what in c["people"])
    st.html(f'<div class="dr-story"><div>{rows}</div><div><section><h2>関係者が重視すること</h2><ul>{people}</ul></section>'
            f'<section class="dr-story-issue"><h2>検討中の論点</h2><p>{esc(c["issue"])}</p></section>'
            f'<section><h2>このデモで確認すること</h2><p>{esc(c["demo"])}</p></section></div></div>')


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
    """最終画面：体験の終了 → 確認できたこと → 資料 → 決定と残件 → 次の行動。"""
    s = ctx.summary()
    total = s["todo_total"]
    shown = 3  # 要約に出す件数
    rest = f"デモの体験は終わりましたが、案件には確認が必要な項目が{total}件残っています。要件定義の完了を示すものではありません。" if total else "デモの体験は終わりました。"
    st.html(f'<div class="dr-sit dr-end"><div class="dr-sit-tag">{esc(p["name"])}｜ガイド {i + 1}/{len(steps)}｜現在の場面：{esc(steps[i]["scene"])}</div><h1 class="dr-g-h dr-end-h">✓ デモ体験はここで終了です</h1>'
            f'<p>{esc(intro["done"])}</p><p>以下から、この案件のサンプル資料を確認・ダウンロードできます。</p><p class="dr-end-n">{esc(rest)}</p></div>')
    recap = "".join(f"<li>{esc(x)}</li>" for x in intro["recap"])
    st.html(f'<h2 class="dr-end-sec">この体験で確認できたこと</h2><ul class="dr-g-list">{recap}</ul><h2 class="dr-end-sec">作成されたサンプル資料を見る・ダウンロードする</h2>')
    artifacts.cards(p)

    st.html('<h2 class="dr-end-sec">決まったことと残っていること</h2>')
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

    st.html('<h2 class="dr-end-sec">次に見るもの</h2>')
    c1, c2 = st.columns(2)
    if c1.button("ほかのデモを見る", key="tour_others", type="primary", width="stretch"):
        state.go_home("dr-demo")
    if c2.button("この案件の機能画面を詳しく見る", key="tour_end", width="stretch"):
        st.session_state["tour_on"] = False
        state.goto("overview")
    c3, c4, _ = st.columns([2, 1, 2])
    if c3.button(f"前へ：{steps[i - 1]['short']}", key="tour_prev", type="tertiary"):
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
    count = step["count"](ctx)
    st.html(f'<div class="dr-g-prog"><b>ガイド {i + 1}/{len(steps)}（要点を見る画面）：{esc(step["process"])}</b>' + (f"<span>{esc(count)}</span>" if count else "") + "</div>"
            f'<h1 class="dr-g-h">{esc(step["title"])}</h1>' + _lead(step, ctx))
    for n, block in enumerate(step["main"](ctx)):
        if block["type"] == "speech":
            _speech(p, block, f"guide_{i}_{n}")
        else:
            RENDER[block["type"]](block)
    if step.get("media_note"):
        st.caption(step["media_note"])
    done = step["done"](ctx) if step.get("done") else None
    if done:
        st.caption(done)
    _support(step)
    _open(step["open"](ctx))
    _more(step, ctx)
    _nav(steps, i, step, ctx)


def sidebar(p: dict) -> None:
    """案内中は工程の一覧だけを見せる。全機能のメニューは案内を閉じると表示される。"""
    steps = guide.load(p["demo"]["id"])
    current = min(st.session_state.get("tour_index", 0), len(steps) - 1)
    for n, s in enumerate(steps):
        if st.button(f"{n + 1}. {s['process']}", key=f"tour_go_{n}", type="primary" if n == current else "secondary", width="stretch"):
            jump(steps, n)
    st.divider()
    if st.button("全機能のメニューを見る", key="tour_close", width="stretch"):
        st.session_state["tour_on"] = False
        st.rerun()


def _nav(steps: list[dict], i: int, step: dict, ctx: guide.Ctx) -> None:
    c1, c2, c3 = st.columns([2, 2, 3])
    if i > 0 and c1.button(f"前へ：{steps[i - 1]['short']}", key="tour_prev", width="stretch"):
        jump(steps, i - 1)
    if c2.button(step["detail"](ctx), key="tour_detail", type="tertiary", width="stretch"):
        st.session_state["tour_on"] = False
        state.goto(step["page"])
    if c3.button(f"次へ：{steps[i + 1]['short']}を見る", key="tour_next", type="primary", width="stretch"):
        jump(steps, i + 1)


def jump(steps: list[dict], i: int) -> None:
    st.session_state["tour_index"] = i
    state.set_stage(steps[i]["stage"], steps[i]["page"])


def back_to_guide(p: dict) -> None:
    """機能画面から、元の工程へ戻る。"""
    steps = guide.load(p["demo"]["id"])
    i = min(st.session_state.get("tour_index", 0), len(steps) - 1)
    st.session_state["tour_on"] = True
    jump(steps, i)
