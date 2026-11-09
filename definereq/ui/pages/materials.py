"""資料の読込と、録画・発言の確認。"""
from __future__ import annotations

import os
import tempfile

import pandas as pd
import streamlit as st

from ... import config
from ... import project as pj
from ...ingest import registry
from ...logic import continuity
from ...ingest.formats import format_time, parse_subtitles
from ...ingest.safety import IngestError, safe_filename
from ...media import probe as media
from ...media import transcribe as tr
from ...logic.evidence import speaker_view
from ...schema import CONTENT_CONFIRM, SOURCE_KINDS, SPEAKER_CONFIRM, UTTERANCE_KINDS, VISIBILITY
from ...usage import gate
from ...usage.ledger import BudgetExceeded, LedgerUnavailable, Limits
from ...logic.guidance import unanalyzed_minutes
from ..ai_panel import ai_panel, current_code
from ..candidates import board
from ..components import main_type, chips, edit_block, esc, head, meeting_select, ok_rerun, play_at, select_item, touch


MODES = {"議事録を取り込む": "議事録", "その他の資料を取り込む": None}
OTHER_KINDS = [k for k in SOURCE_KINDS if k != "議事録"]


def sources(p: dict) -> None:
    from . import prepare
    from .. import drafts, situation

    demo = p.get("is_demo")
    if not demo:
        pstate = drafts.profile_state(p)
        prepare.top_nav("go_setup_src", ("背景・目的・関係者を入力" if pstate == "未入力" else "背景・目的・関係者を編集", "profile", "go_profile_top"))
    head("資料・議事録", "議事録や資料を、ファイルまたは文章の貼り付けで取り込みます。録画は不要です。" if not demo else
         "議事録はWord・Excel・PDF・テキストのファイル、または文章の貼り付けで取り込めます。録画は不要です。", "資料")
    # 登録前は取り込みに集中できるよう、上部に共通の案内を出さない（詳しい案内は画面の下）
    from ...logic import guidance as gd

    guide = None if demo else gd.assess(p, "sources", st.session_state.get("resumed", False))
    if not demo:
        done = _after_register(p)  # 登録した直後は、結果と次の操作を出し、追加のフォームは閉じる
        # 閉じている間もフォームは描画して見えなくするだけにする。描画しないと、入力途中の文章や選んだファイルが消えるため
        with st.container(key="src_form_hidden" if done else "src_form"):
            _source_import(p)
    _source_list(p)
    if guide:
        situation.details(p, "sources", guide, skip={"setup", "profile", "sources"})


