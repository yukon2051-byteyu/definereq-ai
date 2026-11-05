"""有料処理の関門。「使ってよいか」を1か所で判断する。

全ての条件が揃わなければ有料処理は実行しない：
AIパスワード・APIキー・利用記録DB・予算。どれかが欠けても無料機能には影響しない。
"""
from __future__ import annotations

import hmac
from dataclasses import dataclass, field

from .. import config
from .ledger import Ledger, open_ledger

# 公式価格（USD / 100万トークン）。2026-10 時点の Anthropic 公式価格
PRICES = {
    "claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50),
}
DEFAULT_PRICE = (4.0, 20.0)


def check_code(code: str) -> bool:
    code = (code or "").strip()
    return bool(code) and any(hmac.compare_digest(code, c) for c in config.access_codes())


@dataclass
class Readiness:
    ai: bool
    transcribe: bool
    reasons: list[str] = field(default_factory=list)
    ledger: Ledger | None = None


def readiness(code: str | None = None) -> Readiness:
    reasons = []
    if not config.access_codes():
        reasons.append("AIパスワードが未設定です（DEFINEREQ_ACCESS_CODES）。")
    elif code is not None and not check_code(code):
        reasons.append("AIパスワードが正しくありません。")
    ledger = open_ledger()
    if ledger is None:
        reasons.append("利用記録に接続できません（USAGE_HF_DATASET と HF_TOKEN、または USAGE_DATABASE_URL）。利用量を確認できないため有料処理を停止しています。")
    ok = not reasons
    ai_ok = ok and config.has_ai_key()
    tr_ok = ok and config.has_transcribe_key()
    if not config.has_ai_key():
        reasons.append("ANTHROPIC_API_KEY が未設定です。AI生成は使えません。")
    if not config.has_transcribe_key():
        reasons.append("OPENAI_API_KEY が未設定です。外部APIの文字起こしは使えません。")
    return Readiness(ai_ok, tr_ok, reasons, ledger)


def estimate_ai_jpy(input_chars: int, max_output_tokens: int, model: str | None = None) -> float:
    """AIの見積（上限側）。日本語は1文字あたり最大約1トークンとして計算する。"""
    price_in, price_out = PRICES.get(model or config.ai_model(), DEFAULT_PRICE)
    usd = input_chars / 1e6 * price_in + max_output_tokens / 1e6 * price_out
    return usd * config.usd_jpy()


def actual_ai_jpy(input_tokens: int, output_tokens: int, model: str | None = None) -> float:
    price_in, price_out = PRICES.get(model or config.ai_model(), DEFAULT_PRICE)
    return (input_tokens / 1e6 * price_in + output_tokens / 1e6 * price_out) * config.usd_jpy()
