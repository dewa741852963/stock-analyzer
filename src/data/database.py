import sqlite3
import json
from pathlib import Path
from datetime import datetime
import pandas as pd

DB_PATH = Path.home() / ".stock_analyzer" / "cache.db"

PERIOD_DAYS = {
    "1個月": 31,
    "3個月": 92,
    "6個月": 183,
    "1年": 365,
    "2年": 730,
}


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS history_ohlcv (
            symbol         TEXT NOT NULL,
            interval_label TEXT NOT NULL,
            date           TEXT NOT NULL,
            open           REAL,
            high           REAL,
            low            REAL,
            close          REAL,
            volume         REAL,
            PRIMARY KEY (symbol, interval_label, date)
        );
        CREATE TABLE IF NOT EXISTS info_cache (
            symbol     TEXT PRIMARY KEY,
            data       TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    conn.commit()


# ── Save ─────────────────────────────────────────────────────────────────────

def save_history(symbol: str, interval_label: str, hist: pd.DataFrame):
    rows = []
    for ts, row in hist.iterrows():
        date_str = pd.Timestamp(ts).strftime("%Y-%m-%dT%H:%M:%S")
        rows.append((
            symbol, interval_label, date_str,
            _f(row.get("Open")),
            _f(row.get("High")),
            _f(row.get("Low")),
            _f(row.get("Close")),
            _f(row.get("Volume")),
        ))
    with _conn() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO history_ohlcv VALUES (?,?,?,?,?,?,?,?)",
            rows,
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
                 period_label: str = None) -> tuple:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT date, open, high, low, close, volume FROM history_ohlcv "
            "WHERE symbol=? AND interval_label=? ORDER BY date",
            (symbol, interval_label),
        ).fetchall()
    if not rows:
        return None, None

    dates, opens, highs, lows, closes, volumes = zip(*rows)
    df = pd.DataFrame({
        "Open": opens, "High": highs, "Low": lows,
        "Close": closes, "Volume": volumes,
    }, index=pd.to_datetime(dates))
    df.index.name = "Date"

    if period_label and period_label in PERIOD_DAYS:
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=PERIOD_DAYS[period_label])
        df = df[df.index >= cutoff]

    if df.empty:
        return None, None

    updated_at = dates[-1][:16].replace("T", " ")
    return df, updated_at


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
            SELECT h.symbol, i.data, MAX(h.date) as last_date
            FROM history_ohlcv h
            LEFT JOIN info_cache i ON h.symbol = i.symbol
            GROUP BY h.symbol
            ORDER BY last_date DESC
        """).fetchall()
    result = []
    for symbol, info_json, last_date in rows:
        info = json.loads(info_json) if info_json else {}
        name = info.get("longName", info.get("shortName", "")) or ""
        result.append({
            "symbol":     symbol,
            "name":       name[:14] or symbol,
            "updated_at": last_date[:16].replace("T", " ") if last_date else "",
        })
    return result


# ── Row count per symbol/interval (for data status) ──────────────────────────

def row_counts(symbol: str) -> dict:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT interval_label, COUNT(*) FROM history_ohlcv "
            "WHERE symbol=? GROUP BY interval_label",
            (symbol,),
        ).fetchall()
    return dict(rows)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _f(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
