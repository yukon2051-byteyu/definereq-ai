"""資料の読込と、録画・発言の確認。"""
from __future__ import annotations

import os
import tempfile

import pandas as pd
import streamlit as st

from ... import config
from ... import project as pj
from ...ingest import registry
from ...ingest.formats import format_time, parse_subtitles
from ...ingest.safety import IngestError, safe_filename
from ...media import probe as media
from ...media import transcribe as tr
from ...schema import CONTENT_CONFIRM, SOURCE_KINDS, SPEAKER_CONFIRM, UTTERANCE_KINDS, VISIBILITY
from ...usage import gate
from ...usage.ledger import BudgetExceeded, LedgerUnavailable, Limits
from ..ai_panel import access_code_input
from ..components import chips, head, ok_rerun, play_at, select_item, touch


def sources(p: dict) -> None:
    head("資料", "利用の許可がある資料だけを登録してください。構成資料に認証情報が含まれていないことを確認してください。", "資料")
    with st.expander("資料を追加する", expanded=not p["sources"]):
        c1, c2 = st.columns(2)
        kind = c1.selectbox("資料の種類", SOURCE_KINDS, key="src_kind")
        vis = c2.selectbox("公開範囲", VISIBILITY, key="src_vis")
        date = st.text_input("資料の日付（不明なら空欄）", key="src_date")
        files = st.file_uploader("ファイル（PDF / Word / Excel / PowerPoint / テキスト / SRT / VTT）", accept_multiple_files=True,
                                 type=["pdf", "docx", "xlsx", "pptx", "txt", "srt", "vtt"], key="src_up")
        if st.button("読み込む", type="primary", disabled=not files):
            done = 0
            for f in files:
                try:
                    registry.ingest_bytes(p, f.name, f.getvalue(), kind=kind, visibility=vis, occurred_at=date or None)
                    done += 1
                except IngestError as e:
                    st.error(f"{safe_filename(f.name)}：{e}")
            if done:
                touch(p)
                ok_rerun(f"{done}件読み込みました")
        st.divider()
        title = st.text_input("貼り付ける文章の名称", key="paste_t")
        text = st.text_area("文章を貼り付ける", key="paste_b")
        if st.button("貼り付けた文章を登録") and text.strip():
            registry.ingest_paste(p, title, text, kind=kind, visibility=vis, occurred_at=date or None)
            touch(p)
            ok_rerun("登録しました")

    rows = [{"ID": s["id"], "名称": s["name"], "版": f"v{s['version']}", "種類": s["kind"], "日付": s.get("occurred_at") or "未設定", "公開範囲": s["visibility"],
             "単位数": len(s["units"]), "警告": len(s["warnings"]), "状態": "旧版" if s.get("superseded_by") else "最新"} for s in p["sources"]]
    st.dataframe(pd.DataFrame(rows, columns=["ID", "名称", "版", "種類", "日付", "公開範囲", "単位数", "警告", "状態"]), hide_index=True, width="stretch")
    src = select_item(p["sources"], lambda s: f"{s['id']} {s['name']} v{s['version']}", "src_sel", "資料はまだありません。")
    if not src:
        return
    st.caption(f"出所：{src['origin']}／登録日時：{src['registered_at'][:16].replace('T', ' ')}")
    for w in src["warnings"]:
        st.warning(w)
    if src.get("extra", {}).get("slides"):
        st.markdown("**スライド別の抽出結果**")
        st.dataframe(pd.DataFrame([{"スライド": s["no"], "タイトル": s["title"], "抽出した箇所": s["units"], "発表者ノート": "あり（初期状態は対象外）" if s["has_notes"] else "なし",
                                    "文字以外（未理解）": "、".join(s["not_understood"]) or "なし"} for s in src["extra"]["slides"]]), hide_index=True, width="stretch")
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
    note = st.text_area("人の補足（図の構造など。原文とは別に記録します）", value=src.get("supplement") or "", key=f"sup_{src['id']}")
    if st.button("補足を保存", key=f"sup_b_{src['id']}"):
        src["supplement"] = note or None
        touch(p)
        ok_rerun("保存しました")


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


def _transcribe_ui(p: dict) -> None:
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
        st.info(f"同じ録画・同じ区間の文字起こし {reuse['id']} が登録済みです。再利用できるため、処理は不要です。")
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
        code = access_code_input()
        rd = gate.readiness(code if code else None)
        ready = rd.transcribe and bool(code)
        for r in rd.reasons:
            st.caption(r)
    else:
        ready = tr.local_available()
        if not ready:
            st.caption("このサーバーにはローカル処理の部品（faster-whisper）が入っていません。")
    if st.button("この内容で文字起こしを実行", type="primary", disabled=not ready or end - start > max_min, key="rec_go"):
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
                rd.ledger.settle(run_id, "失敗", 0.0, error=str(e))
            st.error(str(e))
            return
        except tr.TranscribeError as e:
            if run_id:  # 課金の可能性がなければ0円で閉じ、あれば予約額のまま残す
                rd.ledger.settle(run_id, "失敗", 0.0 if not e.billed else None, error=str(e))
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
        rec = tr.register_recording(p, safe_filename(up.name), segs, choice, date or None, info.duration, start, end, digest)
        st.session_state.setdefault("media_paths", {})[rec["id"]] = path
        touch(p)
        ok_rerun(f"{len(segs)}件の発言を登録しました")


