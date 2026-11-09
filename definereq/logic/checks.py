"""プログラムで行う確認（確認観点の切替・曖昧語・非機能・矛盾候補・残件・影響の候補）。

ここの結果は「検出できた範囲」であり、見落としがないことの保証ではない。
調査範囲を返して画面に表示する。AIを使わないので、料金は発生しない。
"""
from __future__ import annotations

import re

from .. import config
from .. import project as pj
from . import evidence as ev
from ..schema import NA


# ---- 分野別の確認観点 ----
def perspectives_for(domains: list[str]) -> list[dict]:
    """選んだ分野の観点を返す。複合案件では同じ topic の観点を1つにまとめる。"""
    cp = config.checkpoints()
    merged: dict[str, dict] = {}
    for item in cp["perspectives"]:
        if item["domain"] != "common" and item["domain"] not in domains:
            continue
        key = item["topic"] if item["domain"] != "common" else item["id"]
        if key in merged:
            merged[key]["domains"].append(item["domain"])
            merged[key]["merged_ids"].append(item["id"])
            continue
        merged[key] = {**item, "domains": [item["domain"]], "merged_ids": [item["id"]]}
    return list(merged.values())


def nfr_for(domains: list[str]) -> list[dict]:
    return [n for n in config.checkpoints()["nfr"] if set(n["domains"]) & set(domains)]


def chapters_for(domains: list[str]) -> list[tuple[str, str]]:
    cp = config.checkpoints()["domains"]
    out, seen = [], set()
    for d in domains:
        for ch in cp[d]["chapters"]:
            if ch not in seen:
                seen.add(ch)
                out.append((d, ch))
    return out


def corpus(p: dict) -> str:
    """案件内の主な本文（検索用）。"""
    parts = [str(v.get("value") or "") for v in p["profile"].values()]
    parts += [u["text"] for s in p["sources"] for u in s["units"] if u.get("target", True)]
    parts += [r.get("title", "") + " " + r.get("body", "") for r in p["requirements"]]
    return "\n".join(parts)


def suggest_traits(p: dict) -> list[str]:
    """本文に含まれる語から、深掘りする特徴の候補を示す（確定は人）。"""
    # 「給与計算は対象外」のような文の語を、案件の特徴として提案しない
    sentences = [s for s in re.split(r"[。\n]", corpus(p)) if not re.search(r"対象外|含まない|含めない|行わない|扱わない", s)]
    scope_out = (p["profile"].get("scope_out") or {}).get("value") or ""
    text = "\n".join(s for s in sentences if not (scope_out and s.strip() and s.strip() in scope_out))
    return [k for k, t in config.checkpoints()["traits"].items() if any(w in text for w in t["keywords"])]


def covered_questions(p: dict) -> set[str]:
    return {q.get("perspective_id") for q in p["questions"] if q.get("status") == "回答済み"}


def prep_questions(p: dict) -> list[dict]:
    """固定の観点と案件の特徴を組み合わせて質問候補を作る。回答済みの観点は繰り返さない。"""
    done = covered_questions(p)
    out = []
    for item in perspectives_for(p["domains"]):
        if done & set(item["merged_ids"]):
            continue
        out.append({"perspective_id": item["id"], "text": item["question"], "why": item["why"], "ask": item.get("ask"),
                    "category": item["category"], "prep": item.get("prep"), "domains": item["domains"]})
    traits = config.checkpoints()["traits"]
    for key in p.get("traits", []):
        t = traits.get(key)
        if not t:
            continue
        for i, q in enumerate(t["questions"], 1):
            pid = f"T-{key}-{i}"
            if pid not in done:
                out.append({"perspective_id": pid, "text": q, "why": f"案件の特徴「{t['label']}」の確認。", "ask": None,
                            "category": t["label"], "prep": None, "domains": []})
    return out


# ---- 曖昧な表現 ----
def find_vague(text: str) -> list[dict]:
    out = []
    for v in config.checkpoints()["vague"]:
        if v["word"] in (text or ""):
            out.append({"word": v["word"], "asks": v["asks"]})
    return out


def vague_requirements(p: dict) -> list[dict]:
    res = []
    for r in p["requirements"]:
        if r["status"] in ("廃止", "却下"):
            continue
        hits = find_vague(r.get("title", "") + " " + r.get("body", ""))
        if hits and not r.get("measures"):
            res.append({"requirement": r["id"], "title": r["title"], "hits": hits})
    return res


