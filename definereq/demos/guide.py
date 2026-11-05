"""3分の案内の内容。

文章の見出しと説明はここに書くが、注目カードの中身（発言、要件、判断、数値）は
その段階の案件データから取得する。データにないものは KeyError になり、テストで検出される。
これにより、結論や根拠の創作と、後の段階の結論の先取りを防ぐ。
"""
from __future__ import annotations

from .. import project as pj
from ..ingest.formats import format_time
from ..logic import agreement as ag
from ..logic import checks, why
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
                    name = s.get("speaker") or s.get("speaker_label")
                    return {"type": "speech", "who": self.role(name), "time": format_time(s["start"]), "text": s["text"], "kind": s.get("kind") or "未分類",
                            "speaker_status": s["speaker_status"], "content_status": s["content_status"], "note": note, "rec_id": rec["id"], "start": s["start"],
                            "where": f"{rec['name']}（{format_time(s['start'])}-{format_time(s['end'])}）"}
        raise KeyError(f"発言がありません: {text}")

    def quote(self, text: str, tag: str, title: str | None = None, note: str | None = None) -> dict:
        """資料の引用カード。本文は資料の行をそのまま使う。"""
        for s in self.p["sources"]:
            for u in s["units"]:
                if text in u["text"]:
                    return {"type": "quote", "tag": tag, "title": title, "text": u["text"], "where": f"{s['name']}（{u['locator']}）", "note": note}
        raise KeyError(f"資料の本文にありません: {text}")

    def measure(self, req_title: str, metric: str, said: str | None = None) -> dict:
        """曖昧な言葉と、確認可能な条件の対応。"""
        r = self.req(req_title)
        m = self._find(r["measures"], lambda x: metric in x["metric"], metric)
        value = "値なし" if m.get("value") is None else f"{m['value']}{m.get('unit') or ''}"
        return {"type": "measure", "said": said, "metric": m["metric"], "value": value, "kind": m["kind"], "condition": m.get("condition") or "未設定", "status": m["status"], "basis": m.get("basis") or "未設定"}

    def options(self, topic: str) -> dict:
        d = self.dec(topic)
        rows = [{"label": o["label"], "pros": o.get("pros"), "cons": o.get("cons"), "adopted": o["id"] == d.get("adopted"),
                 "reason": d.get("rejected_reasons", {}).get(o["id"])} for o in d["options"]]
        return {"type": "options", "topic": d["topic"], "state": d["state"], "rows": rows, "rationale": d.get("rationale"), "decider": d.get("decider"),
                "confirmer": d.get("confirmer"), "date": d.get("decided_on"), "confirmation": d.get("confirmation"), "id": d["id"]}

    def compare(self, rows: list[tuple]) -> dict:
        return {"type": "compare", "rows": rows}

    def conflict(self, change: dict) -> list[tuple]:
        """過去の指摘を、当時の要件の版と結び付けて示す。"""
        rows = []
        for c in self.p["conflicts"]:
            if change["id"] in (c["a"], c["b"]):
                view = conflict_view(self.p, c)
                then = " ／ ".join(f"{s['id']}{s['detected_version']}：{s['detected_text']}" for s in view["sides"])
                rows.append(("衝突の候補（検出時の内容）", f"{then}。{c['note']}", c["kind"]))
                rows.append(("現在の状態", view["summary"], c["state"]))
        return rows

    def open_counts(self) -> list[str]:
        bl = checks.backlog(self.p)
        return [f"{k} {v}件" for k, v in bl["counts"].items() if v]

    def unconfirmed(self) -> int:
        return sum(1 for r in self.p["recordings"] for s in r["segments"] if s["speaker_status"] != "確認済み")

    def agreed(self) -> list[str]:
        out = []
        for d in self.p["decisions"]:
            if d["state"] == "合意済み":
                adopted = next((o["label"] for o in d["options"] if o["id"] == d.get("adopted")), None)
                out.append(f"{d['topic']}：{adopted}")
        return out

    def docs(self) -> list[str]:
        return [f"{d['title']}（v{d['version']}）" for d in self.p["shared_docs"]]

    def impacts(self, change: dict) -> tuple[str, int]:
        kinds: dict[str, int] = {}
        for i in change["impacts"]:
            kinds[i["basis"]] = kinds.get(i["basis"], 0) + 1
        return "、".join(f"{k} {v}件" for k, v in kinds.items()), len(ag.unsurveyed_areas(change))

    def why(self, question: str) -> dict:
        a = why.answer(self.p, question)
        if a["status"] != "answered":
            raise KeyError(f"回答できません: {question}")
        return {"type": "why", "question": question, "target": f"{a['target']['title']}", "reason": a["reason"], "recorded": a["reason_recorded"]}

    def summary(self, text: str, remaining: list[str]) -> dict:
        return {"type": "summary", "text": text, "decided": self.agreed(), "remaining": remaining, "docs": self.docs()}


