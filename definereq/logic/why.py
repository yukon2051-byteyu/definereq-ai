"""「なぜこの仕様か」への回答。

登録済みの情報だけから回答を組み立てる（AIを使わず、料金は発生しない）。
- 理由が記録されていなければ「理由の記録がありません」と答える
- 現行・過去案・版を区別する
- 対象が曖昧なら候補を示す（勝手に1つに絞らない）
- 他案件の情報は見ない（引数の案件 p だけを読む）
"""
from __future__ import annotations

import re

from .. import project as pj
from . import evidence as ev

NO_REASON = "理由の記録がありません"
_PAST = re.compile(r"(過去|以前|当初|前の|旧|最初|元々|もともと)")
_STOP = {"なぜ", "どうして", "理由", "この", "仕様", "です", "ます", "ですか", "なの", "なった", "した", "教えて",
         "何", "いつ", "誰", "について", "という", "になった", "ください"}


def _tokens(text: str) -> set[str]:
    """日本語を簡易に語へ分ける（漢字・カタカナ・英数字の連続、およびその2文字片）。"""
    words = set(re.findall(r"[一-龥々]{2,}|[ァ-ヶー]{2,}|[A-Za-z0-9]{2,}", text or ""))
    grams = set()
    for w in words:
        if re.match(r"[一-龥々]", w) and len(w) > 2:
            grams.update(w[i:i + 2] for i in range(len(w) - 1))
    return (words | grams) - _STOP


def _req_text(r: dict) -> str:
    parts = [r.get("title", ""), r.get("body", "")]
    parts += [v.get("body", "") + v.get("title", "") for v in r.get("versions", [])]
    return " ".join(parts)


def resolve(p: dict, question: str) -> list[tuple[int, dict]]:
    """質問に関係する要件を、語の重なりで探す。ID指定があれば優先する。"""
    ids = re.findall(r"REQ-\d{3}", question.upper())
    if ids:
        found = [pj.get(p, "requirements", i) for i in ids]
        return [(100, r) for r in found if r]
    q = _tokens(question)
    scored = []
    for r in p["requirements"]:
        title_hit = len(q & _tokens(r.get("title", "")))
        body_hit = len(q & _tokens(_req_text(r)))
        score = title_hit * 3 + body_hit
        for d in p["decisions"]:
            if r["id"] in d.get("related_requirements", []):
                score += len(q & _tokens(d.get("topic", "")))
                if d.get("state") == "合意済み":  # 質問の語が採用案そのものなら、その判断の対象を優先する
                    score += 5 * len(q & _tokens(_adopted_label(d)))
        if score:
            scored.append((score, r))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return scored


def _adopted_label(d: dict) -> str:
    return next((o["label"] for o in d.get("options", []) if o["id"] == d.get("adopted")), "")


def _best_reason(agreed: list[dict], question: str) -> str | None:
    """質問に最も関係する判断の理由を選ぶ。別の論点の理由を流用しないよう、関連付いた判断の中からのみ選ぶ。"""
    q = _tokens(question)
    with_reason = [d for d in agreed if d.get("rationale")]
    if not with_reason:
        return None

    def score(item: tuple[int, dict]) -> tuple[int, int, int]:
        i, d = item
        label = _adopted_label(d)
        exact = 1 if label and label in question else 0  # 採用案の名称そのものを聞かれた場合を最優先
        return exact, len(q & _tokens(label + d.get("topic", ""))), i

    return max(enumerate(with_reason), key=score)[1]["rationale"]


def _decision_view(p: dict, d: dict) -> dict:
    adopted = next((o for o in d.get("options", []) if o["id"] == d.get("adopted")), None)
    return {
        "id": d["id"], "topic": d["topic"], "state": d["state"], "date": d.get("decided_on"),
        "decider": d.get("decider"), "confirmer": d.get("confirmer"),
        "adopted": adopted["label"] if adopted else None,
        "reason": d.get("rationale"), "hold_reason": d.get("hold_reason"), "confirmation": d.get("confirmation"),
        "options": [{"label": o["label"], "pros": o.get("pros"), "cons": o.get("cons"),
                     "rejected_reason": d.get("rejected_reasons", {}).get(o["id"]),
                     "adopted": o["id"] == d.get("adopted")} for o in d.get("options", [])],
        "citations": [{"text": e.get("quote"), "where": ev.citation(p, e), "verified": e.get("verified", False)}
                      for e in d.get("evidence", [])],
    }


