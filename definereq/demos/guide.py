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


# 残っている項目の見出し。「まだ決まっていない」に一律でまとめず、意味で分ける
DOCUMENT, REPORTED, UNKNOWN, MEASURE, DECIDE, VERIFY, HUMAN, LEFT = "資料に記載", "関係者の申告", "未確認の情報", "計測が必要", "判断待ち", "未検証（実装や試験で確認）", "人の確認待ち", "残っている項目"


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
        term = next((g for g in self.p["glossary"] if g["term"] in m["metric"]), None)
        origin = m.get("origin") or "未設定"
        return {"said": said, "metric": m["metric"], "value": value, "kind": m["kind"], "condition": m.get("condition") or "未設定", "basis": m.get("basis") or "未設定",
                "origin": f"{origin}（{m['basis']}）" if m.get("basis") and origin in ("関係者が提示", "資料に記載") else origin, "help": term["meaning"].split("。", 1)[-1] if term else None,
                "ai_asked": self._ai_asked(said), **checks.measure_view(self.p, r, m)}

    def _ai_asked(self, said: str | None) -> bool:
        """この発言について、AIが確認用の質問を出したか。AIは数値を出していない。"""
        return bool(said) and any(c["kind"] == "質問" and any(e.get("quote") == said for e in c.get("evidence", [])) for c in self.p["candidates"])

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

    def open_summary(self) -> list[tuple[str, str]]:
        """残件の主な内容。件数は最終画面と同じく、重複を除いた対象の数を使う。"""
        bl = checks.backlog(self.p)
        out = [(LEFT, f"確認が必要な項目 全{bl['unique_total']}件（内容は最後の画面で確認できます）")] if bl["unique_total"] else []
        return out + [(DECIDE, f"{d['topic']}（{d['state']}）") for d in self.p["decisions"] if d["state"] == "保留"]

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

    def has(self, text: str) -> bool:
        """資料・発言・質問の回答に実在する文か。"""
        answers = [q.get("answer") or "" for q in self.p["questions"]]
        units = [u["text"] for s in self.p["sources"] for u in s["units"]] + [s["text"] for r in self.p["recordings"] for s in r["segments"]]
        return any(text in x for x in units + answers)

    def story(self, demo_id: str) -> dict:
        """最初の画面の背景。説明の土台の文が記録にあることを確かめる。"""
        s = STORIES[demo_id]
        for text in s["checks"] + [x[3] for x in s["sides"]]:
            if not self.has(text):
                raise KeyError(f"背景の説明が記録と一致しません: {text}")
        sides = [{"label": label, "who": who, "text": text, "quote": self.full(check)} for label, who, text, check in s["sides"]]
        return {"type": "story", **s, "sides": sides}

    def background(self) -> list[tuple[str, str]]:
        """どの画面からでも開ける、短い背景。"""
        s = STORIES[self.p["demo"]["id"]]  # 最初の画面と同じ文章。照合は資料がそろう最初の画面で行う
        return [("今回の論点", s["focus"]), *s["rows"], ("検討中の論点", s["issue"])]

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

    def verdict(self, topic: str, confirm_source: str, unused: str) -> dict:
        """判断画面：採用した案 → 採用理由 → 根拠 → 案の比較。全て判断の記録から取る。

        confirm_source：本人が判断を確認した記録の名前。unused：判断に使っていない（話者未確認の）発言。
        """
        d = self.decision(topic)
        rec = self.dec(topic)
        mail = self._find(self.p["sources"], lambda s: s["name"] == confirm_source, confirm_source)
        basis = []
        for e in rec.get("evidence", []):
            where = ev.citation(self.p, e)
            if str(e["source_id"]).startswith("REC"):
                r = pj.get(self.p, "recordings", e["source_id"])
                seg = next((x for x in r["segments"] if x["id"] == e.get("unit_id")), None)
                if seg is None:
                    raise KeyError(f"根拠の発言がありません: {e.get('quote')}")
                v = ev.speaker_view(r, seg)
                kind = "発言（話者確認済み）" if v["confirmed"] else "発言（話者未確認）"
                where = f"{r['name']} {format_time(seg['start'])}　{v['label']}：{v['name']}"
            elif e["source_id"] == mail["id"]:
                kind = "本人確認済みの記録"
            else:
                kind = "資料"
            basis.append({"kind": kind, "quote": e.get("quote"), "where": where})
        skipped = self.speech(unused)
        if skipped["speaker_check"] == "確認済み":
            raise KeyError(f"話者確認済みの発言です: {unused}")
        return {**d, "type": "verdict", "basis": basis, "mail_id": mail["id"], "mail_name": mail["name"],
                "skipped": {"text": skipped["text"], "where": f"{skipped['where']}　{skipped['who_label']}：{skipped['who']}"}}

    def change_summary(self, req_title: str, change_text: str, topic: str, before: tuple, after: tuple, keep: tuple, scope: str | None = None) -> dict:
        """判断後の仕様の要約：変更前／変更後／引き続き守る制約と、追加要望→衝突→採用した対応。

        before / after / keep は（表示する文, 照合する文）。照合する文が記録にないと例外になる。
        before は変更前の版の本文か受入条件、after は現在の本文、keep は要件の本文で確かめる。
        """
        r, c, d = self.req(req_title), self.chg(change_text), self.dec(topic)
        old = " ".join([r["versions"][-1]["body"]] + [f"{a['given']} {a['when']} {a['then']}" for a in r.get("acceptance", [])])
        bodies = " ".join(x["body"] for x in self.p["requirements"])
        for (text, check), pool, label in ((before, old, "変更前"), (after, r["body"], "変更後"), (keep, bodies, "守る制約")):
            for part in ([check] if isinstance(check, str) else check):
                if part not in pool:
                    raise KeyError(f"{label}の文が記録と一致しません: {part}")
        adopted = next(o for o in d["options"] if o["id"] == d.get("adopted"))
        rejected = next(iter(d.get("rejected_reasons", {}).items()), None)
        if not rejected:
            raise KeyError(f"不採用の理由がありません: {topic}")
        label = next(o["label"] for o in d["options"] if o["id"] == rejected[0])
        clash = f"「{label}」は不採用。{rejected[1]}"
        return {"type": "change_sum", "before": before[0], "after": after[0], "keep": keep[0], "scope": scope,
                "request": c["content"], "clash": clash, "adopted": adopted["label"], "before_v": r["versions"][-1]["version"], "after_v": r["version"]}

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