def _source_import(p: dict) -> None:
    """取り込みの入口。先に「議事録」か「その他の資料」かを選び、選んだ種類で登録する。

    ファイルと貼り付けの入力欄は常に同じ名前で置くため、種類や取り込み方法を切り替えても入力は消えない。
    """
    with edit_block("src"), st.container(border=True, key="src_box"):
        # フォームを閉じている間に消えた選択を戻す（続けて同じ種類の資料を追加しやすくする）
        for k in ("src_mode", "src_kind"):
            if k not in st.session_state and st.session_state.get(f"{k}_keep"):
                st.session_state[k] = st.session_state[f"{k}_keep"]
        mode = st.radio("取り込むもの", list(MODES), horizontal=True, key="src_mode")
        if MODES[mode]:
            kind = MODES[mode]
            st.caption("議事録として登録します。「会議の記録を整理」で、AIで整理する会議の記録として扱われます。")
        else:
            kind = st.selectbox("資料の種類", OTHER_KINDS, key="src_kind")
            st.caption("議事録以外の資料として登録します。AIで候補を作るときに、送信する資料として選べます。")
        with st.expander("補足項目（公開範囲・資料の日付・関連付ける会議）　未設定でも登録できます"):
            c1, c2 = st.columns(2)
            vis = c1.selectbox("公開範囲", VISIBILITY, key="src_vis")
            date = c2.text_input("資料の日付（不明なら空欄）", key="src_date")
            meeting = meeting_select(p, "src_mtg")
        tabs = st.tabs(["ファイルから取り込む", "文章を貼り付けて取り込む"])
        st.caption("利用の許可がある資料だけを登録してください。構成資料に認証情報が含まれていないことを確認してください。")
        kind_note = f'<div class="dr-kind">登録する種類<b>{esc(kind)}</b></div>'
        with tabs[0]:
            n = st.session_state.get("src_up_round", 0)  # 登録が終わったら選択を空にする（同じファイルの二重登録を防ぐ）
            files = st.file_uploader("ファイル（PDF / Word / Excel / PowerPoint / テキスト / SRT / VTT）", accept_multiple_files=True,
                                     type=["pdf", "docx", "xlsx", "pptx", "txt", "srt", "vtt"], key=f"src_up_{n}")
            st.html(kind_note)
            if st.button("読み込む", type="primary", disabled=not files, key="src_read"):
                done = 0
                for f in files:
                    try:
                        registry.ingest_bytes(p, f.name, f.getvalue(), kind=kind, visibility=vis, occurred_at=date or None, meeting_id=meeting)
                        done += 1
                    except IngestError as e:
                        st.error(f"{safe_filename(f.name)}：{e}")
                if done:  # 1件以上の登録に成功したときだけ、次の操作を案内する
                    st.session_state["src_up_round"] = n + 1
                    touch(p)
                    _registered(p, kind, done)
        with tabs[1]:
            m = st.session_state.get("paste_round", 0)
            title = st.text_input("貼り付ける文章の名称", key=f"paste_t_{m}")
            text = st.text_area("文章を貼り付ける", key=f"paste_b_{m}")
            st.html(kind_note)
            if st.button("貼り付けた文章を案件内に登録", key="paste_go", type="primary"):  # 表示中のタブの登録ボタンが主操作
                if not (text or "").strip():
                    st.error("貼り付ける文章を入力してください。")
                else:
                    registry.ingest_paste(p, title, text, kind=kind, visibility=vis, occurred_at=date or None, meeting_id=meeting)
                    st.session_state["paste_round"] = m + 1
                    touch(p)
                    _registered(p, kind, 1)


def _registered(p: dict, kind: str, count: int) -> None:
    """登録の成功を記録して再描画する。件数と種類は実際の登録結果を使う。

    表示は、別の画面へ移るか「続けて資料を追加する」を押すまで残す。
    """
    st.session_state["src_mode_keep"] = st.session_state.get("src_mode")
    st.session_state["src_kind_keep"] = st.session_state.get("src_kind")
    st.session_state["src_done"] = {"project": p["id"], "message": f"{kind}{count}件を登録しました", "scroll": True}
    st.rerun()


def _after_register(p: dict) -> bool:
    """登録した直後の表示：成功メッセージと次の主ボタン。追加のフォームは閉じ、「続けて資料を追加する」で開く。"""
    from .prepare import next_block

    done = st.session_state.get("src_done")
    if not done or done["project"] != p["id"]:
        return False
    with st.container(border=True, key="src_done_box"):
        st.success(done["message"])
        next_block(p, "src_next", "次の操作")
        if st.button("続けて資料を追加する", key="src_more"):
            st.session_state.pop("src_done", None)
            st.rerun()
    if done.pop("scroll", False):  # 登録ボタンの位置から下へ隠れないよう、結果の位置へ1回だけ移動する
        st.iframe(f"<script>/*{pj.now_iso()}*/const t=()=>window.parent.document.querySelector('.st-key-src_done_box')?.scrollIntoView({{block:'center'}});t();setTimeout(t,300)</script>", height=1)
    return True