def _d1() -> dict:
    intro = {"who": "サンプル工業の営業部・経理課・情報システム課が、経費申請アプリの刷新を検討している案件です。",
             "wants": "現場は承認後の金額訂正を簡単にしたい一方、経理は承認済み記録の直接変更を認めていません。",
             "see": "両者の条件を整理し、訂正方式を判断した経緯をたどります。"}
    steps = [
        dict(process="会議前の準備", short="会議前の確認点", stage=1, page="prep", title="承認後の訂正について、会議前に確認する点を絞る",
             lead="規程には承認後は変更できないとありますが、訂正の手順は書かれていません。",
             focus=lambda g: [g.quote("承認された申請の内容は変更できない", "資料からの引用", "経費申請規程"),
                              {"type": "question", "text": g.question("承認後に金額の誤り")["text"], "why": g.question("承認後に金額の誤り")["why"], "ask": g.question("承認後に金額の誤り")["ask"], "status": g.question("承認後に金額の誤り")["status"]}],
             total=lambda g: f"代表例2件／質問 全{len(g.p['questions'])}件",
             learned="規程と要望メモから、会議で確認すべき点を質問にできます。",
             remaining=lambda g: [f"未質問 {sum(1 for q in g.p['questions'] if q['status'] == '未質問')}件"] + g.p["prep"]["gaps"][:2]),
        dict(process="会議後の整理", short="要望と制約の整理", stage=2, page="candidates", title="現場の要望と、経理の制約を分けて整理",
             lead="この時点では方式を確定せず、両方を満たす方法を次の工程で比較します。",
             focus=lambda g: [g.quote("承認後でも金額を訂正できるようにしたい", "要望", "承認後でも金額を訂正できるようにしたい"),
                              g.quote("変更履歴があっても直接変更は認めない", "制約", "直接変更は認めない"),
                              {"type": "ai", "text": next(c for c in g.p["candidates"] if "5回" in c["text"])["text"], "state": next(c for c in g.p["candidates"] if "5回" in c["text"])["state"],
                               "numbers": next(c for c in g.p["candidates"] if "5回" in c["text"])["unsupported_numbers"]}],
             total=lambda g: f"代表例3件／候補 全{len(g.p['candidates'])}件",
             learned="AIの候補は人が確認して採否を決めます。資料にない数値は印が付き、担当者が却下した結果も残ります。",
             remaining=lambda g: ["承認後の訂正の方式は未定（次の工程で比較）"]),
        dict(process="会議での発言", short="第2回の発言", stage=2, page="recordings", title="第2回の発言を、話者の確認状態つきで読む",
             lead="発言をそのまま決定として扱わず、誰の発言で、確認済みかどうかを分けて読みます。",
             focus=lambda g: [g.speech("元の内容を引き継げるなら"), g.speech("元の記録が残る"),
                              g.speech("金額の訂正は再申請で進めます", "ここに注目：この発言は話者が未確認です。このため判断の根拠には使っていません。")],
             total=lambda g: f"代表例3件／全{sum(len(r['segments']) for r in g.p['recordings'])}件",
             learned="要望・制約・決定の区分と、話者や内容の確認状態を発言ごとに残せます。",
             remaining=lambda g: [f"話者が未確認の発言 {g.unconfirmed()}件"],
             media_note="第2回は会議ツールの字幕を取り込んだ記録で、録画の再生はありません。"),
        dict(process="判断", short="訂正方法の比較", stage=2, page="decisions", title="3案を比べて、再申請を採用した理由を残す",
             lead="人が判断した内容として、採用案だけでなく不採用の理由も記録します。",
             focus=lambda g: [g.options("承認後の金額訂正の方式")],
             total=lambda g: f"代表例1件／判断 全{len(g.p['decisions'])}件",
             learned="「なぜこの方式か」を、比較した案と判断者とともに後から確認できます。",
             remaining=lambda g: [f"{d['topic']}（{d['state']}：{d.get('hold_reason')}）" for d in g.p["decisions"] if d["state"] == "保留"]),
        dict(process="追加要望と影響", short="追加要望の影響", stage=3, page="changes", title="経理の直接訂正の要望が、過去の判断と衝突しないか調べる",
             lead="要望は受け付けただけで、要件はまだ変わっていません。",
             focus=lambda g: [g.compare([("現在の要件", f"{g.req('金額の誤り')['title']}：{g.req('金額の誤り')['body']}", g.req("金額の誤り")["status"]),
                                         ("追加された要望", g.chg("直接訂正")["content"], f"受付のみ（{g.chg('直接訂正')['status']}）"),
                                         *g.conflict(g.chg("直接訂正")),
                                         ("影響の調査", g.impacts(g.chg("直接訂正"))[0], f"未調査 {g.impacts(g.chg('直接訂正'))[1]}領域")])],
             total=lambda g: f"代表例1件／追加要望 全{len(g.p['changes'])}件",
             learned="影響は「確認済み」「登録関係」「AI候補」に分かれ、調べていない領域も残ります。",
             remaining=lambda g: [f"未調査の領域 {g.impacts(g.chg('直接訂正'))[1]}件", "直接訂正を認めるかの判断"]),
        dict(process="判断後の仕様", short="判断後の仕様", stage=4, page="trail", title="直接訂正は却下し、経理の代行作成を採用",
             lead="過去の判断と衝突しない形で、月末の締めの問題を解決した経緯です。",
             focus=lambda g: [g.options("経理担当者による直接訂正"),
                              g.compare([("変更前の要件", g.req("金額の誤り")["versions"][-1]["body"], f"v{g.req('金額の誤り')['versions'][-1]['version']}"),
                                         ("判断後の仕様", g.req("金額の誤り")["body"], f"v{g.req('金額の誤り')['version']}・{g.req('金額の誤り')['status']}")]),
                              g.why("なぜ再申請なのか")],
             total=lambda g: f"代表例3件／履歴 全{len(g.p['history'])}件",
             learned="変更前後、却下した案、理由が履歴に残り、「なぜ再申請か」に根拠付きで答えられます。",
             remaining=lambda g: [f"{d['topic']}（{d['state']}）" for d in g.p["decisions"] if d["state"] == "保留"]),
    ]
    final = dict(process="まとめ", short="まとめ", stage=4, page="overview", title="この案件で決まったこと・残っていること",
                 lead="現場と管理部門の意見の違いを整理し、判断の理由を残せました。",
                 focus=lambda g: [g.summary("意見の違いから判断まで、根拠とともにたどれます。", [f"{d['topic']}（{d['state']}）" for d in g.p["decisions"] if d["state"] == "保留"] + g.open_counts())],
                 total=lambda g: None, learned=None, remaining=lambda g: [])
    return {"intro": intro, "steps": steps, "final": final}