# ---- 非機能 ----
def nfr_overview(p: dict) -> list[dict]:
    """非機能の確認状況。項目ごとに 未確認 / 確認済み / 該当なし と根拠を示す。"""
    out = []
    for n in nfr_for(p["domains"]):
        st = p.get("nfr_status", {}).get(n["id"], {})
        reqs = [r["id"] for r in p["requirements"] if n["id"] in (r.get("nfr_tags") or []) and r["status"] not in ("廃止", "却下")]
        out.append({**n, "state": st.get("state", "未確認"), "note": st.get("note"), "requirements": reqs})
    return out


def overclaims(p: dict) -> list[dict]:
    """二重化・バックアップ等があるだけで条件達成と読める要件に注意を出す。"""
    out = []
    patterns = config.checkpoints()["overclaim"]
    for r in p["requirements"]:
        if r["status"] in ("廃止", "却下"):
            continue
        text = r.get("body", "") + " " + str(r.get("behavior") or "")
        for pat in patterns:
            if re.search(pat["pattern"], text) and not r.get("acceptance"):
                out.append({"requirement": r["id"], "title": r["title"], "note": pat["note"]})
                break
    return out


# ---- 矛盾候補 ----
def _texts(p: dict) -> list[tuple[str, str, str]]:
    items = []
    for r in p["requirements"]:
        if r["status"] not in ("廃止", "却下"):
            items.append((r["id"], r["title"], f"{r['title']} {r.get('body', '')}"))
    for c in p["changes"]:
        if c["status"] not in ("却下", "取り下げ", "反映済み"):
            items.append((c["id"], c["content"][:40], c["content"]))
    return items


def scan_conflicts(p: dict) -> dict:
    """矛盾の候補をプログラムで検出する。文章の一致では両立の可否まで判断しないため「候補」とする。

    同じ指標に異なる必要条件が登録されている場合のみ「明確な矛盾」とする。
    """
    found: list[dict] = []
    items = _texts(p)
    for pat in config.checkpoints()["conflict_patterns"]:
        a_hits = [i for i in items if re.search(pat["a"], i[2])]
        b_hits = [i for i in items if re.search(pat["b"], i[2])]
        for a in a_hits:
            for b in b_hits:
                if a[0] == b[0]:
                    continue
                pair = sorted((a[0], b[0]))
                found.append({"key": f"{pat['id']}:{pair[0]}:{pair[1]}", "kind": "前提確認が必要な候補",
                              "a": a[0], "b": b[0], "a_title": a[1], "b_title": b[1], "note": pat["note"]})
    metrics: dict[str, list] = {}
    for r in p["requirements"]:
        if r["status"] in ("廃止", "却下"):
            continue
        for m in r.get("measures", []):
            if m.get("kind") == "必要条件" and m.get("metric") and m.get("value") not in (None, ""):
                metrics.setdefault(m["metric"], []).append((r, m))
    for metric, rows in metrics.items():
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                (r1, m1), (r2, m2) = rows[i], rows[j]
                same_cond = (m1.get("condition") or "") == (m2.get("condition") or "")
                if r1["id"] != r2["id"] and same_cond and (m1["value"], m1.get("unit")) != (m2["value"], m2.get("unit")):
                    found.append({"key": f"metric:{metric}:{r1['id']}:{r2['id']}", "kind": "明確な矛盾",
                                  "a": r1["id"], "b": r2["id"], "a_title": r1["title"], "b_title": r2["title"],
                                  "note": f"同じ指標「{metric}」・同じ条件に異なる値があります（{m1['value']}{m1.get('unit') or ''} と {m2['value']}{m2.get('unit') or ''}）。"})
    uniq = {f["key"]: f for f in found}
    return {"candidates": list(uniq.values()),
            "scope": f"要件{sum(1 for r in p['requirements'] if r['status'] not in ('廃止', '却下'))}件・未反映の追加要望"
                     f"{sum(1 for c in p['changes'] if c['status'] not in ('却下', '取り下げ', '反映済み'))}件を、"
                     f"登録済みの{len(config.checkpoints()['conflict_patterns'])}種類の文型と数値の照合で確認しました。"
                     "文型にない矛盾は検出できません。未検出は矛盾がないことを意味しません。"}


def registered_conflict_keys(p: dict) -> set[str]:
    return {c.get("scan_key") for c in p["conflicts"] if c.get("scan_key")}


def adopt_conflict(p: dict, cand: dict) -> dict:
    return pj.add(p, "conflicts", {"kind": cand["kind"], "a": cand["a"], "b": cand["b"], "note": cand["note"],
                                   "applicability": None, "state": "未確認", "scan_key": cand.get("key"),
                                   "evidence": [], "origin": "プログラム検出", "detected_at": pj.now_iso(),
                                   "detected": {cand["a"]: _target_text(p, cand["a"]), cand["b"]: _target_text(p, cand["b"])}})