# 最初の画面の背景。業務→困りごと→変えたいこと→関係者→論点→このデモ の順に読む。
# checks は資料・発言・回答に実在する文で、説明が記録と食い違うと表示の前に例外になる。
# 後の画面の結論（採用した方式）はここに書かない。
STORIES = {
    "d1": dict(
        title="承認後の金額間違いに対応できる経費申請アプリへ",
        sides=[("現場の要望", "営業部", "承認後に見つかった金額の誤りを訂正したい", "承認後でも金額を訂正できるようにしたい"),
               ("経理の制約", "経理課", "承認済みの記録は直接変更できない", "変更履歴があっても直接変更は認めない")],
        focus="元の記録を残しながら、どう訂正するか？",
        rows=[("現在の業務", "社員は紙の申請書で経費を申請し、承認者の承認を受けます。申請の管理はExcelの台帳で行っています。"),
              ("困りごと", "承認までの状況が見えません。また、現場の申告では金額を1桁間違えたまま承認されることが月に数件あり、今は担当者が台帳を手で直しています。"),
              ("今回、変えたいこと", "申請から精算までを一つのアプリで追えるようにします。あわせて、承認後に金額の誤りが見つかったときの扱いを決めます。")],
        people=[("現場（営業部）", "承認後でも金額を訂正したい。精算が終わった申請まで直す必要はない。"),
                ("経理（経理課）", "金額の直接変更は、変更履歴があっても認めない。監査で説明できなくなるため。"),
                ("情報システム課", "実現方法の案を検討する。"), ("管理部長", "方式と範囲を判断する。")],
        issue="「承認後に訂正したい」と「承認された記録を直接変えない」を、どう両立させるか。規程は承認後の変更を禁じていますが、訂正の手順は書かれていません。",
        demo="会議前の確認から、訂正方法の比較、判断理由の記録、後から届いた追加要望への対応までを、時系列で追います。",
        checks=["紙とExcelの申請", "承認までの状況が見えない", "金額を1桁間違えたまま承認されることが月に数件ある", "担当者が台帳を手で直している", "申請から精算までを一つのアプリで追える",
                "精算が終わった申請まで直したいわけではない", "変更履歴があっても直接変更は認めない", "監査で説明できない", "承認された申請の内容は変更できない"]),
    "d2": dict(
        title="手作業の売上集計を自動化し、クラウド移行も検討する",
        sides=[("利用部門の要望", "経営企画", "毎朝すぐに売上の数字を見たい", "毎朝すぐに売上の数字を見たい"),
               ("現状の制約", "集計の担当", "手作業の集計に約90分かかり、拠点の提出が9時を過ぎる日もある", "月に2回ほど9時を過ぎる")],
        focus="「毎朝すぐ」を、何時までに何が見られればよいという測れる条件にできるか？",
        rows=[("現在の業務", "12拠点がExcelを提出し、本社の担当2名が毎朝手作業でまとめています。集計には約90分かかります（2026年8月の記録）。"),
              ("困りごと", "経営企画は朝9時の部門会議で売上の数字を使います。一方で提出の遅れや重複は手で直しており、大阪拠点の提出が9時を過ぎることも月に2回ほどあります。"),
              ("今回、変えたいこと", "集計を自動化し、毎朝すぐに本社が結果を確認できるようにします。あわせて、現行サーバーの保守と障害対応を情報システム課だけで担っているため、基盤の保守をベンダーへ任せられるクラウド移行も検討します。")],
        people=[("経営企画（利用部門）", "朝の部門会議のために毎朝すぐ数字を見たい。データは失いたくない。"),
                ("経理（集計業務）", "締め後の数字は固定したい。月次報告と合わなくなるため。"),
                ("基盤担当（情報システム課）", "移行では切替の作業で停止が必要になる可能性がある。復旧の試験はしたことがない。")],
        issue="「毎朝すぐ」は何時までか、「失いたくない」はどこまで戻せればよいかが決まっていません。障害の一次受付など、アプリと基盤の担当の境界も未定です。",
        demo="曖昧な要望を確認できる条件に分け、数値の出所を確かめ、アプリと基盤の担当を整理する流れを、時系列で追います。",
        checks=["毎朝手作業で統合", "約90分", "朝9時の部門会議に使うためだ", "月に2回ほど9時を過ぎる", "毎朝すぐに本社が集計結果を確認する", "保守と障害対応を情報システム課だけで担っている",
                "基盤の保守をベンダーへ任せられるクラウドへの移行も検討している", "データを失いたくない", "締め後の数字は固定してほしい", "切替の作業で停止が必要になる可能性がある", "復旧を試験したことはない", "障害の一次受付の担当は未定である"]),
    "d3": dict(
        title="大阪拠点の回線更新と、保守の進め方を見直す",
        sides=[("保守会社の提案", "保守会社", "外部からの遠隔保守で、障害対応を早くしたい", "障害対応を早くするために、外部からの遠隔保守を提案します"),
               ("社内規程の制約", "情報システム課", "外部からの接続は禁止（事前承認による例外の規定あり）", "当社の規程では外部からの接続は禁止です"),],
        focus="遠隔保守の提案と、外部接続を禁じる規程をどう整理するか？",
        rows=[("現在の業務", "大阪拠点と本社は主回線1本で接続しており、代替回線はありません。障害時は保守会社の担当者が拠点へ出向いて対応しています。"),
              ("困りごと", "朝9時の受発注の時間帯に画面が遅くなると現場が申告しています（通信量は未計測）。障害時は担当者の到着まで時間がかかります。"),
              ("今回、変えたいこと", "回線を更新し、受発注の業務が止まりにくい通信環境にします。")],
        people=[("大阪拠点", "速くて止まりにくい回線にしたい。回線が切れても受発注だけは続けたい。"),
                ("保守会社", "障害対応を早くするために、外部からの遠隔保守を提案している。"),
                ("情報システム課", "規程では外部からの接続は禁止。例外の手続きは確認が必要。"), ("情報セキュリティ", "例外を認めるかを判断する。")],
        issue="保守会社の提案と、外部接続を禁じる規程をどう扱うか。遠隔保守はまだ提案の段階で、決定ではありません。規程には事前承認による例外がありますが、条件がそろうかは未確認です。",
        demo="録画の発言を根拠に、提案・制約・合意を区別し、確認すべきことを整理する流れを、時系列で追います。",
        checks=["主回線1本", "代替回線はない", "保守会社の担当者が大阪拠点へ出向いて対応している", "朝九時の受発注の時間帯に画面が遅くなります", "通信量はまだ計測していません", "到着するまで時間がかかる",
                "速くて止まりにくい回線です", "受発注だけでも続けたいです", "障害対応を早くするために、外部からの遠隔保守を提案します", "当社の規程では外部からの接続は禁止です",
                "遠隔保守はまだ提案の段階で、決定ではありません", "事前承認により例外を認める"]),
}


