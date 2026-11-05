"""3分の案内の画面。

各画面の主題を1つに絞り、内容の関係に合う配置で見せる。
対立は左右比較、変更は前後の並び、判断は採用案を大きく、経緯は時系列、残件は一覧。
原文・ID・資料の位置は開閉式の補足へ置く。
"""
from __future__ import annotations

import streamlit as st

from .. import project as pj
from ..demos import guide
from ..project import display
from . import state
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
    chips = tag(c["kind"]) + chip(f"話者：{c['speaker_status']}", "ok" if c["speaker_status"] == "確認済み" else "warn") + chip(f"内容：{c['content_status']}", "ok" if c["content_status"] == "確認済み" else "warn")
    note = f'<div class="dr-g-body">{esc(c["note"])}</div>' if c.get("note") else ""
    st.html(f'<div class="dr-sp"><div class="dr-meta">{esc(c["who"])}　{esc(c["time"])}</div><div class="dr-key">「{esc(c["text"])}」</div><div class="dr-chips">{chips}</div>{note}</div>')
    rec = pj.get(p, "recordings", c["rec_id"])
    if rec.get("video_file"):
        play_at(rec, c["start"], key)


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
        result = "採用" if r["adopted"] else (r["reason"] or "未判断")
        cls = ' class="dr-t-win"' if r["adopted"] else ""
        rows += f'<tr{cls}><td><b>{esc(r["label"])}</b></td><td>{esc(r["pros"] or "記録なし")}</td><td>{esc(r["cons"] or "記録なし")}</td><td>{esc(result)}</td></tr>'
    st.html(f'{head}<div class="dr-t-wrap"><table class="dr-t"><thead><tr><th>案</th><th>利点</th><th>懸念</th><th>採否</th></tr></thead><tbody>{rows}</tbody></table></div>')


def _flow3(c: dict) -> None:
    cols = "".join(f'<div class="dr-f-col"><div class="dr-v-lab">{esc(x["label"])}</div><div class="dr-f-text">{esc(x["text"])}</div><div class="dr-chips">{tag(x["chip"])}</div></div>' for x in c["cols"])
    st.html(f'<div class="dr-f dr-f-{len(c["cols"])}">{cols}</div>')


def _conflict(c: dict) -> None:
    rows = "".join(f'<div class="dr-c-row"><div class="dr-v-lab">{esc(a)}</div><div class="dr-g-sub">{esc(b)}</div><div class="dr-chips">{tag(str(t))}</div></div>' for a, b, t in c["rows"])
    st.html(f'<div class="dr-c">{rows}</div>')


def _convert(c: dict) -> None:
    rows = ""
    for r in c["rows"]:
        said = f'<div class="dr-g-sub">「{esc(r["said"])}」</div>' if r.get("said") else '<div class="dr-g-sub">発言の記録なし</div>'
        rows += (f'<div class="dr-m-row"><div>{said}</div><div class="dr-m-arrow">→</div><div><div class="dr-v-lab">{esc(r["metric"])}</div><div class="dr-key">{esc(r["value"])}</div>'
                 f'<div class="dr-chips">{tag(r["kind"])}{tag(r["status"])}</div></div></div>')
    st.html(f'<div class="dr-m">{rows}</div>')


def _timeline(c: dict) -> None:
    if not c["rows"]:
        return
    rows = "".join(f'<li><span class="dr-tl-d">{esc(r["date"])}</span><span class="dr-g-sub">{esc(r["event"])}</span>{tag(r["outcome"])}</li>' for r in c["rows"])
    st.html(f'<div class="dr-tl"><div class="dr-v-lab">仕様の変遷</div><ul>{rows}</ul></div>')


