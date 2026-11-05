"""録画の文字起こし。方式を差し替えられるようにしている。

方式
- openai : OpenAI の文字起こしAPI（音声が外部へ送信される。有料）
- local  : faster-whisper（アプリのサーバー内で処理。API料金なし。導入は requirements-local.txt）
- prepared/subtitle : 準備済み・字幕の取込（文字起こしの実行ではない）

※ 字幕の取込を「録画を文字起こしした」と表示しないよう、recording["method"] に方式を記録する。
"""
from __future__ import annotations

import hashlib
import re
import sys
from dataclasses import dataclass
from typing import Callable

from .. import config
from .. import project as pj
from . import probe as probe_mod

# 公式価格（2026-11-05 確認）。docs/費用計画.md と合わせる
OPENAI_USD_PER_MIN = {"gpt-4o-transcribe-diarize": 0.006, "whisper-1": 0.006}
DEFAULT_USD_PER_MIN = 0.006


@dataclass
class Plan:
    method: str
    label: str
    destination: str
    minutes: float
    est_jpy: float
    note: str


def plans(minutes: float) -> list[Plan]:
    """実行前に見せる「方式・送信先・対象時間・費用」の一覧。"""
    out = []
    model = config.transcribe_model()
    rate = OPENAI_USD_PER_MIN.get(model, DEFAULT_USD_PER_MIN)
    out.append(Plan("openai", f"OpenAI（{model}）", "OpenAI のサーバーへ音声を送信", minutes,
                    round(minutes * rate * config.usd_jpy(), 1),
                    "話者ラベルと時刻が付きます。話者ラベルは自動推定のため人の確認が必要です。"
                    + ("" if config.has_transcribe_key() else "（OPENAI_API_KEY が未設定のため現在は実行できません）")))
    available = local_available()
    out.append(Plan("local", "ローカル処理（faster-whisper）", "外部へ送信しません（このサーバー内）", minutes, 0.0,
                    "話者の区別はありません。無料CPUでは録画の長さと同程度以上の時間がかかる見込みです。"
                    + ("" if available else "（このサーバーには未導入です）")))
    return out


def local_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


class TranscribeError(Exception):
    """利用者に理由を見せられる文字起こしのエラー。billed は課金された可能性があるか。"""

    def __init__(self, message: str, billed: bool = True):
        super().__init__(message)
        self.billed = billed


def _redact(text: str) -> str:
    """エラー文にキーが混ざっても画面とログへ出さない。"""
    return re.sub(r"(sk-|Bearer\s+)\S+", "****", str(text))[:200]


def _explain_openai(e: Exception) -> TranscribeError:
    """OpenAI のエラーを、原因が分かる案内に変える。"""
    import openai

    code = getattr(e, "code", None)
    status = getattr(e, "status_code", None)
    detail = f"（{type(e).__name__} {status or ''} {code or ''}：{_redact(getattr(e, 'message', e))}）"
    print(f"文字起こしの失敗 {detail}", file=sys.stderr, flush=True)  # 本文やキーは含まない
    if isinstance(e, openai.AuthenticationError):
        return TranscribeError("OpenAI のAPIキーが無効です。キーを確認してください。" + detail, billed=False)
    if isinstance(e, openai.PermissionDeniedError):
        return TranscribeError("OpenAI のキーにこの機能の権限がありません。" + detail, billed=False)
    if isinstance(e, openai.RateLimitError):
        reason = "OpenAI の残高が不足しています。Billing でクレジットを追加してください。" if code == "insufficient_quota" else "OpenAI の利用制限に達しました。時間をおいて再度お試しください。"
        return TranscribeError(reason + detail, billed=False)
    if isinstance(e, openai.BadRequestError):
        return TranscribeError("OpenAI が要求を受け付けませんでした。" + detail, billed=False)
    if isinstance(e, openai.APIConnectionError):
        return TranscribeError("OpenAI へ接続できませんでした。時間をおいて再度お試しください。" + detail, billed=False)
    return TranscribeError("文字起こしに失敗しました。時間をおいて再度お試しください。" + detail)


def _openai_transcribe(wav_path: str, offset: float) -> list[dict]:
    import openai

    client = openai.OpenAI(max_retries=config.AI_MAX_RETRIES)
    model = config.transcribe_model()
    try:
        with open(wav_path, "rb") as f:
            if "diarize" in model:
                r = client.audio.transcriptions.create(model=model, file=f, response_format="diarized_json",
                                                       chunking_strategy="auto", language="ja")
            else:
                r = client.audio.transcriptions.create(model=model, file=f, response_format="verbose_json",
                                                       timestamp_granularities=["segment"], language="ja")
    except openai.OpenAIError as e:
        raise _explain_openai(e) from e
    segs = []
    for s in getattr(r, "segments", None) or []:
        segs.append({"start": float(s.start) + offset, "end": float(s.end) + offset,
                     "speaker_label": getattr(s, "speaker", None), "text": s.text.strip()})
    return segs


