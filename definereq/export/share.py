"""共有資料の内容を組み立てる（Word・画面プレビューで共用）。

同じ案件データから3種類の資料を作る。出力の前に対象を確認できるよう、選択肢を Options で受け取る。
- 内部メモは既定で対象外
- 録画全文や発言は自動掲載しない（人が選んだ引用だけ）
- 決定・提案・確認待ちを区別する
- 送付しても合意にはしない
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import project as pj
from .. import schema
from ..logic import checks
from ..logic import evidence as ev
from ..project import display


@dataclass
class Options:
    doc_type: str = "meeting"
    include_internal: bool = False
    include_drafts: bool = True
    quote_keys: set[str] = field(default_factory=set)   # 掲載を選んだ引用（"項目ID:番号"）
    change_id: str | None = None
    exclude_ids: set[str] = field(default_factory=set)  # 出力前に外した項目


@dataclass
class Section:
    heading: str
    level: int = 1
    paragraphs: list[str] = field(default_factory=list)
    table: dict | None = None  # {"columns": [...], "rows": [[...]], "widths": [...]}


def option_verdict(dec: dict, option: dict) -> str:
    """案の採否を短い言葉で返す。判断の記録がなければ採否を決めつけない。"""
    if dec.get("adopted"):
        return "採用" if option["id"] == dec["adopted"] else "不採用"
    return "保留" if dec.get("state") == "保留" else "未判断"


def _quotes(p: dict, item: dict, opt: Options) -> list[str]:
    out = []
    for i, e in enumerate(item.get("evidence") or []):
        if f"{item['id']}:{i}" in opt.quote_keys:
            out.append(f"「{e.get('quote')}」（{ev.citation(p, e)}）")
    return out


def quotable(p: dict) -> list[dict]:
    """掲載を選べる引用の一覧。"""
    out = []
    for col in ("requirements", "decisions", "changes"):
        for item in p[col]:
            for i, e in enumerate(item.get("evidence") or []):
                out.append({"key": f"{item['id']}:{i}", "item": item["id"], "quote": e.get("quote"),
                            "where": ev.citation(p, e), "is_recording": e["source_id"].startswith("REC")})
    return out


def _active(p: dict, opt: Options) -> list[dict]:
    rows = [r for r in p["requirements"] if r["status"] not in ("却下", "廃止") and r["id"] not in opt.exclude_ids]
    if not opt.include_drafts:
        rows = [r for r in rows if r["status"] != "下書き"]
    return rows


def _status_label(r: dict) -> str:
    if r["status"] == "合意済み":
        return "決定（合意済み）"
    if r["status"] in ("下書き", "提案"):
        return "提案"
    return "確認待ち" if r["status"] == "確認待ち" else f"確認待ち（{r['status']}）"


def _dec_table(p: dict, opt: Options, states: tuple[str, ...]) -> dict:
    rows = []
    for d in p["decisions"]:
        if d["state"] in states and d["id"] not in opt.exclude_ids:
            adopted = next((o["label"] for o in d["options"] if o["id"] == d.get("adopted")), "未定")
            rows.append([d["id"], d["topic"], adopted, d.get("rationale") or d.get("hold_reason") or "理由の記録がありません",
                         display(d.get("decider")), display(d.get("decided_on")), d["state"]])
    return {"columns": ["ID", "論点", "採用案", "理由", "判断者", "判断日", "状態"], "rows": rows, "widths": [1.5, 3.5, 3, 4.5, 1.8, 1.8, 1.5]}


def _qa_rows(p: dict, opt: Options) -> list[list[str]]:
    rows = []
    for q in p["questions"]:
        if q["status"] in ("未質問", "回答待ち") and q["id"] not in opt.exclude_ids:
            rows.append([f"確認-{q['id']}", q["text"], display(q.get("ask")), ""])
    return rows


def _open_rows(p: dict, opt: Options) -> list[list[str]]:
    rows = []
    bl = checks.backlog(p)
    for cat, items in bl["categories"].items():
        for it in items:
            if it["target"] not in opt.exclude_ids:
                rows.append([it["target"], cat, it["content"], display(it.get("ask")), display(it.get("due"))])
    return rows


def _action_rows(p: dict) -> list[list[str]]:
    return [[a["id"], a["content"], display(a.get("owner")), display(a.get("due")), a["state"]] for a in p["actions"]
            if a["state"] in ("未着手", "対応中")]


def _req_rows(reqs: list[dict]) -> list[list[str]]:
    return [[r["id"], f"v{r['version']}", display(r.get("kind")), r["title"], r["body"], display(r.get("scope")), _status_label(r)] for r in reqs]


REQ_COLS = {"columns": ["ID", "版", "種類", "名称", "内容", "範囲", "状態"], "widths": [1.9, 0.8, 1.5, 3, 5.6, 1.6, 2]}


def _measures(reqs: list[dict]) -> list[list[str]]:
    rows = []
    for r in reqs:
        for m in r.get("measures", []):
            rows.append([r["id"], m.get("metric", ""), f"{display(m.get('value'))}{m.get('unit') or ''}",
                         m.get("kind", ""), display(m.get("origin")), display(m.get("condition")), display(m.get("basis")), display(m.get("status"))])
    return rows


def build_meeting(p: dict, opt: Options) -> list[Section]:
    reqs = _active(p, opt)
    sections = [
        Section("目的", paragraphs=[display(p["prep"].get("purpose") if p["prep"].get("purpose") else p["profile"]["purpose"]["value"])]),
        Section("当方の理解", paragraphs=[display(p["prep"].get("understanding") or p["profile"]["request"]["value"])]),
        Section("決定事項", table=_dec_table(p, opt, ("合意済み",))),
        Section("提案・確認待ちの事項", paragraphs=["以下は決定ではありません。ご確認をお願いします。"],
                table={**REQ_COLS, "rows": _req_rows([r for r in reqs if r["status"] != "合意済み"])}),
        Section("未決事項", table={"columns": ["対象", "分類", "内容", "確認相手", "期限"], "rows": _open_rows(p, opt), "widths": [1.6, 3, 7, 2, 1.8]}),
        Section("ご質問", table={"columns": ["確認ID", "質問", "確認相手", "回答欄"], "rows": _qa_rows(p, opt), "widths": [2, 7, 2.5, 4]}),
        Section("次の行動", table={"columns": ["ID", "内容", "担当", "期限", "状態"], "rows": _action_rows(p), "widths": [1.5, 8, 2, 2, 1.5]}),
    ]
    quotes = [q for r in reqs for q in _quotes(p, r, opt)]
    if quotes:
        sections.insert(2, Section("確認に用いた引用", paragraphs=quotes))
    return sections


def build_change(p: dict, opt: Options) -> list[Section]:
    chg = pj.require(p, "changes", opt.change_id) if opt.change_id else (p["changes"][-1] if p["changes"] else None)
    if chg is None:
        return [Section("追加要望", paragraphs=["追加要望は登録されていません。"])]
    dec = pj.get(p, "decisions", chg.get("decision_id")) if chg.get("decision_id") else next(
        (d for d in p["decisions"] if chg["id"] in d.get("related_changes", [])), None)
    before_after = []
    for rid in chg.get("related_requirements", []):
        r = pj.get(p, "requirements", rid)
        if not r:
            continue
        # 却下の履歴には変更前後がないため、実際に反映した履歴だけを見る
        his = [h for h in p["history"] if h.get("requirement_id") == rid and h.get("change_id") == chg["id"] and h.get("after")]
        if his:
            before_after.append([rid, his[-1].get("before") or "", his[-1]["after"]])
        else:
            note = "（変更なし）" if chg["status"] == "反映済み" else "（未反映）"
            before_after.append([rid, r["body"], note])
    conflicts = [[c["id"], c["kind"], pj.label_of(p, c["a"]), pj.label_of(p, c["b"]), c["note"], c["state"]]
                 for c in p["conflicts"] if chg["id"] in (c["a"], c["b"]) or set(chg.get("related_requirements", [])) & {c["a"], c["b"]}]
    options_rows = []
    if dec:
        for o in dec["options"]:
            verdict = option_verdict(dec, o)
            options_rows.append([o["label"], display(o.get("pros")), display(o.get("cons")), verdict,
                                 display(dec.get("rationale")) if verdict == "採用" else display(dec.get("rejected_reasons", {}).get(o["id"]))])
    conclusion = "判断は記録されていません（判断待ち）。"
    if dec:
        adopted = next((o["label"] for o in dec["options"] if o["id"] == dec.get("adopted")), None)
        conclusion = f"状態：{dec['state']}／採用案：{adopted or '未定'}／判断者：{display(dec.get('decider'))}／判断日：{display(dec.get('decided_on'))}"
    return [
        Section("背景", paragraphs=[f"{chg['id']}（要望者：{display(chg.get('requester'))}、受付日：{display(chg.get('requested_at'))}）", display(chg.get("background"))]),
        Section("要望内容", paragraphs=[chg["content"]] + _quotes(p, chg, opt)),
        Section("変更前後", table={"columns": ["要件", "変更前", "変更後"], "rows": before_after, "widths": [1.6, 7, 7]}),
        Section("影響", paragraphs=[f"未調査の領域：{'、'.join(a for a in schema.IMPACT_AREAS if a not in chg['surveyed_areas']) or 'なし'}"],
                table={"columns": ["領域", "対象", "内容", "根拠の区分"], "rows": [[i["area"], display(i.get("target")), i["note"], i["basis"]] for i in chg["impacts"]], "widths": [2, 2, 8.5, 3]}),
        Section("矛盾の確認", table={"columns": ["ID", "区分", "対象A", "対象B", "当時の指摘", "状態"], "rows": conflicts, "widths": [1.5, 2.5, 3, 3, 4.5, 1.5]}),
        Section("選択肢", table={"columns": ["案", "利点", "懸念", "採否", "理由"], "rows": options_rows, "widths": [3.5, 3.5, 3.5, 1.4, 4.1]}),
        Section("ご判断いただく事項", table={"columns": ["確認ID", "質問", "確認相手", "回答欄"], "rows": [[f"確認-{chg['id']}", "上記の内容で進めてよいかご判断ください。", display(chg.get("requester")), ""]], "widths": [2, 7, 2.5, 4]}),
        Section("結論", paragraphs=[conclusion]),
    ]


def build_spec(p: dict, opt: Options) -> list[Section]:
    reqs = _active(p, opt)
    prof = p["profile"]
    pending = [r for r in reqs if r["status"] != "合意済み"]
    sections = [Section("この文書について", paragraphs=[
        "本書は登録された情報から作成した下書きを含みます。" if pending else "本書は合意済みの要件から作成しました。",
        f"確認待ちの要件が {len(pending)} 件あります。該当する行の状態欄を確認してください。" if pending else "記載の範囲について、完全性や正しさを保証するものではありません。"])]
    sections.append(Section("背景・目的", paragraphs=[f"背景：{display(prof['background']['value'])}", f"目的：{display(prof['purpose']['value'])}", f"課題：{display(prof['problem']['value'])}", f"期待する成果：{display(prof['outcome']['value'])}"]))
    sections.append(Section("関係者", table={"columns": ["ID", "氏名・役割", "所属", "立場", "判断・確認できる範囲"], "rows": [[s["id"], s["name"], display(s.get("org")), display(s.get("position")), display(s.get("authority"))] for s in p["stakeholders"]], "widths": [1.5, 3, 3, 3, 5.5]}))
    sections.append(Section("用語", table={"columns": ["用語", "意味"], "rows": [[g["term"], g["meaning"]] for g in p["glossary"]], "widths": [4, 12]}))
    sections.append(Section("範囲・対象外", paragraphs=[f"範囲：{display(prof['scope_in']['value'])}", f"対象外：{display(prof['scope_out']['value'])}"],
                            table={"columns": ["区分", "要件", "理由", "判断者"], "rows": [[r.get("scope"), f"{r['id']} {r['title']}", display(r.get("scope_reason")), display(r.get("scope_decider"))] for r in reqs], "widths": [2.5, 6, 5.5, 2]}))
    sections.append(Section("現状・想定", paragraphs=[display(prof["current"]["value"])]))
    # 分野別の章
    sections.append(Section("要件", paragraphs=["対象分野に応じて章を切り替えています。"]))
    used: set[str] = set()
    labels = {d: schema.DOMAINS[d] for d in schema.DOMAINS}
    for d, chapter in checks.chapters_for(p["domains"]):
        rows = [r for r in reqs if r.get("kind") == chapter and r["id"] not in used and (r.get("domain") in (d, None) or len(p["domains"]) > 1)]
        used.update(r["id"] for r in rows)
        sections.append(Section(f"{labels[d]}：{chapter}", level=2, table={**REQ_COLS, "rows": _req_rows(rows)}))
    rest = [r for r in reqs if r["id"] not in used]
    if rest:
        title = "共通・分野をまたぐ要件" if len(p["domains"]) > 1 else "その他の要件"
        sections.append(Section(title, level=2, table={**REQ_COLS, "rows": _req_rows(rest)}))
    sections.append(Section("数値条件と区分", paragraphs=["必要条件・現状の計測値・仮定・実現方式の候補・人が確定した設計制約を区別しています。出所は誰が示した値か、状態はその値の確認が済んだかを表します。"],
                            table={"columns": ["要件", "指標", "値", "区分", "出所", "測定条件", "根拠", "状態"], "rows": _measures(reqs), "widths": [1.4, 2.7, 1.8, 2.2, 1.9, 2.6, 2.6, 1.3]}))
    nfr_rows = [[n["label"], n["state"], display(n.get("note")), "、".join(n["requirements"]) or "未設定"] for n in checks.nfr_overview(p)]
    sections.append(Section("非機能", table={"columns": ["項目", "状態", "補足", "関連要件"], "rows": nfr_rows, "widths": [3, 2, 8, 3]}))
    sections.append(Section("シナリオ", table={"columns": ["ID", "名称", "種類", "開始条件", "流れ", "終了・失敗時", "関連要件"], "rows": [[s["id"], s["title"], s.get("kind", ""), display(s.get("start")), " → ".join(s.get("steps", [])), display(s.get("end")), "、".join(s.get("related_requirements", []))] for s in p["scenarios"]], "widths": [1.4, 3, 1.4, 2.6, 4.2, 2.4, 1.5]}))
    op_kinds = ("運用", "移行")
    sections.append(Section("運用・移行", table={**REQ_COLS, "rows": _req_rows([r for r in reqs if r.get("kind") in op_kinds])}))
    acc_rows = [[r["id"], a.get("given", ""), a.get("when", ""), a.get("then", ""), a.get("how", "")] for r in reqs for a in r.get("acceptance", []) if isinstance(a, dict)]
    sections.append(Section("受入条件", table={"columns": ["要件", "前提", "条件", "期待結果", "確認方法"], "rows": acc_rows, "widths": [1.5, 4, 3.5, 4, 3]}))
    sections.append(Section("制約", paragraphs=[display(prof["constraints"]["value"])]))
    sections.append(Section("未決事項", table={"columns": ["対象", "分類", "内容", "確認相手", "期限"], "rows": _open_rows(p, opt), "widths": [1.6, 3, 7, 2, 1.8]}))
    sections.append(Section("リスク", table={"columns": ["ID", "内容", "条件", "影響", "対策", "状態"], "rows": [[r["id"], r["content"], display(r.get("condition")), display(r.get("impact")), display(r.get("mitigation")), r["state"]] for r in p["risks"]], "widths": [1.4, 5, 3, 3, 3, 1.5]}))
    sections.append(Section("合意", paragraphs=[
        "ここに記載の合意は利用者が記録したものであり、電子署名ではありません。"], table=_dec_table(p, opt, ("合意済み",))))
    hist = [[h["id"], h.get("requirement_id") or "", display(h.get("decided_on")), h["outcome"], h.get("trigger", ""), h.get("rationale") or "理由の記録がありません", display(h.get("decider"))] for h in p["history"]]
    sections.append(Section("変更履歴", table={"columns": ["ID", "要件", "判断日", "結果", "きっかけ", "理由", "判断者"], "rows": hist, "widths": [1.4, 1.4, 1.8, 1.2, 4, 5, 2]}))
    if opt.include_internal:
        notes = [f"{r['id']}：{r['internal_note']}" for r in reqs if r.get("internal_note")]
        sections.append(Section("内部メモ", paragraphs=notes or ["なし"]))
    return sections


BUILDERS = {"meeting": build_meeting, "change": build_change, "spec": build_spec}


def build(p: dict, opt: Options) -> list[Section]:
    return BUILDERS[opt.doc_type](p, opt)


def item_ids(p: dict, opt: Options) -> list[str]:
    ids = [r["id"] for r in _active(p, opt)]
    ids += [d["id"] for d in p["decisions"] if d["id"] not in opt.exclude_ids]
    return ids


def latest_doc(p: dict, doc_type: str) -> dict | None:
    """発行済みの資料のうち、最新の版。"""
    docs = [d for d in p["shared_docs"] if d["doc_type"] == doc_type]
    return docs[-1] if docs else None


def options_for(doc: dict) -> Options:
    """発行時と同じ既定の範囲で出力する設定。"""
    return Options(doc_type=doc["doc_type"], change_id=doc.get("change_id"))


def doc_is_current(p: dict, doc: dict) -> bool:
    """発行時から内容が変わっていないか。"""
    return doc.get("fingerprint") == pj.fingerprint([s.__dict__ for s in build(p, options_for(doc))])


def register_doc(p: dict, opt: Options, title: str, actor: str = "利用者") -> dict:
    """出力した資料を記録する。版が上がる。送付しても合意にはならない。"""
    version = 1 + sum(1 for d in p["shared_docs"] if d["doc_type"] == opt.doc_type)
    sections = build(p, opt)
    return pj.add(p, "shared_docs", {
        "doc_type": opt.doc_type, "title": title, "version": version, "issued_at": pj.now_iso(), "issued_by": actor,
        "item_ids": item_ids(p, opt), "fingerprint": pj.fingerprint([s.__dict__ for s in sections]),
        "sent": False, "scope_note": "内部メモ含む" if opt.include_internal else "内部メモ除外", "change_id": opt.change_id,
    })


def record_response(p: dict, doc_id: str, item_id: str, content: str, respondent: str | None = None,
                    answered_on: str | None = None) -> dict:
    """回答は資料の版と項目IDに関連付ける。回答しても自動で合意にはならない。"""
    doc = pj.require(p, "shared_docs", doc_id)
    return pj.add(p, "responses", {"doc_id": doc_id, "doc_version": doc["version"], "item_id": item_id,
                                   "content": content, "respondent": respondent, "answered_on": answered_on})