def _source_list(p: dict) -> None:
    st.subheader("取り込んだ資料")
    if not p["sources"]:
        st.caption("取り込んだ資料はまだありません。")
        return
    demo = p.get("is_demo")
    rows = [{"ID": s["id"], "名称": s["name"], "版": f"v{s['version']}", "種類": s["kind"], "日付": s.get("occurred_at") or "未設定",
             "この案件で使った箇所": _usage_short(p, s["id"]), "公開範囲": s["visibility"],
             "会議": continuity.label(p, s.get("meeting_id")), "単位数": len(s["units"]), "警告": len(s["warnings"]), "状態": "旧版" if s.get("superseded_by") else "最新"} for s in p["sources"]]
    cols = ["ID", "名称", "種類", "日付", "この案件で使った箇所", "単位数", "状態"] if demo else ["ID", "名称", "版", "種類", "日付", "公開範囲", "会議", "単位数", "警告", "状態"]
    st.dataframe(pd.DataFrame(rows, columns=cols), hide_index=True, width="stretch")
    if demo and p["recordings"]:  # 録画・字幕は、録画・発言の画面で発言ごとに確認する
        st.markdown("**録画・字幕**")
        for r in p["recordings"]:
            c1, c2 = st.columns([3, 1])
            c1.caption(f"{r['id']} {r['name']}（発言{len(r['segments'])}件／{tr.METHOD_LABEL.get(r['method'], r['method'])}）　使った箇所：{_usage_short(p, r['id'])}")
            if c2.button("録画・発言の画面で見る", key=f"src_rec_{r['id']}"):
                from .. import state
                st.session_state["rec_sel"] = r["id"]
                state.goto("recordings")
    src = select_item(p["sources"], lambda s: f"{s['id']} {s['name']} v{s['version']}", "src_sel", "資料はまだありません。")
    if not src:
        return
    focus = _focus_unit(p, src)
    st.caption(f"出所：{src['origin']}／登録日時：{src['registered_at'][:16].replace('T', ' ')}")
    for w in src["warnings"]:
        st.warning(w)
    if src.get("extra", {}).get("slides"):
        st.markdown("**スライド別の抽出結果**")
        st.dataframe(pd.DataFrame([{"スライド": s["no"], "タイトル": s["title"], "抽出した箇所": s["units"], "発表者ノート": "あり（初期状態は対象外）" if s["has_notes"] else "なし",
                                    "文字以外（未理解）": "、".join(s["not_understood"]) or "なし"} for s in src["extra"]["slides"]]), hide_index=True, width="stretch")
    if demo:
        uses = _usage(p, src["id"])
        st.markdown("**この案件で使った箇所**")
        st.caption("／".join(uses) if uses else "要件・判断・質問の根拠としての引用はありません（資料として登録されています）。")
        _units_readonly(src, focus)
        return
    st.markdown("**抽出した本文**（「対象」を外すとAIへ送信しません）")
    df = pd.DataFrame([{"対象": u.get("target", True), "位置": u["locator"], "本文": u["text"], "_id": u["id"]} for u in src["units"]])
    if df.empty:
        st.info("抽出できた本文はありません。")
    else:
        edited = st.data_editor(df, hide_index=True, width="stretch", disabled=["位置", "本文"], column_config={"_id": None}, key=f"units_{src['id']}")
        if st.button("対象の選択を保存", key=f"save_u_{src['id']}"):
            for row in edited.to_dict("records"):
                registry.set_unit_target(p, src["id"], {row["_id"]}, bool(row["対象"]))
            touch(p)
            ok_rerun("保存しました")
    if p.get("is_demo"):
        st.markdown(f"**人の補足**：{src.get('supplement') or 'なし'}")
    with edit_block("sup"):
        note = st.text_area("人の補足（図の構造など。原文とは別に記録します）", value=src.get("supplement") or "", key=f"sup_{src['id']}")
        if st.button("補足を保存", key=f"sup_b_{src['id']}"):
            src["supplement"] = note or None
            touch(p)
            ok_rerun("保存しました")


def _usage(p: dict, source_id: str) -> list[str]:
    """この資料（または録画）を根拠として引用している要件・判断・質問・候補。"""
    found: list[str] = []
    for col, name, label in (("requirements", "要件", "title"), ("decisions", "判断", "topic"), ("questions", "質問", "text")):
        for item in p[col]:
            if any(e.get("source_id") == source_id for e in item.get("evidence") or []):
                found.append(f"{name} {item['id']}「{str(item[label])[:24]}」")
    return found


