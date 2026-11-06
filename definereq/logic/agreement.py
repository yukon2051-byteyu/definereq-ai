"""決定・合意と追加要望の状態管理。

守るルール
- 作成・発言・送付だけでは合意にならない
- 合意済みにするのは人の操作のみ（判断者・判断日・採用案の記録が必須）
- 追加要望を受け付けただけでは要件を変更しない（合意済みの判断を結び付けて初めて反映できる）
- 認証なしの記録は「利用者による記録」であり、電子署名ではない
"""
from __future__ import annotations

from .. import project as pj
from .. import schema
from . import evidence as ev

RECORD_NOTICE = "この記録は利用者が入力したものです。本人確認や電子署名ではありません。"


def new_decision(p: dict, topic: str, options: list[dict] | None = None, **kw) -> dict:
    item = {
        "topic": topic, "options": options or [], "adopted": None, "rejected_reasons": {},
        "rationale": None, "hold_reason": None, "decider": None, "confirmer": None, "decided_on": None,
        "evidence": [], "related_requirements": [], "related_changes": [], "state": "下書き",
        "state_log": [], "internal_note": None,
    }
    item.update(kw)
    return pj.add(p, "decisions", item)


def set_state(p: dict, dec_id: str, state: str, actor_kind: str, actor: str = "利用者") -> dict:
    if state not in schema.AGREEMENT_STATES:
        raise ValueError(f"不明な状態です: {state}")
    dec = pj.require(p, "decisions", dec_id)
    if state in schema.HUMAN_ONLY_STATES:
        if actor_kind != "human":
            raise PermissionError("合意は人の操作でのみ記録できます。")
        missing = [label for key, label in (("adopted", "採用案"), ("decider", "判断者"), ("decided_on", "判断日"))
                   if not dec.get(key)]
        if missing:
            raise ValueError(f"合意の記録には {'・'.join(missing)} が必要です。")
        evidence = dec.get("evidence") or []
        if evidence and not any(e.get("verified") and not ev.unconfirmed_speech(p, e) for e in evidence):
            raise ValueError("根拠が未確認の情報だけです。話者や内容を確認するか、確認できる根拠を追加してください。")
    if state == "保留" and not dec.get("hold_reason"):
        raise ValueError("保留の理由を入力してください。")
    if state == "合意済み":  # どの版に対する判断かを残す。後で要件が変わったときに古い判断と分かるように
        dec["target_versions"] = _versions(p, dec)
    dec["state_log"].append({"at": pj.now_iso(), "from": dec["state"], "to": state, "by": actor})
    dec["state"] = state
    pj.log(p, f"判断 {dec_id} を「{state}」にしました（{actor}）")
    return dec


def _versions(p: dict, dec: dict) -> dict:
    return {r["id"]: r["version"] for rid in dec.get("related_requirements", []) if (r := pj.get(p, "requirements", rid))}


def decision_targets(p: dict, dec: dict) -> list[dict]:
    """判断の対象の要件と、反映できるかどうか。反映は人が選ぶ。"""
    rows = []
    for rid in dec.get("related_requirements", []):
        r = pj.get(p, "requirements", rid)
        if not r:
            continue
        recorded = (dec.get("target_versions") or {}).get(rid)
        same = recorded is None or recorded == r["version"]
        rows.append({"id": rid, "title": r["title"], "version": r["version"], "recorded_version": recorded, "status": r["status"], "same_version": same,
                     "done": r["status"] == "合意済み" and same, "after": "合意済み" if same else "反映できません（版の確認が必要）",
                     "open": r.get("open_items") or r.get("open_area") or (None if r.get("acceptance") else "受入条件が未設定")})
    return rows


