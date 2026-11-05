"""テスト共通の準備。実APIを呼ばないよう、キーを空にして代替応答だけを使う。"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "USAGE_DATABASE_URL", "DEFINEREQ_ACCESS_CODES", "SPACE_ID"):
    os.environ.pop(key, None)

from definereq import project as pj  # noqa: E402
from definereq.ai.client import AIResult  # noqa: E402
from definereq.usage.ledger import SqliteLedger  # noqa: E402


@pytest.fixture
def project():
    return pj.new_project("テスト案件", ["app"])


@pytest.fixture
def ledger(tmp_path):
    return SqliteLedger(str(tmp_path / "usage.db"))


class FakeLLM:
    """Claude の代替。渡された入力を記録し、決まった出力を返す。"""

    def __init__(self, items=None, error=None, tokens=(1000, 500)):
        self.items, self.error, self.tokens = items or [], error, tokens
        self.calls = []

    def complete(self, system, user, schema, max_tokens):
        self.calls.append({"system": system, "user": user})
        if self.error:
            raise self.error
        return AIResult({"items": self.items, "notes": ""}, *self.tokens)


@pytest.fixture
def fake_llm():
    return FakeLLM
