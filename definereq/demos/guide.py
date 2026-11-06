"""案内付きデモの内容。

文章の見出しと説明はここに書くが、注目カードの中身（発言、要件、判断、数値）は
その段階の案件データから取得する。データにないものは KeyError になり、テストで検出される。
これにより、結論や根拠の創作と、後の段階の結論の先取りを防ぐ。
"""
from __future__ import annotations

import re

from .. import project as pj
from ..export.share import option_verdict
from ..ingest.formats import format_time
from ..logic import agreement as ag
from ..logic import checks, diffview, why
from ..logic import evidence as ev
from ..logic.checks import conflict_view


class Ctx:
    """案件データから代表例を取り出す。見つからなければ例外にする。"""

    def __init__(self, p: dict):
        self.p = p

    def _find(self, items, test, label):
        for item in items:
            if test(item):
                return item
        raise KeyError(f"案内の参照先がありません: {label}")

    def req(self, title: str) -> dict:
        return self._find(self.p["requirements"], lambda r: title in r["title"], title)

    def dec(self, topic: str) -> dict:
        return self._find(self.p["decisions"], lambda d: topic in d["topic"], topic)

    def chg(self, text: str) -> dict:
        return self._find(self.p["changes"], lambda c: text in c["content"], text)

    def question(self, text: str) -> dict:
        return self._find(self.p["questions"], lambda q: text in q["text"], text)

    def role(self, name: str | None) -> str:
        s = next((x for x in self.p["stakeholders"] if x["name"] == name), None)
        return f"{name}（{s['org']} {s['position']}）" if s else (name or "話者未確認")

    def speech(self, text: str, note: str | None = None) -> dict:
        """発言カード。発言者・時刻・全文・区分・確認状態を案件データから取る。"""
        for rec in self.p["recordings"]:
            for s in rec["segments"]:
                if text in s["text"]:
                    view = ev.speaker_view(rec, s)
                    # 確認が済んでいない話者には役職を付けない（確定した人物のように見えるため）
                    who = self.role(view["name"]) if view["confirmed"] else view["name"]
                    return {"type": "speech", "who_label": view["label"], "who": who, "time": format_time(s["start"]), "text": s["text"], "kind": s.get("kind") or "未分類",
                            "speaker_check": view["speaker_check"], "content_check": view["content_check"], "note": note, "rec_id": rec["id"], "start": s["start"],
                            "where": f"{rec['name']}（{format_time(s['start'])}-{format_time(s['end'])}）"}
        raise KeyError(f"発言がありません: {text}")

    def measure(self, req_title: str, metric: str, said: str | None = None) -> dict:
        """曖昧な言葉と、確認可能な条件の対応。"""
        r = self.req(req_title)
        m = self._find(r["measures"], lambda x: metric in x["metric"], metric)
        value = "値なし" if m.get("value") is None else f"{m['value']}{m.get('unit') or ''}"
        return {"said": said, "metric": m["metric"], "value": value, "kind": m["kind"], "condition": m.get("condition") or "未設定", "status": m["status"], "basis": m.get("basis") or "未設定",
                "origin": m.get("origin") or "未設定", "path": self._path(r, m, said)}

    def _path(self, r: dict, m: dict, said: str | None) -> list[str]:
        """言葉が数値になるまでの経過。案件の記録にあることだけを並べる。"""
        steps = []
        if said and any(c["kind"] == "質問" and any(e.get("quote") == said for e in c.get("evidence", [])) for c in self.p["candidates"]):
            steps.append("AIが確認用の質問を提示（数値は提示していない）")
        origin = m.get("origin")
        if origin == "関係者が提示":
            steps.append(f"{m.get('basis') or '会議'}で関係者が値を提示")
        elif origin == "資料に記載":
            steps.append(f"資料の記録（{m.get('basis') or '資料名の記録なし'}）")
        else:
            steps.append("値の出所は未確認")
        agreed = [d for d in self.p["decisions"] if d["state"] == "合意済み" and r["id"] in (d.get("related_requirements") or [])]
        steps.append(f"判断 {agreed[0]['id']} で合意を記録" if agreed else f"要件は「{r['status']}」で未合意")
        if m["status"] == "確認待ち":
            steps.append("値の達成は確認待ち")
        elif m["status"] == "未計測":
            steps.append("未計測のため値はない")
        return steps

    def options(self, topic: str) -> dict:
        d = self.dec(topic)
        rows = [{"label": o["label"], "pros": o.get("pros"), "cons": o.get("cons"), "adopted": o["id"] == d.get("adopted"), "verdict": option_verdict(d, o),
                 "reason": d.get("rejected_reasons", {}).get(o["id"])} for o in d["options"]]
        return {"type": "options", "topic": d["topic"], "state": d["state"], "rows": rows, "rationale": d.get("rationale"), "decider": d.get("decider"),
                "confirmer": d.get("confirmer"), "date": d.get("decided_on"), "confirmation": d.get("confirmation"), "id": d["id"]}

    def conflict(self, change: dict) -> list[tuple]:
        """過去の指摘を、当時の要件の版と結び付けて示す。"""
        rows = []
        for c in self.p["conflicts"]:
            if change["id"] in (c["a"], c["b"]):
                view = conflict_view(self.p, c)
                version = next((s["detected_version"].strip() for s in view["sides"] if s["detected_version"]), "")
                rows.append((f"当時の指摘（要件 {version} の時点）" if version else "当時の指摘", c["note"], c["kind"]))
                rows.append(("現在の状態", view["summary"], c["state"]))
        return rows

    def open_counts(self) -> list[str]:
        bl = checks.backlog(self.p)
        return [f"{k} {v}件" for k, v in bl["counts"].items() if v]

    def unconfirmed(self) -> int:
        return sum(1 for r in self.p["recordings"] for s in r["segments"] if s["speaker_status"] != "確認済み")

    def unconfirmed_open(self) -> list[str]:
        """未決事項の欄に出す項目。0件は課題ではないため出さない。"""
        n = self.unconfirmed()
        return [f"話者の確認が未実施の発言 {n}件"] if n else []

    def confirmed_note(self) -> str | None:
        """全発言の話者を確認済みの場合の補足。"""
        total = sum(len(r["segments"]) for r in self.p["recordings"])
        return f"確認済み：発言{total}件すべての話者" if total and not self.unconfirmed() else None

    def on(self, name: str) -> str:
        """資料または録画の日付（名称の一部で探す）。"""
        for s in self.p["sources"]:
            if name in s["name"] and s.get("occurred_at"):
                return s["occurred_at"]
        for r in self.p["recordings"]:
            if name in r["name"] and r.get("meeting_date"):
                return r["meeting_date"]
        raise KeyError(f"日付の記録がありません: {name}")

    def count(self, collection: str) -> int:
        return len(self.p[collection])

    def requests(self, text: str) -> dict:
        c = self.chg(text)
        return {"date": c.get("requested_at") or "受付日の記録なし", "who": c.get("requester") or "要望者の記録なし", "why": c.get("background") or "背景の記録なし"}

    def background(self) -> list[str]:
        prof = self.p["profile"]
        return [f"背景：{prof['background']['value']}", f"目的：{prof['purpose']['value']}", "関係者：" + "、".join(self.role(s["name"]) for s in self.p["stakeholders"]),
                "閲覧専用のデモです。データは全て架空で、AIの結果は準備済みです。"]

    def agreed(self) -> list[str]:
        out = []
        for d in self.p["decisions"]:
            if d["state"] == "合意済み":
                adopted = next((o["label"] for o in d["options"] if o["id"] == d.get("adopted")), None)
                out.append(f"{d['topic']}：{adopted}")
        return out

    def docs(self) -> list[str]:
        return [f"{d['title']}（第{d['version']}版）" for d in self.p["shared_docs"]]

    def impacts(self, change: dict) -> tuple[str, int]:
        kinds: dict[str, int] = {}
        for i in change["impacts"]:
            kinds[i["basis"]] = kinds.get(i["basis"], 0) + 1
        return "、".join(f"{k} {v}件" for k, v in kinds.items()), len(ag.unsurveyed_areas(change))

    def why(self, question: str) -> dict:
        a = why.answer(self.p, question)
        if a["status"] != "answered":
            raise KeyError(f"回答できません: {question}")
        return {"question": question, "reason": a["reason"], "recorded": a["reason_recorded"]}

    def fact(self, text: str) -> dict:
        """資料または発言に実在する文を取り出す。"""
        for s in self.p["sources"]:
            for u in s["units"]:
                if text in u["text"]:
                    return {"full": u["text"], "where": f"{s['name']}（{u['locator']}）"}
        for rec in self.p["recordings"]:
            for s in rec["segments"]:
                if text in s["text"]:
                    return {"full": s["text"], "where": f"{rec['name']}（{format_time(s['start'])}）"}
        raise KeyError(f"資料にありません: {text}")

    def full(self, text: str) -> str:
        f = self.fact(text)
        return f"「{f['full']}」 {f['where']}"

    def where(self, text: str) -> str:
        return self.fact(text)["where"]

    def line(self, text: str) -> str:
        for rec in self.p["recordings"]:
            for s in rec["segments"]:
                if text in s["text"]:
                    v = ev.speaker_view(rec, s)
                    return f"{format_time(s['start'])} {v['label']}：{v['name']}（{s.get('kind') or '未分類'}・話者確認：{v['speaker_check']}）：{s['text']}"
        raise KeyError(f"発言がありません: {text}")

    def candidate(self, text: str) -> dict:
        return self._find(self.p["candidates"], lambda c: text in c["text"], text)

    def _side(self, spec: tuple) -> dict:
        """(見出し, 表示する文[, 引用か, 照合する文])。引用は資料に実在することを確認する。"""
        label, text = spec[0], spec[1]
        quoted = spec[2] if len(spec) > 2 else True
        check = spec[3] if len(spec) > 3 else (text if quoted else None)
        if check:
            self.fact(check)
        return {"label": label, "text": text, "quoted": quoted}

    def versus(self, left: tuple, right: tuple, below: tuple | None) -> dict:
        return {"type": "versus", "left": self._side(left), "right": self._side(right), "below": below}

    def convert(self, rows: list[dict]) -> dict:
        return {"type": "convert", "rows": rows}

    def decision(self, topic: str) -> dict:
        d = self.options(topic)
        d["type"] = "decision"
        d["adopted"] = next((r["label"] for r in d["rows"] if r["adopted"]), None)
        return d

    def citations(self, topic: str) -> list[str]:
        d = self.dec(topic)
        lines = [f"確認の記録：{d['confirmation']}"] if d.get("confirmation") else []
        return lines + [f"「{e.get('quote')}」 {ev.citation(self.p, e)}" for e in d.get("evidence", [])]

    def table_conflict(self, change: dict) -> dict:
        return {"type": "conflict", "rows": self.conflict(change)}

    def impact_lines(self, change: dict) -> list[str]:
        detected = [f"指摘の対象 {s['id']}{s['detected_version']}：{s['detected_text']}" for c in self.p["conflicts"] if change["id"] in (c["a"], c["b"]) for s in conflict_view(self.p, c)["sides"]]
        return detected + [f"{i['area']}（{i['basis']}）：{i['note']}" for i in change["impacts"]] + [f"未調査の領域：{'、'.join(ag.unsurveyed_areas(change))}"]

    def timeline(self, req_title: str) -> dict:
        r = self.req(req_title)
        ids = pj.lineage(self.p, r["id"])
        rows = [{"date": h.get("decided_on") or "判断日の記録なし", "event": re.sub(r"\s*CHG-\d+", "", h.get("trigger") or ""), "outcome": h["outcome"]}
                for h in self.p["history"] if h.get("requirement_id") in ids]
        return {"type": "timeline", "rows": sorted(rows, key=lambda x: x["date"])}

    def summary(self) -> dict:
        bl = checks.backlog(self.p)
        seen, todo = set(), []
        for items in bl["categories"].values():
            for i in items:
                if i["target"] not in seen:
                    seen.add(i["target"])
                    todo.append({"text": i["content"], "ask": i.get("ask"), "due": i.get("due")})
        return {"type": "summary", "decided": self.agreed(), "todo": todo, "todo_total": len(todo), "docs": self.docs()}