FINAL = dict(process="体験の終了と資料", short="体験の終了と資料", stage=4, page="overview", title="体験の振り返りとサンプル資料", lead=None, finale=True,
             main=lambda g: [], more=lambda g: [], open=lambda g: [], count=lambda g: None)


def _d1() -> dict:
    steps = [
        dict(process="案件の背景", short="案件の背景", stage=2, page="overview", title=STORIES["d1"]["title"],
             lead=None,
             main=lambda g: [g.story("d1")],
             more=lambda g: [],
             open=lambda g: [], count=lambda g: None),
        dict(process="会議前の準備", short="会議前の確認点", stage=1, page="prep", title="規程にない「訂正の手順」を、会議で確認する",
             lead=None,
             main=lambda g: [g.versus(("規程に書いてあること", "承認された申請の内容は変更できない"), ("会議で確認すること", g.question("承認後に金額の誤り")["text"], False), None)],
             more=lambda g: [("質問の詳細を見る", [f"確認する理由：{g.question('承認後に金額の誤り')['why']}", f"確認相手：{g.question('承認後に金額の誤り')['ask']}", f"質問の状態：{g.question('承認後に金額の誤り')['status']}", g.where("承認された申請の内容は変更できない")])],
             open=lambda g: [(REPORTED, "金額の誤りは月に数件（現場の申告）"), (UNKNOWN, "金額の誤りの正確な件数・集計期間・発生しやすい条件"), (UNKNOWN, "台帳を直すときの具体的な手順"), (UNKNOWN, "代理承認の運用")], count=lambda g: f"代表例1件／質問 全{len(g.p['questions'])}件"),
        dict(process="会議後の整理", short="要望と制約の整理", stage=2, page="candidates", title="現場の要望と、経理の制約を分けて整理",
             lead=None,
             main=lambda g: [g.versus(("現場の要望", "承認後でも金額を訂正できるようにしたい"), ("経理の制約", "直接変更は認めない"),
                                      ("アプリの整理（関係者の発言ではありません）", "訂正は必要。ただし、直接変更以外の方法を検討する。"))],
             more=lambda g: [("発言の根拠を見る", [g.full("承認後でも金額を訂正できるようにしたい"), g.full("変更履歴があっても直接変更は認めない")]),
                             ("AI候補を確認する仕組みを見る", [f"AI候補「{g.candidate('5回')['text']}」は、資料にない数値（{'、'.join(g.candidate('5回')['unsupported_numbers'])}）に印が付き、担当者が「{g.candidate('5回')['state']}」としました。"])],
             open=lambda g: [(DECIDE, "訂正の方式（次の工程で比較）")], count=lambda g: f"代表例2件／候補 全{len(g.p['candidates'])}件"),
        dict(process="会議での発言", short="第2回の発言", stage=2, page="recordings", title="話者の確認が未実施の発言は、判断の根拠にしない",
             lead=None,
             main=lambda g: [g.speech("金額の訂正は再申請で進めます", "話者の確認が未実施のため、判断の根拠には使っていません。")],
             more=lambda g: [("他の発言を見る", [g.line("元の内容を引き継げるなら"), g.line("元の記録が残る"), g.line("再申請でも金額の基準は同じです")]),
                             ("判断の根拠を見る", [g.dec("承認後の金額訂正の方式").get("confirmation") or "記録なし"])],
             open=lambda g: [(HUMAN, x) for x in g.unconfirmed_open()], count=lambda g: f"代表例1件／発言 全{sum(len(r['segments']) for r in g.p['recordings'])}件",
             media_note="第2回は会議ツールの字幕を取り込んだ記録で、録画の再生はありません。"),
        dict(process="判断", short="訂正方法の比較", stage=2, page="decisions", title="3案を比べて、再申請を採用した",
             lead=None,
             main=lambda g: [g.verdict("承認後の金額訂正の方式", "判断の確認メール", "金額の訂正は再申請で進めます")],
             evidence_button="この判断に使った確認メールを見る",
             more=lambda g: [],
             open=lambda g: [(DECIDE, f"{d['topic']}（{d['state']}：{d.get('hold_reason')}）") for d in g.p["decisions"] if d["state"] == "保留"], count=lambda g: f"代表例1件／判断 全{len(g.p['decisions'])}件"),
        dict(process="追加要望と影響", short="追加要望の影響", stage=3, page="changes", title="経理の直接訂正の要望が、過去の判断と衝突する",
             lead=lambda g: _request_lead(g, "直接訂正"),
             main=lambda g: [_flow3(g, "金額の誤り", "直接訂正"), g.table_conflict(g.chg("直接訂正"))],
             more=lambda g: [("影響の調査を見る", g.impact_lines(g.chg("直接訂正")))],
             open=lambda g: [(DECIDE, "直接訂正を認めるか"), (UNKNOWN, f"影響を未調査の領域 {g.impacts(g.chg('直接訂正'))[1]}件")], count=lambda g: f"代表例1件／追加要望 全{len(g.p['changes'])}件"),
        dict(process="判断後の仕様", short="判断後の仕様", stage=4, page="trail", title="追加要望への判断と、変更された仕様",
             lead=None,
             main=lambda g: [g.change_summary("金額の誤り", "直接訂正", "経理担当者による直接訂正",
                                              before=("申請者が再申請し、内容を引き継いだ下書きを作る", ["申請者が再申請する", "内容を引き継いだ下書き"]),
                                              after=("経理担当者も、再申請の下書きを代行作成できる", "再申請の下書きは経理担当者が代行作成できる"),
                                              keep=("承認済みの申請は直接変更しない", "承認済みの申請は直接変更できない"),
                                              scope="経理担当者が代行できるのは、再申請の下書きの作成までです。承認済みの申請の金額を直接訂正することは認めていません。"),
                             g.decision("経理担当者による直接訂正"), _after(g, "金額の誤り"), g.timeline("金額の誤り")],
             more=lambda g: [("「なぜ再申請か」の回答を見る", [g.why("なぜ再申請なのか")["reason"]]), ("判断の根拠を見る", g.citations("経理担当者による直接訂正"))],
             open=lambda g: [(DECIDE, f"{d['topic']}（{d['state']}）") for d in g.p["decisions"] if d["state"] == "保留"], count=lambda g: f"履歴 全{len(g.p['history'])}件"),
        FINAL,
    ]
    return steps


