"""基準版（合意版）の保存と比較、再確認対象の検出。

合意を自動で引き継がない：採用した根拠・要件・判断・受入条件のどれかが変わったら再確認対象にする。
"""
from __future__ import annotations

import copy

from .. import project as pj
from . import evidence as ev

_KEYS = ("title", "body", "behavior", "exceptions", "measures", "acceptance", "scope", "priority")


def _req_view(r: dict) -> dict:
    return {k: copy.deepcopy(r.get(k)) for k in _KEYS}


def create(p: dict, label: str, actor: str = "利用者") -> dict:
    """現在の要件・判断を基準版として保存する（合意済みの項目だけが合意版の対象）。"""
    agreed_reqs = [r for r in p["requirements"] if r["status"] == "合意済み"]
    agreed_decs = [d for d in p["decisions"] if d["state"] == "合意済み"]
    item = pj.add(p, "baselines", {
        "label": label, "saved_at": pj.now_iso(), "saved_by": actor,
        "requirements": {r["id"]: {"version": r["version"], "fingerprint": pj.fingerprint(_req_view(r)),
                                   "view": _req_view(r), "evidence": copy.deepcopy(r.get("evidence", []))}
                         for r in agreed_reqs},
        "decisions": {d["id"]: {"fingerprint": pj.fingerprint({k: d.get(k) for k in ("adopted", "rationale", "state")}),
                                "adopted": d.get("adopted"), "rationale": d.get("rationale")} for d in agreed_decs},
    })
    pj.log(p, f"基準版 {item['id']}「{label}」を保存しました")
    return item


def compare(p: dict, baseline_id: str) -> dict:
    """基準版と現在の差分。"""
    b = pj.require(p, "baselines", baseline_id)
    changed, removed = [], []
    for rid, snap in b["requirements"].items():
        r = pj.get(p, "requirements", rid)
        if r is None:
            removed.append(rid)
            continue
        cur = _req_view(r)
        if pj.fingerprint(cur) != snap["fingerprint"] or r["status"] != "合意済み":
            diffs = [{"field": k, "before": snap["view"].get(k), "after": cur.get(k)}
                     for k in _KEYS if snap["view"].get(k) != cur.get(k)]
            changed.append({"id": rid, "title": r["title"], "from_version": snap["version"], "to_version": r["version"],
                            "status": r["status"], "diffs": diffs})
    added = [r["id"] for r in p["requirements"] if r["id"] not in b["requirements"] and r["status"] not in ("廃止", "却下")]
    dec_changed = []
    for did, snap in b["decisions"].items():
        d = pj.get(p, "decisions", did)
        if d is None or d["state"] != "合意済み" or d.get("adopted") != snap["adopted"]:
            dec_changed.append(did)
    return {"changed": changed, "added": added, "removed": removed, "decisions_changed": dec_changed}


def reconfirm_targets(p: dict, baseline_id: str | None = None) -> list[dict]:
    """再確認が必要な項目と、その理由。"""
    out: list[dict] = []
    if baseline_id is None and p["baselines"]:
        baseline_id = p["baselines"][-1]["id"]
    if baseline_id:
        diff = compare(p, baseline_id)
        for c in diff["changed"]:
            out.append({"id": c["id"], "reason": f"基準版から変更（v{c['from_version']}→v{c['to_version']}）"})
        for d in diff["decisions_changed"]:
            out.append({"id": d, "reason": "基準版の判断が変更されました"})
        changed_ids = {c["id"] for c in diff["changed"]}
    else:
        changed_ids = set()
    # 根拠の資料が更新された項目
    for bad in ev.verify_all(p):
        if bad["collection"] in ("requirements", "decisions"):
            reason = "根拠の資料に新しい版があります" if bad.get("stale") else "根拠の引用が現在の本文で確認できません"
            out.append({"id": bad["item_id"], "reason": reason})
            changed_ids.add(bad["item_id"])
    # 共有済み資料に含まれる項目が変わった場合
    for d in p["shared_docs"]:
        hit = changed_ids & set(d.get("item_ids", []))
        if hit:
            out.append({"id": d["id"], "reason": f"共有資料 v{d['version']} に含まれる {', '.join(sorted(hit))} が変更されました"})
    uniq = {(o["id"], o["reason"]): o for o in out}
    return list(uniq.values())