def _flow3(g: Ctx, req_title: str, change_text: str) -> dict:
    """追加要望の時点：変更前／追加要望／変更後。要件はまだ変わっていない。"""
    r, c = g.req(req_title), g.chg(change_text)
    return {"type": "flow3", "cols": [{"label": "変更前の要件", "text": r["body"], "chip": r["status"]},
                                      {"label": "追加された要望", "text": c["content"], "chip": "受付のみ"},
                                      {"label": "変更後", "text": "まだ反映していません", "chip": "判断待ち"}]}


def _after(g: Ctx, req_title: str) -> dict:
    r = g.req(req_title)
    v = r["versions"][-1]
    diff = diffview.parts(v["body"], r["body"])
    return {"type": "flow3", "mode": diff["mode"], "cols": [{"label": f"変更前（v{v['version']}）", "text": v["body"], "chip": v["status"], "parts": diff["before"]},
                                                            {"label": f"判断後（v{r['version']}）", "text": r["body"], "chip": r["status"], "parts": diff["after"]}]}


FINAL = dict(process="体験の終了と資料", short="体験の終了と資料", stage=4, page="overview", title="体験の振り返りとサンプル資料", lead=None, finale=True,
             main=lambda g: [], more=lambda g: [], open=lambda g: [], count=lambda g: None)


