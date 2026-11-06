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
                   "案件情報が未入力で、資料も登録されていないため。", "profile", "案件情報を入力する", 10, {"overview", "profile", "sources"})]


def _after_profile(p: dict) -> list[Advice]:
    """背景だけが登録された状態。会議前の人にも、記録を持っている人にも進み先を示す。"""
    if phase(p) != "unprocessed" or p["sources"] or p["recordings"] or p["questions"]:
        return []
    return [Advice("next_input", "案件の情報を登録しました", "背景や困りごとが登録されています。資料や議事録はまだありません。",
                   "これから会議をする場合は質問を準備し、議事録や資料がある場合は取り込んでください。", "案件情報があり、質問・資料・録画が0件のため。", "prep", "会議の質問を準備する", 12, {"overview", "profile", "prep"}),
            Advice("next_records", "議事録や資料がある場合", "議事録や資料があれば、AIで要望や未決事項を整理できます。", "議事録や資料を取り込んでください。",
                   "資料と録画が0件のため。", "sources", "資料・議事録を取り込む", 13, {"overview", "sources"})]


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
    if active and not p["questions"]:
        out.append(Advice("sources_added", "資料の登録後", f"資料{len(active)}件を登録しましたが、質問はまだ登録されていません。",
                          "確認観点と質問候補を見て、会議で聞く項目を選んでください。", "資料があり、質問が0件のため。", "prep", "質問候補を確認する", 20, {"sources", "prep", "overview"}))
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
                          "議事録を資料として登録するか、録画・字幕を登録してください。", "「初回会議の後」と指定され、会議の記録が0件のため。", "recordings", "会議の記録を登録する", 22, {"recordings", "sources", "meetings"}))
    extracted = any(r["task"] == "extract" for r in p["ai_runs"]) or p["requirements"] or p["candidates"]
    minutes = [s for s in p["sources"] if s.get("kind") == "議事録"]
    if (minutes or p["recordings"]) and not extracted:
        out.append(Advice("extract", "議事録・録画の解析後", "会議の記録がありますが、要望や決定の候補はまだ整理されていません。",
                          "会議後の整理で、要望・決定・未決事項を候補として抽出してください。", "会議の記録があり、候補と要件が0件のため。", "candidates", "会議後の整理へ進む", 28, {"candidates", "recordings"}))
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
                          f"未処理の候補が{len(rest)}件あるため。", "candidates", f"候補{len(rest)}件を確認する", 26, {"candidates", "requirements"}, _titles([c["text"] for c in rest])))
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
        out.append(Advice("owner_missing", "判断者・期限が未設定の要件", f"判断者または期限が未設定の要件が{len(missing)}件あります。AIや案内が自動で設定することはありません。", "判断者と期限を人が決めて入力してください。",
                          "判断者または期限が空欄の要件があるため。", "requirements", "要件を確認する", 50, {"requirements"}, _titles([i["content"] for i in missing])))
    accept = bl["categories"]["受入条件未設定"]
    if accept:
        out.append(Advice("acceptance_missing", "受入条件が未設定の要件", f"受入条件が未設定の要件が{len(accept)}件あります。", "どの状態なら満たすと言えるかを具体化してください。",
                          "受入条件が空欄の要件があるため。", "refine", "受入条件を具体化する", 55, {"refine", "requirements"}, _titles([i["content"] for i in accept])))
    return out


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
    return [Advice("export", "資料を出力する前の確認", f"合意済みでない要件が{pending}件、残件の対象が{bl['unique_total']}件あります。これらは資料に確認待ちや未決事項として記載されます。",
                   "掲載する範囲と内部メモの有無を確認してください。出力は資料を作る操作で、案件の完成や内容の正しさを保証するものではありません。",
                   "共有資料の画面を開いているため。", "share", "共有資料を確認する", 5, {"share"})]


def _resume(p: dict) -> Advice:
    bl = checks.backlog(p)
    when = (p.get("exported_at") or "")[:16].replace("T", " ") or "記録なし"
    return Advice("resume", "保存した案件を再開しました",
                  f"保存用ファイルの作成：{when}／会議{len(p['meetings'])}件／要件{len(p['requirements'])}件／判断{len(p['decisions'])}件／残件の対象{bl['unique_total']}件。前回開いていた画面は記録されていません。",
                  "残件を確認し、次に進める作業を選んでください。", "保存したJSONを読み込んだ直後のため。", "overview", "残件を確認する", 0, {"overview"})


RULES = (_start, _after_profile, _sources, _prep, _meeting_records, _candidates, _conflicts, _changes, _decisions, _classify, _profile, _backlog)


def collect(p: dict, page: str | None = None) -> list[Advice]:
    found = [a for rule in RULES for a in rule(p)]
    if page == "share":
        found += _before_export(p)
    return found


def assess(p: dict, page: str | None = None, resumed: bool = False) -> dict:
    """主な案件案内を選ぶ。今の画面に関連する案内を先にする。"""
    found = sorted(collect(p, page), key=lambda a: (0 if page in a.pages else 1, a.rank))
    if resumed:
        found.insert(0, _resume(p))
    main = found[0] if found else None
    return {"main": main, "extra": found[1:2], "rest": found[2:], "stage_question": needs_stage_question(p)}
