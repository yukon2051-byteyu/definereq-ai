"""案件データの基本操作（ID採番・追加・検索・要件の版管理）。

案件は1つの dict（JSONに保存できる形）で表す。クラスを増やさず、
「どの項目があるか」を new_* 関数で読めるようにして、初学者でも保守しやすくしている。

重要な考え方
- 過去の記録は上書きしない。要件を変えるときは旧版を versions に残す
- 合意済みの要件を変えたら合意は引き継がず「確認待ち」に戻す
- 値の None は「未設定」、schema.NA は「該当なし」
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from . import schema
from .schema import COLLECTIONS, NA

JST = timezone(timedelta(hours=9))


def now_iso() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def today() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def fingerprint(obj: Any) -> str:
    """内容の指紋（少しでも内容が変われば別の値になる）。古い結果の検出に使う。"""
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def field_state(value: Any) -> str:
    """未設定 / 該当なし / 設定済み を区別して返す。"""
    if value is None or value == "" or value == []:
        return "未設定"
    if value == NA:
        return "該当なし"
    return "設定済み"


def display(value: Any) -> str:
    state = field_state(value)
    if state != "設定済み":
        return state
    if isinstance(value, list):
        return "、".join(str(v) for v in value)
    return str(value)


def new_project(name: str, domains: list[str], actor: str = "利用者") -> dict:
    unknown = [d for d in domains if d not in schema.DOMAINS]
    if not name.strip():
        raise ValueError("案件名を入力してください。")
    if not domains or unknown:
        raise ValueError("対象分野を1つ以上選んでください。")
    p: dict = {
        "app": schema.APP_ID,
        "format_version": schema.FORMAT_VERSION,
        "id": "PRJ-" + hashlib.sha256((name + now_iso()).encode()).hexdigest()[:8],
        "name": name.strip(),
        "domains": list(domains),
        "traits": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "is_demo": False,
        "demo": None,
        "profile": {k: {"value": None, "certainty": "未確認"} for k in PROFILE_FIELDS},
        "prep": {"understanding": None, "gaps": [], "materials": [], "purpose": None,
                 "agenda": [], "decide_today": []},
        "nfr_status": {},
        "scope_notes": [],
        "activity": [],
        "seq": {},
    }
    for key in COLLECTIONS:
        p[key] = []
    log(p, f"案件を作成しました（{actor}）")
    return p


PROFILE_FIELDS = {
    "background": "背景", "purpose": "目的", "problem": "課題", "outcome": "期待する成果",
    "current": "現状の業務・構成・運用", "request": "要望の概要", "users": "利用者", "scope_in": "範囲",
    "scope_out": "対象外", "constraints": "制約", "timeline": "時期", "budget": "予算",
}


def log(p: dict, message: str) -> None:
    p.setdefault("activity", []).append({"at": now_iso(), "message": message})
    p["updated_at"] = now_iso()


def next_id(p: dict, collection: str) -> str:
    prefix = COLLECTIONS[collection]
    seq = p.setdefault("seq", {})
    existing = {x.get("id") for x in p[collection]}
    n = seq.get(collection, 0) + 1
    while f"{prefix}-{n:03d}" in existing:
        n += 1
    seq[collection] = n
    return f"{prefix}-{n:03d}"


def add(p: dict, collection: str, item: dict) -> dict:
    item = dict(item)
    item.setdefault("id", next_id(p, collection))
    item.setdefault("created_at", now_iso())
    if any(x["id"] == item["id"] for x in p[collection]):
        raise ValueError(f"IDが重複しています: {item['id']}")
    p[collection].append(item)
    p["updated_at"] = now_iso()
    return item


def get(p: dict, collection: str, item_id: str) -> dict | None:
    return next((x for x in p.get(collection, []) if x.get("id") == item_id), None)


def require(p: dict, collection: str, item_id: str) -> dict:
    item = get(p, collection, item_id)
    if item is None:
        raise KeyError(f"{item_id} が見つかりません。")
    return item


def find_any(p: dict, item_id: str) -> tuple[str, dict] | None:
    for col in COLLECTIONS:
        item = get(p, col, item_id)
        if item:
            return col, item
    return None


def label_of(p: dict, item_id: str) -> str:
    found = find_any(p, item_id)
    if not found:
        return item_id
    _, item = found
    name = item.get("title") or item.get("topic") or item.get("name") or item.get("text") or item.get("content") or ""
    return f"{item_id} {str(name)[:40]}".strip()


def new_requirement(**kw) -> dict:
    base = {
        "version": 1, "domain": None, "kind": None, "title": "", "body": "",
        "background": None, "target": None, "preconditions": None, "behavior": None,
        "exceptions": None, "data_io": None, "nonfunctional": None,
        "measures": [], "priority": None, "scope": "判断待ち", "scope_reason": None,
        "scope_impact": None, "scope_depends": [], "scope_decider": None, "scope_decided_at": None,
        "acceptance": [], "open_items": None, "related": [], "decider": None, "confirm_with": None,
        "due": None, "status": "下書き", "evidence": [], "versions": [],
        "split_from": None, "merged_into": None, "replaced_by": [], "internal_note": None,
        "author": "人",
    }
    base.update(kw)
    return base


# 版として記録する本文側の項目（版番号や履歴の入れ物は含めない）
_VERSIONED_EXCLUDE = {"versions", "created_at"}


def snapshot(req: dict) -> dict:
    return {k: copy.deepcopy(v) for k, v in req.items() if k not in _VERSIONED_EXCLUDE}


def update_requirement(p: dict, req_id: str, changes: dict, reason: str | None = None,
                       actor: str = "利用者", change_id: str | None = None) -> dict:
    """要件を変更して版を1つ進める。

    合意済みの要件の内容を変えると、古い合意を自動で引き継がず「確認待ち」に戻す。
    """
    req = require(p, "requirements", req_id)
    meaningful = {k: v for k, v in changes.items() if req.get(k) != v}
    if not meaningful:
        return req
    was_agreed = req.get("status") == "合意済み"
    entry = snapshot(req)
    entry.update({"superseded_at": now_iso(), "change_reason": reason, "changed_by": actor,
                  "change_id": change_id})
    req.setdefault("versions", []).append(entry)
    req.update(copy.deepcopy(meaningful))
    req["version"] = int(req.get("version", 1)) + 1
    if was_agreed and "status" not in meaningful:
        req["status"] = "確認待ち"
    log(p, f"{req_id} を v{req['version']} に更新しました（{actor}）")
    return req


def covers_version(decision: dict, req: dict) -> bool:
    """判断が要件の現在の版を対象にしているか。版の記録がない古い判断は判定できないため対象として扱う。"""
    version = (decision.get("target_versions") or {}).get(req["id"])
    return version is None or version == req["version"]


def set_requirement_status(p: dict, req_id: str, status: str, actor_kind: str, actor: str = "利用者") -> dict:
    """要件の状態変更。AIの出力やプログラムの自動処理から合意済みにはできない。"""
    if status not in schema.AGREEMENT_STATES:
        raise ValueError(f"不明な状態です: {status}")
    if status in schema.HUMAN_ONLY_STATES and actor_kind != "human":
        raise PermissionError("合意は人の操作でのみ記録できます。")
    req = require(p, "requirements", req_id)
    if status == "合意済み":
        linked = [d for d in p["decisions"] if req_id in d.get("related_requirements", []) and d.get("state") == "合意済み"]
        if not linked:
            raise ValueError("合意済みにするには、この要件に関連付いた合意済みの判断記録が必要です。")
        if not any(covers_version(d, req) for d in linked):
            raise ValueError(f"判断は古い版を対象にしています（現在は v{req['version']}）。現在の版の内容を確認し、判断を確認し直してください。")
    req["status"] = status
    log(p, f"{req_id} の状態を「{status}」にしました（{actor}）")
    return req


def merge_requirements(p: dict, source_ids: list[str], title: str, body: str, reason: str) -> dict:
    """統合。元の要件は廃止として残し、統合先から追跡できるようにする。"""
    merged = add(p, "requirements", new_requirement(title=title, body=body, derived_from=list(source_ids),
                                                     status="下書き"))
    for rid in source_ids:
        update_requirement(p, rid, {"status": "廃止", "merged_into": merged["id"]}, reason=reason)
    return merged


def split_requirement(p: dict, source_id: str, parts: list[dict], reason: str) -> list[dict]:
    """分割。元の要件は廃止として残し、分割先から追跡できるようにする。"""
    created = [add(p, "requirements", new_requirement(split_from=source_id, status="下書き", **part))
               for part in parts]
    update_requirement(p, source_id, {"status": "廃止", "replaced_by": [c["id"] for c in created]}, reason=reason)
    return created


def lineage(p: dict, req_id: str) -> list[str]:
    """分割・統合をたどって関係する要件IDを返す（廃止後も追跡できる）。"""
    seen: list[str] = []
    stack = [req_id]
    while stack:
        rid = stack.pop()
        if rid in seen:
            continue
        seen.append(rid)
        r = get(p, "requirements", rid)
        if not r:
            continue
        stack.extend(r.get("replaced_by") or [])
        for key in ("split_from", "merged_into"):
            if r.get(key):
                stack.append(r[key])
        stack.extend(r.get("derived_from") or [])
    return seen