def _usage_short(p: dict, source_id: str) -> str:
    uses = _usage(p, source_id)
    kinds: dict[str, int] = {}
    for u in uses:
        kinds[u.split(" ")[0]] = kinds.get(u.split(" ")[0], 0) + 1
    return "、".join(f"{k}{v}件の根拠" for k, v in kinds.items()) or "根拠としての引用なし"


def _focus_unit(p: dict, src: dict) -> str | None:
    """デモの判断などから開いた根拠の箇所。開いた箇所を先頭に示し、本文の一覧でも強調する。"""
    focus = st.session_state.get("ev_focus") or {}
    if focus.get("source_id") != src["id"]:
        return None
    unit = next((u for u in src["units"] if u["id"] == focus.get("unit_id")), None) or         next((u for u in src["units"] if focus.get("quote") and focus["quote"] in u["text"]), None)
    if unit:
        st.html(f'<div class="dr-focus"><div class="dr-v-lab">開いた根拠の箇所：{esc(src["name"])}（{esc(unit["locator"])}）</div>'
                f'<div class="dr-key-s">「{esc(unit["text"])}」</div><div class="dr-meta">{esc(focus.get("note") or "")}</div></div>')
        return unit["id"]
    return None


def _units_readonly(src: dict, focus: str | None) -> None:
    """デモの本文：デモ用の架空の資料から抽出した範囲を、閲覧専用で表示する。"""
    st.markdown("**収録されている本文**")
    st.caption("デモ用に作成した架空の資料から抽出した範囲です。図などの文字以外の内容は含みません。")
    if not src["units"]:
        st.info("この資料から抽出できた本文はありません。この画面では本文を確認できません。")
        return
    rows = "".join(f'<li class="{"on" if u["id"] == focus else ""}"><span class="dr-meta">{esc(u["locator"])}</span>{esc(u["text"])}</li>' for u in src["units"])
    st.html(f'<ol class="dr-units">{rows}</ol>')


def _save_upload(up) -> str:
    """録画を一時ファイルへ保存する（ランダムな名前）。セッションの終わりに残らないよう、差し替え時に削除する。"""
    media.sweep_old_files()
    ext = os.path.splitext(safe_filename(up.name))[1].lower()
    fd, path = tempfile.mkstemp(prefix="definereq_", suffix=ext)
    with os.fdopen(fd, "wb") as f:
        f.write(up.getbuffer())
    old = st.session_state.get("upload_path")
    if old and os.path.exists(old):
        os.remove(old)
    st.session_state["upload_path"] = path
    st.session_state["upload_id"] = up.file_id
    return path


