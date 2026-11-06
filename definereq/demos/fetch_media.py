"""公開環境のビルド時に、デモ動画の実体を取得する。

Hugging Face では動画が Git LFS で管理されるため、ビルド先に「参照ファイル」だけが届くことがある。
参照ファイルに書かれたハッシュ値と照合してから置き換える。失敗してもビルドは止めない
（画面では再生できない理由を表示する）。

使い方：python -m definereq.demos.fetch_media
"""
from __future__ import annotations

import hashlib
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

FILES = Path(__file__).parent / "files"
POINTER = b"version https://git-lfs.github.com/spec/v1"
DEFAULT_SPACE = "yukon2051/definereq-ai"


def is_pointer(path: Path) -> bool:
    """Git LFS の参照ファイルか（実体の動画ではないか）。"""
    if not path.exists() or path.stat().st_size > 1024:
        return False
    return path.read_bytes().startswith(POINTER)


def expected_hash(path: Path) -> str | None:
    match = re.search(rb"oid sha256:([0-9a-f]{64})", path.read_bytes())
    return match.group(1).decode() if match else None


def fetch(path: Path, space: str) -> bool:
    want = expected_hash(path)
    url = f"https://huggingface.co/spaces/{space}/resolve/main/definereq/demos/files/{urllib.parse.quote(path.name)}"
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read()
    if hashlib.sha256(data).hexdigest() != want:
        print(f"ハッシュ値が一致しません：{path.name}")
        return False
    path.write_bytes(data)
    print(f"取得しました：{path.name}（{len(data):,}バイト）")
    return True


def main() -> None:
    space = os.environ.get("SPACE_ID") or DEFAULT_SPACE
    for path in FILES.glob("*.mp4"):
        if is_pointer(path):
            try:
                fetch(path, space)
            except OSError as e:
                print(f"取得できませんでした：{path.name}（{e}）")


if __name__ == "__main__":
    main()