def _d2() -> dict:
    return [
        dict(process="案件の背景", short="案件の背景", stage=2, page="overview", title=STORIES["d2"]["title"],
             lead=None,
             main=lambda g: [g.story("d2")],
             more=lambda g: [],
             open=lambda g: [], count=lambda g: None),
        dict(process="会議前の準備", short="資料の確認", stage=1, page="sources", title="資料から読めたことと、読めなかったこと",
             lead=None,
             main=lambda g: [g.versus(("読めたこと", "約90分"), ("読めなかったこと", "データ増加率は未計測", False), None)],
             more=lambda g: [("図の扱いを見る", [next(w for s in g.p["sources"] for w in s["warnings"] if "理解していません" in w), f"人の補足：{next(s['supplement'] for s in g.p['sources'] if s.get('supplement'))}"]),
                             ("資料の位置を見る", [g.where("約90分"), g.where("データ増加率")])],
             open=lambda g: [(MEASURE, "データの増加率"), (DECIDE, "障害の一次受付の担当"), (UNKNOWN, "復旧の手順の有無"), (VERIFY, "復旧できるか（復旧試験は未実施）")], count=lambda g: f"資料 全{len(g.p['sources'])}件"),
        dict(process="具体化", short="条件への具体化", stage=2, page="refine", title="「毎朝すぐ」「失いたくない」を測れる条件に分ける",
             lead=None,
             main=lambda g: [g.convert([g.measure("毎朝8時30分", "集計の完了時刻", "毎朝すぐに売上の数字を見たい"), g.measure("4時間以内", "目標復旧時間", "データを失いたくない"), g.measure("1日分まで", "許容データ損失", "データを失いたくない")])],
             more=lambda g: [("発言の根拠を見る", [g.full("毎朝すぐに売上の数字を見たい"), g.full("データを失いたくない"), g.full("毎朝8時30分までに")])],
             open=lambda g: [(MEASURE, m["metric"]) for r in g.p["requirements"] for m in r["measures"] if m["status"] == "未計測"], count=lambda g: f"代表例3件／数値条件 全{sum(len(r['measures']) for r in g.p['requirements'])}件"),
        dict(process="アプリと基盤の境界", short="アプリと基盤の境界", stage=2, page="nfr", title="アプリと基盤の担当を分け、未決を残す",
             lead=None,
             main=lambda g: [g.versus(("アプリの保守", "情報システム課", False, "アプリの保守は情報システム課"), ("クラウド基盤の保守", "ベンダー", False, "クラウド基盤の保守はベンダー"),
                                      ("まだ決まっていないこと", "障害の一次受付の担当は未定です。"))],
             more=lambda g: [("リスクを見る", [f"{g.p['risks'][0]['content']}（{g.p['risks'][0]['nature']}）"]), ("資料の位置を見る", [g.where("アプリの保守は情報システム課")])],
             open=lambda g: [(VERIFY, "4時間以内に復旧できるか（復旧試験は未実施）"), (DECIDE, "障害の一次受付の担当"), (DECIDE, "切戻しの条件")], count=lambda g: f"リスク 全{len(g.p['risks'])}件"),
        dict(process="意見調整", short="停止の調整", stage=2, page="issues", title="朝の集計を止めずに、保守の停止を認めた",
             lead=None,
             main=lambda g: [g.versus(("業務の希望", "朝の集計は止めないでほしい"), ("基盤の条件", "保守の計画停止は月1回の日曜夜に限る案", False, "保守の計画停止は月1回の日曜夜に限る案"), None), g.decision("計画停止の扱い")],
             more=lambda g: [("判断の根拠を見る", g.citations("計画停止の扱い"))],
             open=lambda g: [(DECIDE, i["topic"]) for i in g.p["issues"] if i["state"] != "結論あり"], count=lambda g: f"論点 全{len(g.p['issues'])}件"),
        dict(process="追加要望と影響", short="再集計の要望", stage=3, page="changes", title="締め後の再集計の要望が、固定のルールと衝突する",
             lead=lambda g: _request_lead(g, "再集計"),
             main=lambda g: [_flow3(g, "締め後の数字", "再集計"), g.table_conflict(g.chg("再集計"))],
             more=lambda g: [("影響の調査を見る", g.impact_lines(g.chg("再集計")))],
             open=lambda g: [(DECIDE, "当月の再集計を認めるか"), (UNKNOWN, f"影響を未調査の領域 {g.impacts(g.chg('再集計'))[1]}件")], count=lambda g: f"代表例1件／追加要望 全{len(g.p['changes'])}件"),
        dict(process="判断後の仕様", short="判断と理由", stage=4, page="why", title="再集計の要望への判断と、変更された仕様",
             lead=None,
             main=lambda g: [g.change_summary("締め後の数字", "再集計", "締め後の再集計",
                                              before=("訂正は、翌月の訂正版として作る", "訂正は翌月の訂正版として作る"),
                                              after=("訂正は、訂正版として翌営業日までに作る", "訂正は訂正版として翌営業日までに作る"),
                                              keep=("締め後の数字は固定し、元の数字は残す", ["締め後の数字は固定し", "元の数字は残す"]),
                                              scope="当月の数字の再集計は認めていません。早めたのは、訂正版を作る時期です。"),
                             g.decision("締め後の再集計"), _after(g, "締め後の数字"), g.timeline("締め後の数字")],
             more=lambda g: [("理由が未記録の例を見る", [f"質問「{g.why('なぜ保存期間は3年なのか')['question']}」への回答：{g.why('なぜ保存期間は3年なのか')['reason']}（AIで補っていません）"]), ("判断の根拠を見る", g.citations("締め後の再集計"))],
             open=lambda g: g.open_summary(), count=lambda g: f"履歴 全{len(g.p['history'])}件"),
        FINAL,
    ]