def _transcribe_ui(p: dict, meeting: str | None) -> None:
    st.markdown("**録画から文字起こしする**")
    st.caption(f"MP4 / WebM / MOV、最大 {config.MAX_MEDIA_MB}MB。許可のある録画だけを使用してください。アップロードしただけでは処理は始まりません。")
    up = st.file_uploader("録画ファイル", type=["mp4", "webm", "mov", "m4a", "mp3", "wav"], key="rec_up")
    if up is None:
        return
    if up.size > config.MAX_MEDIA_MB * 1024 * 1024:
        st.error(f"ファイルが大きすぎます（上限 {config.MAX_MEDIA_MB}MB）。")
        return
    path = st.session_state["upload_path"] if st.session_state.get("upload_id") == up.file_id else _save_upload(up)
    try:
        with st.spinner("録画を確認しています"):
            info = media.validate(safe_filename(up.name), path)
    except IngestError as e:
        st.error(str(e))
        return
    st.success(f"長さ {format_time(info.duration)}／音声 {info.audio_codec}／映像 {info.video_codec or 'なし'}／{info.size_mb:.1f}MB")
    max_min = config.MAX_TRANSCRIBE_MINUTES_PER_RUN * 60
    end_default = min(info.duration, max_min)
    start, end = st.slider("処理する区間（秒）", 0.0, max(info.duration, 1.0), (0.0, end_default), key="rec_range")
    minutes = (end - start) / 60
    if end - start > max_min:
        st.warning(f"1回の処理は {config.MAX_TRANSCRIBE_MINUTES_PER_RUN} 分までです。区間を短くしてください。")
    digest = tr.file_hash(path)
    reuse = tr.find_reusable(p, digest, start, end)
    if reuse:
        st.session_state.setdefault("media_paths", {})[reuse["id"]] = path  # 添付し直した動画で再生できるようにする
        st.info(f"同じ録画・同じ区間の文字起こし {reuse['id']} が登録済みです。再利用できるため、処理は不要です。この動画で再生できます。")
        return
    plans = tr.plans(minutes)
    st.dataframe(pd.DataFrame([{"方式": x.label, "送信先": x.destination, "対象時間": f"{x.minutes:.1f}分", "費用見込み": f"約{x.est_jpy:,.0f}円", "補足": x.note} for x in plans]), hide_index=True, width="stretch")
    choice = st.radio("方式", [x.method for x in plans], format_func=lambda m: next(x.label for x in plans if x.method == m), key="rec_method")
    plan = next(x for x in plans if x.method == choice)
    date = st.text_input("開催日（不明なら空欄）", key="rec_date")
    code = ""
    ready = True
    rd = None
    if choice == "openai":
        code = current_code()
        rd = gate.readiness(code if code else None)
        ready = rd.transcribe and bool(code)
        for r in rd.reasons:
            st.caption(r)
    else:
        ready = tr.local_available()
        if not ready:
            st.caption("このサーバーにはローカル処理の部品（faster-whisper）が入っていません。")
    if st.button("この内容で文字起こしを実行", type=main_type(), disabled=not ready or end - start > max_min, key="rec_go"):
        run_id = None
        try:
            if choice == "openai":
                run_id = rd.ledger.reserve(Limits.from_env(), code, "transcribe", "transcribe", plan.est_jpy, minutes)
            bar = st.progress(0.0, "音声を取り出しています")
            segs = tr.run(path, choice, start, end, lambda r, m: bar.progress(r, m))
            if run_id:
                rd.ledger.settle(run_id, "完了", plan.est_jpy, minutes=minutes)
        except (BudgetExceeded, LedgerUnavailable, IngestError) as e:
            if run_id:
                rd.ledger.settle(run_id, "失敗", 0.0, minutes=0.0, error=str(e))
            st.error(str(e))
            return
        except tr.TranscribeError as e:
            if run_id:  # 課金の可能性がなければ0円で閉じ、あれば予約額のまま残す
                rd.ledger.settle(run_id, "失敗", 0.0 if not e.billed else None, minutes=0.0 if not e.billed else None, error=str(e))
            st.error(str(e))
            return
        except Exception:  # 外部APIの障害など。費用が発生した可能性があるため予約額のまま残す
            if run_id:
                rd.ledger.settle(run_id, "失敗", None, error="文字起こしの失敗")
            st.error("文字起こしに失敗しました。時間をおいて再度お試しください。")
            return
        if not segs:
            st.warning("発言を検出できませんでした。音声を確認してください。")
            return
        rec = tr.register_recording(p, safe_filename(up.name), segs, choice, date or None, info.duration, start, end, digest, meeting_id=meeting)
        st.session_state.setdefault("media_paths", {})[rec["id"]] = path
        touch(p)
        ok_rerun(f"{len(segs)}件の発言を登録しました")


SUBTITLES = (".srt", ".vtt")


