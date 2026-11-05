"""AIの呼び出し部品。ここだけが Claude API を知っている。

テストでは同じ形の代替クラスを渡すため、実APIは呼ばれない。
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from .. import config


class AIError(Exception):
    """利用者に理由を見せられるAIのエラー。billed は課金された可能性があるか。"""

    def __init__(self, message: str, billed: bool = True):
        super().__init__(message)
        self.billed = billed


@dataclass
class AIResult:
    data: dict
    input_tokens: int
    output_tokens: int
    attempts: int = 1


class ClaudeClient:
    """Claude API の呼び出し。出力はJSONスキーマで固定する。"""

    def __init__(self):
        import anthropic

        self._sdk = anthropic
        # 再試行は課金が増えるため上限を小さくする。文字通りの時間制限で待ち続けを防ぐ
        self.client = anthropic.Anthropic(max_retries=config.AI_MAX_RETRIES, timeout=240.0)

    def complete(self, system: str, user: str, schema: dict, max_tokens: int) -> AIResult:
        sdk = self._sdk
        try:
            with self.client.beta.messages.stream(
                model=config.ai_model(),
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                thinking={"type": "adaptive"},
                output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}},
                # 安全判定で断られたときに、別モデルへ自動で切り替える指定
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            ) as stream:
                msg = stream.get_final_message()
        except sdk.AuthenticationError as e:
            raise AIError("APIキーが無効です。管理者に連絡してください。", billed=False) from e
        except sdk.RateLimitError as e:
            raise AIError("混み合っているか利用制限に達しました。時間をおいて再度お試しください。", billed=False) from e
        except sdk.BadRequestError as e:
            raise AIError("AIへの要求が受け付けられませんでした。入力を減らして再度お試しください。", billed=False) from e
        except sdk.APITimeoutError as e:
            raise AIError("AIの応答が時間内に返りませんでした。対象を減らして再度お試しください。") from e
        except sdk.APIStatusError as e:
            raise AIError(f"AIの呼び出しに失敗しました（状態コード {e.status_code}）。") from e
        except sdk.APIConnectionError as e:
            raise AIError("AIへ接続できませんでした。時間をおいて再度お試しください。", billed=False) from e
        if msg.stop_reason == "refusal":
            raise AIError("AIがこの内容の処理を辞退しました。対象を見直してください。")
        if msg.stop_reason == "max_tokens":
            raise AIError("出力が上限に達して途中で終わりました。対象を減らして再度お試しください。")
        text = next((b.text for b in msg.content if b.type == "text"), "")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise AIError("AIの出力を読み取れませんでした。") from e
        return AIResult(data, msg.usage.input_tokens, msg.usage.output_tokens)
