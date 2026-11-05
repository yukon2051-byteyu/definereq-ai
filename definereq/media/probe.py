"""録画の検証と音声の取り出し（PyAV を利用。外部コマンドは実行しない）。

- 拡張子だけを信じず、実際に開いて音声トラックとコーデックを確認する
- 文字起こし用に 16kHz モノラルの WAV へ変換する（10分あたり約19MB）
- 一時ファイルはランダムな名前で作り、呼び出し側が処理後に削除する
"""
from __future__ import annotations

import os
import tempfile
import wave
from dataclasses import dataclass

from .. import config
from ..ingest.safety import IngestError


@dataclass
class MediaInfo:
    duration: float
    has_audio: bool
    audio_codec: str | None
    video_codec: str | None
    size_mb: float
    container: str


def probe(path: str) -> MediaInfo:
    import av

    try:
        with av.open(path) as c:
            audio = next((s for s in c.streams if s.type == "audio"), None)
            video = next((s for s in c.streams if s.type == "video"), None)
            duration = float(c.duration / av.time_base) if c.duration else 0.0
            if not duration:
                for s in c.streams:
                    if s.duration and s.time_base:
                        duration = max(duration, float(s.duration * s.time_base))
            return MediaInfo(duration, audio is not None, audio.codec_context.name if audio else None,
                             video.codec_context.name if video else None,
                             os.path.getsize(path) / 1024 / 1024, c.format.name)
    except av.FFmpegError as e:
        raise IngestError("録画ファイルを開けませんでした（破損、または未対応のコーデックの可能性）。") from e


def validate(filename: str, path: str) -> MediaInfo:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in config.ALLOWED_VIDEO | config.ALLOWED_AUDIO:
        raise IngestError(f"未対応の形式です（{ext}）。MP4 / WebM / MOV に対応しています。")
    info = probe(path)
    if info.size_mb > config.MAX_MEDIA_MB:
        raise IngestError(f"ファイルが大きすぎます（上限 {config.MAX_MEDIA_MB}MB）。")
    if not info.has_audio:
        raise IngestError("音声が含まれていません。音声付きの録画を指定してください。")
    return info


def extract_wav(path: str, start: float = 0.0, end: float | None = None) -> list[tuple[str, float]]:
    """指定区間の音声を WAV に変換し、(ファイル, 録画内の開始秒) のリストを返す。

    外部APIの上限に収まるよう CHUNK_SECONDS ごとに分ける。呼び出し側で削除すること。
    """
    import av
    from av.audio.resampler import AudioResampler

    rate = 16000
    chunks: list[tuple[str, float]] = []
    writer = None
    written = 0
    chunk_limit = config.CHUNK_SECONDS * rate
    tmpdir = tempfile.mkdtemp(prefix="definereq_")

    def open_chunk(offset: float):
        path_out = os.path.join(tmpdir, f"chunk{len(chunks):03d}.wav")
        w = wave.open(path_out, "wb")
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        chunks.append((path_out, offset))
        return w

    try:
        with av.open(path) as c:
            stream = next(s for s in c.streams if s.type == "audio")
            if start > 0:
                c.seek(int(start * av.time_base))
            resampler = AudioResampler(format="s16", layout="mono", rate=rate)
            position = None  # 次に書き込むサンプルの、録画内の位置（秒）
            for frame in c.decode(stream):
                if frame.pts is None:
                    continue
                t = float(frame.pts * frame.time_base)
                if end is not None and t >= end:
                    break
                if t + (frame.samples / (frame.sample_rate or rate)) < start:
                    continue
                for out in resampler.resample(frame):
                    pcm = bytes(out.planes[0])[: out.samples * 2]
                    if position is None:
                        position = max(t, start)
                    if writer is None or written >= chunk_limit:
                        if writer is not None:
                            writer.close()
                        writer = open_chunk(position)
                        written = 0
                    writer.writeframes(pcm)
                    written += out.samples
                    position += out.samples / rate
    except av.FFmpegError as e:
        raise IngestError("音声の取り出しに失敗しました。") from e
    finally:
        if writer is not None:
            writer.close()
    if not chunks:
        raise IngestError("指定区間に音声がありません。")
    return chunks


def sweep_old_files(hours: float = 6.0, directory: str | None = None) -> int:
    """アップロードの一時ファイルを、一定時間後に削除する（再起動しない環境でも残し続けない）。"""
    import glob
    import shutil
    import time

    limit = time.time() - hours * 3600
    removed = 0
    for path in glob.glob(os.path.join(directory or tempfile.gettempdir(), "definereq_*")):
        try:
            if os.path.getmtime(path) < limit:
                shutil.rmtree(path, ignore_errors=True) if os.path.isdir(path) else os.remove(path)
                removed += 1
        except OSError:
            continue
    return removed


def cleanup(chunks: list[tuple[str, float]]) -> None:
    dirs = set()
    for path, _ in chunks:
        dirs.add(os.path.dirname(path))
        try:
            os.remove(path)
        except OSError:
            pass
    for d in dirs:
        try:
            os.rmdir(d)
        except OSError:
            pass