def _import_files(p: dict, files: list, visibility: str, date: str | None, meeting: str | None) -> int:
    """議事録と字幕を取り込む。字幕は時刻付きの発言、それ以外は議事録として登録する。"""
    done = 0
    for f in files:
        name = safe_filename(f.name)
        try:
            if name.lower().endswith(SUBTITLES):
                segs = parse_subtitles(f.getvalue().decode("utf-8-sig", errors="replace"))
                if not segs:
                    st.error(f"{name}：字幕の時刻を読み取れませんでした。")
                    continue
                tr.register_recording(p, name, segs, "subtitle", date, segs[-1]["end"], 0, segs[-1]["end"], meeting_id=meeting)
            else:
                registry.ingest_bytes(p, f.name, f.getvalue(), kind="議事録", visibility=visibility, occurred_at=date, meeting_id=meeting)
            done += 1
        except IngestError as e:
            st.error(f"{name}：{e}")
    return done


def minutes_import(p: dict, meeting: str | None, key: str, main: str | None = None) -> None:
    """議事録・字幕の取込み。録画がない会議でも、この欄だけで記録を登録できる。"""
    st.markdown("**議事録・字幕を取り込む**（Word / Excel / PDF / PowerPoint / テキスト / SRT / VTT）")
    st.caption("議事録として登録します。録画は必要ありません。")
    round_no = st.session_state.get(f"{key}_round", 0)  # 取込み後に選択を空にするため、部品の名前を変える
    files = st.file_uploader("議事録のファイル", accept_multiple_files=True, type=["docx", "xlsx", "pdf", "pptx", "txt", "srt", "vtt"], key=f"{key}_files_{round_no}")
    c1, c2 = st.columns(2)
    date = c1.text_input("開催日（不明なら空欄）", key=f"{key}_date")
    visibility = c2.selectbox("公開範囲", VISIBILITY, key=f"{key}_vis")
    kind = main or main_type()  # 記録がまだないときだけ取り込みを主操作にする（呼び出し側が指定）
    # 主操作は1つ：ファイルを選んだらファイルの取り込み、選んでいなければ貼り付けた文章の登録
    file_kind, paste_kind = (kind, "secondary") if files else ("secondary", kind)
    if st.button("ファイルを取り込む", type=file_kind, disabled=not files, key=f"{key}_go"):
        done = _import_files(p, files, visibility, date or None, meeting)
        if done:
            st.session_state[f"{key}_round"] = round_no + 1
            touch(p)
            ok_rerun(f"{done}件読み込みました")
    title = st.text_input("貼り付ける議事録の名称", key=f"{key}_paste_t")
    text = st.text_area("議事録の文章を貼り付ける", key=f"{key}_paste_b")
    if st.button("貼り付けた文章を議事録として登録", key=f"{key}_paste_go", type=paste_kind) and text.strip():
        registry.ingest_paste(p, title, text, kind="議事録", visibility=visibility, occurred_at=date or None, meeting_id=meeting)
        touch(p)
        ok_rerun("登録しました")


