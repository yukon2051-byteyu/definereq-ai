"""デモ案件の組み立て。

デモは固定のJSONを読むのではなく、サンプルファイルを実際に読み込み、
本番と同じ業務ロジック（根拠照合・合意・反映・履歴）を順に実行して作る。
そのため、デモが動く＝ロジックがその流れで動く、という確認にもなる。

段階：1 会議前 → 2 会議後 → 3 変更 → 4 判断後
"""
from __future__ import annotations

from .. import config
from .. import project as pj
from ..ai import tasks as ai
from ..ingest import formats, registry
from ..logic import agreement as ag
from ..logic import baseline, checks, continuity
from ..logic import evidence as ev
from ..media import transcribe as tr
from ..export import share

STAGES = {1: "会議前", 2: "会議後", 3: "変更", 4: "判断後"}


class B:
    """デモを書きやすくするための小さな補助。"""

    def __init__(self, p: dict):
        self.p = p
        self.s: dict[str, str] = {}
        self.r: dict[str, str] = {}
        self.d: dict[str, str] = {}
        self.c: dict[str, str] = {}

    def profile(self, certainty: dict | None = None, **values):
        for k, v in values.items():
            self.p["profile"][k] = {"value": v, "certainty": (certainty or {}).get(k, "本人申告")}

    def stake(self, name, org, position, authority, certainty="確認済み", note=None):
        return pj.add(self.p, "stakeholders", {"name": name, "org": org, "position": position, "authority": authority,
                                               "certainty": certainty, "note": note})["id"]

    def term(self, term, meaning):
        pj.add(self.p, "glossary", {"term": term, "meaning": meaning})

    def src(self, alias, filename, kind, visibility="社内のみ", date=None):
        data = (config.DEMO_FILES / filename).read_bytes()
        item = registry.ingest_bytes(self.p, filename, data, kind=kind, visibility=visibility,
                                     origin="デモ用サンプル（架空）", occurred_at=date)
        self.s[alias] = item["id"]
        return item

    def paste(self, alias, title, text, kind, date=None):
        item = registry.ingest_paste(self.p, title, text, kind=kind, occurred_at=date, visibility="関係者限定")
        self.s[alias] = item["id"]
        return item

    def rec(self, alias, name, vtt_file, method, date, duration=None, note=None):
        text = (config.DEMO_FILES / vtt_file).read_text(encoding="utf-8")
        segs = formats.parse_subtitles(text)
        dur = duration or (segs[-1]["end"] if segs else 0)
        item = tr.register_recording(self.p, name, segs, method, date, dur, 0, dur, source_note=note)
        self.s[alias] = item["id"]
        return item

    def confirm_speakers(self, alias, mapping: dict[str, str], skip_last=False):
        rec = pj.get(self.p, "recordings", self.s[alias])
        segs = rec["segments"][:-1] if skip_last else rec["segments"]
        for s in segs:
            name = mapping.get(s["speaker_label"])
            if name:
                tr.edit_segment(rec, s["id"], speaker=name, speaker_status="確認済み", content_status="確認済み")

    def E(self, alias, quote):
        return ev.make(self.p, self.s[alias], quote)

    def req(self, key, **kw):
        item = pj.add(self.p, "requirements", pj.new_requirement(**kw))
        self.r[key] = item["id"]
        return item["id"]

    def R(self, *keys):
        return [self.r[k] for k in keys]

    def question(self, text, why, ask, priority="中", status="未質問", answer=None, perspective_id=None, evidence=None):
        return pj.add(self.p, "questions", {"text": text, "why": why, "ask": ask, "priority": priority, "status": status,
                                            "answer": answer, "perspective_id": perspective_id, "evidence": evidence or []})["id"]

    def decide(self, key, topic, options, adopted, rationale, rejected, decider, confirmer, date, evidence, reqs,
               state="合意済み", changes=None, hold=None):
        d = ag.new_decision(self.p, topic, options, adopted=adopted, rationale=rationale, rejected_reasons=rejected,
                            decider=decider, confirmer=confirmer, decided_on=date, evidence=evidence,
                            related_requirements=reqs, related_changes=changes or [], hold_reason=hold, state="提案")
        self.d[key] = d["id"]
        if state != "提案":
            ag.set_state(self.p, d["id"], state, "human", "デモ担当者")
        return d["id"]

    def agree(self, *keys):
        for k in keys:
            pj.set_requirement_status(self.p, self.r[k], "合意済み", "human", "デモ担当者")

    def ai_prepared(self, task, items, source_ids=None, recording_ids=None, extra=""):
        """準備済みのAI結果を、本番と同じ検証を通して候補にする。"""
        t = ai.TASKS[task]
        context = ai.build_context(self.p, t, source_ids, recording_ids, extra)
        run = ai.record_run(self.p, task, "準備済み", context, len(items), "デモ用に事前に用意した結果です（AIを実行していません）",
                            selection={"source_ids": source_ids, "recording_ids": recording_ids, "extra": extra})
        return ai.to_candidates(self.p, run["id"], items, context, t.label)

    def resolve_candidate(self, cand: dict, state: str, as_id: str | None = None):
        cand["state"] = state
        cand["resolved_as"] = as_id
        cand["resolved_by"] = "デモ担当者"

    def scan_and_adopt(self):
        for cand in checks.scan_conflicts(self.p)["candidates"]:
            if cand["key"] not in checks.registered_conflict_keys(self.p):
                checks.adopt_conflict(self.p, cand)

    def issue_doc(self, doc_type, title, change_id=None):
        return share.register_doc(self.p, share.Options(doc_type=doc_type, change_id=change_id), title, "デモ担当者")

    def nfr(self, **states):
        for k, v in states.items():
            self.p["nfr_status"][k] = {"state": v[0], "note": v[1]}

    def snapshot_baseline(self, label):
        return baseline.create(self.p, label, "デモ担当者")

    def fill_prep_questions(self, limit):
        for q in checks.prep_questions(self.p)[:limit]:
            self.question(q["text"], q["why"], q.get("ask"), perspective_id=q["perspective_id"])