def _d1() -> dict:
    steps = [
        dict(process="案件の背景", short="案件の背景", stage=2, page="overview", title="現場と経理の条件が対立している案件",
             lead=None,
             main=lambda g: [g.versus(("現場の要望", "承認後でも金額を訂正できるようにしたい"), ("経理の制約", "直接変更は認めない"),
                                      ("このデモで確認すること", "両方の条件を満たす訂正方法を検討し、判断の理由まで記録する案件です。"))],
             more=lambda g: [],
             open=lambda g: [], count=lambda g: None),
        dict(process="会議前の準備", short="会議前の確認点", stage=1, page="prep", title="規程にない「訂正の手順」を、会議で確認する",
             lead=None,
             main=lambda g: [g.versus(("規程に書いてあること", "承認された申請の内容は変更できない"), ("会議で確認すること", g.question("承認後に金額の誤り")["text"], False), None)],
             more=lambda g: [("質問の詳細を見る", [f"確認する理由：{g.question('承認後に金額の誤り')['why']}", f"確認相手：{g.question('承認後に金額の誤り')['ask']}", f"質問の状態：{g.question('承認後に金額の誤り')['status']}", g.where("承認された申請の内容は変更できない")])],
             open=lambda g: g.p["prep"]["gaps"][:3], count=lambda g: f"代表例1件／質問 全{len(g.p['questions'])}件"),
        dict(process="会議後の整理", short="要望と制約の整理", stage=2, page="candidates", title="現場の要望と、経理の制約を分けて整理",
             lead=None,
             main=lambda g: [g.versus(("現場の要望", "承認後でも金額を訂正できるようにしたい"), ("経理の制約", "直接変更は認めない"),
                                      ("アプリの整理（関係者の発言ではありません）", "訂正は必要。ただし、直接変更以外の方法を検討する。"))],
             more=lambda g: [("発言の根拠を見る", [g.full("承認後でも金額を訂正できるようにしたい"), g.full("変更履歴があっても直接変更は認めない")]),
                             ("AI候補を確認する仕組みを見る", [f"AI候補「{g.candidate('5回')['text']}」は、資料にない数値（{'、'.join(g.candidate('5回')['unsupported_numbers'])}）に印が付き、担当者が「{g.candidate('5回')['state']}」としました。"])],
             open=lambda g: ["訂正の方式は未確定（次の工程で比較）"], count=lambda g: f"代表例2件／候補 全{len(g.p['candidates'])}件"),
        dict(process="会議での発言", short="第2回の発言", stage=2, page="recordings", title="話者の確認が未実施の発言は、判断の根拠にしない",
             lead=None,
             main=lambda g: [g.speech("金額の訂正は再申請で進めます", "話者の確認が未実施のため、判断の根拠には使っていません。")],
             more=lambda g: [("他の発言を見る", [g.line("元の内容を引き継げるなら"), g.line("元の記録が残る"), g.line("再申請でも金額の基準は同じです")]),
                             ("判断の根拠を見る", [g.dec("承認後の金額訂正の方式").get("confirmation") or "記録なし"])],
             open=lambda g: g.unconfirmed_open(), count=lambda g: f"代表例1件／発言 全{sum(len(r['segments']) for r in g.p['recordings'])}件",
             media_note="第2回は会議ツールの字幕を取り込んだ記録で、録画の再生はありません。"),
        dict(process="判断", short="訂正方法の比較", stage=2, page="decisions", title="3案を比べて、再申請を採用した",
             lead=None,
             main=lambda g: [g.decision("承認後の金額訂正の方式")],
             more=lambda g: [("判断の根拠を見る", g.citations("承認後の金額訂正の方式"))],
             open=lambda g: [f"{d['topic']}（{d['state']}：{d.get('hold_reason')}）" for d in g.p["decisions"] if d["state"] == "保留"], count=lambda g: f"代表例1件／判断 全{len(g.p['decisions'])}件"),
        dict(process="追加要望と影響", short="追加要望の影響", stage=3, page="changes", title="経理の直接訂正の要望が、過去の判断と衝突する",
             lead="要望は受け付けただけで、要件はまだ変わっていません。",
             main=lambda g: [_flow3(g, "金額の誤り", "直接訂正"), g.table_conflict(g.chg("直接訂正"))],
             more=lambda g: [("影響の調査を見る", g.impact_lines(g.chg("直接訂正")))],
             open=lambda g: ["直接訂正を認めるかの判断", f"未調査の領域 {g.impacts(g.chg('直接訂正'))[1]}件"], count=lambda g: f"代表例1件／追加要望 全{len(g.p['changes'])}件"),
        dict(process="判断後の仕様", short="判断後の仕様", stage=4, page="trail", title="直接訂正は却下し、経理の代行作成を採用",
             lead=None,
             main=lambda g: [g.decision("経理担当者による直接訂正"), _after(g, "金額の誤り"), g.timeline("金額の誤り")],
             more=lambda g: [("「なぜ再申請か」の回答を見る", [g.why("なぜ再申請なのか")["reason"]]), ("判断の根拠を見る", g.citations("経理担当者による直接訂正"))],
             open=lambda g: [f"{d['topic']}（{d['state']}）" for d in g.p["decisions"] if d["state"] == "保留"], count=lambda g: f"履歴 全{len(g.p['history'])}件"),
        FINAL,
    ]
    return steps