def _d3() -> dict:
    return [
        dict(process="案件の背景", short="案件の背景", stage=2, page="overview", title=STORIES["d3"]["title"],
             lead=None,
             main=lambda g: [g.story("d3")],
             more=lambda g: [],
             open=lambda g: [], count=lambda g: None),
        dict(process="会議前の準備", short="通信と構成の確認", stage=1, page="sources", title="通信一覧と構成図で、分かることと未確認を分ける",
             lead=None,
             main=lambda g: [g.versus(("資料から分かること", "拠点間は主回線1本で接続している"), ("未確認のまま残すこと", "保守会社の通信のポートは未確認", False), None)],
             more=lambda g: [("図の扱いを見る", [next(w for s in g.p["sources"] for w in s["warnings"] if "理解していません" in w), f"人の補足：{next(s['supplement'] for s in g.p['sources'] if s.get('supplement'))}"]),
                             ("通信一覧の原文を見る", [g.full("F03")])],
             open=lambda g: [(MEASURE, "通信量"), (MEASURE, "ピークの時間帯"), (MEASURE, "切替時間"), (DECIDE, "許容できる停止時間")], count=lambda g: f"資料 全{len(g.p['sources'])}件"),
        dict(process="録画の発言", short="録画の発言", stage=2, page="recordings", title="保守会社の発言は「提案」であり、決定ではない",
             lead=None,
             main=lambda g: [g.speech("外部からの遠隔保守を提案します", "区分は「提案」です。この発言だけでは合意になりません。")],
             more=lambda g: [("他の発言を見る", [g.line("現場の要望は、速くて止まりにくい回線です"), g.line("外部からの接続は禁止です"), g.line("遠隔保守はまだ提案の段階")])],
             open=lambda g: [(DOCUMENT, g.fact("事前承認により例外を認める")["full"]), (UNKNOWN, "今回の遠隔保守が例外の対象になるか"), (UNKNOWN, "例外の申請先と承認の手順")] + [(HUMAN, x) for x in g.unconfirmed_open()], done=lambda g: g.confirmed_note(), count=lambda g: f"代表例1件／発言 全{sum(len(r['segments']) for r in g.p['recordings'])}件"),
        dict(process="具体化", short="条件への具体化", stage=2, page="refine", title="「速く、止まりにくく」を条件と未計測に分ける",
             lead=None,
             main=lambda g: [g.convert([g.measure("受発注の画面", "画面の表示時間", "朝九時の受発注の時間帯に画面が遅くなります"), g.measure("受発注の画面", "ピーク時の通信量"),
                                        g.measure("回線断", "許容停止時間"), g.measure("回線断", "代替回線への切替時間")])],
             more=lambda g: [("発言の根拠を見る", [g.full("朝9時の受発注の画面は3秒以内"), g.full("受発注の停止は30分まで")])],
             open=lambda g: [(MEASURE, m["metric"]) for r in g.p["requirements"] for m in r["measures"] if m["status"] == "未計測"], count=lambda g: f"代表例4件／数値条件 全{sum(len(r['measures']) for r in g.p['requirements'])}件"),
        dict(process="合意前の確認", short="提案の状態", stage=2, page="decisions", title="遠隔保守の扱いは、まだ合意していない",
             lead=None,
             main=lambda g: [g.decision("遠隔保守の扱い")],
             more=lambda g: [("確認する質問を見る", g.p["issues"][0]["extra_questions"])],
             open=lambda g: [(DECIDE, "遠隔保守の扱い（判断者：" + (g.dec("遠隔保守の扱い").get("decider") or "未設定") + "）")], count=lambda g: f"判断 全{len(g.p['decisions'])}件"),
        dict(process="追加要望と影響", short="常時接続の要望", stage=3, page="changes", title="常時接続の要望が、外部接続の禁止と衝突する",
             lead=lambda g: _request_lead(g, "常時接続"),
             main=lambda g: [_flow3(g, "遠隔保守", "常時接続"), g.table_conflict(g.chg("常時接続"))],
             more=lambda g: [("影響の調査を見る", g.impact_lines(g.chg("常時接続")))],
             open=lambda g: [(DECIDE, "保守の方式"), (UNKNOWN, f"影響を未調査の領域 {g.impacts(g.chg('常時接続'))[1]}件")], count=lambda g: f"代表例1件／追加要望 全{len(g.p['changes'])}件"),
        dict(process="判断後の仕様", short="判断と理由", stage=4, page="why", title="常時接続の要望への判断と、変更された仕様",
             lead=None,
             main=lambda g: [g.change_summary("現地対応", "常時接続", "遠隔保守の扱い",
                                              before=("保守会社が遠隔保守を行う（提案の段階）", "保守会社が遠隔保守を行う（提案）"),
                                              after=("今回の保守は現地対応とし、時間限定の遠隔接続は次回以降に検討する", ["今回の保守は現地対応とする", "時間限定の遠隔接続は次回以降に検討する"]),
                                              keep=("社外から社内ネットワークへの外部接続は禁止する", "社外から社内ネットワークへの外部接続は禁止する"),
                                              scope="常時接続は認めていません。時間限定の接続は、承認者とログの運用が決まるまで次回以降の検討です。"),
                             g.decision("遠隔保守の扱い"), _after(g, "現地対応"), g.timeline("現地対応")],
             more=lambda g: [("過去の指摘を見る", [f"{a}：{b}" for a, b, _ in g.conflict(g.chg("常時接続"))] + g.impact_lines(g.chg("常時接続"))[:2]), ("判断の根拠を見る", g.citations("遠隔保守の扱い"))],
             open=lambda g: g.open_summary(), count=lambda g: f"履歴 全{len(g.p['history'])}件"),
        FINAL,
    ]


