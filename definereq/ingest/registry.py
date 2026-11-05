"""読み込んだ資料を案件へ登録する（版管理つき）。

同じ名前の資料を読み直すと版が上がる。旧版の本文は残し、根拠が「どの版の引用か」を追える。
"""
from __future__ import annotations

from .. import project as pj
from .formats import Parsed, finalize, parse_file, parse_text


def register(p: dict, name: str, parsed: Parsed, kind: str = "その他", origin: str = "アップロード",
             visibility: str = "社内のみ", occurred_at: str | None = None, note: str | None = None,
             meeting_id: str | None = None) -> dict:
    prev = next((s for s in reversed(p["sources"]) if s["name"] == name and not s.get("superseded_by")), None)
    item = {
        "name": name, "kind": kind, "version": (prev["version"] + 1) if prev else 1,
        "occurred_at": occurred_at, "registered_at": pj.now_iso(), "origin": origin, "visibility": visibility,
        "file_kind": parsed.kind, "units": parsed.units, "warnings": parsed.warnings, "extra": parsed.extra,
        "supplement": note, "meeting_id": meeting_id, "superseded_by": None, "replaces": prev["id"] if prev else None,
    }
    item = pj.add(p, "sources", item)
    if prev:
        prev["superseded_by"] = item["id"]
    pj.log(p, f"資料 {item['id']}「{name}」v{item['version']} を登録しました")
    return item


def ingest_bytes(p: dict, filename: str, data: bytes, **kw) -> dict:
    name, parsed = parse_file(filename, data)
    return register(p, name, parsed, **kw)


def ingest_paste(p: dict, title: str, text: str, **kw) -> dict:
    parsed = parse_text(text)
    finalize(parsed)
    kw.setdefault("origin", "文章貼り付け")
    return register(p, (title or "貼り付けた文章").strip(), parsed, **kw)


def set_unit_target(p: dict, source_id: str, unit_ids: set[str], target: bool) -> None:
    src = pj.require(p, "sources", source_id)
    for u in src["units"]:
        if u["id"] in unit_ids:
            u["target"] = target


def target_units(p: dict, source_ids: list[str] | None = None) -> list[dict]:
    """AIへの送信対象の単位だけを返す（旧版と対象外の単位は含めない）。"""
    out = []
    for s in p["sources"]:
        if s.get("superseded_by") or (source_ids is not None and s["id"] not in source_ids):
            continue
        for u in s["units"]:
            if u.get("target", True):
                out.append({"source_id": s["id"], "source_name": s["name"], "version": s["version"], **u})
    return out