def _d2() -> dict:
    return [
        dict(process="案件の背景", short="案件の背景", stage=2, page="overview", title="曖昧な要望と、基盤の条件をすり合わせる案件",
             lead=None,
             main=lambda g: [g.versus(("経営企画の要望", "毎朝すぐに売上の数字を見たい"), ("基盤担当の条件", "切替の作業で停止が必要になる可能性がある"),
                                      ("このデモで確認すること", "曖昧な要望を確認可能な条件に分け、アプリと基盤の境界を整理する案件です。"))],
             more=lambda g: [],
             open=lambda g: [], count=lambda g: None),
        dict(process="会議前の準備", short="資料の確認", stage=1, page="sources", title="資料から読めたことと、読めなかったことを分ける",
             lead=None,
             main=lambda g: [g.versus(("読めたこと", "約90分"), ("読めなかったこと", "データ増加率は未計測", False), None)],
             more=lambda g: [("図の扱いを見る", [next(w for s in g.p["sources"] for w in s["warnings"] if "理解していません" in w), f"人の補足：{next(s['supplement'] for s in g.p['sources'] if s.get('supplement'))}"]),
                             ("資料の位置を見る", [g.where("約90分"), g.where("データ増加率")])],
             open=lambda g: g.p["prep"]["gaps"], count=lambda g: f"資料 全{len(g.p['sources'])}件"),
        dict(process="具体化", short="条件への具体化", stage=2, page="refine", title="「毎朝すぐ」「失いたくない」を測れる条件に分ける",
             lead=None,
             main=lambda g: [g.convert([g.measure("毎朝8時30分", "集計の完了時刻", "毎朝すぐに売上の数字を見たい"), g.measure("4時間以内", "目標復旧時間", "データを失いたくない"), g.measure("1日分まで", "許容データ損失", "データを失いたくない")])],
             more=lambda g: [("発言の根拠を見る", [g.full("毎朝すぐに売上の数字を見たい"), g.full("データを失いたくない"), g.full("毎朝8時30分までに")])],
             open=lambda g: [f"{m['metric']}：未計測" for r in g.p["requirements"] for m in r["measures"] if m["status"] == "未計測"], count=lambda g: f"代表例3件／数値条件 全{sum(len(r['measures']) for r in g.p['requirements'])}件"),
        dict(process="アプリと基盤の境界", short="アプリと基盤の境界", stage=2, page="nfr", title="アプリと基盤の担当を分け、未決を残す",
             lead=None,
             main=lambda g: [g.versus(("アプリの保守", "情報システム課", False, "アプリの保守は情報システム課"), ("クラウド基盤の保守", "ベンダー", False, "クラウド基盤の保守はベンダー"),
                                      ("まだ決まっていないこと", "障害の一次受付の担当は未定です。"))],
             more=lambda g: [("リスクを見る", [f"{g.p['risks'][0]['content']}（{g.p['risks'][0]['nature']}）"]), ("資料の位置を見る", [g.where("アプリの保守は情報システム課")])],
             open=lambda g: [f"{r['title']}：{r['open_area']}" for r in g.p["requirements"] if r.get("open_area")], count=lambda g: f"リスク 全{len(g.p['risks'])}件"),
        dict(process="意見調整", short="停止の調整", stage=2, page="issues", title="朝の集計を止めずに、保守の停止を認めた",
             lead=None,
             main=lambda g: [g.versus(("業務の希望", "朝の集計は止めないでほしい"), ("基盤の条件", "保守の計画停止は月1回の日曜夜に限る案", False, "保守の計画停止は月1回の日曜夜に限る案"), None), g.decision("計画停止の扱い")],
             more=lambda g: [("判断の根拠を見る", g.citations("計画停止の扱い"))],
             open=lambda g: [i["topic"] for i in g.p["issues"] if i["state"] != "結論あり"], count=lambda g: f"論点 全{len(g.p['issues'])}件"),
        dict(process="追加要望と影響", short="再集計の要望", stage=3, page="changes", title="締め後の再集計の要望が、固定のルールと衝突する",
             lead="要望は受け付けただけで、要件はまだ変わっていません。",
             main=lambda g: [_flow3(g, "締め後の数字", "再集計"), g.table_conflict(g.chg("再集計"))],
             more=lambda g: [("影響の調査を見る", g.impact_lines(g.chg("再集計")))],
             open=lambda g: ["当月の再集計を認めるかの判断", f"未調査の領域 {g.impacts(g.chg('再集計'))[1]}件"], count=lambda g: f"代表例1件／追加要望 全{len(g.p['changes'])}件"),
        dict(process="判断後の仕様", short="判断と理由", stage=4, page="why", title="訂正版で対応すると判断し、理由を残した",
             lead=None,
             main=lambda g: [g.decision("締め後の再集計"), _after(g, "締め後の数字"), g.timeline("締め後の数字")],
             more=lambda g: [("理由が未記録の例を見る", [f"質問「{g.why('なぜ保存期間は3年なのか')['question']}」への回答：{g.why('なぜ保存期間は3年なのか')['reason']}（AIで補っていません）"]), ("判断の根拠を見る", g.citations("締め後の再集計"))],
             open=lambda g: g.open_counts()[:3], count=lambda g: f"履歴 全{len(g.p['history'])}件"),
        FINAL,
    ]