def recordings(p: dict) -> None:
    head("録画・発言", "発言ごとに話者と内容を確認します。AIが話者を確定することはありません。発言を全員の合意として扱いません。", "資料")
    with st.expander("録画・字幕を追加する", expanded=not p["recordings"]):
        if p.get("is_demo"):
            st.caption("デモでも録画の検証は実行できますが、文字起こしの実行は準備済みの結果を利用します。")
        _transcribe_ui(p)
        st.divider()
        st.markdown("**字幕・議事録の時刻付きテキストを取り込む**（SRT / VTT）")
        st.caption("この取り込みは録画の文字起こしではありません。方式は「字幕の取込」と記録されます。")
        sub = st.file_uploader("字幕ファイル", type=["srt", "vtt"], key="sub_up")
        name = st.text_input("会議の名称", key="sub_name")
        date = st.text_input("開催日（不明なら空欄）", key="sub_date")
        if sub is not None and st.button("字幕を取り込む"):
            segs = parse_subtitles(sub.getvalue().decode("utf-8-sig", errors="replace"))
            if not segs:
                st.error("字幕の時刻を読み取れませんでした。")
            else:
                dur = segs[-1]["end"]
                tr.register_recording(p, name or safe_filename(sub.name), segs, "subtitle", date or None, dur, 0, dur)
                touch(p)
                ok_rerun("取り込みました")

    rec = select_item(p["recordings"], lambda r: f"{r['id']} {r['name']} v{r['version']}", "rec_sel", "録画はまだありません。")
    if not rec:
        return
    st.caption(f"方式：{tr.METHOD_LABEL.get(rec['method'], rec['method'])}／開催日：{rec.get('meeting_date') or '記録なし'}／長さ：{format_time(rec.get('duration') or 0)}"
               + (f"／{rec['note']}" if rec.get("note") else ""))
    chips(f"話者未確認 {sum(1 for s in rec['segments'] if s['speaker_status'] != '確認済み')}件", f"内容未確認 {sum(1 for s in rec['segments'] if s['content_status'] != '確認済み')}件")
    names = sorted({s["name"] for s in p["stakeholders"]} | {s["speaker"] for s in rec["segments"] if s.get("speaker")})
    df = pd.DataFrame([{"時刻": format_time(s["start"]), "話者ラベル": s.get("speaker_label") or "なし", "話者": s.get("speaker"), "話者の確認": s["speaker_status"],
                        "発言": s["text"], "性質": s.get("kind"), "内容の確認": s["content_status"], "聞き取り不能": s.get("inaudible", False), "対象": s.get("target", True), "_id": s["id"]} for s in rec["segments"]])
    edited = st.data_editor(df, hide_index=True, width="stretch", disabled=["時刻", "話者ラベル"], key=f"seg_{rec['id']}", column_config={
        "_id": None, "話者": st.column_config.SelectboxColumn(options=names), "話者の確認": st.column_config.SelectboxColumn(options=SPEAKER_CONFIRM, required=True),
        "性質": st.column_config.SelectboxColumn(options=UTTERANCE_KINDS), "内容の確認": st.column_config.SelectboxColumn(options=CONTENT_CONFIRM, required=True)})
    if st.button("発言の確認を保存", type="primary"):
        for row in edited.to_dict("records"):
            seg = tr.edit_segment(rec, row["_id"], text=row["発言"], speaker=row["話者"] or "", speaker_status=row["話者の確認"],
                                  content_status=row["内容の確認"], kind=row["性質"])
            seg["inaudible"], seg["target"] = bool(row["聞き取り不能"]), bool(row["対象"])
        touch(p)
        ok_rerun("保存しました（自動の原文と修正履歴は残ります）")
    seg = st.selectbox("発言を聞き直す", rec["segments"], format_func=lambda s: f"{format_time(s['start'])} {s['text'][:40]}", key="seg_play")
    if seg:
        play_at(rec, seg["start"], f"seg_{seg['id']}")
        with st.expander("自動の原文と修正履歴"):
            st.write(seg["text_auto"])
            for e in seg["edits"]:
                st.caption(f"{e['at'][:16].replace('T', ' ')} {e['by']}：{e['before']} → {e['after']}")