def apply_decision(p: dict, dec_id: str, req_ids: list[str], actor_kind: str, actor: str = "利用者") -> list[dict]:
    """合意済みの判断を、人が選んだ要件へ反映する。古い版へは反映しない。"""
    if actor_kind != "human":
        raise PermissionError("合意は人の操作でのみ記録できます。")
    dec = pj.require(p, "decisions", dec_id)
    if dec["state"] != "合意済み":
        raise ValueError("反映には合意済みの判断が必要です。")
    done = []
    for rid in req_ids:
        if rid not in dec.get("related_requirements", []):
            raise ValueError(f"{rid} はこの判断に関連付いていません。")
        req = pj.require(p, "requirements", rid)
        if not pj.covers_version(dec, req):
            raise ValueError(f"{rid} は判断の後に v{req['version']} へ変更されています。内容を確認してください。")
        pj.set_requirement_status(p, rid, "合意済み", "human", actor)
        record_history(p, rid, "採用", f"判断 {dec_id}（{dec['topic']}）", decision_id=dec_id, after=req["body"], decided_on=dec.get("decided_on"), meeting_id=dec.get("meeting_id"),
                       options=[o["label"] for o in dec.get("options", [])], rationale=dec.get("rationale"), decider=dec.get("decider"), confirmer=dec.get("confirmer"), evidence=dec.get("evidence"))
        done.append(req)
    return done


def reconfirm_version(p: dict, dec_id: str, req_id: str, actor_kind: str, actor: str = "利用者") -> dict:
    """要件の現在の版を見たうえで、判断の対象を人が更新する。自動では更新しない。"""
    if actor_kind != "human":
        raise PermissionError("判断の確認は人の操作でのみ記録できます。")
    dec = pj.require(p, "decisions", dec_id)
    req = pj.require(p, "requirements", req_id)
    dec.setdefault("target_versions", {})[req_id] = req["version"]
    dec["state_log"].append({"at": pj.now_iso(), "from": dec["state"], "to": dec["state"], "by": actor, "note": f"{req_id} v{req['version']} を確認"})
    pj.log(p, f"判断 {dec_id} の対象を {req_id} v{req['version']} に更新しました（{actor}）")
    return dec


def receive_change(p: dict, content: str, requester: str | None = None, background: str | None = None,
                   evidence: list | None = None, desired_by: str | None = None,
                   requested_at: str | None = None, related_requirements: list[str] | None = None,
                   meeting_id: str | None = None) -> dict:
    """追加要望の受付。要件は変更しない。"""
    item = pj.add(p, "changes", {
        "requested_at": requested_at, "requester": requester, "background": background, "content": content,
        "evidence": evidence or [], "desired_by": desired_by, "status": "受付", "classification": "未分類",
        "related_requirements": related_requirements or [], "impacts": [], "surveyed_areas": [],
        "decision_id": None, "internal_note": None, "meeting_id": meeting_id,
    })
    pj.log(p, f"追加要望 {item['id']} を受け付けました（要件は変更していません）")
    return item


def add_impact(p: dict, chg_id: str, area: str, target: str | None, note: str, basis: str) -> dict:
    if area not in schema.IMPACT_AREAS:
        raise ValueError(f"不明な影響領域です: {area}")
    if basis not in schema.IMPACT_BASIS:
        raise ValueError(f"不明な根拠の区分です: {basis}")
    chg = pj.require(p, "changes", chg_id)
    impact = {"area": area, "target": target, "note": note, "basis": basis}
    chg["impacts"].append(impact)
    if area not in chg["surveyed_areas"]:
        chg["surveyed_areas"].append(area)
    return impact


def unsurveyed_areas(chg: dict) -> list[str]:
    return [a for a in schema.IMPACT_AREAS if a not in chg.get("surveyed_areas", [])]