def _d3() -> dict:
    return [
        dict(process="案件の背景", short="案件の背景", stage=2, page="overview", title="遠隔保守の提案と、外部接続の禁止がぶつかる案件",
             lead=None,
             main=lambda g: [g.versus(("保守会社の提案", "外部からの遠隔保守を提案します"), ("規程の制約", "外部からの接続は禁止です"),
                                      ("このデモで確認すること", "接続ルールと保守の要望の関係を確認し、提案・未確認事項・合意を区別する案件です。"))],
             more=lambda g: [],
             open=lambda g: [], count=lambda g: None),
        dict(process="会議前の準備", short="通信と構成の確認", stage=1, page="sources", title="通信一覧と構成図で、分かることと未確認を分ける",
             lead=None,
             main=lambda g: [g.versus(("資料から分かること", "拠点間は主回線1本で接続している"), ("未確認のまま残すこと", "保守会社の通信のポートは未確認", False), None)],
             more=lambda g: [("図の扱いを見る", [next(w for s in g.p["sources"] for w in s["warnings"] if "理解していません" in w), f"人の補足：{next(s['supplement'] for s in g.p['sources'] if s.get('supplement'))}"]),
                             ("通信一覧の原文を見る", [g.full("F03")])],
             open=lambda g: g.p["prep"]["gaps"], count=lambda g: f"資料 全{len(g.p['sources'])}件"),
        dict(process="録画の発言", short="録画の発言", stage=2, page="recordings", title="保守会社の発言は「提案」であり、決定ではない",
             lead=None,
             main=lambda g: [g.speech("外部からの遠隔保守を提案します", "区分は「提案」です。この発言だけでは合意になりません。")],
             more=lambda g: [("他の発言を見る", [g.line("現場の要望は、速くて止まりにくい回線です"), g.line("外部からの接続は禁止です"), g.line("遠隔保守はまだ提案の段階")])],
             open=lambda g: g.unconfirmed_open() + ["例外の手続きの有無"], done=lambda g: g.confirmed_note(), count=lambda g: f"代表例1件／発言 全{sum(len(r['segments']) for r in g.p['recordings'])}件"),
        dict(process="具体化", short="条件への具体化", stage=2, page="refine", title="「速く、止まりにくく」を条件と未計測に分ける",
             lead=None,
             main=lambda g: [g.convert([g.measure("受発注の画面", "画面の表示時間", "朝九時の受発注の時間帯に画面が遅くなります"), g.measure("受発注の画面", "ピーク時の通信量"),
                                        g.measure("回線断", "許容停止時間"), g.measure("回線断", "代替回線への切替時間")])],
             more=lambda g: [("発言の根拠を見る", [g.full("朝9時の受発注の画面は3秒以内"), g.full("受発注の停止は30分まで")])],
             open=lambda g: [f"{m['metric']}：未計測" for r in g.p["requirements"] for m in r["measures"] if m["status"] == "未計測"], count=lambda g: f"代表例4件／数値条件 全{sum(len(r['measures']) for r in g.p['requirements'])}件"),
        dict(process="合意前の確認", short="提案の状態", stage=2, page="decisions", title="遠隔保守の扱いは、まだ合意していない",
             lead=None,
             main=lambda g: [g.decision("遠隔保守の扱い")],
             more=lambda g: [("確認する質問を見る", g.p["issues"][0]["extra_questions"])],
             open=lambda g: ["判断者の判断の記録"], count=lambda g: f"判断 全{len(g.p['decisions'])}件"),
        dict(process="追加要望と影響", short="常時接続の要望", stage=3, page="changes", title="常時接続の要望が、外部接続の禁止と衝突する",
             lead="要望は受け付けただけで、要件はまだ変わっていません。",
             main=lambda g: [_flow3(g, "遠隔保守", "常時接続"), g.table_conflict(g.chg("常時接続"))],
             more=lambda g: [("影響の調査を見る", g.impact_lines(g.chg("常時接続")))],
             open=lambda g: ["保守の方式の判断", f"未調査の領域 {g.impacts(g.chg('常時接続'))[1]}件"], count=lambda g: f"代表例1件／追加要望 全{len(g.p['changes'])}件"),
        dict(process="判断後の仕様", short="判断と理由", stage=4, page="why", title="今回は現地対応とし、時間限定の接続は次回以降に検討",
             lead=None,
             main=lambda g: [g.decision("遠隔保守の扱い"), _after(g, "現地対応"), g.timeline("現地対応")],
             more=lambda g: [("過去の指摘を見る", [f"{a}：{b}" for a, b, _ in g.conflict(g.chg("常時接続"))] + g.impact_lines(g.chg("常時接続"))[:2]), ("判断の根拠を見る", g.citations("遠隔保守の扱い"))],
             open=lambda g: g.open_counts()[:3], count=lambda g: f"履歴 全{len(g.p['history'])}件"),
        FINAL,
    ]