def records(p: dict) -> None:
    """会議の記録の整理を1画面で行う。状態に合わせて、主な操作を先頭に置く。

    - 未整理の記録あり：件数と対象名 → AIで整理（対象を確認してから実行）→ 候補 → 追加の取り込み（閉じた状態）
    - 整理済みのみ：候補の確認 → 追加の取り込み（閉じた状態）
    - 記録なし：取り込みを最初に出す
    """
    from ...logic import guidance as gd
    from .. import situation

    demo = p.get("is_demo")
    head("会議の記録を整理", "議事録や録画をAIで整理し、要望・決定事項・未決事項の候補を確認します。録画はなくても進められます。", "記録を取り込む")
    latest = [s for s in p["sources"] if s.get("kind") == "議事録" and not s.get("superseded_by")]
    names = [s["name"] for s in latest] + [r["name"] for r in p["recordings"]]
    waiting = set(gd.unanalyzed_minutes(p))
    pending = gd.requirement_candidates(p)
    tasks = tuple(sorted({r["task"] for r in p["ai_runs"]} - {"prep"}))
    if demo:
        _records_demo(p, names, tasks)
        return
    if waiting:
        wait_src = [s["id"] for s in latest if s["name"] in waiting]
        wait_rec = [r["id"] for r in p["recordings"] if r["name"] in waiting]
        st.html(_status(f"未整理の議事録 {len(waiting)}件", "、".join(sorted(waiting))))
        with st.container(border=True, key="records_run"):
            ai_panel_extract(p, wait_src, wait_rec)
    elif names:
        cs = gd.candidate_status(p)
        if cs["extracted"]:  # AIで整理した後は、件数と「AI候補を確認する」を先頭に出す
            st.html(_status("AI整理完了", f"{cs['text']}（整理済みの記録：{'、'.join(names)}）"))
            if cs["waiting"]:
                if st.button("AI候補を確認する →", key="records_go_cand", type="primary"):
                    from .. import state
                    state.goto("candidates")
            elif cs["adopted"] and st.button("採用した要件を確認する →", key="records_go_reqs", type="primary"):
                from .. import state
                state.goto("requirements")
        else:
            st.html(_status("未整理の議事録 0件", f"整理済みの記録：{'、'.join(names)}"))
    else:
        st.html(_status("会議の記録はまだありません", "議事録のファイルを選ぶか、文章を貼り付けて登録してください。録画がなくても進められます。"))
    meeting = None
    if names:
        if waiting and gd.candidate_status(p)["waiting"]:  # 前回の整理の候補が残っているときは、補助の操作として出す
            if st.button("前回の整理で作成したAI候補を確認する", key="records_go_cand_prev", type="tertiary"):
                from .. import state
                state.goto("candidates")
        if not waiting:
            with st.expander("AIでもう一度整理する（対象を選んで実行）"):
                ai_panel_extract(p, [], [], primary=False)
        with edit_block("records"), st.expander("議事録・録画を追加する"):
            meeting = meeting_select(p, "records_mtg")
            minutes_import(p, meeting, "records", main="secondary")
            st.markdown("**録画から文字起こしする（録画がある場合）**")
            _transcribe_ui(p, meeting)
    else:
        with edit_block("records"), st.container(border=True):
            meeting = meeting_select(p, "records_mtg")
            minutes_import(p, meeting, "records", main="primary")
            with st.expander("録画から文字起こしする（録画がある場合）"):
                _transcribe_ui(p, meeting)
    if st.button("ほかの作業：次回の質問を準備する", key="records_prep", type="tertiary"):
        from .. import state
        state.goto("prep")
    situation.details(p, "records", gd.assess(p, "records", st.session_state.get("resumed", False)), skip={"setup", "records", "prep"})


def _status(title: str, detail: str) -> str:
    return f'<div class="dr-now"><b>{esc(title)}</b><span>{esc(detail)}</span></div>'


def ai_panel_extract(p: dict, src_ids: list[str], rec_ids: list[str], primary: bool = True) -> None:
    from ..ai_panel import extract_runner

    extract_runner(p, src_ids, rec_ids, primary)


def _records_demo(p: dict, names: list[str], tasks: tuple) -> None:
    """デモ：記録と候補を閲覧する（AIは実行しない）。"""
    st.caption("登録済みの記録：" + "、".join(names) if names else "登録済みの記録はまだありません。")
    ai_panel(p, "extract")
    board(p, None, "records_cand", None)