def record_history(p: dict, req_id: str | None, outcome: str, trigger: str, *, change_id: str | None = None,
                   decision_id: str | None = None, before: str | None = None, after: str | None = None,
                   meeting_date: str | None = None, proposed_on: str | None = None, decided_on: str | None = None,
                   applied_on: str | None = None, options: list[str] | None = None, rationale: str | None = None,
                   decider: str | None = None, confirmer: str | None = None, evidence: list | None = None,
                   impact: str | None = None, artifacts: list[str] | None = None, corrects: str | None = None,
                   meeting_id: str | None = None) -> dict:
    """仕様の変遷を追加する。不明な日付は None のまま残し、記録日時で代用しない。"""
    if outcome not in schema.HISTORY_OUTCOMES:
        raise ValueError(f"不明な結果です: {outcome}")
    return pj.add(p, "history", {
        "requirement_id": req_id, "change_id": change_id, "decision_id": decision_id, "trigger": trigger,
        "meeting_date": meeting_date, "proposed_on": proposed_on, "decided_on": decided_on, "applied_on": applied_on,
        "recorded_at": pj.now_iso(), "before": before, "after": after, "options": options or [],
        "outcome": outcome, "rationale": rationale, "decider": decider, "confirmer": confirmer,
        "evidence": evidence or [], "impact": impact, "artifacts": artifacts or [], "corrects": corrects, "meeting_id": meeting_id,
    })


def correct_history(p: dict, his_id: str, fields: dict, reason: str) -> dict:
    """過去の履歴は上書きせず、訂正の履歴を追加する。"""
    old = pj.require(p, "history", his_id)
    new = {k: v for k, v in old.items() if k not in ("id", "created_at", "recorded_at")}
    new.update(fields)
    new["corrects"] = his_id
    new["correction_reason"] = reason
    new["recorded_at"] = pj.now_iso()
    return pj.add(p, "history", new)


def apply_change(p: dict, chg_id: str, decision_id: str, updates: dict[str, dict], actor_kind: str,
                 applied_on: str | None = None, reason: str | None = None, actor: str = "利用者") -> list[dict]:
    """合意済みの判断に基づいて、追加要望を要件へ反映する。

    updates = {要件ID: {変更する項目: 値}}
    反映した要件は「確認待ち」に戻る（新しい内容の確認が済むまで合意を引き継がない）。
    """
    if actor_kind != "human":
        raise PermissionError("要件への反映は人の操作でのみ行えます。")
    chg = pj.require(p, "changes", chg_id)
    dec = pj.require(p, "decisions", decision_id)
    if dec["state"] != "合意済み":
        raise ValueError("反映には合意済みの判断が必要です。")
    if chg_id not in dec.get("related_changes", []):
        raise ValueError("この判断は追加要望に関連付いていません。")
    results = []
    meeting_id = dec.get("meeting_id")
    meeting = pj.get(p, "meetings", meeting_id) if meeting_id else None
    for req_id, fields in updates.items():
        req = pj.require(p, "requirements", req_id)
        before = req.get("body")
        req = pj.update_requirement(p, req_id, fields, reason=reason or dec.get("rationale"), actor=actor,
                                    change_id=chg_id)
        record_history(p, req_id, "採用", f"追加要望 {chg_id}", change_id=chg_id, decision_id=decision_id,
                       before=before, after=req.get("body"), decided_on=dec.get("decided_on"), applied_on=applied_on,
                       meeting_id=meeting_id, meeting_date=meeting.get("held_on") if meeting else None,
                       proposed_on=chg.get("requested_at"), options=[o["label"] for o in dec.get("options", [])],
                       rationale=dec.get("rationale"), decider=dec.get("decider"), confirmer=dec.get("confirmer"),
                       evidence=dec.get("evidence"), impact=f"{len(chg.get('impacts', []))}件の影響を調査")
        dec.setdefault("target_versions", {})[req_id] = req["version"]  # この判断に基づく変更なので、新しい版が対象になる
        results.append(req)
    chg["status"] = "反映済み"
    chg["decision_id"] = decision_id
    pj.log(p, f"追加要望 {chg_id} を判断 {decision_id} に基づき反映しました（{actor}）")
    return results
