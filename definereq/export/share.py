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
    """画面と同じ状態名を使う。"""
    return r["status"]


def _dec_table(p: dict, opt: Options, states: tuple[str, ...]) -> dict:
    rows = []
    for d in p["decisions"]:
        if d["state"] in states and d["id"] not in opt.exclude_ids:
            rows.append([d["id"], d["topic"], _adopted(d), display(d.get("decided_on")), d["state"]])
    return {"columns": ["ID", "論点", "採用案", "判断日", "状態"], "rows": rows, "widths": [1.8, 6, 5, 2.2, 2], "empty": "記録された判断はまだありません。"}


def _adopted(d: dict) -> str:
    return next((o["label"] for o in d["options"] if o["id"] == d.get("adopted")), "未定")


def _dec_details(p: dict, opt: Options, states: tuple[str, ...]) -> list[Section]:
    """判断の理由などの長文は、細い列に入れず判断ごとに書く。"""
    out = []
    for d in p["decisions"]:
        if d["state"] in states and d["id"] not in opt.exclude_ids:
            versions = d.get("target_versions") or {}
            targets = "、".join(f"{pj.label_of(p, r)}（v{versions[r]}）" if r in versions else pj.label_of(p, r) for r in d.get("related_requirements", [])) or "要件を伴わない判断"
            out.append(Section(f"{d['id']} {d['topic']}", level=3, paragraphs=[f"採用案：{_adopted(d)}", f"理由：{d.get('rationale') or d.get('hold_reason') or '理由の記録がありません'}", f"対象の要件：{targets}",
                                                                              f"判断者：{display(d.get('decider'))}／確認者：{display(d.get('confirmer'))}／判断日：{display(d.get('decided_on'))}"]))
    return out


OPEN_COLS = {"columns": ["ID", "種別", "内容", "関連要件", "確認相手", "期限", "状態"], "widths": [1.8, 2.2, 5.6, 1.9, 2, 2.2, 1.6]}


def open_items(p: dict, opt: Options | None = None, skip: tuple[str, ...] = ()) -> dict:
    """案件に登録された未解決事項を1か所にまとめる。

    対象：質問・確認事項、要件の未確認事項、判断待ち・保留、未調整の論点、対応中の追加要望、未確認の矛盾候補、未完了の依頼。
    同じ内容は1行にまとめ、関連要件を統合する。対象から外した要件だけに関連する項目は除外し、理由を返す。
    """
    opt = opt or Options(doc_type="spec")
    raw = []

    def add(item_id, kind, text, related, ask, due, state):
        if text and kind not in skip:
            raw.append({"id": item_id, "kind": kind, "content": str(text).strip(), "related": [r for r in related or [] if str(r).startswith("REQ-")], "ask": ask, "due": due, "state": state})

    for q in p["questions"]:
        if q["status"] in ("未質問", "回答待ち"):
            add(q["id"], q.get("category") or "質問", q["text"], q.get("related_requirements"), q.get("ask"), None, q["status"])
    for r in p["requirements"]:
        if r["status"] not in ("廃止", "却下"):
            for key in ("open_items", "open_area"):
                if r.get(key) and r[key] != schema.NA:
                    add(r["id"], "要件の未確認事項", r[key], [r["id"]], r.get("confirm_with"), r.get("due"), "未確認")
    for d in p["decisions"]:
        if d["state"] in ("提案", "確認待ち", "保留"):
            add(d["id"], "保留" if d["state"] == "保留" else "判断待ち", f"{d['topic']}" + (f"（{d['hold_reason']}）" if d.get("hold_reason") else ""), d.get("related_requirements"), d.get("decider"), None, d["state"])
    for i in p["issues"]:
        if i["state"] != "結論あり":
            add(i["id"], "意見の調整", i["topic"], i.get("related_requirements"), i.get("ask"), i.get("due"), i["state"])
    for c in p["changes"]:
        if c["status"] in ("受付", "調査中", "判断待ち"):
            add(c["id"], "追加要望", c["content"], c.get("related_requirements"), c.get("requester"), c.get("desired_by"), c["status"])
    for c in p["conflicts"]:
        if c["state"] in ("未確認", "確認中"):
            add(c["id"], "矛盾の候補", c["note"], [c["a"], c["b"]], None, None, c["state"])
    for a in p["actions"]:
        if a["state"] in ("未着手", "対応中"):
            add(a["id"], "確認・依頼", a["content"], a.get("related"), a.get("owner") or a.get("ask"), a.get("due"), a["state"])

    merged: dict[str, dict] = {}
    for item in raw:  # 同じ内容の重複を除き、関連は残す
        key = ev.norm(item["content"])
        if key in merged:
            base = merged[key]
            base["related"] = list(dict.fromkeys(base["related"] + item["related"]))
            base["also"] = base.get("also", []) + [item["id"]]
        else:
            merged[key] = item
    drafts = {r["id"] for r in p["requirements"] if r["status"] == "下書き"} if not opt.include_drafts else set()
    excluded, included = [], []
    for item in merged.values():
        hidden = set(opt.exclude_ids) | drafts
        if item["id"] in opt.exclude_ids or (item["related"] and set(item["related"]) <= hidden):
            excluded.append({**item, "reason": "対象から外した要件だけに関連するため"})
        else:
            included.append(item)
    return {"registered": len(raw), "merged": len(raw) - len(merged), "included": included, "excluded": excluded}


