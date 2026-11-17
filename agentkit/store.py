"""SQLite persistence for runs, their event streams, memories and eval results."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, status TEXT, title TEXT,
  input TEXT, output TEXT, created REAL, finished REAL);
CREATE TABLE IF NOT EXISTS events (
  run_id INTEGER, seq INTEGER, type TEXT, payload TEXT, ts REAL,
  PRIMARY KEY (run_id, seq));
CREATE TABLE IF NOT EXISTS memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, text TEXT, meta TEXT,
  uses INTEGER DEFAULT 0, wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0, created REAL);
CREATE TABLE IF NOT EXISTS evals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, suite TEXT, summary TEXT, results TEXT, created REAL);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT, updated REAL);
"""


class Store:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript(_SCHEMA)
            self.db.execute("UPDATE runs SET status='interrupted' WHERE status='running'")
            self.db.commit()

    def execute(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    def query(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    # runs and events -------------------------------------------------------
    def create_run(self, kind: str, title: str, input_: dict) -> int:
        return self.execute("INSERT INTO runs(kind,status,title,input,created) VALUES(?,?,?,?,?)",
                            (kind, "running", title, json.dumps(input_), time.time())).lastrowid

    def finish_run(self, run_id: int, status: str, output: dict | None) -> None:
        self.execute("UPDATE runs SET status=?, output=?, finished=? WHERE id=?",
                     (status, json.dumps(output) if output is not None else None, time.time(), run_id))

    def get_run(self, run_id: int) -> dict | None:
        rows = self.query("SELECT * FROM runs WHERE id=?", (run_id,))
        return self._run(rows[0]) if rows else None

    def list_runs(self, kind: str | None = None, limit: int = 50) -> list[dict]:
        if kind:
            rows = self.query("SELECT * FROM runs WHERE kind=? ORDER BY id DESC LIMIT ?", (kind, limit))
        else:
            rows = self.query("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))
        return [self._run(r) for r in rows]

    @staticmethod
    def _run(row: dict) -> dict:
        row["input"] = json.loads(row["input"]) if row["input"] else None
        row["output"] = json.loads(row["output"]) if row["output"] else None
        return row

    def add_event(self, run_id: int, type_: str, payload: dict) -> int:
        with self.lock:
            seq = self.db.execute("SELECT COALESCE(MAX(seq),0)+1 FROM events WHERE run_id=?", (run_id,)).fetchone()[0]
            self.db.execute("INSERT INTO events VALUES(?,?,?,?,?)",
                            (run_id, seq, type_, json.dumps(payload, default=str), time.time()))
            self.db.commit()
            return seq

    def events(self, run_id: int, after: int = 0) -> list[dict]:
        rows = self.query("SELECT seq,type,payload,ts FROM events WHERE run_id=? AND seq>? ORDER BY seq", (run_id, after))
        for r in rows:
            r["payload"] = json.loads(r["payload"])
        return rows

    # key-value and evals ---------------------------------------------------
    def put(self, key: str, value) -> None:
        self.execute("INSERT INTO kv VALUES(?,?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v, updated=excluded.updated",
                     (key, json.dumps(value, default=str), time.time()))

    def get(self, key: str, default=None):
        rows = self.query("SELECT v FROM kv WHERE k=?", (key,))
        return json.loads(rows[0]["v"]) if rows else default

    def save_eval(self, suite: str, summary: dict, results: list) -> int:
        return self.execute("INSERT INTO evals(suite,summary,results,created) VALUES(?,?,?,?)",
                            (suite, json.dumps(summary), json.dumps(results, default=str), time.time())).lastrowid

    def latest_eval(self, suite: str) -> dict | None:
        rows = self.query("SELECT * FROM evals WHERE suite=? ORDER BY id DESC LIMIT 1", (suite,))
        if not rows:
            return None
        row = rows[0]
        row["summary"], row["results"] = json.loads(row["summary"]), json.loads(row["results"])
        return row

    def eval_history(self, suite: str, limit: int = 20) -> list[dict]:
        rows = self.query("SELECT id,summary,created FROM evals WHERE suite=? ORDER BY id DESC LIMIT ?", (suite, limit))
        for r in rows:
            r["summary"] = json.loads(r["summary"])
        return rows[::-1]
