"""3分の案内の画面。

同じ案件データを使い、代表例だけを順に見せる。全件は「詳細画面を見る」から確認する。
表示の順序：工程と見出し → ここに注目 → 分かること・残る確認事項 → 原文 → 前後の移動
"""
from __future__ import annotations

import streamlit as st

from .. import project as pj
from ..demos import builder, guide
from ..schema import DOMAINS
from . import state
from .components import STATUS_TONE, chip, esc, play_at


def tag(text: str) -> str:
    return chip(text, STATUS_TONE.get(text, "plain"))


def _speech(p: dict, c: dict, key: str) -> None:
    chips = tag(c["kind"]) + chip(f"話者：{c['speaker_status']}", "ok" if c["speaker_status"] == "確認済み" else "warn") + chip(f"内容：{c['content_status']}", "ok" if c["content_status"] == "確認済み" else "warn")
    note = f'<div class="dr-g-note">{esc(c["note"])}</div>' if c.get("note") else ""
    cls = "dr-g-card dr-g-hot" if c.get("note") else "dr-g-card"
    st.html(f'<div class="{cls}"><div class="dr-g-meta"><b>{esc(c["who"])}</b>　{esc(c["time"])}</div>'
            f'<div class="dr-g-text">{esc(c["text"])}</div><div class="dr-chips">{chips}</div>{note}</div>')
    rec = pj.get(p, "recordings", c["rec_id"])
    if rec.get("video_file"):
        play_at(rec, c["start"], key)


def _quote(c: dict) -> None:
    title = f'<div class="dr-g-title">{esc(c["title"])}</div>' if c.get("title") else ""
    note = f'<div class="dr-g-note">{esc(c["note"])}</div>' if c.get("note") else ""
    st.html(f'<div class="dr-g-card"><div class="dr-chips">{tag(c["tag"])}</div>{title}<div class="dr-g-q"><span>資料の原文</span>{esc(c["text"])}</div>{note}</div>')


def _options(c: dict) -> None:
    rows = ""
    for r in c["rows"]:
        result = chip("採用", "ok") if r["adopted"] else (esc(r["reason"]) if r["reason"] else chip("未判断", "warn"))
        rows += (f'<div class="dr-g-opt{" dr-g-win" if r["adopted"] else ""}"><div class="dr-g-title">{esc(r["label"])}</div>'
                 f'<div class="dr-g-sm">利点：{esc(r["pros"] or "記録なし")}</div><div class="dr-g-sm">懸念：{esc(r["cons"] or "記録なし")}</div>'
                 f'<div class="dr-g-res">{result}</div></div>')
    if c["state"] == "合意済み":
        foot = f'判断者：{esc(c["decider"] or "記録なし")}／確認者：{esc(c["confirmer"] or "記録なし")}／判断日：{esc(c["date"] or "記録なし")}'
    else:
        foot = f'判断者（予定）：{esc(c["decider"] or "記録なし")}／判断はまだ記録されていません'
    reason = f'<div class="dr-g-text">採用の理由：{esc(c["rationale"])}</div>' if c.get("rationale") else ""
    conf = f'<div class="dr-g-sm">確認の記録：{esc(c["confirmation"])}</div>' if c.get("confirmation") else ""
    st.html(f'<div class="dr-g-card"><div class="dr-g-title">{esc(c["topic"])} {tag(c["state"])}</div><div class="dr-g-opts">{rows}</div>{reason}{conf}<div class="dr-g-sm">{foot}</div></div>')


def _compare(c: dict) -> None:
    rows = "".join(f'<div class="dr-g-row"><div class="dr-g-rl">{esc(a)}</div><div class="dr-g-rv">{esc(str(b))}<div class="dr-chips">{tag(str(t))}</div></div></div>' for a, b, t in c["rows"])
    st.html(f'<div class="dr-g-card">{rows}</div>')


def _measure(c: dict) -> None:
    said = f'<div class="dr-g-q"><span>発言</span>{esc(c["said"])}</div>' if c.get("said") else ""
    st.html(f'<div class="dr-g-card">{said}<div class="dr-g-title">{esc(c["metric"])}：{esc(c["value"])}</div>'
            f'<div class="dr-chips">{tag(c["kind"])}{tag(c["status"])}</div><div class="dr-g-sm">測定条件：{esc(c["condition"])}／根拠：{esc(c["basis"])}</div></div>')


def _summary(c: dict) -> None:
    def block(title: str, items: list[str]) -> str:
        body = "".join(f"<li>{esc(i)}</li>" for i in items) or "<li>なし</li>"
        return f'<div class="dr-g-col"><div class="dr-g-title">{esc(title)}</div><ul>{body}</ul></div>'

    st.html(f'<div class="dr-g-card"><div class="dr-g-text">{esc(c["text"])}</div><div class="dr-g-cols">{block("決まったこと", c["decided"])}'
            f'{block("まだ残っていること", c["remaining"])}{block("共有できる資料", c["docs"])}</div></div>')