def _d2() -> dict:
    intro = {"who": "12拠点のExcelを本社の2名が毎朝手作業で統合している、売上集計の自動化とクラウド移行の案件です。",
             "wants": "経営企画は「毎朝すぐ」「データを失いたくない」と求めていますが、そのままでは確認できる条件になっていません。",
             "see": "曖昧な要望を確認可能な条件に分け、アプリと基盤の境界を整理する流れを確認します。"}
    steps = [
        dict(process="会議前の準備", short="資料の確認", stage=1, page="sources", title="資料から読めたことと、読めなかったことを分ける",
             lead="表の数値は読めますが、図の矢印や画像の意味は文字だけでは分かりません。",
             focus=lambda g: [g.quote("約90分", "資料からの引用", "現状の集計時間"),
                              g.quote("データ増加率", "未計測", "データ増加率は未計測"),
                              {"type": "warn", "title": "ここに注目：図は未理解として扱います", "text": next(w for s in g.p["sources"] for w in s["warnings"] if "理解していません" in w), "extra": next(s["supplement"] for s in g.p["sources"] if s.get("supplement"))}],
             total=lambda g: f"代表例3件／資料 全{len(g.p['sources'])}件",
             learned="読み取れた本文、計測されていない値、人の補足が必要な図を区別できます。",
             remaining=lambda g: g.p["prep"]["gaps"]),
        dict(process="具体化", short="条件への具体化", stage=2, page="refine", title="「毎朝すぐ」「失いたくない」を測れる条件に分ける",
             lead="復旧の時間と失ってよいデータの範囲は、別の条件として確認します。",
             focus=lambda g: [g.measure("毎朝8時30分", "集計の完了時刻", "毎朝すぐに売上の数字を見たい"),
                              g.measure("4時間以内", "目標復旧時間"), g.measure("1日分まで", "許容データ損失", "データを失いたくない")],
             total=lambda g: f"代表例3件／数値条件 全{sum(len(r['measures']) for r in g.p['requirements'])}件",
             learned="要望の言葉が、値・条件・根拠のある条件に変わります。現状の計測値と必要条件も分かれています。",
             remaining=lambda g: [f"{m['metric']}：未計測" for r in g.p["requirements"] for m in r["measures"] if m["status"] == "未計測"]),
        dict(process="非機能と境界", short="アプリと基盤の境界", stage=2, page="nfr", title="アプリと基盤の担当と、確認できていない点を分ける",
             lead="バックアップがあるだけでは、復旧できる根拠にはなりません。",
             focus=lambda g: [g.quote("アプリの保守は情報システム課", "担当の想定", "アプリと基盤の担当"),
                              g.quote("障害の一次受付の担当は未定である", "未決", "障害の一次受付は未定"),
                              {"type": "risk", "text": g.p["risks"][0]["content"], "nature": g.p["risks"][0]["nature"], "uncertainty": g.p["risks"][0]["uncertainty"]}],
             total=lambda g: f"代表例3件／リスク 全{len(g.p['risks'])}件",
             learned="責任分界の未決や、試験していない復旧を、達成済みとせず残件にできます。",
             remaining=lambda g: [f"{r['title']}：{r['open_area']}" for r in g.p["requirements"] if r.get("open_area")]),
        dict(process="意見調整", short="停止の調整", stage=2, page="issues", title="朝の集計を止めたくない希望と、保守の停止を調整する",
             lead="業務上の希望と技術の制約を分け、両立できる条件で判断します。",
             focus=lambda g: [g.quote("朝の集計は止めないでほしい", "業務上の希望", "朝の集計は止めない"),
                              g.quote("保守の計画停止は月1回の日曜夜に限る案", "技術の制約", "保守の計画停止が必要"),
                              g.options("計画停止の扱い")],
             total=lambda g: f"代表例3件／論点 全{len(g.p['issues'])}件",
             learned="「無停止」の希望を、止めてはいけない時間帯と計画停止の条件に分けられます。",
             remaining=lambda g: [i["topic"] for i in g.p["issues"] if i["state"] != "結論あり"]),
        dict(process="追加要望と影響", short="再集計の要望", stage=3, page="changes", title="締め後の再集計の要望が、固定のルールと衝突する",
             lead="要望は受け付けただけで、要件はまだ変わっていません。",
             focus=lambda g: [g.compare([("現在の要件", f"{g.req('締め後の数字')['title']}：{g.req('締め後の数字')['body']}", g.req("締め後の数字")["status"]),
                                         ("追加された要望", g.chg("再集計")["content"], f"受付のみ（{g.chg('再集計')['status']}）"),
                                         *g.conflict(g.chg("再集計")),
                                         ("影響の調査", g.impacts(g.chg("再集計"))[0], f"未調査 {g.impacts(g.chg('再集計'))[1]}領域")])],
             total=lambda g: f"代表例1件／追加要望 全{len(g.p['changes'])}件",
             learned="矛盾は候補として示し、適用範囲は人が確認します。AI候補と確認済みの影響は区別されます。",
             remaining=lambda g: ["当月の再集計を認めるかの判断", f"未調査の領域 {g.impacts(g.chg('再集計'))[1]}件"]),
        dict(process="判断後の仕様", short="判断と理由", stage=4, page="why", title="訂正版で対応すると判断し、理由を残す",
             lead="理由が記録されていない項目には、記録がないと答えます。",
             focus=lambda g: [g.options("締め後の再集計"),
                              g.compare([("変更前の要件", g.req("締め後の数字")["versions"][-1]["body"], f"v{g.req('締め後の数字')['versions'][-1]['version']}"),
                                         ("判断後の仕様", g.req("締め後の数字")["body"], f"v{g.req('締め後の数字')['version']}・{g.req('締め後の数字')['status']}")]),
                              g.why("なぜ保存期間は3年なのか")],
             total=lambda g: f"代表例3件／履歴 全{len(g.p['history'])}件",
             learned="判断の理由を残し、記録のない理由をAIで埋めません。",
             remaining=lambda g: g.open_counts()[:3]),
    ]
    final = dict(process="まとめ", short="まとめ", stage=4, page="overview", title="この案件で決まったこと・残っていること",
                 lead="曖昧な要望を確認可能な条件に分け、アプリと基盤の境界を整理できました。",
                 focus=lambda g: [g.summary("条件と未決事項が、要件定義書にそのまま引き継がれます。", g.open_counts())],
                 total=lambda g: None, learned=None, remaining=lambda g: [])
    return {"intro": intro, "steps": steps, "final": final}


