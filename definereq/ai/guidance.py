"""状況案内のAI補足。

プログラムの判定（logic/guidance.py）を土台に、内容の解釈が必要な部分だけをAIに補足させる。

- 画面の表示や移動では呼ばれない。人がボタンを押したときだけ実行する
- 同じ状態の結果があれば、AIを呼ばずに保存済みの結果を返す（重複実行と費用の防止）
- 結果には対象の状態の指紋を付ける。案件が変わると「以前の補足」として扱う
- 結果は案内の保存先だけに置く。要件・判断・合意は変更しない
"""
from __future__ import annotations

import json

from .. import config
from .. import project as pj
from ..ingest.registry import target_units
from ..logic import evidence as ev
from ..logic import guidance as gd
from ..usage import gate
from ..usage.ledger import BudgetExceeded, Limits
from . import tasks
from .client import AIError, ClaudeClient

KINDS = ("重要な不足情報", "対立の説明", "確認する質問", "見直す論点")
MAX_ITEMS = 5
MAX_TEXT = 300
MAX_OUTPUT_TOKENS = 4000
MAX_MATERIAL_CHARS = 20000
MAX_NOTES = 5

INSTRUCTION = f"""今回の作業：状況案内の補足
プログラムが判定した現在の状況を読み、担当者が次に確認するとよいことを補足してください。
- 判定結果の言い換えではなく、資料や発言の内容を読まないと分からない点を挙げます。
- 要件の確定、合意の成立、判断者の設定、期限の決定、仕様変更はしないでください。提案は確認のための候補として書きます。
- 利用者が指定した段階や役割を変更しないでください。
- 項目は{MAX_ITEMS}件以内。kind には次のいずれかを書きます：{' / '.join(KINDS)}
- text は1文、detail は理由を1文。ask には確認相手の役割を書きます（不明なら空にします）。"""


def build_context(p: dict, advice: gd.Advice) -> str:
    """送信する内容を、案内に必要な範囲へ絞る。内部メモと対象外の資料は含めない。"""
    open_reqs = [{"id": r["id"], "title": r["title"], "body": r["body"], "status": r["status"]} for r in p["requirements"] if r["status"] not in ("廃止", "却下")]
    summary = {
        "判定された状況": advice.title, "状況の説明": advice.situation, "判定の理由": advice.reason,
        "要件": open_reqs[:40],
        "未回答の質問": [q["text"] for q in p["questions"] if q["status"] in ("未質問", "回答待ち")][:20],
        "矛盾の候補": [c["note"] for c in p["conflicts"] if c["state"] in ("未確認", "確認中")][:10],
        "対応中の追加要望": [c["content"] for c in p["changes"] if c["status"] in ("受付", "調査中", "判断待ち")][:10],
        "判断待ち": [d["topic"] for d in p["decisions"] if d["state"] in ("提案", "確認待ち", "保留")][:10],
    }
    units = target_units(p) + tasks._segment_units(p, None)
    lines, used = [], 0
    for u in units:
        line = f"[source_id={u['source_id']} unit_id={u['id']} 位置={u['locator']}] {u['text']}"
        if used + len(line) > MAX_MATERIAL_CHARS:
            break
        lines.append(line)
        used += len(line)
    return "\n\n".join([f"案件名：{p['name']}", "対象分野：" + "、".join(p["domains"]),
                        "現在の登録状況：" + json.dumps(summary, ensure_ascii=False), "<資料>\n" + "\n".join(lines) + "\n</資料>"])


def current_note(p: dict, state_fp: str, advice_id: str) -> dict | None:
    """同じ状態・同じ案内のAI補足があれば返す。"""
    notes = (p.get("guidance") or {}).get("notes", [])  # 表示だけで案件データを変えない
    return next((n for n in notes if n["state_fp"] == state_fp and n.get("advice_id") == advice_id), None)


def stale_notes(p: dict, state_fp: str) -> list[dict]:
    """案件が変わった後の、以前の補足。"""
    return [n for n in (p.get("guidance") or {}).get("notes", []) if n["state_fp"] != state_fp]


def validate_items(p: dict, items, context: str) -> list[dict]:
    """AIの出力を検証する。形式が違う項目は捨て、引用は本文で照合し、入力にない数値に印を付ける。"""
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or not str(it.get("text") or "").strip():
            continue
        text, detail = str(it["text"]).strip()[:MAX_TEXT], str(it.get("detail") or "").strip()[:MAX_TEXT]
        quotes = [ev.make(p, str(e.get("source_id") or ""), str(e.get("quote") or ""), e.get("unit_id") or None) for e in it.get("evidence") or [] if isinstance(e, dict)]
        verified = [e for e in quotes if e["verified"]]
        out.append({"kind": it.get("kind") if it.get("kind") in KINDS else "確認する質問", "text": text, "detail": detail or None, "ask": str(it.get("ask") or "").strip()[:60] or None,
                    "evidence": [{"quote": e["quote"], "where": ev.citation(p, e)} for e in verified[:2]],
                    "no_evidence": not verified, "unsupported_numbers": tasks.unsupported_numbers(f"{text} {detail}", context)})
        if len(out) == MAX_ITEMS:
            break
    return out


def run(p: dict, advice: gd.Advice, code: str, ledger, llm=None, limits: Limits | None = None) -> dict:
    """AI補足を作る。同じ状態の結果があれば、AIを呼ばずにそれを返す。"""
    state_fp = gd.state_fingerprint(p)
    same = current_note(p, state_fp, advice.id)
    if same:
        return same
    if ledger is None:
        raise BudgetExceeded("利用記録に接続できないため、有料処理を実行しません。")
    context = build_context(p, advice)
    est = tasks.estimate(context, MAX_OUTPUT_TOKENS)
    run_id = ledger.reserve(limits or Limits.from_env(), code, "ai", "guidance", est)
    system = f"{tasks.COMMON_RULES}\n\n{INSTRUCTION}"
    llm = llm or ClaudeClient()
    try:
        result = llm.complete(system, context, tasks.ITEM_SCHEMA, MAX_OUTPUT_TOKENS)
        items = validate_items(p, result.data.get("items"), context)
    except AIError as e:
        ledger.settle(run_id, "失敗", 0.0 if not e.billed else None, error=str(e))
        raise
    except Exception:
        ledger.settle(run_id, "失敗", None, error="予期しないエラー")
        raise
    cost = gate.actual_ai_jpy(result.input_tokens, result.output_tokens)
    ledger.settle(run_id, "完了", cost, result.input_tokens, result.output_tokens, result.attempts)
    note = {"state_fp": state_fp, "advice_id": advice.id, "advice_title": advice.title, "generated_at": pj.now_iso(), "model": config.ai_model(), "items": items, "cost_jpy": cost}
    store = gd.guidance_store(p)
    store["notes"] = (store["notes"] + [note])[-MAX_NOTES:]
    return note
