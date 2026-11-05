"""アップロードファイルの安全確認（ファイル名・容量・圧縮爆弾）。

マクロ等は実行しない：Office ファイルは本文を読むだけで、埋め込みコードを動かす処理を持たない。
"""
from __future__ import annotations

import io
import os
import re
import unicodedata
import zipfile

from .. import config


class IngestError(Exception):
    """利用者に理由を見せられる読込エラー。"""


def safe_filename(name: str) -> str:
    """表示・保存に使うファイル名を安全な形にする（パスの除去、制御文字の除去）。"""
    name = unicodedata.normalize("NFKC", name or "").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[\x00-\x1f\x7f<>:\"|?*]", "_", name).strip(" .")
    if not name:
        return "無題"
    stem, ext = os.path.splitext(name)
    return stem[:100] + ext[:10]


def check_size(data: bytes, limit_mb: int) -> None:
    if not data:
        raise IngestError("ファイルが空です。")
    if len(data) > limit_mb * 1024 * 1024:
        raise IngestError(f"ファイルが大きすぎます（上限 {limit_mb}MB）。")


def check_zip(data: bytes) -> None:
    """docx / xlsx / pptx は zip 形式。展開量を確認してから読む。"""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            infos = z.infolist()
    except zipfile.BadZipFile as e:
        raise IngestError("ファイルが壊れているか、形式が拡張子と一致しません。") from e
    if len(infos) > config.MAX_ZIP_ENTRIES:
        raise IngestError("ファイル内の要素数が多すぎます。")
    total = sum(i.file_size for i in infos)
    if total > config.MAX_ZIP_UNCOMPRESSED_MB * 1024 * 1024:
        raise IngestError("展開後の容量が上限を超えます。")
    compressed = sum(i.compress_size for i in infos) or 1
    if total > 10 * 1024 * 1024 and total / compressed > config.MAX_ZIP_RATIO:
        raise IngestError("圧縮率が異常に高いため読み込みを中止しました。")
