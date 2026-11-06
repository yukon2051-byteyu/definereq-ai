"""根拠（引用）の照合。

根拠 = {"source_id": "SRC-001" または "REC-001", "unit_id": ..., "version": 1,
        "quote": "原文の引用", "locator": "p.3" / "00:01:20", "verified": True/False}

AIや人が示した引用が、指定の資料の本文に実在するかをプログラムで確かめる。
実在しない引用は「未確認」のまま表示し、確認済みの根拠として扱わない。
"""
from __future__ import annotations

import re
import unicodedata

from .. import project as pj
from ..ingest.formats import format_time


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"[\s　、。,.\-ー・「」『』()（）]", "", text).lower()


def locate(p: dict, source_id: str, quote: str, unit_id: str | None = None) -> dict | None:
    """引用が本文のどこにあるか探す。見つかれば単位の情報を返す。"""
    q = norm(quote)
    if not q:
        return None
    if source_id.startswith("REC"):
        rec = pj.get(p, "recordings", source_id)
        for s in (rec or {}).get("segments", []):
            if (unit_id is None or s["id"] == unit_id) and (q in norm(s["text"]) or q in norm(s["text_auto"])):
                return {"unit_id": s["id"], "locator": f"{format_time(s['start'])}-{format_time(s['end'])}",
                        "version": rec["version"]}
        return None
    src = pj.get(p, "sources", source_id)
    for u in (src or {}).get("units", []):
        if (unit_id is None or u["id"] == unit_id) and q in norm(u["text"]):
            return {"unit_id": u["id"], "locator": u["locator"], "version": src["version"]}
    return None


def make(p: dict, source_id: str, quote: str, unit_id: str | None = None) -> dict:
    """根拠を作る。本文に実在すれば verified=True。"""
    found = locate(p, source_id, quote, unit_id)
    if found:
        return {"source_id": source_id, "quote": quote, "verified": True, **found}
    return {"source_id": source_id, "unit_id": unit_id, "version": None, "quote": quote,
            "locator": "位置不明", "verified": False}


def unconfirmed_speech(p: dict, ev: dict) -> bool:
    """根拠が、話者または内容の確認が済んでいない発言かどうか。"""
    if not str(ev.get("source_id", "")).startswith("REC"):
        return False
    rec = pj.get(p, "recordings", ev["source_id"])
    seg = next((s for s in (rec or {}).get("segments", []) if s["id"] == ev.get("unit_id")), None)
    return seg is None or seg["speaker_status"] != "確認済み" or seg["content_status"] != "確認済み"


def unconfirmed_parts(p: dict, ev: dict) -> list[str]:
    """発言の根拠で、確認が済んでいない対象（話者／内容）を返す。"""
    if not str(ev.get("source_id", "")).startswith("REC"):
        return []
    rec = pj.get(p, "recordings", ev["source_id"])
    seg = next((s for s in (rec or {}).get("segments", []) if s["id"] == ev.get("unit_id")), None)
    if seg is None:
        return ["話者", "発言内容"]
    return [name for name, ok in (("話者", seg["speaker_status"] == "確認済み"), ("発言内容", seg["content_status"] == "確認済み")) if not ok]


SPEAKER_SOURCE = {"subtitle": "字幕上の話者"}


def speaker_view(rec: dict, seg: dict) -> dict:
    """話者の表示。未確認の名前を確定した話者のように見せないため、出所を付ける。"""
    confirmed = seg["speaker_status"] == "確認済み"
    return {"label": "話者" if confirmed else SPEAKER_SOURCE.get(rec.get("method"), "文字起こし上の話者"),
            "name": seg.get("speaker") or seg.get("speaker_label") or "記録なし", "confirmed": confirmed,
            "speaker_check": "確認済み" if confirmed else "未実施", "content_check": seg["content_status"]}


def source_name(p: dict, source_id: str) -> str:
    item = pj.get(p, "recordings" if source_id.startswith("REC") else "sources", source_id)
    return item["name"] if item else f"{source_id}（登録なし）"


def recheck(p: dict, ev: dict) -> dict:
    """現在の本文で引用を再確認する。読み直しで本文が変わった場合も検出する。"""
    src_id = ev["source_id"]
    found = locate(p, src_id, ev.get("quote", ""), ev.get("unit_id"))
    state = {"verified": bool(found), "stale": False}
    if not src_id.startswith("REC"):
        src = pj.get(p, "sources", src_id)
        if src and src.get("superseded_by"):
            state["stale"] = True
            state["newer"] = src["superseded_by"]
    return state


def verify_all(p: dict) -> list[dict]:
    """案件内の全ての根拠を照合し、問題のあるものを返す。"""
    bad = []
    for col in ("requirements", "candidates", "decisions", "changes", "risks", "conflicts", "issues"):
        for item in p[col]:
            for ev in item.get("evidence", []) or []:
                st = recheck(p, ev)
                if not st["verified"] or st["stale"]:
                    bad.append({"collection": col, "item_id": item["id"], "evidence": ev, **st})
    return bad


def citation(p: dict, ev: dict) -> str:
    return f"{source_name(p, ev['source_id'])}（{ev.get('locator', '位置不明')}）"