def _target_text(p: dict, item_id: str) -> dict:
    """検出時点の版と文章を残す。後で要件が変わっても、当時の指摘を説明できるようにする。"""
    found = pj.find_any(p, item_id)
    if not found:
        return {"version": None, "text": "（登録なし）"}
    col, item = found
    if col == "requirements":
        return {"version": item["version"], "text": f"{item['title']}：{item['body']}"}
    return {"version": None, "text": item.get("content", "")}


def conflict_view(p: dict, c: dict) -> dict:
    """当時の指摘と現在の内容を分けて返す。"""
    sides = []
    for item_id in (c["a"], c["b"]):
        then = (c.get("detected") or {}).get(item_id) or {"version": None, "text": "（検出時の記録なし）"}
        now = _target_text(p, item_id)
        version = (lambda v: f" v{v}" if v else "")
        sides.append({"id": item_id, "detected_version": version(then["version"]), "detected_text": then["text"],
                      "current_version": version(now["version"]), "current_text": now["text"], "changed": then["text"] != now["text"]})
    if c["state"] in ("解消", "矛盾なしと確認"):
        reason = c.get("resolution") or c.get("applicability") or "理由の記録がありません"
        summary = f"現在は{c['state']}：{reason}"
    else:
        summary = "現在も確認が必要です。"
    return {"sides": sides, "summary": summary}


# ---- 影響（登録された関係からたどれる範囲）----
def related_impacts(p: dict, req_ids: list[str]) -> list[dict]:
    """登録済みの関連をたどって影響候補を列挙する。ここに出ないものは「未調査」であり影響なしではない。"""
    out = []
    seen_reqs = set()
    for rid in req_ids:
        for lid in pj.lineage(p, rid):
            seen_reqs.add(lid)
        r = pj.get(p, "requirements", rid)
        if r:
            seen_reqs.update(r.get("related") or [])
    for r in p["requirements"]:
        if rid_related := (set(r.get("related") or []) & set(req_ids)):
            seen_reqs.add(r["id"])
            _ = rid_related
    for rid in sorted(seen_reqs - set(req_ids)):
        if pj.get(p, "requirements", rid):
            out.append({"area": "要件", "target": rid, "note": f"登録された関連：{pj.label_of(p, rid)}", "basis": "登録関係"})
    all_reqs = set(req_ids) | seen_reqs
    for s in p["scenarios"]:
        if all_reqs & set(s.get("related_requirements", [])):
            out.append({"area": "シナリオ", "target": s["id"], "note": f"関連シナリオ：{s['title']}", "basis": "登録関係"})
    for d in p["decisions"]:
        if all_reqs & set(d.get("related_requirements", [])):
            out.append({"area": "過去の判断", "target": d["id"], "note": f"関連する判断：{d['topic']}（{d['state']}）", "basis": "登録関係"})
    for rid in sorted(all_reqs):
        r = pj.get(p, "requirements", rid)
        if r and r.get("acceptance"):
            out.append({"area": "受入条件", "target": rid, "note": f"{rid} の受入条件（{len(r['acceptance'])}件）", "basis": "登録関係"})
    for d in p["shared_docs"]:
        if all_reqs & set(d.get("item_ids", [])):
            out.append({"area": "成果物", "target": d["id"], "note": f"共有資料 {d['title']} 第{d['version']}版", "basis": "登録関係"})
    return out


# ---- 数値条件の状態 ----
def measure_view(p: dict, r: dict, m: dict) -> dict:
    """数値の「要求値の合意」と「達成の検証」を分けて返す。値に合意しても、達成できるとは限らないため。"""
    if m.get("kind") == "現状の計測値":
        agreement = "対象外（現状の値）"
    else:
        linked = [d for d in p["decisions"] if d["state"] == "合意済み" and r["id"] in (d.get("related_requirements") or []) and pj.covers_version(d, r)]
        agreement = f"済み（{linked[0]['id']}）" if linked and r["status"] == "合意済み" else f"未合意（要件は{r['status']}）"
    if m.get("verify"):
        verify = m["verify"]
    elif m.get("status") in ("計測済み", "未計測"):
        verify = m["status"]
    else:
        verify = "未検証" if m.get("kind") == "必要条件" else "対象外"
    return {"agreement": agreement, "verify": verify}


