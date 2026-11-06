"""変更前後の文章の差分。

長い文章を読み比べなくても変更点が分かるように、変わった部分だけを切り出す。
色だけに頼らないよう、画面では「追加」「削除」の文字を一緒に表示する。
"""
from __future__ import annotations

from difflib import SequenceMatcher

# 一致部分がこの文字数より短いときは、前後の変更とまとめて1か所として見せる（細切れを防ぐ）
MIN_EQUAL = 4
# 文章の大半が変わった場合は、部分の強調をやめて全体の変更として見せる
WHOLE_RATIO = 0.45


def _merged_ops(before: str, after: str) -> list[list]:
    ops: list[list] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, before, after, autojunk=False).get_opcodes():
        short_equal = tag == "equal" and i2 - i1 < MIN_EQUAL and ops and j2 < len(after)
        if tag != "equal" or short_equal:
            if ops and ops[-1][0] == "change":
                ops[-1][2], ops[-1][4] = i2, j2
            else:
                ops.append(["change", i1, i2, j1, j2])
        else:
            ops.append(["equal", i1, i2, j1, j2])
    return ops


def parts(before: str, after: str) -> dict:
    """{"mode": same/partial/whole, "before": [(種類, 文)], "after": [(種類, 文)]}。種類は same/del/add。"""
    before, after = before or "", after or ""
    if before == after:
        return {"mode": "same", "before": [("same", before)], "after": [("same", after)]}
    if SequenceMatcher(None, before, after, autojunk=False).ratio() < WHOLE_RATIO:
        return {"mode": "whole", "before": [("del", before)], "after": [("add", after)]}
    left, right = [], []
    for tag, i1, i2, j1, j2 in _merged_ops(before, after):
        if tag == "equal":
            left.append(("same", before[i1:i2]))
            right.append(("same", after[j1:j2]))
            continue
        if i2 > i1:
            left.append(("del", before[i1:i2]))
        if j2 > j1:
            right.append(("add", after[j1:j2]))
    return {"mode": "partial", "before": left, "after": right}
