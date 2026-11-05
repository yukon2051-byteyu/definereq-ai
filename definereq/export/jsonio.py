"""案件JSONの保存と安全な読込。

読込は「検証に合格したときだけ」現在の案件と入れ替える。
不正なファイルを読んでも、作業中の案件は失われない。
"""
from __future__ import annotations

import json

from .. import config, schema
from ..schema import COLLECTIONS


class LoadError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def dumps(p: dict) -> bytes:
    return json.dumps(p, ensure_ascii=False, indent=1, default=str).encode("utf-8")


def validate(p) -> list[str]:
    errors: list[str] = []
    if not isinstance(p, dict):
        return ["案件データの形式が正しくありません。"]
    if p.get("app") != schema.APP_ID:
        errors.append("DefineReq_AI の案件ファイルではありません。")
    if p.get("format_version") != schema.FORMAT_VERSION:
        errors.append(f"形式の版が対応外です（{p.get('format_version')}）。対応：{schema.FORMAT_VERSION}")
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
    return errors


def loads(data: bytes) -> dict:
    """読込。問題があれば LoadError（理由の一覧つき）を出す。"""
    if len(data) > config.MAX_JSON_MB * 1024 * 1024:
        raise LoadError([f"ファイルが大きすぎます（上限 {config.MAX_JSON_MB}MB）。"])
    try:
        p = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise LoadError(["JSONとして読み込めませんでした。"]) from e
    errors = validate(p)
    if errors:
        raise LoadError(errors[:20])
    return p
