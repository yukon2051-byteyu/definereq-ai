"""設定（上限値・環境変数・確認観点の読込）。

秘密情報はコードに書かず、環境変数（Hugging Face Spaces では Secrets）から読む。
"""
from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKPOINTS_PATH = ROOT / "config" / "checkpoints.toml"
DEMO_FILES = Path(__file__).resolve().parent / "demos" / "files"

# ---- アップロードの上限（壊れたファイルや巨大ファイルでアプリを止めないため）----
MAX_DOC_MB = 20
MAX_MEDIA_MB = 200
MAX_ZIP_ENTRIES = 3000
MAX_ZIP_UNCOMPRESSED_MB = 200
MAX_ZIP_RATIO = 120          # 圧縮爆弾の検出（展開後/圧縮後の比）
MAX_TEXT_CHARS = 400_000     # 1資料あたりの本文の上限（超えた分は省略と表示）
MAX_PDF_PAGES = 400
MAX_SHEET_ROWS = 20_000

# ---- 録画 ----
ALLOWED_VIDEO = {".mp4", ".webm", ".mov"}
ALLOWED_AUDIO = {".m4a", ".mp3", ".wav"}
MAX_TRANSCRIBE_MINUTES_PER_RUN = 30   # 1回に処理する長さの上限（長い録画は区間指定）
CHUNK_SECONDS = 600                   # 外部APIの上限（25MB）に収まるよう10分ごとに分ける

# ---- AI ----
MAX_AI_INPUT_CHARS = 60_000           # 1回に送る本文の上限
MAX_AI_OUTPUT_TOKENS = 16_000
AI_MAX_RETRIES = 1                    # 再試行の上限（費用が増えすぎないよう小さく）


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def ai_model() -> str:
    return env("DEFINEREQ_AI_MODEL", "claude-opus-5-5")


def transcribe_model() -> str:
    return env("DEFINEREQ_TRANSCRIBE_MODEL", "gpt-4o-transcribe-diarize")


def usd_jpy() -> float:
    """費用計算に使う為替レート（実勢より円安側の値にして、見積を小さくしすぎない）。"""
    return float(env("DEFINEREQ_USD_JPY", "160"))


def monthly_budget_jpy() -> int:
    """アプリが予約できるAPI費用の月額上限。固定費と余裕を除いた額（docs/費用計画.md）。"""
    return int(env("DEFINEREQ_MONTHLY_API_BUDGET_JPY", "7000"))


def per_code_budget_jpy() -> int:
    return int(env("DEFINEREQ_CODE_BUDGET_JPY", "2500"))


def per_code_runs() -> int:
    return int(env("DEFINEREQ_CODE_RUNS", "80"))


def per_code_minutes() -> int:
    return int(env("DEFINEREQ_CODE_MINUTES", "240"))


def access_codes() -> set[str]:
    """AIパスワード（カンマ区切り）。未設定なら有料機能は誰も使えない。"""
    return {c.strip() for c in env("DEFINEREQ_ACCESS_CODES").split(",") if c.strip()}


def has_ai_key() -> bool:
    return bool(env("ANTHROPIC_API_KEY"))


def has_transcribe_key() -> bool:
    return bool(env("OPENAI_API_KEY"))


def usage_db_url() -> str:
    return env("USAGE_DATABASE_URL")


def usage_hf_dataset() -> str:
    """利用記録を置く Hugging Face の非公開データセット（例：user/definereq-usage）。"""
    return env("USAGE_HF_DATASET")


def allow_local_ledger() -> bool:
    """手元の開発でのみ、SQLite ファイルを利用記録に使う（再起動で消える環境では使わない）。"""
    return env("DEFINEREQ_ALLOW_LOCAL_LEDGER") == "1" and not env("SPACE_ID")


def local_ledger_path() -> str:
    return env("DEFINEREQ_LOCAL_LEDGER", str(ROOT / "data" / "usage.db"))


@lru_cache(maxsize=1)
def checkpoints() -> dict:
    with open(CHECKPOINTS_PATH, "rb") as f:
        return tomllib.load(f)