GUIDES = {"d1": _d1, "d2": _d2, "d3": _d3}

# デモ用の役割と、体験の振り返り。実案件の利用者の役割を決めるものではない
INTRO = {
    "d1": dict(role="現場と経理の要望を取りまとめる要件定義担当者", short_role="要件定義担当者", mission="承認後の金額訂正について、両部門が納得できる方法を検討します。",
               done="対立する要望の整理から、判断理由の記録、追加要望への対応までを確認しました。",
               recap=["対立する条件を整理した", "比較と判断理由を記録した", "追加要望と過去の判断の関係を追跡した"]),
    "d2": dict(role="業務部門と基盤担当の条件を取りまとめる要件定義担当者", short_role="要件定義担当者", mission="「毎朝すぐ」「失いたくない」を確認できる条件にし、アプリと基盤の担当範囲を整理します。",
               done="曖昧な要望の具体化から、アプリと基盤の整理、追加要望への対応までを確認しました。",
               recap=["曖昧な要望を、確認できる条件に分けた", "数値の出所と確認状態を区別した", "アプリと基盤の担当範囲と未決事項を整理した"]),
    "d3": dict(role="拠点の要望と保守会社の提案を取りまとめる要件定義担当者", short_role="要件定義担当者", mission="回線の要望と遠隔保守の提案を、社内規程と照らして整理します。",
               done="録画の発言の確認から、提案と合意の区別、追加要望への対応までを確認しました。",
               recap=["録画の発言を、時刻付きの根拠として確認した", "提案・制約・合意を区別した", "追加要望の影響を調べ、判断と理由を記録した"]),
}