def answer(p: dict, question: str) -> dict:
    """回答の構造データを返す（画面と文書で共用）。"""
    question = (question or "").strip()
    if not question:
        return {"status": "empty", "message": "質問を入力してください。"}
    hits = resolve(p, question)
    if not hits:
        return {"status": "not_found", "message": "この案件の登録情報に、質問に関係する要件が見つかりませんでした。",
                "note": "他の案件の情報や一般論では回答しません。"}
    top = hits[0][0]
    near = [r for s, r in hits if s >= max(top * 0.7, 1)]
    if len(near) > 1 and top < 100 and hits[1][0] >= top * 0.85:
        return {"status": "ambiguous", "message": "対象の要件を特定できません。どの要件について確認しますか。",
                "candidates": [{"id": r["id"], "title": r["title"], "status": r["status"]} for r in near[:5]]}
    r = hits[0][1]
    decisions = [d for d in p["decisions"] if r["id"] in d.get("related_requirements", [])]
    agreed = [d for d in decisions if d["state"] == "合意済み"]
    others = [d for d in decisions if d["state"] != "合意済み"]
    best = _best_reason(agreed, question)
    reasons = [best] if best else []
    trail = sorted((h for h in p["history"] if h.get("requirement_id") in pj.lineage(p, r["id"])),
                   key=lambda h: h.get("decided_on") or h.get("recorded_at") or "")
    corrected = {h.get("corrects") for h in trail if h.get("corrects")}
    if not reasons:
        reasons = [h["rationale"] for h in trail if h.get("rationale") and h.get("outcome") == "採用"]
    return {
        "status": "answered", "target": {"id": r["id"], "title": r["title"]},
        "wants_past": bool(_PAST.search(question)),
        "current": {"version": r["version"], "status": r["status"], "body": r.get("body"),
                    "scope": r.get("scope"), "notice": _current_notice(r)},
        "past_versions": [{"version": v.get("version"), "body": v.get("body"), "status": v.get("status"),
                           "change_reason": v.get("change_reason")} for v in r.get("versions", [])],
        "reason": reasons[-1] if reasons else NO_REASON,
        "reason_recorded": bool(reasons),
        "decisions": [_decision_view(p, d) for d in agreed],
        "not_agreed": [_decision_view(p, d) for d in others],
        "history": [{"id": h["id"], "meeting": h.get("meeting_id"), "date": h.get("decided_on"), "applied": h.get("applied_on"), "outcome": h["outcome"],
                     "trigger": h.get("trigger"), "before": h.get("before"), "after": h.get("after"),
                     "rationale": h.get("rationale"), "decider": h.get("decider"),
                     "superseded": h["id"] in corrected, "corrects": h.get("corrects")} for h in trail],
        "evidence": [{"text": e.get("quote"), "where": ev.citation(p, e), "verified": e.get("verified", False)}
                     for e in r.get("evidence", [])],
    }


def _current_notice(r: dict) -> str | None:
    if r["status"] == "廃止":
        ids = r.get("replaced_by") or ([r["merged_into"]] if r.get("merged_into") else [])
        return "この要件は廃止されています" + (f"（後継：{', '.join(ids)}）" if ids else "")
    if r["status"] != "合意済み":
        return f"現在の状態は「{r['status']}」で、合意済みではありません。"
    return None


def to_text(result: dict) -> str:
    """回答を文章にする（画面の補足、テスト用）。"""
    if result["status"] != "answered":
        return result.get("message", "")
    lines = [f"対象：{result['target']['id']} {result['target']['title']}（v{result['current']['version']}・{result['current']['status']}）",
             f"現在の条件：{result['current']['body']}", f"採用理由：{result['reason']}"]
    for d in result["decisions"]:
        lines.append(f"判断 {d['id']}（{d['date'] or '日付の記録なし'}・判断者 {d['decider'] or '記録なし'}）：{d['adopted']}")
        for o in d["options"]:
            if not o["adopted"]:
                lines.append(f"  比較した案：{o['label']}／不採用の理由：{o['rejected_reason'] or NO_REASON}")
    return "\n".join(lines)