def _card(p: dict, c: dict, key: str) -> None:
    kind = c["type"]
    if kind == "speech":
        _speech(p, c, key)
    elif kind == "quote":
        _quote(c)
    elif kind == "options":
        _options(c)
    elif kind == "compare":
        _compare(c)
    elif kind == "measure":
        _measure(c)
    elif kind == "summary":
        _summary(c)
    elif kind == "why":
        label = c["reason"] if c["recorded"] else f"{c['reason']}（AIで補っていません）"
        st.html(f'<div class="dr-g-card"><div class="dr-chips">{chip("登録情報からの回答", "info")}</div><div class="dr-g-title">質問：{esc(c["question"])}</div><div class="dr-g-text">{esc(label)}</div></div>')
    elif kind == "question":
        st.html(f'<div class="dr-g-card"><div class="dr-chips">{tag("質問")}{tag(c["status"])}</div><div class="dr-g-title">{esc(c["text"])}</div><div class="dr-g-sm">理由：{esc(c["why"] or "記録なし")}／確認相手：{esc(c["ask"] or "未設定")}</div></div>')
    elif kind == "ai":
        nums = "、".join(c["numbers"])
        st.html(f'<div class="dr-g-card dr-g-hot"><div class="dr-chips">{chip("準備済みのAI候補", "info")}{tag(c["state"])}</div><div class="dr-g-title">{esc(c["text"])}</div>'
                f'<div class="dr-g-note">ここに注目：資料にない数値（{esc(nums)}）に印が付き、担当者が却下した結果です。</div></div>')
    elif kind == "warn":
        st.html(f'<div class="dr-g-card dr-g-hot"><div class="dr-g-title">{esc(c["title"])}</div><div class="dr-g-sm">{esc(c["text"])}</div><div class="dr-g-sm">人の補足：{esc(c["extra"])}</div></div>')
    elif kind == "risk":
        st.html(f'<div class="dr-g-card"><div class="dr-chips">{tag("リスク")}{tag(c["nature"])}</div><div class="dr-g-title">{esc(c["text"])}</div><div class="dr-g-sm">不確かさ：{esc(c["uncertainty"])}</div></div>')


def _details(cards: list[dict]) -> None:
    where = [c["where"] for c in cards if c.get("where")]
    if not where:
        return
    with st.expander("原文の位置を見る"):
        for w in where:
            st.caption(w)


def _intro(p: dict, step: dict, demo: dict) -> None:
    i = step["intro"]
    st.html(f'<div class="dr-g-card"><div class="dr-g-col2"><div class="dr-g-lab">どんな案件か</div><div class="dr-g-text">{esc(i["who"])}</div></div>'
            f'<div class="dr-g-col2"><div class="dr-g-lab">要望と制約</div><div class="dr-g-text">{esc(i["wants"])}</div></div>'
            f'<div class="dr-g-col2"><div class="dr-g-lab">このデモで確認できること</div><div class="dr-g-text">{esc(i["see"])}</div></div></div>')
    st.caption("分野：" + "、".join(DOMAINS[d] for d in p["domains"]) + "／閲覧専用のデモです。データは全て架空で、AIの結果は準備済みです。")


def _lists(step: dict, ctx: guide.Ctx) -> None:
    remaining = step["remaining"](ctx) if step.get("remaining") else []
    if not step.get("learned") and not remaining:
        return
    items = "".join(f"<li>{esc(str(x))}</li>" for x in remaining) or "<li>この時点で登録された事項はありません</li>"
    st.html(f'<div class="dr-g-cols2"><div class="dr-g-col"><div class="dr-g-lab">この画面で分かること</div><div class="dr-g-text">{esc(step["learned"] or "")}</div></div>'
            f'<div class="dr-g-col"><div class="dr-g-lab">残っている確認事項</div><ul>{items}</ul></div></div>')


def render(p: dict) -> None:
    demo_id = p["demo"]["id"]
    steps = guide.load(demo_id)
    i = min(st.session_state.get("tour_index", 0), len(steps) - 1)
    step = steps[i]
    ctx = guide.Ctx(p)
    head, close = st.columns([5, 1])
    head.html(f'<div class="dr-g-prog"><b>{i + 1}/{len(steps)} {esc(step["process"])}</b><span>{esc(p["name"])}・閲覧専用</span></div>')
    if close.button("案内を閉じる", key="tour_close", width="stretch"):
        st.session_state["tour_on"] = False
        st.rerun()
    st.html(f'<h1 class="dr-g-h">{esc(step["title"])}</h1>' + (f'<p class="dr-g-lead">{esc(step["lead"])}</p>' if step.get("lead") else ""))
    if step.get("intro"):
        _intro(p, step, demo_id)
    else:
        cards = step["focus"](ctx)
        count = step["total"](ctx) if step.get("total") else None
        if step["process"] != "まとめ":
            st.html(f'<div class="dr-g-focus">ここに注目{f"<span>{esc(count)}</span>" if count else ""}</div>')
        for n, c in enumerate(cards):
            _card(p, c, f"guide_{i}_{n}")
        if step.get("media_note"):
            st.caption(step["media_note"])
        _lists(step, ctx)
        _details(cards)
    _nav(steps, i, step)


def _nav(steps: list[dict], i: int, step: dict) -> None:
    c1, c2, c3 = st.columns([1, 1, 1])
    if i > 0 and c1.button(f"前へ：{steps[i - 1]['short']}", key="tour_prev", width="stretch"):
        jump(steps, i - 1)
    if not step.get("intro") and c2.button("関連する全件を見る", key="tour_detail", width="stretch"):
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


__all__ = ["render", "back_to_guide", "builder"]