def _report(g: Ctx, text: str, lead: str) -> str:
    r = g.requests(text)
    return f"{lead}{r['date']}に{r['who']}から追加要望が届きました。背景：{r['why']}"


# 各画面の場面。「ガイドの何画面目か」とは別の、案件の時間の流れを示す
SCENES = {
    "d1": [
        dict(scene="全体像 — 対立している要望と制約を把握する場面", check="現場の要望と経理の制約が、どこでぶつかっているか", move=None, detail=lambda g: "案件の概要と残件を見る"),
        dict(scene="第1回会議の前 — 資料から確認点を洗い出す場面", check="規程に書かれていない手順を、会議で誰に確認するか",
             move=lambda g: "ここから時系列で追います。まず、第1回会議の前に戻って準備を確認します。", detail=lambda g: f"質問{g.count('questions')}件を確認する"),
        dict(scene="第1回会議の後 — 要望と制約を整理する場面", check="発言を、要望・制約・アプリの整理に分けられているか",
             move=lambda g: f"第1回打ち合わせ（{g.on('第1回')}）が終わりました。議事録から要望と制約を整理します。", detail=lambda g: f"候補{g.count('candidates')}件を確認する"),
        dict(scene="第2回会議の記録 — 訂正方法についての発言を確認する場面", check="誰の発言として確認できているか。根拠に使えるか",
             move=lambda g: f"初回会議で要望と制約を整理しました。続いて、第2回打ち合わせ（{g.on('第2回打ち合わせ')}）の記録から、訂正方法についての発言を確認します。", detail=lambda g: f"発言{sum(len(r['segments']) for r in g.p['recordings'])}件と確認状態を見る"),
        dict(scene="第2回会議の後 — 訂正方法を判断する場面", check="どの案を、誰が、どの理由で選び、ほかの案をなぜ選ばなかったか",
             move=lambda g: "発言の確認を踏まえて、判断者が訂正方法を決めた記録を見ます。", detail=lambda g: f"判断{g.count('decisions')}件と根拠を見る"),
        dict(scene="追加要望の受付 — 過去の判断との関係を調べる場面", check="要望と過去の判断がどこで衝突し、何が未調査か",
             move=lambda g: _report(g, "直接訂正", "第2回では、経理の田中課長が直接変更を認めませんでした。その後、"), detail=lambda g: "変更影響の詳細を見る"),
        dict(scene="第3回会議の後 — 関係者の判断の結果を見る場面", check="要望の採否、変更された部分、判断の理由",
             move=lambda g: f"ここからは、影響を確認した後に関係者が判断した結果を見ます（第3回打ち合わせ {g.on('第3回')}）。画面の移動で合意や変更が起きたのではなく、判断の記録を表示しています。", detail=lambda g: "仕様の変遷と理由を見る"),
        dict(scene="デモの終了 — 結果と資料を確認する場面", check="確認できたこと、資料、次に見るもの", move=None, detail=lambda g: "機能画面を見る"),
    ],
    "d2": [
        dict(scene="全体像 — 曖昧な要望と基盤の条件を把握する場面", check="何が曖昧で、誰と条件をすり合わせる必要があるか", move=None, detail=lambda g: "案件の概要と残件を見る"),
        dict(scene="第1回会議の前 — 資料から分かることを確認する場面", check="資料から読めたことと、読めなかったことの違い",
             move=lambda g: "ここから時系列で追います。まず、第1回会議の前に戻って資料を確認します。", detail=lambda g: f"資料{g.count('sources')}件を確認する"),
        dict(scene="第2回会議の後 — 要望を確認できる条件にする場面", check="数値を誰が示したか。確認が済んでいるか",
             move=lambda g: f"第1回（{g.on('第1回')}）の「毎朝すぐ」「失いたくない」という発言を受け、第2回（{g.on('第2回')}）で条件を確認しました。", detail=lambda g: "数値条件と受入条件を見る"),
        dict(scene="第2回会議の後 — アプリと基盤の担当を整理する場面", check="担当が決まった範囲と、まだ決まっていないこと",
             move=lambda g: "条件が見えてきたところで、誰が何を担当するかを整理します。", detail=lambda g: "非機能の確認状況を見る"),
        dict(scene="第2回会議の後 — 意見の違いを調整する場面", check="対立する希望を、どの条件で両立させたか",
             move=lambda g: "担当の整理に続いて、朝の集計を止めたくない希望と保守の停止の調整を見ます。", detail=lambda g: f"論点{g.count('issues')}件を確認する"),
        dict(scene="追加要望の受付 — 過去の判断との関係を調べる場面", check="要望と固定のルールがどこで衝突し、何が未調査か",
             move=lambda g: _report(g, "再集計", "合意の後、"), detail=lambda g: "変更影響の詳細を見る"),
        dict(scene="第3回会議の後 — 関係者の判断の結果を見る場面", check="要望の採否、変更された部分、判断の理由",
             move=lambda g: f"ここからは、影響を確認した後に関係者が判断した結果を見ます（第3回打ち合わせ {g.on('第3回')}）。画面の移動で合意や変更が起きたのではなく、判断の記録を表示しています。", detail=lambda g: "「なぜこの仕様か」を試す"),
        dict(scene="デモの終了 — 結果と資料を確認する場面", check="確認できたこと、資料、次に見るもの", move=None, detail=lambda g: "機能画面を見る"),
    ],
    "d3": [
        dict(scene="全体像 — 提案と規程の衝突を把握する場面", check="保守の提案と社内規程が、どこでぶつかっているか", move=None, detail=lambda g: "案件の概要と残件を見る"),
        dict(scene="初回の定例の前 — 資料から分かることを確認する場面", check="資料から分かることと、未確認のまま残すこと",
             move=lambda g: "ここから時系列で追います。まず、初回の定例の前に戻って資料を確認します。", detail=lambda g: f"資料{g.count('sources')}件を確認する"),
        dict(scene="初回の定例の後 — 録画の発言を確認する場面", check="発言が提案か決定か。録画の該当箇所を確認できるか",
             move=lambda g: f"定例（{g.on('定例（録画）')}）の録画から、発言を時刻付きで確認します。", detail=lambda g: f"発言{sum(len(r['segments']) for r in g.p['recordings'])}件と確認状態を見る"),
        dict(scene="第2回定例の後 — 要望を確認できる条件にする場面", check="数値を誰が示したか。未計測の項目は何か",
             move=lambda g: f"第2回定例（{g.on('第2回定例')}）で、「速く、止まりにくく」の条件を確認しました。", detail=lambda g: "数値条件と受入条件を見る"),
        dict(scene="第2回定例の後 — 合意の状態を確認する場面", check="案の比較と、判断がまだ記録されていないこと",
             move=lambda g: "条件を整理したうえで、遠隔保守の扱いがまだ決まっていないことを確認します。", detail=lambda g: f"判断{g.count('decisions')}件と根拠を見る"),
        dict(scene="追加要望の受付 — 規程との関係を調べる場面", check="要望と規程がどこで衝突し、何が未調査か",
             move=lambda g: _report(g, "常時接続", "遠隔保守の判断が決まらないうちに、"), detail=lambda g: "変更影響の詳細を見る"),
        dict(scene="第3回定例の後 — 関係者の判断の結果を見る場面", check="要望の採否、変更された部分、判断の理由",
             move=lambda g: f"ここからは、影響を確認した後に関係者が判断した結果を見ます（第3回定例 {g.on('第3回定例')}）。画面の移動で合意や変更が起きたのではなく、判断の記録を表示しています。", detail=lambda g: "「なぜこの仕様か」を試す"),
        dict(scene="デモの終了 — 結果と資料を確認する場面", check="確認できたこと、資料、次に見るもの", move=None, detail=lambda g: "機能画面を見る"),
    ],
}


def load(demo_id: str) -> list[dict]:
    """案内の全画面（全体像→時系列の工程→終了）を返す。"""
    return [{**step, **scene} for step, scene in zip(GUIDES[demo_id](), SCENES[demo_id], strict=True)]