# ---- 残件 ----
def backlog(p: dict) -> dict:
    """残件を分類して返す。分類別件数と、重複を除いた総件数（対象の数）を分けて返す。

    完成度の点数は作らない。未設定の担当・期限はAIで埋めない。
    """
    cats: dict[str, list[dict]] = {k: [] for k in BACKLOG_CATEGORIES}

    def push(cat, target, content, action, ask=None, due=None, page="requirements"):
        cats[cat].append({"category": cat, "target": target, "content": content, "action": action,
                          "ask": ask, "due": due, "page": page, "state": "未対応"})

    active = [r for r in p["requirements"] if r["status"] not in ("廃止", "却下")]
    for r in active:
        in_scope = r.get("scope") in ("今回必須", "今回できれば", "判断待ち")
        ask, due = r.get("confirm_with"), r.get("due")
        if in_scope and not r.get("acceptance") and r.get("acceptance") != NA:
            push("受入条件未設定", r["id"], r["title"], "受入条件を具体化する", ask, due, "refine")
        if in_scope and (not r.get("decider") or not r.get("due")) and r["status"] != "合意済み":
            miss = "判断者" if not r.get("decider") else "期限"
            if not r.get("decider") and not r.get("due"):
                miss = "判断者・期限"
            push("判断者・期限未設定", r["id"], f"{r['title']}（{miss}）", f"{miss}を人が決めて入力する", ask, due)
        for m in r.get("measures", []):
            if m.get("status") == "未計測":
                push("計測値未確認", r["id"], f"{r['title']}：{m.get('metric')}", "計測または確認する", ask, due, "refine")
        if r.get("open_area"):
            push("復旧・通信・責任分界未決", r["id"], f"{r['title']}：{r['open_area']}", "論点を確認する", ask, due)
        if r["status"] == "確認待ち":
            push("再確認待ち", r["id"], r["title"], "変更後の内容を関係者に確認する", ask, due, "baseline")
    for i in p["issues"]:
        if i["state"] != "結論あり":
            push("意見未調整", i["id"], i["topic"], "判断者と追加質問を確認する", i.get("ask"), i.get("due"), "issues")
    for c in p["changes"]:
        if c["status"] in ("受付", "調査中", "判断待ち"):
            push("変更調査待ち", c["id"], c["content"][:60], "影響を調査して判断を記録する", c.get("requester"), c.get("desired_by"), "changes")
    for d in p["decisions"]:
        if d["state"] in ("提案", "確認待ち", "保留"):
            push("再確認待ち", d["id"], f"{d['topic']}（{d['state']}）", "判断者の確認を記録する", d.get("decider"), None, "decisions")
    for d in p["decisions"]:
        if d["state"] == "合意済み" and any(ev.unconfirmed_speech(p, e) for e in d.get("evidence", [])):
            push("再確認待ち", d["id"], f"{d['topic']}（未確認の発言を根拠に含む）", "発言の話者と内容を確認する", d.get("decider"), None, "decisions")
    unique = {i["target"] for items in cats.values() for i in items}
    return {"categories": cats, "counts": {k: len(v) for k, v in cats.items()},
            "category_total": sum(len(v) for v in cats.values()), "unique_total": len(unique)}


def related_requirements(p: dict, target: str) -> list[str]:
    """残件や確認・依頼事項の対象（ID）から、関係する要件のIDを返す。

    対象が要件ならそのID。ほかの記録なら、その記録に登録された要件IDの参照だけを使う（名前の似かたでは結び付けない）。
    """
    reqs = {r["id"] for r in p["requirements"] if r["status"] not in ("廃止", "却下")}
    if target in reqs:
        return [target]
    for col in ("issues", "changes", "decisions", "actions", "questions", "risks", "conflicts", "scenarios"):
        item = next((x for x in p.get(col, []) if x.get("id") == target), None)
        if item is None:
            continue
        found: list[str] = []
        for key in ("related_requirements", "related", "requirements", "targets", "affected", "a", "b"):
            value = item.get(key)
            for v in value if isinstance(value, list) else [value]:
                if isinstance(v, str) and v in reqs and v not in found:
                    found.append(v)
        for imp in item.get("impacts") or []:  # 追加要望の影響の対象
            if imp.get("target") in reqs and imp["target"] not in found:
                found.append(imp["target"])
        return found
    return []


BACKLOG_CATEGORIES = ["受入条件未設定", "意見未調整", "判断者・期限未設定", "計測値未確認",
                      "復旧・通信・責任分界未決", "変更調査待ち", "再確認待ち"]


def next_actions(p: dict, limit: int = 5) -> list[dict]:
    """次の行動。優先順は固定の並び（重要度の点数は付けない）。"""
    acts = [a for a in p["actions"] if a["state"] in ("未着手", "対応中")]
    bl = backlog(p)
    picked = []
    for cat in ("変更調査待ち", "意見未調整", "再確認待ち", "受入条件未設定", "計測値未確認"):
        picked.extend(bl["categories"][cat][:2])
    return {"actions": acts, "suggested": picked[:limit]}  # type: ignore[return-value]