def opt(id_, label, pros, cons):
    return {"id": id_, "label": label, "pros": pros, "cons": cons}


def measure(metric, value, unit, kind, condition=None, basis=None, status="確認待ち", origin=None):
    return {"metric": metric, "value": value, "unit": unit, "kind": kind, "condition": condition, "basis": basis, "status": status, "origin": origin}


def accept(given, when, then, how):
    return {"given": given, "when": when, "then": then, "how": how}


def scenario(p, title, kind, start, steps, end, failure, reqs, roles=None):
    return pj.add(p, "scenarios", {"title": title, "kind": kind, "start": start, "roles": roles, "steps": steps,
                                   "end": end, "failure": failure, "related_requirements": reqs})["id"]


def risk(p, content, nature, condition, impact, uncertainty, mitigation, ask, evidence=None, reqs=None):
    return pj.add(p, "risks", {"content": content, "nature": nature, "condition": condition, "impact": impact,
                               "uncertainty": uncertainty, "mitigation": mitigation, "ask": ask, "action": None,
                               "state": "未対応", "evidence": evidence or [], "related_requirements": reqs or []})["id"]


def action(p, content, owner=None, due=None, related=None):
    return pj.add(p, "actions", {"content": content, "owner": owner, "due": due, "related": related or [], "state": "未着手"})["id"]


def issue(p, topic, opinions, common_goal, conflict_condition, options, decider, ask, evidence, reqs, state="調整中",
          conclusion=None, extra_questions=None):
    return pj.add(p, "issues", {"topic": topic, "opinions": opinions, "common_goal": common_goal,
                                "conflict_condition": conflict_condition, "options": options, "decider": decider,
                                "ask": ask, "extra_questions": extra_questions or [], "conclusion": conclusion,
                                "state": state, "evidence": evidence, "related_requirements": reqs})["id"]


def build(demo_id: str, stage: int = 4) -> dict:
    from . import d1, d2, d3

    mod = {"d1": d1, "d2": d2, "d3": d3}[demo_id]
    p = pj.new_project(mod.NAME, mod.DOMAINS, actor="デモ")
    p["is_demo"] = True
    p["demo"] = {"id": demo_id, "stage": stage, "edited": False}
    p["traits"] = list(mod.TRAITS)
    b = B(p)
    for i, step in enumerate(mod.STEPS, 1):
        if i > stage:
            break
        step(b)
    continuity.backfill(p)  # 録画と議事録から会議を作り、判断と履歴を関連付ける
    return p


CATALOG = None


def catalog() -> list[dict]:
    from . import d1, d2, d3

    return [{"id": m.ID, "name": m.NAME, "lead": m.LEAD, "strength": m.STRENGTH, "domains": m.DOMAINS, "tour": m.TOUR,
             "summary": m.SUMMARY, "situation": m.SITUATION, "highlights": m.HIGHLIGHTS}
            for m in (d1, d2, d3)]