def recordings(p: dict) -> None:
    head("録画・発言", "発言ごとに話者と内容を確認します。AIが話者を確定することはありません。発言を全員の合意として扱いません。", "資料")
    with edit_block("rec"), st.expander("録画・議事録・字幕を追加する", expanded=not p["recordings"]):
        if p.get("is_demo"):
            st.caption("デモでも録画の検証は実行できますが、文字起こしの実行は準備済みの結果を利用します。")
        meeting = meeting_select(p, "rec_mtg")
        _transcribe_ui(p, meeting)
        st.divider()
        minutes_import(p, meeting, "rec")

    rec = select_item(p["recordings"], lambda r: f"{r['id']} {r['name']} v{r['version']}", "rec_sel", "録画はまだありません。")
    if not rec:
        return
    focus = st.session_state.get("ev_focus") or {}
    seg = next((x for x in rec["segments"] if focus.get("source_id") == rec["id"] and (x["id"] == focus.get("unit_id") or (focus.get("quote") and focus["quote"] in x["text"]))), None)
    if seg:  # デモの判断などから開いた発言を先頭に示す
        view = speaker_view(rec, seg)
        st.html(f'<div class="dr-focus"><div class="dr-v-lab">開いた発言：{esc(rec["name"])} {esc(format_time(seg["start"]))}　{esc(view["label"])}：{esc(view["name"])}'
                f'（話者確認：{esc(view["speaker_check"])}・区分：{esc(seg.get("kind") or "未分類")}）</div><div class="dr-key-s">「{esc(seg["text"])}」</div>'
                f'<div class="dr-meta">{esc(focus.get("note") or "")}</div></div>')
        play_at(rec, seg["start"], f"focus_{seg['id']}")
    st.caption(f"会議：{continuity.label(p, rec.get('meeting_id'))}")
    st.caption(f"方式：{tr.METHOD_LABEL.get(rec['method'], rec['method'])}／開催日：{rec.get('meeting_date') or '記録なし'}／長さ：{format_time(rec.get('duration') or 0)}"
               + (f"／{rec['note']}" if rec.get("note") else ""))
    chips(f"話者未確認 {sum(1 for s in rec['segments'] if s['speaker_status'] != '確認済み')}件", f"内容未確認 {sum(1 for s in rec['segments'] if s['content_status'] != '確認済み')}件")
    names = sorted({s["name"] for s in p["stakeholders"]} | {s["speaker"] for s in rec["segments"] if s.get("speaker")})
    df = pd.DataFrame([{"時刻": format_time(s["start"]), "話者ラベル": s.get("speaker_label") or "なし", "話者": s.get("speaker"), "話者の確認": s["speaker_status"],
                        "発言": s["text"], "性質": s.get("kind"), "内容の確認": s["content_status"], "聞き取り不能": s.get("inaudible", False), "対象": s.get("target", True), "_id": s["id"]} for s in rec["segments"]])
    edited = st.data_editor(df, hide_index=True, width="stretch", disabled=["時刻", "話者ラベル"], key=f"seg_{rec['id']}", column_config={
        "_id": None, "話者": st.column_config.SelectboxColumn(options=names), "話者の確認": st.column_config.SelectboxColumn(options=SPEAKER_CONFIRM, required=True),
        "性質": st.column_config.SelectboxColumn(options=UTTERANCE_KINDS), "内容の確認": st.column_config.SelectboxColumn(options=CONTENT_CONFIRM, required=True)})
    if st.button("発言の確認を保存", type=main_type()):
        for row in edited.to_dict("records"):
            seg = tr.edit_segment(rec, row["_id"], text=row["発言"], speaker=row["話者"] or "", speaker_status=row["話者の確認"],
                                  content_status=row["内容の確認"], kind=row["性質"])
            seg["inaudible"], seg["target"] = bool(row["聞き取り不能"]), bool(row["対象"])
        touch(p)
        ok_rerun("保存しました（自動の原文と修正履歴は残ります）")
    with st.expander("全発言を全文で読む"):
        for segment in rec["segments"]:
            view = speaker_view(rec, segment)
            st.markdown(f"**{format_time(segment['start'])} {view['label']}：{view['name']}**（{segment.get('kind') or '未分類'}・話者確認：{view['speaker_check']}・発言内容の確認：{view['content_check']}）")
            st.write(segment["text"])
    if not rec.get("video_file") and rec["id"] not in st.session_state.get("media_paths", {}):
        st.caption("この記録には再生できる動画がありません。")
    seg = st.selectbox("発言を聞き直す", rec["segments"], format_func=lambda s: f"{format_time(s['start'])} {s['text'][:40]}", key="seg_play")
    if seg:
        play_at(rec, seg["start"], f"seg_{seg['id']}")
        with st.expander("自動の原文と修正履歴"):
            st.write(seg["text_auto"])
            for e in seg["edits"]:
                st.caption(f"{e['at'][:16].replace('T', ' ')} {e['by']}：{e['before']} → {e['after']}")
