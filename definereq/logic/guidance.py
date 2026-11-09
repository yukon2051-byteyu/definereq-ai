"""実案件の状況案内（プログラムによる判定）。

案件データから「今の状況」「確認するとよいこと」「案内を出した理由」を求める。AIは呼ばない。
データから自動で求めるため、解決した案内は次の表示で消える。

守ること
- この処理は案件データを読むだけで、書き換えない（要件・合意・判断者・期限を決めない）
- 段階が分からないときは断定しない。利用者が指定した段階を優先する
- 主な案内は1件。補足は1件まで。残りは開閉式で示す
- 優先順位は固定の並びと、今開いている画面との関連で決める（進捗率は使わない）
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .. import project as pj
from ..schema import COLLECTIONS, IMPACT_AREAS
from . import checks

# 案件の内容を表す部分。案内の保存先と操作の記録は含めない
_STATE_KEYS = ("name", "domains", "traits", "profile", "prep", "nfr_status")
_SKIP = {"ai_runs", "shared_docs"}


def state_fingerprint(p: dict) -> str:
    """案内の対象となる状態の指紋。関連データが変わると別の値になる。保存して読み直しても同じ値になる。"""
    return pj.fingerprint({**{k: p.get(k) for k in _STATE_KEYS}, **{c: p.get(c) for c in COLLECTIONS if c not in _SKIP}})


def guidance_store(p: dict) -> dict:
    """案内の保存先を返す。古いJSONには項目がないため、ここで補う。"""
    g = p.setdefault("guidance", {})
    g.setdefault("notes", [])
    g.setdefault("user_stage", None)
    return g


def user_stage(p: dict) -> str | None:
    return (p.get("guidance") or {}).get("user_stage")


@dataclass
class Advice:
    id: str
    title: str          # 現在の状況の見出し
    situation: str      # 記録から分かる状況
    todo: str           # 今、確認するとよいこと
    reason: str         # 案内を出した理由
    page: str           # 移動先の画面
    button: str         # 移動のボタン
    rank: int           # 既定の順位（小さいほど先）
    pages: set = field(default_factory=set)  # 関連する画面
    items: list = field(default_factory=list)  # 該当する項目
    short: str = ""  # 説明を閉じても残す短い文
    alt: list = field(default_factory=list)  # 副操作（ボタン名, 画面）
    short: str = ""  # 説明を閉じても残す短い文
    alt: list = field(default_factory=list)  # 副操作（ボタン名, 画面）


def _titles(items: list, limit: int = 3) -> list[str]:
    return [str(x) for x in items[:limit]]


def has_meeting_record(p: dict) -> bool:
    """会議の記録（会議の登録、録画、議事録）があるか。"""
    return bool(p["meetings"] or p["recordings"] or any(s.get("kind") == "議事録" for s in p["sources"]))


def needs_stage_question(p: dict) -> bool:
    """段階を判断できないときだけ、利用者に確かめる。"""
    has_content = bool(p["sources"] or p["requirements"] or p["questions"])
    return has_content and not has_meeting_record(p)


def phase(p: dict) -> str:
    """案件の段階。empty：未登録／unprocessed：情報はあるが未解析／clear：確認した範囲で検出なし／open：確認事項あり。"""
    has_info = any(v.get("value") for v in p["profile"].values()) or p["sources"] or p["recordings"] or p["requirements"] or p["prep"].get("understanding")
    if not has_info:
        return "empty"
    bl = checks.backlog(p)
    pending = any(c["state"] in ("候補", "要再確認") for c in p["candidates"])
    if bl["unique_total"] or pending or p["questions"] or p["actions"]:
        return "open"
    return "clear" if p["requirements"] or p["ai_runs"] else "unprocessed"


def _start(p: dict) -> list[Advice]:
    if phase(p) != "empty":
        return []
    return [Advice("start", "案件を作成した直後", "案件名と対象分野だけが登録されています。",
                   "背景・目的・要望の概要を入力するか、手元の資料を登録してください。",
                   "案件情報が未入力で、資料も登録されていないため。", "setup", "準備の概要を開く", 10, {"setup", "overview", "profile", "sources"},
                   short="背景の入力と資料の取り込みは、どちらからでも始められます。")]


def unanalyzed_minutes(p: dict) -> list[str]:
    """AIでまだ整理していない議事録と録画の名前。"""
    runs = [(r.get("selection") or {}) for r in p["ai_runs"] if r["task"] == "extract"]
    done_src = {s for r in runs for s in (r.get("source_ids") or [])}
    done_rec = {s for r in runs for s in (r.get("recording_ids") or [])}
    everything = any(r.get("source_ids") is None for r in runs)
    minutes = [s["name"] for s in p["sources"] if s.get("kind") == "議事録" and not s.get("superseded_by") and s["id"] not in done_src and not everything]
    return minutes + [r["name"] for r in p["recordings"] if r["id"] not in done_rec and not everything]


def requirement_candidates(p: dict) -> list[dict]:
    """確認待ちの要件候補（会議準備のAI候補は除く）。_candidates と同じ条件。"""
    tasks = {r["id"]: r["task"] for r in p["ai_runs"]}
    return [c for c in p["candidates"] if c["state"] in ("候補", "要再確認") and tasks.get(c.get("origin_run")) != "prep"]


def candidate_status(p: dict) -> dict:
    """AI候補（会議準備の候補を除く）の状態。確認待ちの件数と、確定した反映先ごとの件数。"""
    tasks = {r["id"]: r["task"] for r in p["ai_runs"]}
    items = [c for c in p["candidates"] if tasks.get(c.get("origin_run")) != "prep"]
    waiting = [c for c in items if c["state"] in ("候補", "要再確認")]
    done: dict[str, int] = {}
    for c in items:
        if c["state"] in ("採用", "修正して採用"):
            label = c.get("resolved_label") or "記録"
            done[label] = done.get(label, 0) + 1
    words = {"要件": "要件に採用"}
    parts = [f"{words.get(k, k + 'へ反映')} {v}件" for k, v in done.items()]
    adopted = [r for r in p["requirements"] if r.get("from_candidate")]
    return {"total": len(items), "waiting": len(waiting), "done": done, "text": " · ".join([f"確認待ち{len(waiting)}件", *parts]), "adopted": adopted,
            "extracted": any(t == "extract" for t in tasks.values())}


def has_profile(p: dict) -> bool:
    return any(v.get("value") for v in p["profile"].values()) or bool(p["stakeholders"])


PREP = ("会議の準備へ進む", "prep", "背景と資料をもとに、次の打ち合わせで確認することを整理できます。")
RECORDS = ("会議の記録を整理する", "records", "取り込んだ議事録から、要望・決定事項・未決事項を整理できます。")
CANDIDATES = ("AI候補を確認する", "candidates", "整理した候補を確認し、要件として採用するか判断できます。")  # デモと同じ機能名


def setup_next(p: dict) -> dict:
    """案件の準備と資料の画面に出す「次にすること」。主な操作1つと、ほかに進める作業。

    議事録の判定は unanalyzed_minutes（資料種別「議事録」と録画、AIで未整理のもの）を使う。
    未整理の議事録があれば、要件候補があっても記録の整理を先に勧める。背景が空欄でも進められる。
    """
    waiting, cands = unanalyzed_minutes(p), requirement_candidates(p)
    if waiting:
        main, alts = RECORDS, [CANDIDATES] if cands else [PREP]
        status = f"未整理の議事録 {len(waiting)}件"
        detail = f"AIで整理していない記録：{'、'.join(waiting[:3])}" + (f" ほか{len(waiting) - 3}件" if len(waiting) > 3 else "")
    elif cands:
        main, alts, status, detail = CANDIDATES, [PREP], f"確認待ちの要件候補 {len(cands)}件", f"確認待ちの候補：{len(cands)}件"
    elif p["requirements"]:  # 要件の整理が進んだ後は、状況の判定（assess）の結果を使う
        a = assess(p, "setup")["main"]
        if a and a.page not in ("setup", "profile", "sources"):
            return {"label": a.button, "page": a.page, "reason": a.short or a.reason, "status": a.title, "detail": None, "alts": [PREP[:2]] if a.page != "prep" else []}
        main, alts, status, detail = PREP, [], "要件を整理中", None
    elif p["sources"] or has_profile(p):
        main, alts, detail = PREP, [("議事録を取り込む", "sources")] if not p["sources"] else [], None
        status = "資料を登録済み" if p["sources"] else "背景を入力済み・資料は未登録"
    else:
        return {"label": "資料・議事録を取り込む", "page": "sources", "reason": "議事録や要望書があれば取り込むと、次の作業を案内できます。背景の入力から始めることもできます。",
                "status": "背景・資料とも未登録", "detail": None, "alts": [("背景・目的・関係者を入力", "profile")], "empty": True}
    return {"label": main[0], "page": main[1], "reason": main[2], "status": status, "detail": detail, "alts": [x[:2] for x in alts]}


def _after_profile(p: dict) -> list[Advice]:
    """背景だけが登録された状態。会議前の人にも、記録を持っている人にも進み先を示す。"""
    if phase(p) != "unprocessed" or p["sources"] or p["recordings"] or p["questions"]:
        return []
    return [Advice("next_input", "案件の情報を登録しました", "背景や困りごとが登録されています。資料や議事録はまだありません。",
                   "これから会議をする場合は質問を準備し、議事録や資料がある場合は取り込んでください。", "案件情報があり、質問・資料・録画が0件のため。", "prep", "会議を準備する", 12, {"overview", "profile", "prep"},
                   short="背景・目的を登録しました。次は会議の準備、または議事録の取込みへ進めます。", alt=[("議事録を取り込む", "records")])]


def _sources(p: dict) -> list[Advice]:
    out = []
    active = [s for s in p["sources"] if not s.get("superseded_by")]
    empty = [s for s in active if not s.get("units")]
    if empty:
        out.append(Advice("source_empty", "資料の本文を読み取れていません", f"{len(empty)}件の資料から本文を取り出せませんでした。",
                          "資料の内容を確認し、文章を貼り付けるか別の形式で登録し直してください。", "本文の単位が0件の資料があるため。", "sources", "資料を確認する", 15,
                          {"sources"}, _titles([s["name"] for s in empty])))
    unread = [s for s in active if not s.get("supplement") and any("理解していません" in w for w in s.get("warnings", []))]
    if unread:
        out.append(Advice("source_figure", "図の内容を読み取れていない資料があります", f"{len(unread)}件の資料に、内容を理解できていない図があります。",
                          "図の意味を人が補足してください。補足がない図は根拠に使われません。", "資料に図の未理解の警告があり、人の補足が未入力のため。", "sources", "資料を確認する", 45,
                          {"sources"}, _titles([s["name"] for s in unread])))
    if active and not p["questions"] and not has_meeting_record(p):  # 議事録があれば会議前とは限らない
        out.append(Advice("sources_added", "資料の登録後", f"資料{len(active)}件を登録しましたが、質問はまだ登録されていません。",
                          "確認観点と質問候補を見て、会議で聞く項目を選んでください。", "資料があり、会議の記録と質問が0件のため。", "prep", "質問候補を確認する", 20, {"sources", "prep", "overview"},
                          alt=[("議事録を取り込む", "records")]))
    return out


def _prep(p: dict) -> list[Advice]:
    unasked = [q for q in p["questions"] if q["status"] == "未質問"]
    if not unasked:
        return []
    known = has_meeting_record(p)
    stage = user_stage(p)
    if known:
        title = "次の会議の準備"
    elif stage == "before_first":
        title = "初回会議の準備"
    else:
        title = "会議の準備"  # 初回かどうかは記録から分からないため断定しない
    gaps = p["prep"].get("gaps") or []
    known_gap = f"未確認の情報：{'、'.join(_titles(gaps))}。" if gaps else ""
    return [Advice("prep", title, f"未質問の質問が{len(unasked)}件あります。{known_gap}", "質問候補を確認し、会議で聞く項目を選んでください。",
                   f"状態が「未質問」の質問が{len(unasked)}件あるため。", "prep", "質問候補を確認する", 40, {"prep", "meetings"}, _titles([q["text"] for q in unasked]))]


def _meeting_records(p: dict) -> list[Advice]:
    out = []
    unconfirmed = [s for r in p["recordings"] for s in r["segments"] if s.get("target", True) and (s["speaker_status"] != "確認済み" or s["content_status"] != "確認済み")]
    if unconfirmed:
        out.append(Advice("recording_check", "議事録・録画の解析後", f"話者または内容の確認が済んでいない発言が{len(unconfirmed)}件あります。確認が済むまで、判断の根拠としては扱いません。",
                          "発言の話者と内容を確認してください。", "話者または内容の確認状態が「確認済み」でない発言があるため。", "recordings", f"発言{len(unconfirmed)}件を確認する", 25, {"recordings", "sources"}))
    if user_stage(p) == "after_first" and not has_meeting_record(p):
        out.append(Advice("meeting_missing", "会議の記録が未登録", "会議は実施済みと指定されていますが、議事録や録画が登録されていません。",
                          "Word・Excel・PDF・テキストの議事録を取り込むか、文章を貼り付けてください。録画がなくても進められます。", "会議の記録が0件のため。", "records", "議事録を取り込む", 22, {"records", "recordings", "sources", "meetings"},
                          short="議事録を取り込み、AIで整理し、候補を確認します。録画がなくても進められます。"))
    waiting = unanalyzed_minutes(p)
    if waiting:
        # 要件を手作業で登録している場合は、解析を強く勧めない
        out.append(Advice("extract", "議事録を登録しました", f"AIで整理していない会議の記録が{len(waiting)}件あります。", "AIで要望・決定・未決事項を候補として整理してください。",
                          "会議の記録があり、AIの整理が済んでいないため。", "records", "議事録をAIで整理する", 60 if p["requirements"] else 16, {"records", "candidates", "recordings", "sources"}, _titles(waiting),
                          short="議事録を登録しました。次はAIで要望や未決事項を整理します。", alt=[("次回の質問を準備する", "prep")]))
    return out


def _candidates(p: dict) -> list[Advice]:
    pending = [c for c in p["candidates"] if c["state"] in ("候補", "要再確認")]
    if not pending:
        return []
    weak = sum(1 for c in pending if c.get("no_evidence") or c.get("unsupported_numbers"))
    note = f"うち{weak}件は根拠の確認が必要です。" if weak else ""
    tasks = {r["id"]: r["task"] for r in p["ai_runs"]}
    prep = [c for c in pending if tasks.get(c.get("origin_run")) == "prep"]
    out = []
    if prep:
        out.append(Advice("prep_candidates", "会議準備の候補の確認", f"AIが作成した準備の候補が{len(prep)}件あります。", "内容を読み、質問や議題へ追加するか却下してください。",
                          f"会議準備のAI候補に未処理が{len(prep)}件あるため。", "prep", f"候補{len(prep)}件を確認する", 30, {"prep"}, _titles([c["text"] for c in prep])))
    rest = [c for c in pending if c not in prep]
    if rest:
        kinds: dict[str, int] = {}
        for c in rest:
            kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
        breakdown = "、".join(f"{k}{v}件" for k, v in kinds.items())
        title = "議事録・資料の解析が完了" if any(tasks.get(c.get("origin_run")) == "extract" for c in rest) else "AI候補の確認"
        out.append(Advice("candidates", title, f"{len(rest)}件の候補を整理しました（{breakdown}）。{note}候補のままでは要件になりません。", "内容と引用を確認し、必要なものを案件へ反映してください。",
                          f"未処理の候補が{len(rest)}件あるため。", "candidates", "AI候補を確認する", 26, {"records", "candidates", "requirements"}, _titles([c["text"] for c in rest]),
                          short=f"確認待ち{len(rest)}件。候補のままでは要件になりません。"))
    return out


def _conflicts(p: dict) -> list[Advice]:
    open_items = [c for c in p["conflicts"] if c["state"] in ("未確認", "確認中")]
    known = checks.registered_conflict_keys(p)
    found = [c for c in checks.scan_conflicts(p)["candidates"] if c["key"] not in known]
    total = len(open_items) + len(found)
    if not total:
        return []
    return [Advice("conflicts", "対立・矛盾の候補", f"確認が済んでいない矛盾の候補が{total}件あります。候補であり、矛盾と確定したものではありません。",
                   "適用範囲や例外を確認し、矛盾かどうかを判断してください。", "プログラムの照合で候補を検出した、または未確認の登録があるため。", "conflicts", "矛盾の候補を確認する", 35, {"conflicts", "requirements", "changes"},
                   _titles([c["note"] for c in open_items + found]))]


def _changes(p: dict) -> list[Advice]:
    out = []
    received = [c for c in p["changes"] if c["status"] == "受付" and not c.get("impacts")]
    if received:
        out.append(Advice("change_new", "追加要望の登録後", f"影響を調べていない追加要望が{len(received)}件あります。受付だけでは要件は変わりません。", "影響する領域を調べて記録してください。",
                          "状態が「受付」で、影響の記録がない追加要望があるため。", "changes", "追加要望の影響を調べる", 18, {"changes", "overview"}, _titles([c["content"] for c in received])))
    waiting = [c for c in p["changes"] if c["status"] in ("受付", "調査中", "判断待ち") and c.get("impacts")]
    if waiting:
        unsurveyed = sum(1 for c in waiting for a in IMPACT_AREAS if a not in c.get("surveyed_areas", []))
        note = f"未調査の領域が合計{unsurveyed}件あります。" if unsurveyed else ""
        out.append(Advice("change_wait", "追加要望の影響分析後", f"判断が記録されていない追加要望が{len(waiting)}件あります。{note}判断を記録するまで、要件は変わりません。",
                          "影響の内容を判断者と確認し、採否を記録してください。", "影響の記録があり、状態が判断前の追加要望があるため。", "changes", "追加要望の判断を記録する", 19, {"changes", "decisions"}, _titles([c["content"] for c in waiting])))
    return out


def _decisions(p: dict) -> list[Advice]:
    out = []
    pending = [d for d in p["decisions"] if d["state"] in ("提案", "確認待ち", "保留")]
    if pending:
        missing = sum(1 for d in pending if not d.get("decider"))
        note = f"うち{missing}件は判断者が未設定です。判断者は人が決めてください。" if missing else ""
        out.append(Advice("decision_wait", "判断待ち・保留の項目", f"合意に至っていない判断が{len(pending)}件あります。{note}", "判断者へ確認し、結果を記録してください。",
                          "状態が提案・確認待ち・保留の判断があるため。", "decisions", f"判断{len(pending)}件を確認する", 38, {"decisions", "issues"}, _titles([f"{d['topic']}（{d['state']}）" for d in pending])))
    agreed = [d for d in p["decisions"] if d["state"] == "合意済み"]
    stale = []
    for d in agreed:
        for rid in d.get("related_requirements") or []:
            r = pj.get(p, "requirements", rid)
            if r and r["status"] not in ("合意済み", "廃止", "却下"):
                stale.append(r)
    if stale:
        names = list({r["id"]: r["title"] for r in stale}.values())
        out.append(Advice("after_decision", "判断の確定後", f"判断は記録されていますが、関連する要件{len(names)}件の状態は合意済みになっていません。", "判断の内容が要件に正しく反映されているか確認し、人が状態を更新してください。",
                          "合意済みの判断に、状態が合意済みでない要件が関連付いているため。", "requirements", "関連する要件を確認する", 32, {"decisions", "requirements"}, _titles(names)))
    return out


def _backlog(p: dict) -> list[Advice]:
    bl = checks.backlog(p)
    out = []
    missing = bl["categories"]["判断者・期限未設定"]
    if missing:
        out.append(Advice("owner_missing", "判断者・期限が未設定の要件", f"判断者または期限が未設定の要件が{len(missing)}件あります。AIやプログラムが自動で設定することはありません。", "判断者と期限を人が決めて入力してください。",
                          "判断者または期限が空欄の要件があるため。", "requirements", "要件を確認する", 50, {"requirements"}, _titles([i["content"] for i in missing])))
    accept = bl["categories"]["受入条件未設定"]
    if accept:
        out.append(Advice("acceptance_missing", "受入条件が未設定の要件", f"受入条件が未設定の要件が{len(accept)}件あります。", "どの状態なら満たすと言えるかを具体化してください。",
                          "受入条件が空欄の要件があるため。", "refine", "受入条件を具体化する", 55, {"refine", "requirements"}, _titles([i["content"] for i in accept])))
    return out


def _organize(p: dict) -> list[Advice]:
    """要件を採用した後の進み先。判断の記録と受入条件の具体化へつなぐ。"""
    if any(c["state"] in ("候補", "要再確認") for c in p["candidates"]):
        return []
    active = [r for r in p["requirements"] if r["status"] not in ("廃止", "却下", "合意済み")]
    linked = {x for d in p["decisions"] for x in d.get("related_requirements", [])}
    waiting = [r for r in active if r["id"] not in linked]
    if not waiting:
        return []
    return [Advice("decide_next", "要件を登録しました", f"判断の記録がない要件が{len(waiting)}件あります。", "内容を具体化し、関係者の判断を記録してください。",
                   "未合意の要件に、関連する判断がないため。", "decisions", "判断を記録する", 37, {"decisions", "requirements", "refine"}, _titles([r["title"] for r in waiting]),
                   short=f"未合意の要件が{len(waiting)}件あります。次は具体化と判断の記録へ進めます。", alt=[("受入条件を具体化する", "refine")])]


def _classify(p: dict) -> list[Advice]:
    missing = [r for r in p["requirements"] if r["status"] not in ("廃止", "却下") and not r.get("kind")]
    if not missing:
        return []
    return [Advice("unclassified", "分類が未設定の要件", f"分野や種類が未設定の要件が{len(missing)}件あります。文書では「分類未設定の要件」の章に入ります。", "要件の編集で分類を確認してください。",
                   "要件の種類が空欄のため。", "requirements", "要件を確認する", 47, {"requirements"}, _titles([r["title"] for r in missing]))]


def _profile(p: dict) -> list[Advice]:
    from .intake import profile_suggestions

    found = profile_suggestions(p)
    if not found:
        return []
    return [Advice("profile_reflect", "案件情報へ反映できる内容があります", f"{len(found)}件の内容が案件情報と一致していません。文書の背景・目的は案件情報を参照します。", "内容を確認し、必要なものを案件情報へ反映してください。",
                   "会議準備やAI候補に、案件情報へ未反映の内容があるため。", "profile", "案件情報への反映を確認する", 44, {"profile", "overview", "share"}, _titles([f"{s['label']}：{s['value']}" for s in found]))]


def _before_export(p: dict) -> list[Advice]:
    bl = checks.backlog(p)
    pending = sum(1 for r in p["requirements"] if r["status"] not in ("合意済み", "廃止", "却下"))
    return [Advice("export", "資料の作成", f"合意済みでない要件が{pending}件、残件の対象が{bl['unique_total']}件あります。これらは資料に未合意や未決事項として記載されます。",
                   "掲載する範囲と内部メモの有無を確認してください。出力は資料を作る操作で、案件の完成や内容の正しさを保証するものではありません。",
                   "共有資料の画面を開いているため。", "share", "共有資料を確認する", 5, {"share"})]


def _resume(p: dict) -> Advice:
    bl = checks.backlog(p)
    when = (p.get("exported_at") or "")[:16].replace("T", " ") or "記録なし"
    return Advice("resume", "保存した案件を再開しました",
                  f"保存用ファイルの作成：{when}／会議{len(p['meetings'])}件／要件{len(p['requirements'])}件／判断{len(p['decisions'])}件／残件の対象{bl['unique_total']}件。前回開いていた画面は記録されていません。",
                  "残件を確認し、次に進める作業を選んでください。", "保存したJSONを読み込んだ直後のため。", "overview", "残件を確認する", 0, {"overview"})


RULES = (_start, _after_profile, _sources, _prep, _meeting_records, _candidates, _conflicts, _changes, _decisions, _organize, _classify, _profile, _backlog)

# 利用者が選んだ作業の段階。案件の状態より優先する（AIは変更しない）
STAGE_LABELS = {None: "案件の状態から判定する", "before_first": "これから会議をする", "after_first": "会議が終わり、記録を整理する", "deciding": "要件を具体化・判断する", "output": "資料を作成する"}
STAGE_FOCUS = {"before_first": {"prep", "prep_candidates", "sources_added", "next_input"}, "after_first": {"meeting_missing", "extract", "recording_check", "candidates"},
               "deciding": {"after_decision", "decide_next", "decision_wait", "conflicts", "change_new", "change_wait", "unclassified", "acceptance_missing"}, "output": {"export"}}


STAGE_PAGES = {"before_first": "prep", "after_first": "records", "deciding": "requirements", "output": "share"}


def _stage_default(p: dict, stage: str) -> Advice | None:
    """選んだ段階に当てはまる項目がないときの、次の操作。段階を選んでも何も起きない状態を作らない。"""
    if stage == "before_first":
        return Advice("stage_prep", "これから会議をする", "会議の質問はまだ準備していません。", "質問候補を確認し、会議で聞く項目を選んでください。", "「これから会議をする」を選んだため。", "prep", "質問候補を確認する", 1, {"prep"},
                      short="会議で聞く質問と議題を準備します。")
    if stage == "after_first":
        return Advice("stage_records", "会議が終わり、記録を整理する", "整理する会議の記録がまだありません。", "議事録を貼り付けるか、ファイルを登録してください。", "「会議が終わり、記録を整理する」を選び、未整理の記録がないため。", "records", "議事録を取り込む", 1, {"records"},
                      short="議事録を取り込み、AIで整理し、候補を確認します。この画面だけで進められます。")
    if stage == "deciding":
        if p["requirements"]:
            return Advice("stage_refine", "要件を具体化・判断する", "確認が必要な要件は検出されていません。", "要件の内容と受入条件を確認してください。", "「要件を具体化・判断する」を選んだため。", "requirements", "要件を確認する", 1, {"requirements"},
                          short="要件の内容を確認し、具体化と判断へ進めます。", alt=[("判断を記録する", "decisions")])
        return Advice("stage_require", "要件を具体化・判断する", "要件はまだ登録されていません。", "要件を手作業で追加するか、議事録をAIで整理して候補から採用してください。", "「要件を具体化・判断する」を選び、要件が0件のため。", "requirements", "要件を追加する", 1, {"requirements"},
                      short="要件はまだありません。手作業で追加するか、議事録の整理から候補を採用します。", alt=[("議事録をAIで整理する", "records")])
    return None


def collect(p: dict, page: str | None = None) -> list[Advice]:
    found = [a for rule in RULES for a in rule(p)]
    if page == "share" or user_stage(p) == "output":
        found += _before_export(p)
    return found


def assess(p: dict, page: str | None = None, resumed: bool = False) -> dict:
    """次にすることを1つ選ぶ。判定は案件の状態で共通にし、開いている画面で結論を変えない。
    資料の画面だけは、作成前の確認を先に出す。"""
    focus = STAGE_FOCUS.get(user_stage(p), set())
    found = sorted(collect(p, page), key=lambda a: (0 if a.id in focus else 1, a.rank))
    if focus and not any(a.id in focus for a in found):
        fallback = _stage_default(p, user_stage(p))
        if fallback:
            found.insert(0, fallback)
    if resumed:
        found.insert(0, _resume(p))
    main = found[0] if found else None
    return {"main": main, "extra": found[1:2], "rest": found[2:], "stage_question": needs_stage_question(p)}
