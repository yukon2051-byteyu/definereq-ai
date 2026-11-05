"""複数回の会議をまたいで案件を続けるための処理。

- 会議ごとに資料・発言・判断を関連付ける
- 前回までの未決事項・宿題を次回の準備へ引き継ぐ
- 新しい情報を「補足・変更候補・新規要望・確認事項」に振り分ける

振り分けは合意済みの要件を書き換えない。変更は追加要望として受け付け、判断を経て反映する。
"""
from __future__ import annotations

from .. import project as pj
from .. import schema
from . import agreement as ag


def add_meeting(p: dict, name: str, held_on: str | None = None, note: str | None = None, origin: str = "利用者が登録") -> dict:
    if not name.strip():
        raise ValueError("会議名を入力してください。")
    item = pj.add(p, "meetings", {"name": name.strip(), "held_on": held_on or None, "note": note or None, "origin": origin})
    pj.log(p, f"会議 {item['id']}「{item['name']}」を登録しました")
    return item


def label(p: dict, meeting_id: str | None) -> str:
    m = pj.get(p, "meetings", meeting_id) if meeting_id else None
    return f"{m['name']}（{m.get('held_on') or '開催日の記録なし'}）" if m else "会議の記録なし"


def backfill(p: dict) -> None:
    """会議の記録がない案件に、記録済みの情報から会議を補う。

    録画と議事録を会議とし、同じ開催日の記録は1つにまとめる。開催日の記録がない場合は日付を補わない。
    判断と履歴は、根拠の資料が属する会議に関連付ける。
    """
    by_date = {m["held_on"]: m for m in p["meetings"] if m.get("held_on")}

    def attach(item: dict, name: str, held_on: str | None) -> None:
        if item.get("meeting_id"):
            return
        meeting = by_date.get(held_on) if held_on else None
        if meeting is None:
            meeting = add_meeting(p, name, held_on, origin="既存の記録から作成")
            if held_on:
                by_date[held_on] = meeting
        item["meeting_id"] = meeting["id"]

    for r in p["recordings"]:
        attach(r, r["name"], r.get("meeting_date"))
    for s in p["sources"]:
        if s.get("kind") == "議事録":
            attach(s, s["name"], s.get("occurred_at"))
    owners = {x["id"]: x.get("meeting_id") for x in p["sources"] + p["recordings"]}
    for d in p["decisions"]:
        if not d.get("meeting_id"):
            linked = [owners.get(e.get("source_id")) for e in d.get("evidence") or []]
            d["meeting_id"] = next((m for m in reversed(linked) if m), None)
    decisions = {d["id"]: d.get("meeting_id") for d in p["decisions"]}
    for h in p["history"]:
        if not h.get("meeting_id"):
            h["meeting_id"] = decisions.get(h.get("decision_id"))


def carryover(p: dict) -> dict[str, list[dict]]:
    """前回までに残っている事項。次回の会議の準備で参照する。"""
    def row(item_id, text, ask=None, due=None, meeting_id=None):
        return {"id": item_id, "text": text, "ask": ask, "due": due, "meeting": label(p, meeting_id)}

    return {
        "未回答の質問": [row(q["id"], q["text"], q.get("ask"), None, q.get("meeting_id")) for q in p["questions"] if q["status"] in ("未質問", "回答待ち")],
        "宿題": [row(a["id"], a["content"], a.get("owner"), a.get("due"), a.get("meeting_id")) for a in p["actions"] if a["state"] in ("未着手", "対応中")],
        "未調整の論点": [row(i["id"], i["topic"], i.get("ask"), i.get("due"), i.get("meeting_id")) for i in p["issues"] if i["state"] != "結論あり"],
        "判断待ち": [row(d["id"], f"{d['topic']}（{d['state']}）", d.get("decider"), None, d.get("meeting_id")) for d in p["decisions"] if d["state"] in ("提案", "確認待ち", "保留")],
        "調査中の追加要望": [row(c["id"], c["content"], c.get("requester"), c.get("desired_by"), c.get("meeting_id")) for c in p["changes"] if c["status"] in ("受付", "調査中", "判断待ち")],
        "未確認の矛盾候補": [row(c["id"], c["note"], None, None, None) for c in p["conflicts"] if c["state"] in ("未確認", "確認中")],
    }


def meeting_items(p: dict, meeting_id: str) -> dict[str, list[str]]:
    """会議に関連付いた項目。"""
    def pick(col, name):
        return [f"{x['id']} {x.get(name) or ''}"[:60] for x in p[col] if x.get("meeting_id") == meeting_id]

    return {"資料": pick("sources", "name"), "録画": pick("recordings", "name"), "質問": pick("questions", "text"), "判断": pick("decisions", "topic"),
            "追加要望": pick("changes", "content"), "変更履歴": pick("history", "trigger")}


def intake_candidate(p: dict, cand_id: str, kind: str, target: str | None = None, meeting_id: str | None = None,
                     actor: str = "利用者") -> dict:
    """候補を人が振り分ける。どの振り分けでも、既存の要件の本文は変更しない。"""
    if kind not in schema.CANDIDATE_INTAKE:
        raise ValueError(f"不明な振り分けです: {kind}")
    cand = pj.require(p, "candidates", cand_id)
    if kind in ("既存要件の補足", "変更候補"):
        if not target:
            raise ValueError("対象の要件を選んでください。")
        pj.require(p, "requirements", target)
        item = ag.receive_change(p, cand["text"], background=cand.get("detail"), evidence=cand.get("evidence"),
                                 related_requirements=[target], meeting_id=meeting_id)
        item["classification"] = "補足" if kind == "既存要件の補足" else "変更"
    elif kind == "新規要望":
        item = pj.add(p, "requirements", pj.new_requirement(title=cand["text"][:60], body=cand["text"], evidence=cand.get("evidence", []),
                                                             status="下書き", author="AI候補を人が採用", meeting_id=meeting_id))
    else:
        item = pj.add(p, "questions", {"text": cand["text"], "why": cand.get("detail"), "ask": cand.get("ask"), "priority": None, "status": "未質問",
                                       "answer": None, "perspective_id": None, "evidence": cand.get("evidence", []), "meeting_id": meeting_id})
    cand.update(state="採用", resolved_as=item["id"], intake=kind, meeting_id=meeting_id, resolved_by=actor)
    pj.log(p, f"候補 {cand_id} を「{kind}」として {item['id']} に振り分けました（{actor}）")
    return item
