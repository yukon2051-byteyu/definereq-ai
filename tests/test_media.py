"""録画：検証、音声の取り出し、区間指定、再利用、話者。外部APIは使わない。"""
import wave
from fractions import Fraction

import av
import numpy as np
import pytest

from definereq import config
from definereq.ingest.safety import IngestError
from definereq.media import probe, transcribe as tr

VIDEO = str(config.DEMO_FILES / "d3_拠点ネットワーク定例.mp4")


def test_validate_real_video():
    info = probe.validate("x.mp4", VIDEO)
    assert info.has_audio and info.audio_codec == "aac" and 50 < info.duration < 90


def test_rejects_video_without_audio(tmp_path):
    path = str(tmp_path / "v.mp4")
    with av.open(path, "w") as c:
        s = c.add_stream("libx264", rate=2)
        s.width, s.height, s.pix_fmt = 64, 64, "yuv420p"
        for i in range(4):
            fr = av.VideoFrame.from_ndarray(np.zeros((64, 64, 3), dtype=np.uint8), format="rgb24")
            fr.pts, fr.time_base = i, Fraction(1, 2)
            for pkt in s.encode(fr):
                c.mux(pkt)
        for pkt in s.encode():
            c.mux(pkt)
    with pytest.raises(IngestError, match="音声が含まれていません"):
        probe.validate("v.mp4", path)


def test_rejects_broken_and_wrong_ext(tmp_path):
    bad = tmp_path / "b.mp4"
    bad.write_bytes(b"garbage")
    with pytest.raises(IngestError):
        probe.validate("b.mp4", str(bad))
    with pytest.raises(IngestError, match="未対応"):
        probe.validate("b.avi", str(bad))


def test_extract_range_offset_and_cleanup():
    chunks = probe.extract_wav(VIDEO, 10.0, 20.0)
    path, offset = chunks[0]
    with wave.open(path, "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1
        assert 9.0 < w.getnframes() / 16000 < 11.5
    assert 9.0 < offset < 11.0
    probe.cleanup(chunks)
    import os

    assert not os.path.exists(path)


def test_chunking_keeps_time_offsets(monkeypatch):
    monkeypatch.setattr(config, "CHUNK_SECONDS", 20)
    chunks = probe.extract_wav(VIDEO, 0.0, 50.0)
    assert len(chunks) == 3
    assert chunks[1][1] == pytest.approx(chunks[0][1] + 20, abs=0.5)
    probe.cleanup(chunks)


def test_run_with_fake_backend_adds_offset(monkeypatch):
    monkeypatch.setitem(tr.BACKENDS, "fake", lambda wav, off: [{"start": off + 1, "end": off + 2, "speaker_label": "A", "text": "発言"}])
    segs = tr.run(VIDEO, "fake", 10.0, 15.0)
    assert 10.5 < segs[0]["start"] < 12.5


def test_plans_show_cost_destination_before_run():
    plans = tr.plans(10)
    openai = next(p for p in plans if p.method == "openai")
    assert "OpenAI" in openai.destination and openai.est_jpy > 0
    local = next(p for p in plans if p.method == "local")
    assert local.est_jpy == 0 and "外部へ送信しません" in local.destination


def test_openai_parser_handles_diarized_segments(monkeypatch, tmp_path):
    """OpenAI の応答形式の処理（通信は代替）。"""
    import openai

    class Seg:
        start, end, text, speaker = 1.0, 2.0, " こんにちは ", "A"

    class R:
        segments = [Seg()]

    class Fake:
        def __init__(self, **kw):
            self.audio = self
            self.transcriptions = self

        def create(self, **kw):
            self.kw = kw
            return R()

    monkeypatch.setattr(openai, "OpenAI", Fake)
    p = tmp_path / "a.wav"
    p.write_bytes(b"x")
    segs = tr._openai_transcribe(str(p), 100.0)
    assert segs == [{"start": 101.0, "end": 102.0, "speaker_label": "A", "text": "こんにちは"}]


def test_reuse_same_file_and_range(project):
    rec = tr.register_recording(project, "m.mp4", [{"start": 0, "end": 1, "text": "x"}], "local", None, 60, 0, 60, "hash1")
    assert tr.find_reusable(project, "hash1", 10, 20)["id"] == rec["id"]
    assert tr.find_reusable(project, "hash2", 10, 20) is None
    assert tr.find_reusable(project, "hash1", 10, 90) is None


def test_speaker_is_not_auto_confirmed_and_edit_history(project):
    rec = tr.register_recording(project, "m", [{"start": 0, "end": 1, "speaker_label": "SPEAKER_00", "text": "自動の原文"}], "openai", None, 1, 0, 1)
    seg = rec["segments"][0]
    assert seg["speaker"] is None and seg["speaker_status"] == "未確認"
    tr.edit_segment(rec, seg["id"], text="修正文")
    assert seg["text_auto"] == "自動の原文" and seg["text"] == "修正文" and seg["edits"][0]["before"] == "自動の原文"


def test_subtitle_import_is_not_labeled_as_transcription():
    assert "文字起こしではない" in tr.METHOD_LABEL["subtitle"]


def _openai_error(cls, code=None, msg="失敗"):
    import httpx2 as httpx
    import openai

    req = httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions")
    status = {openai.RateLimitError: 429, openai.AuthenticationError: 401, openai.BadRequestError: 400}[cls]
    return cls(msg, response=httpx.Response(status, request=req), body={"code": code, "message": msg})


@pytest.mark.parametrize("name,code,billed,word", [("RateLimitError", "insufficient_quota", False, "残高"), ("RateLimitError", "rate", False, "利用制限"),
                                                   ("AuthenticationError", None, False, "キー"), ("BadRequestError", "bad", False, "受け付けません")])
def test_openai_errors_are_explained(name, code, billed, word):
    import openai

    err = tr._explain_openai(_openai_error(getattr(openai, name), code))
    assert word in str(err) and err.billed is billed


def test_key_is_redacted_from_error():
    import openai

    err = tr._explain_openai(_openai_error(openai.AuthenticationError, None, "Incorrect API key provided: sk-abc123secret"))
    assert "sk-abc123secret" not in str(err)
