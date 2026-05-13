import sqlite3
import json
import io
from pathlib import Path
from datetime import datetime
import pandas as pd

DB_PATH = Path.home() / ".stock_analyzer" / "cache.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS history_cache (
            symbol        TEXT NOT NULL,
            interval_label TEXT NOT NULL,
            period_label  TEXT NOT NULL,
            data          TEXT NOT NULL,
            updated_at    TEXT NOT NULL,
            PRIMARY KEY (symbol, interval_label, period_label)
        );
        CREATE TABLE IF NOT EXISTS info_cache (
            symbol     TEXT PRIMARY KEY,
            data       TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    conn.commit()


# ── Save ─────────────────────────────────────────────────────────────────────

def save_history(symbol: str, interval_label: str, period_label: str,
                 hist: pd.DataFrame):
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO history_cache VALUES (?,?,?,?,?)",
            (symbol, interval_label, period_label,
             hist.to_json(date_format="iso"), _now()),
        )


def save_info(symbol: str, info: dict):
    if not info:
        return
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO info_cache VALUES (?,?,?)",
            (symbol, json.dumps(info, ensure_ascii=False), _now()),
        )


# ── Load ─────────────────────────────────────────────────────────────────────

def load_history(symbol: str, interval_label: str,
                 period_label: str) -> tuple[pd.DataFrame | None, str | None]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT data, updated_at FROM history_cache "
            "WHERE symbol=? AND interval_label=? AND period_label=?",
            (symbol, interval_label, period_label),
        ).fetchone()
    if row is None:
        return None, None
    df = pd.read_json(io.StringIO(row[0]))
    df.index = pd.to_datetime(df.index)
    if hasattr(df.index, "tz") and df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    return df, row[1]


def load_info(symbol: str) -> dict | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT data FROM info_cache WHERE symbol=?", (symbol,)
        ).fetchone()
    return json.loads(row[0]) if row else None


# ── List all cached stocks ────────────────────────────────────────────────────

def list_cached() -> list[dict]:
    with _conn() as conn:
        rows = conn.execute("""
            SELECT h.symbol, i.data, MAX(h.updated_at) as last_update
            FROM history_cache h
            LEFT JOIN info_cache i ON h.symbol = i.symbol
            GROUP BY h.symbol
            ORDER BY last_update DESC
        """).fetchall()
    result = []
    for symbol, info_json, updated_at in rows:
        info = json.loads(info_json) if info_json else {}
        name = info.get("longName", info.get("shortName", "")) or ""
        result.append({
            "symbol":     symbol,
            "name":       name[:14] or symbol,
            "updated_at": updated_at[:16].replace("T", " ") if updated_at else "",
        })
    return result


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