def _open_table(p: dict, opt: Options, skip: tuple[str, ...] = ()) -> dict:
    rows = [[i["id"], i["kind"], i["content"], "、".join(i["related"]) or "未設定", display(i.get("ask")), display(i.get("due")), i["state"]] for i in open_items(p, opt, skip)["included"]]
    return {**OPEN_COLS, "rows": rows, "empty": "登録された未解決事項はありません。"}


def precheck(p: dict, opt: Options | None = None) -> dict:
    """出力前の確認。件数は実データから求める。不足があっても下書きとして出力できる。"""
    opt = opt or Options(doc_type="spec")
    reqs = _active(p, opt)
    prof = p["profile"]
    pending_cands = [c for c in p["candidates"] if c["state"] in ("候補", "要再確認")]
    missing_profile = [label for key, label in (("background", "背景"), ("purpose", "目的")) if not prof[key]["value"]]
    opens = open_items(p, opt)
    rows = [("合意済みの要件", sum(1 for r in reqs if r["status"] == "合意済み"), None),
            ("未合意の要件", sum(1 for r in reqs if r["status"] != "合意済み"), "requirements"),
            ("分類未設定の要件", sum(1 for r in reqs if not r.get("kind")), "requirements"),
            ("受入条件未設定の要件", sum(1 for r in reqs if not r.get("acceptance")), "refine"),
            ("未処理の会議記録の候補（文書には入りません）", len(pending_cands), "candidates")]
    return {"rows": rows, "missing_profile": missing_profile, "pending_candidates": pending_cands, "open": opens, "targets": [f"{r['id']} v{r['version']} {r['title']}（{_status_label(r)}）" for r in reqs],
            "is_draft": bool(missing_profile) or any(n and page for _, n, page in rows)}


def _qa_rows(p: dict, opt: Options) -> list[list[str]]:
    rows = []
    for q in p["questions"]:
        if q["status"] in ("未質問", "回答待ち") and q["id"] not in opt.exclude_ids and q.get("category") != "確認事項":
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


def scope_label(value) -> str:
    return schema.SCOPE_LABELS.get(value, display(value))


def short_title(text: str, limit: int = 28) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def _req_rows(reqs: list[dict]) -> list[list[str]]:
    """一覧は比較に使う項目だけにする。本文などは要件ごとの詳細に書く。"""
    return [[r["id"], f"v{r['version']}", display(r.get("kind")), short_title(r["title"]), scope_label(r.get("scope")), _status_label(r)] for r in reqs]