def _summary(c: dict) -> None:
    decided = "".join(f"<li>{esc(i)}</li>" for i in c["decided"]) or "<li>なし</li>"
    docs = "".join(f"<li>{esc(i)}</li>" for i in c["docs"]) or "<li>なし</li>"
    todo = "".join(f'<tr><td>{esc(t["text"])}</td><td>{esc(display(t["ask"]))}</td><td>{esc(display(t["due"]))}</td></tr>' for t in c["todo"])
    more = f'<div class="dr-meta">代表例{len(c["todo"])}件／全{c["todo_total"]}件</div>' if c["todo_total"] > len(c["todo"]) else ""
    st.html(f'<div class="dr-win"><div class="dr-v-lab">決まったこと</div><ul class="dr-key-list">{decided}</ul></div>'
            f'<div class="dr-v-lab dr-sp-top">次に確認すること</div><div class="dr-t-wrap"><table class="dr-t"><thead><tr><th>内容</th><th>確認相手</th><th>期限</th></tr></thead><tbody>{todo}</tbody></table></div>{more}'
            f'<div class="dr-v-lab dr-sp-top">共有できる資料</div><ul class="dr-g-list">{docs}</ul>')


RENDER = {"versus": _versus, "decision": _decision, "flow3": _flow3, "conflict": _conflict, "convert": _convert, "timeline": _timeline, "summary": _summary}


def _more(step: dict, ctx: guide.Ctx) -> None:
    for title, lines in step["more"](ctx):
        with st.expander(title):
            for line in lines:
                st.write(line)


def render(p: dict) -> None:
    steps = guide.load(p["demo"]["id"])
    i = min(st.session_state.get("tour_index", 0), len(steps) - 1)
    step = steps[i]
    ctx = guide.Ctx(p)
    count = step["count"](ctx)
    st.html(f'<div class="dr-g-prog"><b>{i + 1}/{len(steps)} {esc(step["process"])}</b>' + (f"<span>{esc(count)}</span>" if count else "") + "</div>"
            f'<h1 class="dr-g-h">{esc(step["title"])}</h1>' + (f'<p class="dr-g-lead">{esc(step["lead"])}</p>' if step.get("lead") else ""))
    for n, block in enumerate(step["main"](ctx)):
        if block["type"] == "speech":
            _speech(p, block, f"guide_{i}_{n}")
        else:
            RENDER[block["type"]](block)
    if step.get("media_note"):
        st.caption(step["media_note"])
    remaining = step["open"](ctx)
    if remaining:
        items = "".join(f"<li>{esc(str(x))}</li>" for x in remaining)
        st.html(f'<div class="dr-open"><div class="dr-v-lab">まだ決まっていないこと</div><ul class="dr-g-list">{items}</ul></div>')
    _more(step, ctx)
    _nav(steps, i, step)


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


def _nav(steps: list[dict], i: int, step: dict) -> None:
    c1, c2, c3 = st.columns([2, 2, 3])
    if i > 0 and c1.button(f"前へ：{steps[i - 1]['short']}", key="tour_prev", width="stretch"):
        jump(steps, i - 1)
    if c2.button("詳細画面を見る", key="tour_detail", type="tertiary", width="stretch"):
        st.session_state["tour_on"] = False
        state.goto(step["page"])
    if i + 1 < len(steps):
        if c3.button(f"次へ：{steps[i + 1]['short']}を見る", key="tour_next", type="primary", width="stretch"):
            jump(steps, i + 1)
    elif c3.button("全画面を閲覧する", key="tour_end", type="primary", width="stretch"):
        st.session_state["tour_on"] = False
        st.rerun()


def jump(steps: list[dict], i: int) -> None:
    st.session_state["tour_index"] = i
    state.set_stage(steps[i]["stage"], steps[i]["page"])


def back_to_guide(p: dict) -> None:
    """全画面の閲覧から、元の工程へ戻る。"""
    steps = guide.load(p["demo"]["id"])
    i = min(st.session_state.get("tour_index", 0), len(steps) - 1)
    st.session_state["tour_on"] = True
    jump(steps, i)