def _d3() -> dict:
    intro = {"who": "大阪拠点のネットワーク更新を検討している案件です。",
             "wants": "現場は速く止まりにくい回線を求め、保守会社は遠隔保守を提案していますが、規程は社外からの接続を禁止しています。",
             "see": "接続ルールと保守の要望の関係を確認し、提案・未確認事項・合意を区別する流れを確認します。"}
    steps = [
        dict(process="会議前の準備", short="通信と構成の確認", stage=1, page="sources", title="通信一覧と構成図で、分かることと未確認を分ける",
             lead="ポートなど資料にない値は作らず、未確認のまま残します。",
             focus=lambda g: [g.quote("F03", "資料からの引用", "保守会社から拠点への通信は提案のみ"),
                              g.quote("社外から社内ネットワークへの外部接続は禁止する", "制約", "外部接続は規程で禁止"),
                              {"type": "warn", "title": "ここに注目：図の線は未理解として扱います", "text": next(w for s in g.p["sources"] for w in s["warnings"] if "理解していません" in w), "extra": next(s["supplement"] for s in g.p["sources"] if s.get("supplement"))}],
             total=lambda g: f"代表例3件／資料 全{len(g.p['sources'])}件",
             learned="通信の用途と、確認されていない項目を分けて質問にできます。",
             remaining=lambda g: g.p["prep"]["gaps"]),
        dict(process="録画の発言", short="録画の発言", stage=2, page="recordings", title="録画の発言から、要望・提案・制約を聞き分ける",
             lead="保守担当の提案と、規程に基づく制約は、同じ会議の発言でも重みが違います。",
             focus=lambda g: [g.speech("現場の要望は、速くて止まりにくい回線です"), g.speech("外部からの遠隔保守を提案します", "ここに注目：これは提案です。決定ではありません。"),
                              g.speech("外部からの接続は禁止です")],
             total=lambda g: f"代表例3件／全{sum(len(r['segments']) for r in g.p['recordings'])}件",
             learned="発言の時刻と話者を根拠として残し、録画の該当箇所から聞き直せます。",
             remaining=lambda g: [f"話者が未確認の発言 {g.unconfirmed()}件", "例外の手続きの有無"]),
        dict(process="具体化", short="条件への具体化", stage=2, page="refine", title="「速く、止まりにくく」を条件と未計測に分ける",
             lead="人数や資料から速度を決めず、測っていない値は未計測のまま残します。",
             focus=lambda g: [g.measure("受発注の画面", "画面の表示時間", "朝九時の受発注の時間帯に画面が遅くなります"), g.measure("受発注の画面", "ピーク時の通信量"),
                              g.measure("回線断", "許容停止時間", "停止が何分まで許容できるかは持ち帰ります"), g.measure("回線断", "代替回線への切替時間")],
             total=lambda g: f"代表例4件／数値条件 全{sum(len(r['measures']) for r in g.p['requirements'])}件",
             learned="必要条件と現状の計測値を分け、未計測の値を推測で埋めません。",
             remaining=lambda g: [f"{m['metric']}：未計測" for r in g.p["requirements"] for m in r["measures"] if m["status"] == "未計測"]),
        dict(process="合意前の確認", short="提案の状態", stage=2, page="decisions", title="保守会社の提案を、合意として扱わない",
             lead="3つの保守方式は比較中で、判断者の判断はまだ記録されていません。",
             focus=lambda g: [g.options("遠隔保守の扱い")],
             total=lambda g: f"代表例1件／判断 全{len(g.p['decisions'])}件",
             learned="発言や提案だけでは合意になりません。判断者・判断日・採用案がそろって初めて記録できます。",
             remaining=lambda g: g.p["issues"][0]["extra_questions"]),
        dict(process="追加要望と影響", short="常時接続の要望", stage=3, page="changes", title="常時接続の要望が、外部接続の禁止と衝突する",
             lead="要望は受け付けただけで、要件はまだ変わっていません。",
             focus=lambda g: [g.compare([("現在の要件", f"{g.req('遠隔保守')['title']}：{g.req('遠隔保守')['body']}", g.req("遠隔保守")["status"]),
                                         ("追加された要望", g.chg("常時接続")["content"], f"受付のみ（{g.chg('常時接続')['status']}）"),
                                         *g.conflict(g.chg("常時接続")),
                                         ("影響の調査", g.impacts(g.chg("常時接続"))[0], f"未調査 {g.impacts(g.chg('常時接続'))[1]}領域")])],
             total=lambda g: f"代表例1件／追加要望 全{len(g.p['changes'])}件",
             learned="分離・運用・責任分界への影響を、確認済み・AI候補・未調査に分けて確認できます。",
             remaining=lambda g: ["保守の方式の判断", f"未調査の領域 {g.impacts(g.chg('常時接続'))[1]}件"]),
        dict(process="判断後の仕様", short="判断と理由", stage=4, page="why", title="今回は現地対応とし、時間限定の接続は次回以降に検討",
             lead="判断者はセキュリティ責任者です。過去の指摘は当時の版のまま残ります。",
             focus=lambda g: [g.options("遠隔保守の扱い"),
                              g.compare([("変更前の要件", g.req("現地対応")["versions"][-1]["body"], f"v{g.req('現地対応')['versions'][-1]['version']}"),
                                         ("判断後の仕様", g.req("現地対応")["body"], f"v{g.req('現地対応')['version']}・{g.req('現地対応')['status']}"), *g.conflict(g.chg("常時接続"))]),
                              g.why("なぜ遠隔保守を今回やらないのか")],
             total=lambda g: f"代表例3件／履歴 全{len(g.p['history'])}件",
             learned="提案から判断までの経緯と、不採用の理由を確認できます。機器や速度の十分性は保証していません。",
             remaining=lambda g: g.open_counts()[:3]),
    ]
    final = dict(process="まとめ", short="まとめ", stage=4, page="overview", title="この案件で決まったこと・残っていること",
                 lead="接続ルールと保守の要望の関係を確認し、提案・未確認事項・合意を区別できました。",
                 focus=lambda g: [g.summary("未計測の値と次回の検討事項は、残件として引き継がれます。", g.open_counts())],
                 total=lambda g: None, learned=None, remaining=lambda g: [])
    return {"intro": intro, "steps": steps, "final": final}


GUIDES = {"d1": _d1, "d2": _d2, "d3": _d3}


def load(demo_id: str) -> list[dict]:
    """案内の全画面（背景→工程→まとめ）を返す。"""
    g = GUIDES[demo_id]()
    first = g["steps"][0]
    return [dict(process="案件の背景", short="案件の背景", stage=first["stage"], page="overview", intro=g["intro"], title="この案件の背景", lead=None),
            *g["steps"], g["final"]]


def citations(p: dict, evidence: list[dict]) -> list[str]:
    return [ev.citation(p, e) for e in evidence]


__all__ = ["Ctx", "load", "pj"]
