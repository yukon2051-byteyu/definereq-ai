"""画面の共通部品（見出し・状態表示・根拠・三択の入力）。

利用者の文字を HTML に入れるときは必ず esc() を通す（HTML注入の対策）。
"""
from __future__ import annotations

import html

import streamlit as st

from .. import config
from .. import project as pj
from ..demos.fetch_media import is_pointer
from ..logic import evidence as ev
from ..project import display
from ..schema import NA

esc = html.escape

TONE = {
    "ok": ("#E7F4ED", "#1C7A4D"), "warn": ("#FBF1E0", "#8A4B00"), "bad": ("#FBE9E7", "#B3261E"),
    "info": ("#E8EFFA", "#2A5DB0"), "plain": ("#EFEFF2", "#45474D"),
}
STATUS_TONE = {
    "合意済み": "ok", "確認済み": "ok", "採用": "ok", "修正して採用": "ok", "解消": "ok", "反映済み": "ok", "結論あり": "ok",
    "計測済み": "ok", "回答済み": "ok", "完了": "ok", "対応済み": "ok", "最新": "ok", "矛盾なしと確認": "ok",
    "確認待ち": "warn", "提案": "warn", "判断待ち": "warn", "調査中": "warn", "調整中": "warn", "回答待ち": "warn", "候補": "warn",
    "対応中": "warn", "確認中": "warn", "未計測": "warn", "前提確認が必要な候補": "warn", "保留": "warn",
    "却下": "bad", "明確な矛盾": "bad", "未対応": "bad", "未調整": "bad", "未確認": "bad", "要聞き直し": "bad", "未調査": "bad",
    "下書き": "plain", "廃止": "plain", "取り下げ": "plain", "受付": "info", "未質問": "plain", "未着手": "plain",
    "登録関係": "info", "登録関係からの影響": "info", "AI候補": "info", "AI推測": "info", "今回必須": "info",
}


def chip(text: str, tone: str | None = None) -> str:
    bg, fg = TONE[tone or STATUS_TONE.get(text, "plain")]
    return f'<span class="dr-chip" style="background:{bg};color:{fg}">{esc(str(text))}</span>'


def chips(*texts: str) -> None:
    st.html('<div class="dr-chips">' + "".join(chip(t) for t in texts if t) + "</div>")


def head(title: str, lead: str = "", eyebrow: str = "") -> None:
    st.html(f'<div class="dr-head"><div class="dr-eyebrow">{esc(eyebrow)}</div>'
            f'<h1 class="dr-title">{esc(title)}</h1><p class="dr-lead">{esc(lead)}</p></div>')


def card(title: str, body: str, foot: str = "") -> None:
    st.html(f'<div class="dr-card"><div class="dr-card-t">{esc(title)}</div><div class="dr-card-b">{esc(body)}</div>'
            f'<div class="dr-card-f">{foot}</div></div>')


def flow(steps: list[tuple[str, str]]) -> None:
    """入力→AI候補→人の判断→結果 のつながりを見せる。"""
    cells = "".join(f'<div class="dr-flow-c"><div class="dr-flow-l">{esc(a)}</div><div class="dr-flow-v">{esc(b)}</div></div>'
                    for a, b in steps)
    st.html(f'<div class="dr-flow">{cells}</div>')


def evidence_block(p: dict, e: dict, key: str = "") -> None:
    state = ev.recheck(p, e)
    tag = chip("引用を確認済み", "ok") if state["verified"] else chip("本文で確認できません", "bad")
    if ev.unconfirmed_speech(p, e):
        tag += chip("・".join(ev.unconfirmed_parts(p, e)) + "の確認が未実施", "warn")
    if state.get("stale"):
        tag += chip("新しい版あり", "warn")
    st.html(f'<div class="dr-ev"><div class="dr-ev-q">「{esc(str(e.get("quote")))}」</div>'
            f'<div class="dr-ev-w">{esc(ev.citation(p, e))} {tag}</div></div>')
    if e["source_id"].startswith("REC"):
        rec = pj.get(p, "recordings", e["source_id"])
        seg = next((s for s in (rec or {}).get("segments", []) if s["id"] == e.get("unit_id")), None)
        if rec and seg and key:
            play_at(rec, seg["start"], key)


def play_at(rec: dict, start: float, key: str) -> None:
    """時刻から聞き直す。元動画が手元にない場合は名称と時刻を示す。"""
    path = None
    if rec.get("video_file"):  # デモの動画
        candidate = config.DEMO_FILES / rec["video_file"]
        if candidate.exists() and not is_pointer(candidate):  # 実体のない参照ファイルは再生できない
            path = str(candidate)
    uploaded = st.session_state.get("media_paths", {}).get(rec["id"])
    path = path or uploaded
    at = f"{int(start // 60):02d}:{int(start % 60):02d}"
    if not path:
        st.caption(f"元動画はこの画面にありません。「{rec['name']}」の {at} を確認するか、録画・発言の画面で同じ動画を添付し直してください。")
        return
    opened = st.session_state.get(f"video_{key}", False)
    if st.button("■ 動画を閉じる" if opened else f"▶ {at}から再生", key=f"play_{key}"):
        st.session_state[f"video_{key}"] = not opened
        st.rerun()
    if opened:
        try:
            st.video(path, start_time=int(start), autoplay=True)
            st.caption(f"「{rec['name']}」の {at} から表示しています。再生が始まらないときは、動画の再生ボタンを押してください。")
        except Exception:  # 動画を開けない場合も無反応にしない
            st.warning(f"動画を開けませんでした。「{rec['name']}」の {at} を、元の動画で確認してください。")


