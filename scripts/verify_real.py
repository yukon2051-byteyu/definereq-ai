"""実物での確認（開発用。有料APIは使わない）。

1. 埋め込みの PostgreSQL で利用記録の並行予約を確認する
2. faster-whisper（ローカル処理）でデモ動画を文字起こしし、時間とメモリを測る

事前に：pip install pgserver faster-whisper psutil
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from definereq import config  # noqa: E402
from definereq.media import transcribe as tr  # noqa: E402
from definereq.usage.ledger import BudgetExceeded, Limits, PostgresLedger  # noqa: E402

result: dict = {}


def check_postgres() -> None:
    import pgserver

    with tempfile.TemporaryDirectory() as td:
        server = pgserver.get_server(td)
        try:
            led = PostgresLedger(server.get_uri())
            limits = Limits(100, 1000, 1000, 1000)
            ok, ng = [], []

            def work(i: int) -> None:
                try:
                    ok.append(led.reserve(limits, f"c{i}", "ai", "t", 30))
                except BudgetExceeded:
                    ng.append(i)

            threads = [threading.Thread(target=work, args=(i,)) for i in range(20)]
            [t.start() for t in threads]
            [t.join() for t in threads]
            led.settle(ok[0], "完了", 10.0, 100, 50)
            led.settle(ok[1], "失敗", None, error="テスト")
            s = led.summary("c0")
            result["postgres"] = {"accepted": len(ok), "rejected": len(ng), "total_jpy": s["all"]["cost_jpy"], "failed": s["all"]["failed"], "pending": s["all"]["pending"]}
            again = PostgresLedger(server.get_uri())
            result["postgres"]["persisted_runs"] = again.summary()["all"]["runs"]
        finally:
            server.cleanup()


def check_transcribe() -> None:
    import psutil

    video = str(config.DEMO_FILES / "d3_拠点ネットワーク定例.mp4")
    start = time.time()
    peak = [0]
    stop = threading.Event()

    def watch() -> None:
        me = psutil.Process()
        while not stop.is_set():
            peak[0] = max(peak[0], me.memory_info().rss)
            time.sleep(0.2)

    t = threading.Thread(target=watch)
    t.start()
    segs = tr.run(video, "local", 0, 62)
    stop.set()
    t.join()
    took = time.time() - start
    result["transcribe"] = {"model": config.env("DEFINEREQ_LOCAL_MODEL", "small"), "seconds": round(took, 1), "video_seconds": 61.5,
                            "peak_rss_mb": round(peak[0] / 1024 / 1024), "segments": len(segs),
                            "sample": [{"start": round(s["start"], 1), "text": s["text"]} for s in segs]}


if __name__ == "__main__":
    for name, fn in (("postgres", check_postgres), ("transcribe", check_transcribe)):
        try:
            fn()
        except Exception as e:  # 片方の失敗でもう片方を止めない
            result[name] = {"error": f"{type(e).__name__}: {e}"}
    out = Path(__file__).resolve().parent.parent / "docs" / "実物確認の結果.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))