GUIDES = {"d1": _d1, "d2": _d2, "d3": _d3}

# 本文上部に出す大きな区分（名前と、含む画面の数）。画面の並びと合わないとテストで検出する
PHASES = {
    "d1": [("背景と準備", 3), ("比較と判断", 2), ("変更と成果物", 3)],
    "d2": [("背景と資料", 2), ("条件の具体化と調整", 3), ("変更と成果物", 3)],
    "d3": [("背景と資料", 2), ("録画の確認と条件", 3), ("変更と成果物", 3)],
}

# 見どころへの近道（画面の番号は0から）。一覧のカードで説明した体験に直結する画面を選ぶ
SHORTCUTS = {
    "d1": (4, "見どころへ：3案の比較と採用理由"),
    "d2": (2, "見どころへ：「毎朝すぐ」を測れる条件にする"),
    "d3": (2, "見どころへ：録画の発言と提案の扱い"),
}


def phase_of(demo_id: str, index: int) -> tuple[int, str]:
    """画面の番号から、大きな区分の番号と名前を返す。"""
    end = 0
    for n, (name, size) in enumerate(PHASES[demo_id]):
        end += size
        if index < end:
            return n, name
    raise IndexError(index)

# デモ用の役割と、体験の振り返り。実案件の利用者の役割を決めるものではない
INTRO = {
    "d1": dict(role="現場と経理の要望を取りまとめる要件定義担当者",
               done="対立する要望の整理から、判断理由の記録、追加要望への対応までを確認しました。",
               recap=["対立する条件を整理した", "比較と判断理由を記録した", "追加要望と過去の判断の関係を追跡した"],
               spec_note="再申請方式を採用した理由と、未確認の項目がどう記録されたかを確認できます。"),
    "d2": dict(role="業務部門と基盤担当の条件を取りまとめる要件定義担当者",
               done="曖昧な要望の具体化から、アプリと基盤の整理、追加要望への対応までを確認しました。",
               recap=["曖昧な要望を、確認できる条件に分けた", "数値の出所と確認状態を区別した", "アプリと基盤の担当範囲と未決事項を整理した"],
               spec_note="「毎朝8時30分まで」などの数値条件と、訂正版で対応する判断の理由、未確認の項目を確認できます。"),
    "d3": dict(role="拠点の要望と保守会社の提案を取りまとめる要件定義担当者",
               done="録画の発言の確認から、提案と合意の区別、追加要望への対応までを確認しました。",
               recap=["録画の発言を、時刻付きの根拠として確認した", "提案・制約・合意を区別した", "追加要望の影響を調べ、判断と理由を記録した"],
               spec_note="現地対応を採用した理由と、時間限定の遠隔接続など未決の項目がどう記録されたかを確認できます。"),
}