def _local_transcribe(wav_path: str, offset: float) -> list[dict]:
    import wave

    import numpy as np
    from faster_whisper import WhisperModel

    model = WhisperModel(config.env("DEFINEREQ_LOCAL_MODEL", "small"), device="cpu", compute_type="int8")
    with wave.open(wav_path, "rb") as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    segments, _ = model.transcribe(pcm, language="ja", vad_filter=True)
    return [{"start": s.start + offset, "end": s.end + offset, "speaker_label": None, "text": s.text.strip()}
            for s in segments if s.text.strip()]


BACKENDS: dict[str, Callable[[str, float], list[dict]]] = {"openai": _openai_transcribe, "local": _local_transcribe}


def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()[:24]


def find_reusable(p: dict, digest: str, start: float, end: float) -> dict | None:
    """同じ録画・同じ区間の文字起こしがあれば再利用する（費用を二重に払わない）。"""
    for r in p["recordings"]:
        if r.get("file_hash") == digest and r.get("range_start", 0) <= start and r.get("range_end", 0) >= end:
            return r
    return None


def run(path: str, method: str, start: float, end: float,
        on_progress: Callable[[float, str], None] | None = None) -> list[dict]:
    """音声を取り出して文字起こしを実行する。人が実行ボタンを押したときだけ呼ばれる。"""
    backend = BACKENDS[method]
    chunks = probe_mod.extract_wav(path, start, end)
    segs: list[dict] = []
    try:
        for i, (wav, offset) in enumerate(chunks):
            if on_progress:
                on_progress(i / len(chunks), f"{i + 1}/{len(chunks)} 区間目を処理しています")
            segs.extend(backend(wav, offset))
    finally:
        probe_mod.cleanup(chunks)
    if on_progress:
        on_progress(1.0, "完了")
    return segs


def to_segments(raw: list[dict]) -> list[dict]:
    """文字起こし結果を、確認状態つきの発言区間に変換する。話者の氏名は人が確定する。"""
    out = []
    for i, s in enumerate(raw, 1):
        out.append({
            "id": f"S{i:04d}", "start": round(float(s["start"]), 2), "end": round(float(s["end"]), 2),
            "speaker_label": s.get("speaker_label"), "speaker": None, "speaker_status": "未確認",
            "text_auto": s["text"], "text": s["text"], "edits": [], "content_status": "未確認",
            "kind": None, "inaudible": bool(s.get("inaudible")), "target": True,
        })
    return out


def register_recording(p: dict, name: str, raw_segments: list[dict], method: str, meeting_date: str | None,
                       duration: float, range_start: float, range_end: float, digest: str | None = None,
                       source_note: str | None = None) -> dict:
    version = 1 + sum(1 for r in p["recordings"] if r["name"] == name)
    rec = pj.add(p, "recordings", {
        "name": name, "version": version, "meeting_date": meeting_date, "duration": duration,
        "range_start": range_start, "range_end": range_end, "method": method, "file_hash": digest,
        "note": source_note, "segments": to_segments(raw_segments), "visibility": "社内のみ",
        "registered_at": pj.now_iso(),
    })
    pj.log(p, f"録画 {rec['id']}「{name}」の文字起こしを登録しました（{method}）")
    return rec


METHOD_LABEL = {
    "openai": "外部APIで文字起こし", "local": "ローカルで文字起こし",
    "prepared": "準備済みの文字起こし（デモ用）", "subtitle": "会議ツールの字幕を取込（録画の文字起こしではない）",
}


def edit_segment(rec: dict, seg_id: str, text: str | None = None, speaker: str | None = None,
                 speaker_status: str | None = None, content_status: str | None = None,
                 kind: str | None = None, actor: str = "利用者") -> dict:
    """発言の修正。自動の原文は残し、修正履歴を追加する。"""
    seg = next(s for s in rec["segments"] if s["id"] == seg_id)
    if text is not None and text != seg["text"]:
        seg["edits"].append({"at": pj.now_iso(), "by": actor, "before": seg["text"], "after": text})
        seg["text"] = text
    if speaker is not None:
        seg["speaker"] = speaker or None
    if speaker_status is not None:
        seg["speaker_status"] = speaker_status
    if content_status is not None:
        seg["content_status"] = content_status
    if kind is not None:
        seg["kind"] = kind
    return seg
