"""Hugging Face Spaces への反映（公開操作のため、--yes を付けたときだけ実行する）。

使い方：
  python scripts/deploy_hf.py <ユーザー名/スペース名>          … 送るファイルの一覧を表示するだけ
  python scripts/deploy_hf.py <ユーザー名/スペース名> --yes    … 実際に作成・反映する

トークンは環境変数 HF_TOKEN、またはログイン済みの情報（hf auth login）を使う。コードやログに書かない。
"""
from __future__ import annotations

import os
import sys
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IGNORE = [".git/*", ".venv/*", "*__pycache__*", ".pytest_cache/*", "data/*", "tests/*", "scripts/*", "DefineReq_AI.txt", ".env", "*.db"]


def selected() -> list[str]:
    files = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()]
    return [f for f in files if not any(fnmatch(f, g) for g in IGNORE)]


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    repo = sys.argv[1]
    files = selected()
    print(f"送信先：{repo}（{len(files)}ファイル）")
    for f in files:
        print(" ", f)
    if "--yes" not in sys.argv:
        print("確認のみです。実行するには --yes を付けてください。")
        return
    from huggingface_hub import HfApi

    api = HfApi(token=os.environ.get("HF_TOKEN"))  # 未設定ならログイン済みの情報を使う
    api.create_repo(repo, repo_type="space", space_sdk="docker", exist_ok=True)
    api.upload_folder(folder_path=str(ROOT), repo_id=repo, repo_type="space", ignore_patterns=IGNORE, commit_message="DefineReq_AI を反映")
    print(f"反映しました：https://huggingface.co/spaces/{repo}")


if __name__ == "__main__":
    main()
