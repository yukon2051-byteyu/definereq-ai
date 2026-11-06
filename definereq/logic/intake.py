"""AI候補の反映先。候補の種類に合う場所へ、人の操作で反映する。

守ること
- 反映は人の操作だけで行う。AIの出力だけで要件や合意は確定しない
- 「決定」の候補は判断記録の下書きになるだけで、合意は成立しない
- 既存の要件は書き換えない（補足・変更は continuity.intake_candidate で追加要望として受け付ける）
- 分類は推測として提示し、人が確認する。原文にない動作は加えない
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .. import project as pj
from ..project import PROFILE_FIELDS
from . import agreement as ag


@dataclass(frozen=True)
class Route:
    kind: str     # 反映の種類
    button: str   # ボタンの言葉
    page: str | None  # 反映先の画面


_QUESTION = Route("question", "会議の質問に追加", "prep")
_CONFIRM = Route("confirm", "確認事項に追加", "prep")
_REQUIREMENT = Route("requirement", "要件候補として採用", "requirements")
_RISK = Route("risk", "リスク候補として追加", "risks")
_NOTE = Route("note", "記録として残す", None)

ROUTES = {
    "質問": _QUESTION, "議題": Route("agenda", "議題に追加", "prep"), "必要資料": Route("material", "資料の依頼事項に追加", "prep"),
    "今回決めたいこと": Route("decide_today", "今回決めたいことに追加", "prep"),
    "不足情報": _CONFIRM, "未回答": _CONFIRM, "保留": _CONFIRM, "未確認の観点": _CONFIRM,
    "次の行動": Route("action", "確認・依頼事項に追加", "overview"),
    "要望": _REQUIREMENT, "要件": _REQUIREMENT, "制約": _REQUIREMENT,
    "リスク": _RISK, "リスク候補": _RISK,
    "決定": Route("decision", "判断記録の下書きに追加", "decisions"),
    "意見の違い": Route("issue", "意見調整に追加", "issues"),
    "案件情報": Route("profile", "案件情報へ反映", "profile"),
}


def route_for(kind: str) -> Route:
    return ROUTES.get(kind, _NOTE)


def _resolve(c: dict, item_id: str | None, route: Route, actor: str, label: str) -> None:
    c.update(state="採用", resolved_as=item_id, resolved_by=actor, resolved_page=route.page, resolved_label=label)


def _append_line(p: dict, key: str, text: str) -> None:
    lines = p["prep"].setdefault(key, [])
    if text not in lines:
        lines.append(text)


def apply(p: dict, cand_id: str, owner: str | None = None, due: str | None = None, actor: str = "利用者", meeting_id: str | None = None) -> str:
    """候補を種類に合う場所へ反映し、反映先の説明を返す。要件と案件情報は専用の処理を使う。"""
    c = pj.require(p, "candidates", cand_id)
    if c["state"] != "候補" and c["state"] != "要再確認":
        raise ValueError("この候補はすでに処理されています。")
    route = route_for(c["kind"])
    if route.kind in ("requirement", "profile"):
        raise ValueError("この候補は内容を確認してから反映してください。")
    base = {"evidence": c.get("evidence", []), "meeting_id": meeting_id, "from_candidate": c["id"]}
    item_id, label = None, route.button.replace("に追加", "")
    if route.kind in ("question", "confirm"):
        item = pj.add(p, "questions", {"text": c["text"], "why": c.get("detail"), "ask": owner or c.get("ask"), "priority": None, "status": "未質問", "answer": None, "perspective_id": None,
                                       "category": "確認事項" if route.kind == "confirm" else "質問", **base})
        item_id = item["id"]
    elif route.kind == "agenda":
        _append_line(p, "agenda", c["text"])
    elif route.kind == "material":
        _append_line(p, "materials", c["text"])
    elif route.kind == "decide_today":
        _append_line(p, "decide_today", c["text"])
    elif route.kind == "action":
        item_id = pj.add(p, "actions", {"content": c["text"], "owner": owner or c.get("ask"), "due": due, "related": [], "state": "未着手", "from_candidate": c["id"], "meeting_id": meeting_id})["id"]
    elif route.kind == "risk":
        item_id = pj.add(p, "risks", {"content": c["text"], "nature": "AI候補", "condition": None, "impact": None, "uncertainty": c.get("detail"), "mitigation": None, "ask": c.get("ask"),
                                      "action": None, "state": "未対応", "evidence": c.get("evidence", []), "related_requirements": [], "from_candidate": c["id"]})["id"]
    elif route.kind == "decision":
        # 下書きにするだけで、合意にはしない。判断者・判断日・採用案は人が記録する
        item_id = ag.new_decision(p, c["text"], [{"id": "A", "label": c["text"], "pros": None, "cons": None}], evidence=c.get("evidence", []), meeting_id=meeting_id, from_candidate=c["id"])["id"]
    elif route.kind == "issue":
        item_id = pj.add(p, "issues", {"topic": c["text"], "opinions": [], "common_goal": None, "conflict_condition": c.get("detail"), "options": [], "decider": None, "ask": c.get("ask"),
                                       "extra_questions": [], "conclusion": None, "state": "未調整", "evidence": c.get("evidence", []), "related_requirements": []})["id"]
    _resolve(c, item_id, route, actor, label)
    pj.log(p, f"候補 {cand_id} を「{label}」へ反映しました（{actor}）")
    return label


KIND_RULES = (("連携", r"連携|CSV|csv|API|外部システム|取り込|取込|出力"), ("画面・帳票", r"画面|帳票|レイアウト"), ("性能", r"秒|応答|性能|速度"), ("復旧", r"復旧|バックアップ|RTO|RPO"),
              ("可用性", r"停止|無停止|稼働率"), ("移行", r"移行|切替"), ("認証", r"認証|ログイン"), ("通信", r"通信|ポート"), ("接続", r"回線|拠点間"), ("データ", r"保存期間|データの保持"), ("運用", r"運用|保守"))
DOMAIN_RULES = (("network", r"回線|通信|ネットワーク|VPN|ポート"), ("infra", r"サーバー|クラウド|バックアップ|基盤"))
TARGET_WORDS = r"従業員|社員|上長|管理者|人事|経理|担当者|申請者|承認者"


def suggest(p: dict, c: dict) -> dict:
    """要件へ採用するときの分類候補。ルールによる推測であり、確定ではない。"""
    text = f"{c['text']} {c.get('detail') or ''}"
    kind = next((k for k, pat in KIND_RULES if re.search(pat, text)), "機能")
    if len(p["domains"]) == 1:
        domain = p["domains"][0]
    else:
        domain = next((d for d, pat in DOMAIN_RULES if d in p["domains"] and re.search(pat, text)), p["domains"][0])
    users = re.findall(TARGET_WORDS, text)
    open_item = c.get("detail") if c.get("detail") and re.search(r"未確認|未定|不明", c["detail"]) else None
    return {"domain": domain, "kind": kind, "target": "、".join(dict.fromkeys(users)) or (p["profile"].get("users") or {}).get("value"),
            "data_io": c["text"] if kind == "連携" else None, "open_items": open_item, "background": (p["profile"].get("background") or {}).get("value"), "basis": "ルールによる推測"}


def split_proposal(text: str) -> list[str]:
    """複数の動作を含む文の分割案。原文を切り分けるだけで、動作を付け足さない。"""
    m = re.match(r"(.+?)し、(.+)", text.strip().rstrip("。"))
    if not m or len(m.group(1)) < 3 or len(m.group(2)) < 3:
        return []
    return [f"{m.group(1)}する", m.group(2)]


def adopt_requirement(p: dict, cand_id: str, fields: dict | None = None, parts: list[str] | None = None, actor: str = "利用者", meeting_id: str | None = None) -> list[dict]:
    """候補を要件（下書き）にする。分割案を選んだ場合は複数作り、全てに元の候補と引用を残す。既存の要件は変更しない。"""
    c = pj.require(p, "candidates", cand_id)
    if c["state"] not in ("候補", "要再確認"):
        raise ValueError("この候補はすでに処理されています。")
    fields = {k: v for k, v in (fields or {}).items() if v not in (None, "")}
    texts = [t.strip() for t in parts or [] if t.strip()] or [c["text"]]
    created = [pj.add(p, "requirements", pj.new_requirement(**{"title": t[:60], "body": t, "evidence": c.get("evidence", []), "status": "下書き", "author": "AI候補を人が採用",
                                                                "from_candidate": c["id"], "meeting_id": meeting_id, **fields})) for t in texts]
    _resolve(c, created[0]["id"], route_for(c["kind"]), actor, "要件")
    c["resolved_items"] = [r["id"] for r in created]
    pj.log(p, f"候補 {cand_id} を要件 {'、'.join(c['resolved_items'])} として採用しました（{actor}）")
    return created


def profile_suggestions(p: dict) -> list[dict]:
    """案件情報への反映候補。文書の背景や目的は案件情報を参照するため、入力場所の違いをここでつなぐ。"""
    out = []
    pr = p["prep"]
    for field, value, origin in (("background", pr.get("understanding"), "会議準備の「現時点の理解」"), ("purpose", pr.get("purpose"), "会議準備の「会議の目的」")):
        if value:
            out.append({"id": f"prep:{field}", "field": field, "value": value, "origin": origin, "certainty": "本人申告"})
    names = {v: k for k, v in PROFILE_FIELDS.items()}
    for c in p["candidates"]:
        if c["kind"] == "案件情報" and c["state"] == "候補":
            field = names.get(c.get("ask") or "") or "background"
            out.append({"id": c["id"], "field": field, "value": c["text"], "origin": f"AI候補 {c['id']}（{c.get('origin')}）", "certainty": "未確認"})
    for s in out:
        s["label"] = PROFILE_FIELDS[s["field"]]
        s["current"] = p["profile"][s["field"]]["value"]
    return [s for s in out if s["current"] != s["value"]]


def apply_profile(p: dict, suggestion: dict, mode: str = "set", actor: str = "利用者") -> None:
    """人の確認後に案件情報へ反映する。内容が異なるときは、mode の指定なしでは上書きしない。"""
    cur = p["profile"][suggestion["field"]]
    if cur["value"] and mode == "set":
        raise ValueError("すでに内容があります。差分を確認し、置き換えるか追記するかを選んでください。")
    value = f"{cur['value']}\n{suggestion['value']}" if mode == "append" else suggestion["value"]
    cur.update(value=value, certainty=suggestion["certainty"], origin=suggestion["origin"])
    c = pj.get(p, "candidates", suggestion["id"])
    if c:
        _resolve(c, None, ROUTES["案件情報"], actor, "案件情報")
    pj.log(p, f"案件情報「{suggestion['label']}」を更新しました（出所：{suggestion['origin']}）")