def _body_rows(reqs: list[dict]) -> list[list[str]]:
    return [[r["id"], f"v{r['version']}", display(r.get("kind")), r["body"], scope_label(r.get("scope")), _status_label(r)] for r in reqs]


def _req_details(p: dict, reqs: list[dict], opt: Options) -> list[Section]:
    """要件ごとの詳細。未設定の項目は補わず、未設定と書く。"""
    out = []
    for r in reqs:
        lines = [f"内容：{r['body']}"] if r["body"] != r["title"] else []
        for m in r.get("measures", []):
            lines.append(f"条件：{m.get('metric')} {display(m.get('value'))}{m.get('unit') or ''}（{display(m.get('condition'))}）")
        for key, label in (("target", "対象"), ("data_io", "入出力・連携"), ("exceptions", "例外")):
            if r.get(key):
                lines.append(f"{label}：{display(r[key])}")
        opens = [r[k] for k in ("open_items", "open_area") if r.get(k) and r[k] != schema.NA]
        lines.append("未確認事項：" + ("、".join(opens) if opens else "登録なし"))
        acc = [a for a in r.get("acceptance") or [] if isinstance(a, dict)]
        lines += [f"受入条件：{a.get('given')}のとき、{a.get('when')}と、{a.get('then')}（確認方法：{a.get('how')}）" for a in acc] or ["受入条件：未設定" if r.get("acceptance") != schema.NA else "受入条件：該当なし"]
        sources = list(dict.fromkeys(ev.citation(p, e) for e in r.get("evidence") or []))
        lines.append("根拠：" + ("、".join(sources) if sources else "未設定"))
        lines += _quotes(p, r, opt)
        out.append(Section(f"{r['id']} {short_title(r['title'], 40)}（{_status_label(r)}）", level=3, paragraphs=lines))
    return out


REQ_COLS = {"columns": ["ID", "版", "種類", "名称", "範囲", "状態"], "widths": [1.8, 0.9, 1.8, 7.3, 2.2, 2.2]}
BODY_COLS = {"columns": ["ID", "版", "種類", "内容", "範囲", "状態"], "widths": [1.8, 0.9, 1.8, 7.3, 2.2, 2.2]}


def _measures(p: dict, reqs: list[dict]) -> list[list[str]]:
    rows = []
    for r in reqs:
        for m in r.get("measures", []):
            v = checks.measure_view(p, r, m)
            rows.append([r["id"], m.get("metric", ""), f"{display(m.get('value'))}{m.get('unit') or ''}", m.get("kind", ""), display(m.get("origin")), v["agreement"], v["verify"],
                         f"{display(m.get('condition'))}（根拠：{display(m.get('basis'))}）"])
    return rows