def _request_lead(g: Ctx, text: str) -> str:
    r = g.requests(text)
    return f"要望者：{r['who']}。背景：{r['why']} 要望は受け付けただけで、要件はまだ変わっていません。"


def _adopted(g: Ctx, topic: str) -> str:
    return g.decision(topic)["adopted"]


AI, PROGRAM = "AIの支援（準備済みの結果）", "プログラムの処理"
AFTER = "判断後の仕様を要件の新しい版として記録し、変更前後の差分と履歴を残す"

# 各画面の場面。scene は案件の時点、date はその日付、check はこの場面の要点（1〜2文）。
# support は入力・根拠／AI／プログラム／人の役割で、実際に動く機能だけを書く。
SCENES = {
    "d1": [
        dict(scene="案件の背景", check="", support=None, detail=lambda g: "案件の概要と残件を見る"),
        dict(scene="第1回会議の前", check="規程に訂正の手順がないため、会議で誰に何を聞くかを準備します。", detail=lambda g: f"質問{g.count('questions')}件を確認する",
             support=[("入力・根拠", "要望メモと経費申請規程"), (AI, "規程から確認すべき質問と不足情報の候補を作成"), (PROGRAM, "分野別の確認観点から質問候補を作成"), ("人が行うこと", "質問を選び、確認相手を決める")]),
        dict(scene="第1回会議の後", date=lambda g: g.on("第1回"), check="第1回の発言を、現場の要望と経理の制約に分けます。", detail=lambda g: f"候補{g.count('candidates')}件を確認する",
             support=[("入力・根拠", "第1回議事録と第2回の字幕"), (AI, "要望・制約・決定の候補を抽出"), (PROGRAM, "引用を原文と照合し、資料にない数値に印を付ける"), ("人が行うこと", "候補を読み、採用か却下かを決める")]),
        dict(scene="第2回会議の記録", date=lambda g: g.on("第2回打ち合わせ"), check="初回で整理した要望と制約を受け、訂正方法についての発言を確認します。", detail=lambda g: f"発言{sum(len(r['segments']) for r in g.p['recordings'])}件と確認状態を見る",
             support=[("入力・根拠", "会議ツールの字幕"), (PROGRAM, "発言ごとに話者と内容の確認状態を記録し、未確認の情報だけでは合意できないようにする"), ("人が行うこと", "話者と内容を確認する")]),
        dict(scene="第2回会議の後", date=lambda g: g.dec("承認後の金額訂正の方式")["decided_on"], check="発言の確認を受け、判断者が訂正方法を選びました。", detail=lambda g: "決定・合意の一覧を見る",
             support=[("入力・根拠", "3つの案、第2回の発言、確認メール"), (PROGRAM, "採用案・判断者・判断日がそろわない記録は合意にしない"), ("人が行うこと", "案を比べ、採否と理由を判断する（AIは比較も判断もしていません）")]),
        dict(scene="追加要望の受付", date=lambda g: g.requests("直接訂正")["date"], check="判断の後、経理担当者から直接訂正の要望が届きました。過去の判断と衝突していないかを確認します。", detail=lambda g: "変更影響の詳細を見る",
             support=[("入力・根拠", "追加要望のメールと過去の判断"), (AI, "影響しそうな点の候補を作成"), (PROGRAM, "登録済みの関連から影響をたどり、文型の照合で矛盾の候補を検出し、未調査の領域を示す"), ("人が行うこと", "影響を確認し、採否を判断する")]),
        dict(scene="第3回会議の後", date=lambda g: g.on("第3回"), check=lambda g: f"関係者の判断で、直接訂正は認めず「{_adopted(g, '経理担当者による直接訂正')}」を採用しました。変更された部分と理由を確認します。", detail=lambda g: "仕様の変遷と理由を見る",
             support=[("入力・根拠", "第3回打ち合わせメモと判断の記録"), (PROGRAM, AFTER), ("人が行うこと", "採否を判断し、要件への反映を確認する")]),
        dict(scene="デモの終了", check="", support=None, detail=lambda g: "機能画面を見る"),
    ],
    "d2": [
        dict(scene="案件の背景", check="", support=None, detail=lambda g: "案件の概要と残件を見る"),
        dict(scene="第1回会議の前", check="計画案・処理量の表・運用メモを読み、会議で確認することを洗い出します。", detail=lambda g: f"資料{g.count('sources')}件を確認する",
             support=[("入力・根拠", "移行計画案、現状の処理量、運用メモ"), (AI, "不足情報と質問の候補を作成"), (PROGRAM, "資料の位置を保って読み取り、内容を読めない図に印を付ける"), ("人が行うこと", "図の意味を補足し、質問を選ぶ")]),
        dict(scene="第2回会議の後", date=lambda g: g.on("第2回"), check="第1回の曖昧な言葉を、第2回の発言をもとに確認できる条件へ分けます。", detail=lambda g: "数値条件と受入条件を見る",
             support=[("入力・根拠", "第1回議事録と第2回打ち合わせメモ"), (AI, "曖昧な言葉を確認する質問を作成（数値は出していません）"), (PROGRAM, "資料にない数値に印を付け、未計測の項目を残件にする"), ("人が行うこと", "数値を確認して登録する")]),
        dict(scene="第2回会議の後", date=lambda g: g.on("第2回"), check="条件を受けて、誰が何を担当するかを整理します。", detail=lambda g: "非機能の確認状況を見る",
             support=[("入力・根拠", "運用メモと要件"), (PROGRAM, "非機能の確認状況を一覧にし、未確認の項目を残す"), ("人が行うこと", "担当範囲を確認し、未定の項目の判断者を決める")]),
        dict(scene="第2回会議の後", date=lambda g: g.on("第2回"), check="朝の集計を止めたくない希望と、保守の停止の調整を見ます。", detail=lambda g: f"論点{g.count('issues')}件を確認する",
             support=[("入力・根拠", "業務の希望と基盤の条件"), (PROGRAM, "意見の立場と根拠を分けて記録する"), ("人が行うこと", "条件を調整し、判断する（AIは判断していません）")]),
        dict(scene="追加要望の受付", date=lambda g: g.requests("再集計")["date"], check="合意の後、福岡拠点から当月の再集計の要望が届きました。固定のルールと衝突していないかを確認します。", detail=lambda g: "変更影響の詳細を見る",
             support=[("入力・根拠", "拠点からの要望と過去の判断"), (AI, "朝の集計と重なる可能性を影響の候補として提示（未計測）"), (PROGRAM, "登録済みの関連から影響をたどり、文型の照合で矛盾の候補を検出し、未調査の領域を示す"), ("人が行うこと", "影響を確認し、採否を判断する")]),
        dict(scene="第3回会議の後", date=lambda g: g.on("第3回"), check=lambda g: f"関係者の判断で、当月の再集計は認めず「{_adopted(g, '締め後の再集計')}」を採用しました。変更された部分と理由を確認します。", detail=lambda g: "「なぜこの仕様か」を試す",
             support=[("入力・根拠", "第3回打ち合わせメモと判断の記録"), (PROGRAM, AFTER + "。「なぜこの仕様か」には登録情報から回答する"), ("人が行うこと", "採否を判断し、要件への反映を確認する")]),
        dict(scene="デモの終了", check="", support=None, detail=lambda g: "機能画面を見る"),
    ],
    "d3": [
        dict(scene="案件の背景", check="", support=None, detail=lambda g: "案件の概要と残件を見る"),
        dict(scene="初回の定例の前", check="通信一覧と構成の資料を読み、会議で確認することを洗い出します。", detail=lambda g: f"資料{g.count('sources')}件を確認する",
             support=[("入力・根拠", "通信一覧、構成説明、規程抜粋、保守の現状メモ"), (AI, "質問と不足情報の候補を作成"), (PROGRAM, "資料の位置を保って読み取り、内容を読めない図に印を付ける"), ("人が行うこと", "図の意味を補足し、質問を選ぶ")]),
        dict(scene="初回の定例の後", date=lambda g: g.on("定例（録画）"), check="定例の録画から、発言が提案か決定かを確認します。", detail=lambda g: f"発言{sum(len(r['segments']) for r in g.p['recordings'])}件と確認状態を見る",
             support=[("入力・根拠", "定例の録画"), (AI, "発言の文字起こし"), (PROGRAM, "発言と時刻を結び付け、指定の時刻から再生できるようにする"), ("人が行うこと", "話者と発言の区分を確認する")]),
        dict(scene="第2回定例の後", date=lambda g: g.on("第2回定例"), check="録画の要望を、第2回定例の発言をもとに確認できる条件へ分けます。", detail=lambda g: "数値条件と受入条件を見る",
             support=[("入力・根拠", "録画の発言と第2回定例メモ"), (AI, "曖昧な言葉を確認する質問を作成（数値は出していません）"), (PROGRAM, "未計測の項目を値のないまま残件にする"), ("人が行うこと", "数値を確認して登録する")]),
        dict(scene="第2回定例の後", date=lambda g: g.on("第2回定例"), check="条件を踏まえて案を比べます。判断はまだ記録されていません。", detail=lambda g: f"判断{g.count('decisions')}件と根拠を見る",
             support=[("入力・根拠", "保守会社の提案、規程、第2回定例メモ"), (AI, "「遠隔保守を採用する」という候補を出したが、提案のため人が却下"), (PROGRAM, "採用案・判断者・判断日がそろわない記録は合意にしない"), ("人が行うこと", "案を比べ、判断する")]),
        dict(scene="追加要望の受付", date=lambda g: g.requests("常時接続")["date"], check="判断が決まらないうちに、保守会社から常時接続の要望が届きました。規程と衝突していないかを確認します。", detail=lambda g: "変更影響の詳細を見る",
             support=[("入力・根拠", "保守会社の要望と規程"), (AI, "影響しそうな点の候補を作成"), (PROGRAM, "登録済みの関連から影響をたどり、文型の照合で矛盾の候補を検出し、未調査の領域を示す"), ("人が行うこと", "影響を確認し、採否を判断する")]),
        dict(scene="第3回定例の後", date=lambda g: g.on("第3回定例"), check=lambda g: f"関係者の判断で、常時接続は認めず「{_adopted(g, '遠隔保守の扱い')}」を採用しました。変更された部分と理由を確認します。", detail=lambda g: "「なぜこの仕様か」を試す",
             support=[("入力・根拠", "第3回定例メモと判断の記録"), (PROGRAM, AFTER), ("人が行うこと", "採否を判断し、要件への反映を確認する")]),
        dict(scene="デモの終了", check="", support=None, detail=lambda g: "機能画面を見る"),
    ],
}


def load(demo_id: str) -> list[dict]:
    """案内の全画面（全体像→時系列の工程→終了）を返す。"""
    return [{**step, **scene} for step, scene in zip(GUIDES[demo_id](), SCENES[demo_id], strict=True)]