def tri_text(label: str, value, key: str, area: bool = False):
    """未設定 / 該当なし / 入力 を区別して入力する。"""
    states = ["未設定", "該当なし", "入力する"]
    cur = 2 if value not in (None, "", NA) else (1 if value == NA else 0)
    c1, c2 = st.columns([1, 3])
    state = c1.selectbox(label, states, index=cur, key=f"{key}_s")
    if state == "未設定":
        return None
    if state == "該当なし":
        return NA
    widget = c2.text_area if area else c2.text_input
    return widget(f"{label}の内容", value="" if value in (None, NA) else str(value), key=f"{key}_t") or None


def save_controls(p: dict, key: str) -> None:
    """案件の保存。ダウンロードの作成日時と、作成後の変更の有無を示す。"""
    from ..export import jsonio
    from . import state

    st.download_button("再開用ファイルをダウンロード", jsonio.dumps(p), file_name=f"{pj.today()}_DefineReq_{p['id']}.json", mime="application/json",
                       key=key, width="stretch", on_click=state.mark_saved, args=(p,))
    made = st.session_state.get("save_time")
    if not state.is_dirty(p):
        st.caption(f"{made[11:16]} に最新の内容でファイルを作成しました。" if made else "読み込んだファイルから変更はありません。")
    elif made:
        st.caption(f"{made[11:16]} にファイルを作成した後、案件に変更があります。")
    else:
        st.caption("案件はブラウザーを閉じると消えます。続きを行うときは、このファイルを手元に保管してください。")


def definition(rows: list[tuple[str, object]]) -> None:
    """閲覧用の定義リスト。"""
    body = "".join(f"<dt>{esc(str(k))}</dt><dd>{esc(display(v))}</dd>" for k, v in rows)
    st.html(f'<dl class="dr-dl">{body}</dl>')


def edit_block(name: str):
    """編集の部品をまとめる入れ物。デモでは表示しない。"""
    return st.container(key=f"edit-{name}")


def add_evidence_form(p: dict, item: dict, key: str) -> None:
    """人が根拠を追加する。引用は本文に実在するかを確認して記録する。"""
    if p.get("is_demo"):
        return
    sources = [(s["id"], s["name"]) for s in p["sources"] if not s.get("superseded_by")] + [(r["id"], r["name"]) for r in p["recordings"]]
    if not sources:
        st.caption("根拠に使う資料や録画がまだありません。")
        return
    with st.form(f"ev_{key}", clear_on_submit=True):
        names = dict(sources)
        src = st.selectbox("根拠の資料", list(names), format_func=names.get)
        quote = st.text_area("引用（資料の文章をそのまま貼り付け）")
        if st.form_submit_button("根拠を追加") and quote.strip():
            e = ev.make(p, src, quote.strip())
            item.setdefault("evidence", []).append(e)
            touch(p)
            ok_rerun("根拠を追加しました" if e["verified"] else "本文で確認できない引用です。確認できない根拠として記録しました")


def meeting_select(p: dict, key: str, value: str | None = None) -> str | None:
    """関連付ける会議を選ぶ。"""
    from ..logic import continuity

    ids = [None, *[m["id"] for m in p["meetings"]]]
    return st.selectbox("関連付ける会議", ids, index=ids.index(value) if value in ids else 0,
                        format_func=lambda i: "関連付けない" if i is None else continuity.label(p, i), key=key)


def people(p: dict) -> list[str]:
    return [s["name"] for s in p["stakeholders"]]


def touch(p: dict) -> None:
    """編集の印。デモでは作業コピーが編集されたことを記録する。"""
    if p.get("demo"):
        p["demo"]["edited"] = True


def ok_rerun(message: str) -> None:
    st.session_state["flash"] = message
    st.rerun()


def show_flash() -> None:
    msg = st.session_state.pop("flash", None)
    if msg:
        st.toast(msg)


def guard(func, *args, **kwargs):
    """業務ロジックの「人に見せる理由つきエラー」を画面に出す。"""
    try:
        return func(*args, **kwargs)
    except (ValueError, PermissionError, KeyError) as e:
        st.error(str(e).strip("'\""))
        return None


def select_item(items: list[dict], label, key: str, placeholder: str = "項目がありません") -> dict | None:
    if not items:
        st.info(placeholder)
        return None
    ids = [i["id"] for i in items]
    chosen = st.selectbox("表示する項目", ids, format_func=lambda x: label(next(i for i in items if i["id"] == x)), key=key)
    return next(i for i in items if i["id"] == chosen)