def build_meeting(p: dict, opt: Options) -> list[Section]:
    reqs = _active(p, opt)
    sections = [
        Section("目的", paragraphs=[display(p["prep"].get("purpose") if p["prep"].get("purpose") else p["profile"]["purpose"]["value"])]),
        Section("当方の理解", paragraphs=[display(p["prep"].get("understanding") or p["profile"]["request"]["value"])]),
        Section("決定事項", table=_dec_table(p, opt, ("合意済み",))),
        *_dec_details(p, opt, ("合意済み",)),
        Section("未合意の要件", paragraphs=["以下は決定ではありません。ご確認をお願いします。"],
                table={**BODY_COLS, "rows": _body_rows([r for r in reqs if r["status"] != "合意済み"]), "empty": "未合意の要件はありません。"}),
        Section("未決事項", table=_open_table(p, opt, skip=("質問", "確認・依頼"))),
        Section("ご質問", table={"columns": ["確認ID", "質問", "確認相手", "回答欄"], "rows": _qa_rows(p, opt), "widths": [2.7, 6.3, 2.5, 4], "empty": "未回答の質問はありません。"}),
        Section("次の行動", table={"columns": ["ID", "内容", "担当", "期限", "状態"], "rows": _action_rows(p), "widths": [1.8, 7.5, 2, 2.2, 1.5], "empty": "登録された行動はありません。"}),
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
    agreed = len(reqs) - len(pending)
    sections = [Section("この文書について", paragraphs=[
        "本書は登録された情報から作成した下書きを含みます。" if pending else "本書は合意済みの要件から作成しました。",
        f"合意済みの要件 {agreed} 件、未合意の要件 {len(pending)} 件を記載しています。未合意の要件は決定事項ではありません。状態欄を確認してください。" if pending else "記載の範囲について、完全性や正しさを保証するものではありません。",
        "背景・目的は案件情報を参照しています。未登録の会議記録の候補は本書に含まれません。「未設定」は記録がないこと、「該当なし」は該当しないと確認したことを表します。状態の「下書き」「提案」「確認待ち」「保留」は未合意です。"])]
    sections.append(Section("背景・目的", paragraphs=[f"背景：{display(prof['background']['value'])}", f"目的：{display(prof['purpose']['value'])}", f"課題：{display(prof['problem']['value'])}", f"期待する成果：{display(prof['outcome']['value'])}"]))
    sections.append(Section("関係者", table={"columns": ["ID", "氏名・役割", "所属", "立場", "判断・確認できる範囲"], "rows": [[s["id"], s["name"], display(s.get("org")), display(s.get("position")), display(s.get("authority"))] for s in p["stakeholders"]], "widths": [1.5, 3, 3, 3, 5.5]}))
    sections.append(Section("用語", table={"columns": ["用語", "意味"], "rows": [[g["term"], g["meaning"]] for g in p["glossary"]], "widths": [4, 12], "empty": "用語はまだ登録されていません。"}))
    sections.append(Section("範囲・対象外", paragraphs=[f"範囲：{display(prof['scope_in']['value'])}", f"対象外：{display(prof['scope_out']['value'])}"],
                            table={"columns": ["区分", "要件", "理由", "判断者"], "rows": [[scope_label(r.get("scope")), f"{r['id']} {short_title(r['title'])}", display(r.get("scope_reason")), display(r.get("scope_decider"))] for r in reqs], "widths": [2.5, 6, 5.5, 2]}))
    sections.append(Section("現状・想定", paragraphs=[display(prof["current"]["value"])]))
    # 分野別の章
    sections.append(Section("要件", paragraphs=["対象分野に応じて章を切り替えています。"]))
    used: set[str] = set()
    labels = {d: schema.DOMAINS[d] for d in schema.DOMAINS}
    empty_chapters = []
    for d, chapter in checks.chapters_for(p["domains"]):
        rows = [r for r in reqs if r.get("kind") == chapter and r["id"] not in used and (r.get("domain") in (d, None) or len(p["domains"]) > 1)]
        used.update(r["id"] for r in rows)
        if rows:
            sections.append(Section(f"{labels[d]}：{chapter}", level=2, table={**REQ_COLS, "rows": _req_rows(rows)}))
        else:
            empty_chapters.append(f"{labels[d]}：{chapter}")
    unclassified = [r for r in reqs if r["id"] not in used and not r.get("kind")]
    other = [r for r in reqs if r["id"] not in used and r.get("kind")]
    if other:
        title = "共通・分野をまたぐ要件" if len(p["domains"]) > 1 else "その他の要件"
        sections.append(Section(title, level=2, table={**REQ_COLS, "rows": _req_rows(other)}))
    if unclassified:
        sections.append(Section("分類未設定の要件", level=2, paragraphs=["分野や種類が確認されていない要件です。"], table={**REQ_COLS, "rows": _req_rows(unclassified)}))
    if empty_chapters:  # 空の表を章の数だけ並べず、未登録の章としてまとめる
        sections.append(Section("要件が未登録の章", level=2, paragraphs=["次の章には要件が登録されていません。該当しないと確認されたものではありません。", "、".join(empty_chapters)]))
    sections.append(Section("要件の詳細"))
    sections.extend(_req_details(p, reqs, opt))
    sections.append(Section("数値条件と区分", paragraphs=["必要条件・現状の計測値・仮定・実現方式の候補・人が確定した設計制約を区別しています。出所は誰が示した値か、要求値の合意は値に合意したか、達成の検証は実際に達成できると確かめたかを表します。合意済みの値でも、達成できるとは限りません。"],
                            table={"columns": ["要件", "指標", "値", "区分", "出所", "要求値の合意", "達成の検証", "測定条件・根拠"], "rows": _measures(p, reqs), "widths": [1.5, 2.4, 1.5, 1.9, 1.7, 2.0, 2.0, 3.5], "empty": "数値条件はまだ登録されていません。"}))
    nfr_rows = [[n["label"], n["state"], display(n.get("note")), "、".join(n["requirements"]) or "未設定"] for n in checks.nfr_overview(p)]
    sections.append(Section("非機能", paragraphs=["状態が未確認の項目は、問題がないことを示すものではありません。"], table={"columns": ["項目", "状態", "補足", "関連要件"], "rows": nfr_rows, "widths": [3, 2, 8, 3]}))
    sections.append(Section("シナリオ", table={"columns": ["ID", "名称", "種類", "開始条件", "流れ", "終了・失敗時", "関連要件"], "rows": [[s["id"], s["title"], s.get("kind", ""), display(s.get("start")), " → ".join(s.get("steps", [])), display(s.get("end")), "、".join(s.get("related_requirements", []))] for s in p["scenarios"]], "widths": [1.8, 3, 1.4, 2.6, 4, 2.4, 1.8], "empty": "シナリオはまだ登録されていません。"}))
    op_kinds = ("運用", "移行")
    ops = [r for r in reqs if r.get("kind") in op_kinds]
    if ops:
        sections.append(Section("運用・移行", table={**REQ_COLS, "rows": _req_rows(ops)}))
    acc_rows = [[r["id"], a.get("given", ""), a.get("when", ""), a.get("then", ""), a.get("how", "")] for r in reqs for a in r.get("acceptance", []) if isinstance(a, dict)]
    sections.append(Section("受入条件", table={"columns": ["要件", "前提", "条件", "期待結果", "確認方法"], "rows": acc_rows, "widths": [1.8, 4, 3.5, 4, 2.7], "empty": "受入条件はまだ登録されていません。"}))
    sections.append(Section("制約", paragraphs=[display(prof["constraints"]["value"])]))
    sections.append(Section("未決事項", paragraphs=["案件に登録された未解決の事項です。"], table=_open_table(p, opt)))
    sections.append(Section("記入が不足している項目", paragraphs=["受入条件や判断者など、プログラムが検出した未入力の項目です。"], table={"columns": ["対象", "分類", "内容", "確認相手", "期限"], "rows": _open_rows(p, opt), "widths": [1.8, 3, 6.8, 2, 2.2], "empty": "検出された項目はありません。"}))
    sections.append(Section("リスク", table={"columns": ["ID", "内容", "条件", "影響", "対策", "状態"], "rows": [[r["id"], r["content"], display(r.get("condition")), display(r.get("impact")), display(r.get("mitigation")), r["state"]] for r in p["risks"]], "widths": [1.8, 5, 3, 3, 3, 1.6], "empty": "リスクはまだ登録されていません。"}))
    sections.append(Section("合意", paragraphs=[
        "ここに記載の合意は利用者が記録したものであり、電子署名ではありません。"], table=_dec_table(p, opt, ("合意済み",))))
    sections.extend(_dec_details(p, opt, ("合意済み",)))
    hist = [[h["id"], h.get("requirement_id") or "", display(h.get("decided_on")), h["outcome"], h.get("trigger", ""), h.get("rationale") or "理由の記録がありません", display(h.get("decider"))] for h in p["history"]]
    sections.append(Section("変更履歴", table={"columns": ["ID", "要件", "判断日", "結果", "きっかけ", "理由", "判断者"], "rows": hist, "widths": [1.8, 1.8, 2.2, 1.2, 3.6, 4.5, 1.6], "empty": "変更履歴はまだありません。"}))
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
