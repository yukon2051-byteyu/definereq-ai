"""利用記録（本文を含まない）。有料処理の費用枠を「予約→精算」で管理する。

- 実行前に見積額で枠を予約する。予約中も枠を消費するので、同時に実行しても上限を超えない
- 予約はデータベースのトランザクション内で「確認と書込」を一度に行う（二重使用の防止）
- 失敗時：外部APIが課金した可能性があるため、実額が不明なら予約額のまま確定する
- 記録できない（DB障害など）場合は例外になり、呼び出し側は有料処理を実行しない
- アクセスコードは平文で保存しない（ハッシュのみ）。本文・ファイル名は保存しない

保存先は3種類：
- HubLedger：Hugging Face の非公開データセット（Spaces の通信制限 80/443/8080 に収まる。公開環境の第一候補）
- PostgresLedger：外部の PostgreSQL（接続できる環境向け）
- SqliteLedger：手元の開発とテスト
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime

from .. import config
from ..project import JST, now_iso


class BudgetExceeded(Exception):
    """枠の不足。理由を利用者に見せる。"""


class LedgerUnavailable(Exception):
    """利用記録に書けない。有料処理を止める。"""


def code_hash(code: str) -> str:
    return hashlib.sha256(("definereq:" + (code or "").strip()).encode()).hexdigest()[:16]


def month_key(dt: datetime | None = None) -> str:
    return (dt or datetime.now(JST)).strftime("%Y-%m")


@dataclass
class Limits:
    monthly_jpy: float
    code_jpy: float
    code_runs: int
    code_minutes: float

    @classmethod
    def from_env(cls) -> "Limits":
        return cls(config.monthly_budget_jpy(), config.per_code_budget_jpy(), config.per_code_runs(), config.per_code_minutes())


SCHEMA = """CREATE TABLE IF NOT EXISTS usage_ledger (
  run_id TEXT PRIMARY KEY, month TEXT NOT NULL, code_hash TEXT NOT NULL, kind TEXT NOT NULL, task TEXT NOT NULL,
  status TEXT NOT NULL, reserved_jpy DOUBLE PRECISION NOT NULL, cost_jpy DOUBLE PRECISION, minutes DOUBLE PRECISION NOT NULL,
  input_tokens BIGINT NOT NULL, output_tokens BIGINT NOT NULL, attempts INTEGER NOT NULL,
  error TEXT, started_at TEXT NOT NULL, finished_at TEXT)"""

_SUM = ("SELECT COALESCE(SUM(COALESCE(cost_jpy, reserved_jpy)),0), COUNT(*), COALESCE(SUM(minutes),0), "
        "COALESCE(SUM(CASE WHEN status='予約中' THEN 1 ELSE 0 END),0), "
        "COALESCE(SUM(CASE WHEN status='失敗' THEN 1 ELSE 0 END),0) FROM usage_ledger WHERE month={ph}")


class Ledger:
    """SQL を共通にした基底クラス。ph はプレースホルダ（SQLite は ?、PostgreSQL は %s）。"""
    ph = "?"
    durable = False

    @contextmanager
    def _tx(self):
        raise NotImplementedError
        yield

    def _totals(self, cur, month: str, code: str | None = None) -> dict:
        sql = _SUM.format(ph=self.ph)
        args = [month]
        if code:
            sql += f" AND code_hash={self.ph}"
            args.append(code)
        cur.execute(sql, args)
        c, n, m, pending, failed = cur.fetchone()
        return {"cost_jpy": float(c), "runs": int(n), "minutes": float(m), "pending": int(pending), "failed": int(failed)}

    def summary(self, code: str | None = None, month: str | None = None) -> dict:
        month = month or month_key()
        try:
            with self._tx() as cur:
                out = {"month": month, "all": self._totals(cur, month)}
                if code:
                    out["code"] = self._totals(cur, month, code_hash(code))
                return out
        except LedgerUnavailable:
            raise
        except Exception as e:
            raise LedgerUnavailable("利用記録を読めません。") from e

    def reserve(self, limits: Limits, code: str, kind: str, task: str, est_jpy: float, minutes: float = 0.0) -> str:
        """枠を確認して予約する。不足なら BudgetExceeded。"""
        month, ch = month_key(), code_hash(code)
        run_id = uuid.uuid4().hex[:16]
        try:
            with self._tx() as cur:
                total = self._totals(cur, month)
                mine = self._totals(cur, month, ch)
                reasons = []
                if total["cost_jpy"] + est_jpy > limits.monthly_jpy:
                    reasons.append(f"今月の全体予算（{limits.monthly_jpy:,.0f}円）を超える見込みです。")
                if mine["cost_jpy"] + est_jpy > limits.code_jpy:
                    reasons.append(f"このコードの今月の費用枠（{limits.code_jpy:,.0f}円）を超える見込みです。")
                if mine["runs"] + 1 > limits.code_runs:
                    reasons.append(f"このコードの今月の実行回数の上限（{limits.code_runs}回）に達しました。")
                if mine["minutes"] + minutes > limits.code_minutes:
                    reasons.append(f"このコードの今月の音声時間の上限（{limits.code_minutes:.0f}分）を超えます。")
                if reasons:
                    raise BudgetExceeded(" ".join(reasons))
                cur.execute(
                    f"INSERT INTO usage_ledger (run_id,month,code_hash,kind,task,status,reserved_jpy,cost_jpy,minutes,"
                    f"input_tokens,output_tokens,attempts,error,started_at,finished_at) VALUES "
                    f"({','.join([self.ph] * 15)})",
                    (run_id, month, ch, kind, task, "予約中", round(est_jpy, 2), None, minutes, 0, 0, 0, None, now_iso(), None))
            return run_id
        except BudgetExceeded:
            raise
        except LedgerUnavailable:
            raise
        except Exception as e:
            raise LedgerUnavailable("利用記録に書き込めないため、有料処理を実行しません。") from e

    def settle(self, run_id: str, status: str, cost_jpy: float | None = None, input_tokens: int = 0,
               output_tokens: int = 0, attempts: int = 1, minutes: float | None = None, error: str | None = None) -> None:
        """精算。cost_jpy=None のときは予約額のまま残す（失敗時に実額が不明な場合の安全側）。"""
        sets = ["status=" + self.ph, "input_tokens=" + self.ph, "output_tokens=" + self.ph, "attempts=" + self.ph,
                "error=" + self.ph, "finished_at=" + self.ph]
        args: list = [status, input_tokens, output_tokens, attempts, (error or "")[:120] or None, now_iso()]
        if cost_jpy is not None:
            sets.append("cost_jpy=" + self.ph)
            args.append(round(cost_jpy, 2))
        if minutes is not None:
            sets.append("minutes=" + self.ph)
            args.append(minutes)
        args.append(run_id)
        try:
            with self._tx() as cur:
                cur.execute(f"UPDATE usage_ledger SET {', '.join(sets)} WHERE run_id={self.ph}", args)
        except Exception as e:
            raise LedgerUnavailable("利用記録の精算に失敗しました。") from e


class SqliteLedger(Ledger):
    """手元の開発・テスト用。BEGIN IMMEDIATE で書込を1本に絞り、確認と予約を一度に行う。"""

    def __init__(self, path: str):
        self.path = path
        with self._tx() as cur:
            cur.execute(SCHEMA)

    @contextmanager
    def _tx(self):
        import os

        if self.path != ":memory:":
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            cur = con.cursor()
            cur.execute("BEGIN IMMEDIATE")
            try:
                yield cur
                cur.execute("COMMIT")
            except BaseException:
                cur.execute("ROLLBACK")
                raise
        finally:
            con.close()


class PostgresLedger(Ledger):
    """本番用。トランザクション内で表ロックを取り、並行実行の二重使用を防ぐ。"""
    ph = "%s"
    durable = True

    def __init__(self, url: str):
        self.url = url
        with self._tx() as cur:
            cur.execute(SCHEMA)

    @contextmanager
    def _tx(self):
        import psycopg

        with psycopg.connect(self.url, connect_timeout=10) as con:
            with con.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(20261105)")
                yield cur


class HubLedger(SqliteLedger):
    """利用記録を Hugging Face の非公開データセットへ保存する。

    起動時に最新の記録を取得し、予約・精算のたびに送り直す。送れなければ例外になり、有料処理は実行しない。
    無料CPUは1台で動く（複製は有料機能）ため、プロセス内のロックで予約の二重使用を防げる。
    """
    FILE = "usage.db"
    durable = True

    def __init__(self, repo_id: str, token: str, path: str):
        self.repo_id, self.token = repo_id, token
        self._lock = threading.RLock()
        self._pull(path)
        super().__init__(path)

    def _pull(self, path: str) -> None:
        import shutil

        import huggingface_hub
        from huggingface_hub.errors import EntryNotFoundError

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        try:
            got = huggingface_hub.hf_hub_download(self.repo_id, self.FILE, repo_type="dataset", token=self.token, force_download=True)
        except EntryNotFoundError:
            return  # まだ記録がない（初回）
        shutil.copyfile(got, path)

    def _push(self) -> None:
        import huggingface_hub

        try:
            huggingface_hub.HfApi(token=self.token).upload_file(path_or_fileobj=self.path, path_in_repo=self.FILE, repo_id=self.repo_id,
                                                                repo_type="dataset", commit_message="利用記録の更新")
        except Exception as e:  # 通信・権限の失敗は種類を問わず「記録できない」として有料処理を止める
            raise LedgerUnavailable("利用記録を保存できないため、有料処理を実行しません。") from e

    def reserve(self, *args, **kwargs) -> str:
        with self._lock:
            run_id = super().reserve(*args, **kwargs)
            self._push()
            return run_id

    def settle(self, *args, **kwargs) -> None:
        with self._lock:
            super().settle(*args, **kwargs)
            self._push()


_hub_singleton: HubLedger | None = None
_hub_lock = threading.Lock()


def open_ledger() -> Ledger | None:
    """使える利用記録を返す。使えなければ None（有料処理は実行できない）。"""
    global _hub_singleton
    url = config.usage_db_url()
    repo = config.usage_hf_dataset()
    try:
        if repo and config.env("HF_TOKEN"):
            with _hub_lock:  # 1プロセスで1つだけ持つ（画面の再描画のたびに取得しない）
                if _hub_singleton is None:
                    _hub_singleton = HubLedger(repo, config.env("HF_TOKEN"), config.env("DEFINEREQ_HUB_CACHE", "/tmp/definereq_usage/usage.db"))
                return _hub_singleton
        if url:
            return PostgresLedger(url)
        if config.allow_local_ledger():
            return SqliteLedger(config.local_ledger_path())
    except Exception:  # 接続文字列を画面やログに出さないよう、種類を問わず「使えない」として扱う
        return None
    return None
