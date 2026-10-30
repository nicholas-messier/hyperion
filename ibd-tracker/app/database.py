import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

DEFAULT_DB_PATH = os.getenv("DB_PATH", "data/tracker.db")

def get_db_path() -> str:
    db_path = os.getenv("DB_PATH", DEFAULT_DB_PATH)
    parent = Path(db_path).parent
    parent.mkdir(parents=True, exist_ok=True)
    return db_path

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                bristol INTEGER NOT NULL CHECK (bristol BETWEEN 1 AND 7),
                pain INTEGER NOT NULL CHECK (pain BETWEEN 1 AND 10),
                blood TEXT NOT NULL CHECK (blood IN ('none', 'some', 'alot')),
                notes TEXT DEFAULT ''
            );
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);
            """
        )
        conn.commit()

def add_log(
    bristol: int,
    pain: int,
    blood: str,
    notes: str = "",
    custom_timestamp: Optional[str] = None
) -> Dict[str, Any]:
    if blood not in ("none", "some", "alot"):
        raise ValueError(f"Invalid blood value: {blood}")
    if not (1 <= bristol <= 7):
        raise ValueError(f"Bristol must be between 1 and 7, got {bristol}")
    if not (1 <= pain <= 10):
        raise ValueError(f"Pain must be between 1 and 10, got {pain}")

    ts = custom_timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO logs (timestamp, bristol, pain, blood, notes)
            VALUES (?, ?, ?, ?, ?)
            """,
            (ts, bristol, pain, blood, notes or "")
        )
        log_id = cursor.lastrowid
        conn.commit()

    return {
        "id": log_id,
        "timestamp": ts,
        "bristol": bristol,
        "pain": pain,
        "blood": blood,
        "notes": notes or ""
    }

def add_logs_batch(entries: List[Dict[str, Any]]) -> int:
    inserted = 0
    with get_connection() as conn:
        cursor = conn.cursor()
        for item in entries:
            blood = item.get("blood", "none")
            bristol = int(item.get("bristol", 4))
            pain = int(item.get("pain", 1))
            notes = item.get("notes", "")
            ts = item.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if blood in ("none", "some", "alot") and (1 <= bristol <= 7) and (1 <= pain <= 10):
                cursor.execute(
                    """
                    INSERT INTO logs (timestamp, bristol, pain, blood, notes)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (ts, bristol, pain, blood, notes or "")
                )
                inserted += 1
        conn.commit()
    return inserted

def get_today_count(target_date: Optional[str] = None) -> int:
    today_str = target_date or datetime.now().astimezone().strftime("%Y-%m-%d")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM logs
            WHERE date(timestamp) = date(?)
            """,
            (today_str,)
        )
        row = cursor.fetchone()
        return row["count"] if row else 0

def get_today_logs(target_date: Optional[str] = None) -> List[Dict[str, Any]]:
    today_str = target_date or datetime.now().astimezone().strftime("%Y-%m-%d")
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, timestamp, bristol, pain, blood, notes
            FROM logs
            WHERE date(timestamp) = date(?)
            ORDER BY timestamp ASC
            """,
            (today_str,)
        )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def get_stats(days: int = 30) -> Dict[str, Any]:
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Summary Query for the time window
        cursor.execute(
            """
            SELECT
                COUNT(*) as total_logs,
                AVG(bristol) as avg_bristol,
                AVG(pain) as avg_pain,
                SUM(CASE WHEN blood = 'none' THEN 1 ELSE 0 END) as blood_none,
                SUM(CASE WHEN blood = 'some' THEN 1 ELSE 0 END) as blood_some,
                SUM(CASE WHEN blood = 'alot' THEN 1 ELSE 0 END) as blood_alot,
                COUNT(DISTINCT date(timestamp)) as active_days,
                MIN(date(timestamp)) as min_date,
                MAX(date(timestamp)) as max_date
            FROM logs
            WHERE date(timestamp) >= date('now', 'localtime', '-' || ? || ' days')
            """,
            (days,)
        )
        sum_row = cursor.fetchone()
        total_logs = sum_row["total_logs"] if sum_row and sum_row["total_logs"] else 0
        avg_bristol = round(sum_row["avg_bristol"], 2) if sum_row and sum_row["avg_bristol"] is not None else None
        avg_pain = round(sum_row["avg_pain"], 2) if sum_row and sum_row["avg_pain"] is not None else None
        blood_none = sum_row["blood_none"] if sum_row and sum_row["blood_none"] else 0
        blood_some = sum_row["blood_some"] if sum_row and sum_row["blood_some"] else 0
        blood_alot = sum_row["blood_alot"] if sum_row and sum_row["blood_alot"] else 0
        
        blood_total_events = blood_some + blood_alot
        blood_pct = round((blood_total_events / total_logs * 100), 1) if total_logs > 0 else 0.0
        avg_daily = round(total_logs / max(days, 1), 2)

        summary = {
            "total_logs": total_logs,
            "days_window": days,
            "avg_daily_count": avg_daily,
            "avg_bristol": avg_bristol,
            "avg_pain": avg_pain,
            "blood_events": {
                "none": blood_none,
                "some": blood_some,
                "alot": blood_alot
            },
            "blood_incidence_pct": blood_pct
        }

        # 2. Daily breakdown
        cursor.execute(
            """
            SELECT
                date(timestamp) as log_date,
                COUNT(*) as count,
                AVG(bristol) as avg_bristol,
                AVG(pain) as avg_pain,
                MAX(pain) as max_pain,
                SUM(CASE WHEN blood = 'none' THEN 1 ELSE 0 END) as blood_none,
                SUM(CASE WHEN blood = 'some' THEN 1 ELSE 0 END) as blood_some,
                SUM(CASE WHEN blood = 'alot' THEN 1 ELSE 0 END) as blood_alot
            FROM logs
            WHERE date(timestamp) >= date('now', 'localtime', '-' || ? || ' days')
            GROUP BY date(timestamp)
            ORDER BY log_date ASC
            """,
            (days,)
        )
        breakdown_rows = cursor.fetchall()
        daily_breakdown = []
        for r in breakdown_rows:
            daily_breakdown.append({
                "date": r["log_date"],
                "count": r["count"],
                "avg_bristol": round(r["avg_bristol"], 2) if r["avg_bristol"] is not None else None,
                "avg_pain": round(r["avg_pain"], 2) if r["avg_pain"] is not None else None,
                "max_pain": r["max_pain"],
                "blood_events": {
                    "none": r["blood_none"],
                    "some": r["blood_some"],
                    "alot": r["blood_alot"]
                }
            })

        # 3. Recent logs
        cursor.execute(
            """
            SELECT id, timestamp, bristol, pain, blood, notes
            FROM logs
            ORDER BY timestamp DESC
            LIMIT 50
            """
        )
        recent_rows = cursor.fetchall()
        recent_logs = [dict(r) for r in recent_rows]

    return {
        "summary": summary,
        "daily_breakdown": daily_breakdown,
        "recent_logs": recent_logs
    }

def get_all_logs(start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
    query = "SELECT id, timestamp, bristol, pain, blood, notes FROM logs"
    params: List[Any] = []
    conditions = []
    
    if start_date:
        conditions.append("date(timestamp) >= date(?)")
        params.append(start_date)
    if end_date:
        conditions.append("date(timestamp) <= date(?)")
        params.append(end_date)
        
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
        
    query += " ORDER BY timestamp ASC"

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def delete_log(log_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM logs WHERE id = ?", (log_id,))
        conn.commit()
        return cursor.rowcount > 0
