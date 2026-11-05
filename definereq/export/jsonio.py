"""案件JSONの保存と安全な読込。

読込は「検証に合格したときだけ」案件を差し替える。
不正なファイルを読んでも、作業中の案件は失われない。読込だけでAI処理は始まらない。

JSONに含めるもの：案件情報、資料の抽出テキスト、文字起こし、要件、判断、履歴など案件の全データ
JSONに含めないもの：元の動画・資料ファイル、APIキー、AIパスワード（案件データの外で管理している）
"""
from __future__ import annotations

import copy
import json

from .. import config, schema
from .. import project as pj
from ..logic import continuity
from ..schema import COLLECTIONS, FORMAT_VERSION


class LoadError(Exception):
    def __init__(self, errors: list[str], hint: str = "保存した案件JSONを選び直してください。"):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.hint = hint


def dumps(p: dict) -> bytes:
    """保存用のJSONを作る。作成日時は記録するが、実際に保存されたかは分からない。"""
    data = {**p, "exported_at": pj.now_iso()}
    return json.dumps(data, ensure_ascii=False, indent=1, default=str).encode("utf-8")


def migrate(p: dict) -> dict:
    """古い形式を現在の形式へ変換する。元のデータは変更しない。"""
    q = copy.deepcopy(p)
    if q.get("format_version") == 1:
        q.setdefault("meetings", [])  # 版1には会議の一覧がなかった
        q["format_version"] = 2
        q["migrated_from"] = 1
        continuity.backfill(q)
    return q


def validate(p) -> list[str]:
    errors: list[str] = []
    if not isinstance(p, dict):
        return ["案件データの形式が正しくありません。"]
    if p.get("app") != schema.APP_ID:
        errors.append("DefineReq_AI の案件ファイルではありません。")
    if p.get("format_version") != FORMAT_VERSION:
        errors.append(f"形式の版が対応外です（{p.get('format_version')}）。対応：{FORMAT_VERSION}")
    if not isinstance(p.get("name"), str) or not p.get("name", "").strip():
        errors.append("案件名がありません。")
    domains = p.get("domains")
    if not isinstance(domains, list) or not domains or any(d not in schema.DOMAINS for d in domains):
        errors.append("対象分野が正しくありません。")
    if not isinstance(p.get("profile"), dict):
        errors.append("案件情報がありません。")
    for col, prefix in COLLECTIONS.items():
        items = p.get(col)
        if not isinstance(items, list):
            errors.append(f"一覧「{col}」がありません。")
            continue
        ids = set()
        for it in items:
            if not isinstance(it, dict) or not isinstance(it.get("id"), str):
                errors.append(f"一覧「{col}」にIDのない項目があります。")
                continue
            if not it["id"].startswith(prefix + "-"):
                errors.append(f"IDの形式が正しくありません: {it['id']}")
            if it["id"] in ids:
                errors.append(f"IDが重複しています: {it['id']}")
            ids.add(it["id"])
    if errors:
        return errors
    for col, field, allowed in schema.ENUM_CHECKS:
        for it in p[col]:
            if it.get(field) not in allowed:
                errors.append(f"{it['id']} の {field} の値が正しくありません: {it.get(field)}")
    for col, field, target in schema.REF_CHECKS:
        known = {x["id"] for x in p[target]}
        for it in p[col]:
            for ref in it.get(field) or []:
                if ref not in known:
                    errors.append(f"{it['id']} の参照先がありません: {ref}")
    source_ids = {x["id"] for x in p["sources"]} | {x["id"] for x in p["recordings"]}
    for col in ("requirements", "decisions", "changes", "candidates"):
        for it in p[col]:
            for e in it.get("evidence") or []:
                if e.get("source_id") not in source_ids:
                    errors.append(f"{it['id']} の根拠の資料がありません: {e.get('source_id')}")
    meetings = {x["id"] for x in p["meetings"]}
    for col in schema.MEETING_LINKED:
        for it in p[col]:
            if it.get("meeting_id") and it["meeting_id"] not in meetings:
                errors.append(f"{it['id']} の会議がありません: {it['meeting_id']}")
    return errors


def loads(data: bytes) -> dict:
    """読込。問題があれば LoadError（理由と対処方法つき）を出す。"""
    if len(data) > config.MAX_JSON_MB * 1024 * 1024:
        raise LoadError([f"ファイルが大きすぎます（上限 {config.MAX_JSON_MB}MB）。"])
    try:
        raw = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise LoadError(["JSONとして読み込めませんでした。ファイルが壊れている可能性があります。"]) from e
    version = raw.get("format_version") if isinstance(raw, dict) else None
    if isinstance(version, int) and version > FORMAT_VERSION:
        raise LoadError([f"このファイルは新しい形式（版{version}）です。このアプリは版{FORMAT_VERSION}まで対応しています。"],
                        hint="アプリを最新にしてから読み込んでください。")
    p = migrate(raw) if isinstance(raw, dict) else raw
    errors = validate(p)
    if errors:
        raise LoadError(errors[:20])
    if p.get("is_demo"):  # デモから保存した案件は、通常の案件として続きを編集できるようにする
        p.update(is_demo=False, demo=None, from_demo=True)
    return p


def summary(p: dict) -> dict:
    """読込前に見せる概要。記録がない情報は「記録なし」とし、推測で補わない。"""
    return {
        "案件名": p["name"],
        "対象分野": "、".join(schema.DOMAINS[d] for d in p["domains"]),
        "保存用ファイルの作成日時": _time(p.get("exported_at")),
        "最終更新": _time(p.get("updated_at")),
        "会議": f"{len(p['meetings'])}件",
        "要件": f"{len(p['requirements'])}件",
        "判断": f"{len(p['decisions'])}件",
        "変更履歴": f"{len(p['history'])}件",
    }


def _time(value) -> str:
    return value[:16].replace("T", " ") if value else "記録なし"


def missing_files(p: dict) -> list[str]:
    """JSONに含まれないファイルの案内。"""
    names = [r["name"] for r in p["recordings"] if r["method"] in ("openai", "local")]
    notes = ["元の動画・資料ファイルはJSONに含まれません。抽出した本文と文字起こしは復元されます。"]
    if names:
        notes.append("動画の再生には、録画・発言の画面で同じ動画を添付し直してください：" + "、".join(names))
    return notes
