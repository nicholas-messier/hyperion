import csv
import io
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException, Query, Request, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app import database
from app.models import (
    LogCreate,
    LogCreateResponse,
    StatsResponse,
    TodayResponse,
)

API_KEY = os.getenv("API_KEY") or os.getenv("IBD_TRACKER_API_KEY") or ""

def verify_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None),
    key: Optional[str] = Query(None)
):
    if not API_KEY:
        return True
    cookie_key = request.cookies.get("ibd_api_key") or request.cookies.get("api_key")
    provided = x_api_key or api_key or key or cookie_key
    if not provided or provided != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key"
        )
    return True

@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield

app = FastAPI(
    title="IBD Symptom & Bowel Movement Tracker",
    description="Self-hosted symptom tracking API for IBD management and GI doctor reporting",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routes
@app.get("/health")
@app.head("/health")
def health_check():
    return {"status": "ok"}

@app.post("/api/log", response_model=LogCreateResponse, status_code=status.HTTP_201_CREATED)
def create_log(
    request: Request,
    log_data: LogCreate,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None),
    key: Optional[str] = Query(None)
):
    verify_api_key(request, x_api_key, api_key, key)
    try:
        created = database.add_log(
            bristol=log_data.bristol,
            pain=log_data.pain,
            blood=log_data.blood,
            notes=log_data.notes or "",
            custom_timestamp=log_data.timestamp
        )
        today_count = database.get_today_count()
        return LogCreateResponse(
            status="success",
            id=created["id"],
            timestamp=created["timestamp"],
            today_count=today_count,
            message=f"Logged successfully. Movement #{today_count} today."
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

def _normalize_raw_entry(item: Any) -> Optional[dict]:
    if not isinstance(item, dict):
        return None
    
    d = {str(k).lower().strip(): v for k, v in item.items()}
    
    # Reject dummy or empty dictionaries
    recognized = {
        "bristol", "consistency", "bristol_score", "bristol_scale",
        "pain", "pain_level", "pain_scale",
        "blood", "blood_presence",
        "notes", "note", "comment",
        "timestamp", "date", "time", "created_at"
    }
    has_valid_key = any(k in recognized and v is not None and str(v).strip() != "" for k, v in d.items())
    if not has_valid_key:
        return None

    bristol_raw = d.get("bristol") or d.get("consistency") or d.get("bristol_score") or d.get("bristol_scale") or 4
    bristol = 4
    if isinstance(bristol_raw, (int, float)):
        bristol = int(bristol_raw)
    elif isinstance(bristol_raw, str):
        match = re.search(r"([1-7])", bristol_raw)
        if match:
            bristol = int(match.group(1))
    bristol = max(1, min(7, bristol))

    pain_raw = d.get("pain") or d.get("pain_level") or d.get("pain_scale") or 1
    pain = 1
    if isinstance(pain_raw, (int, float)):
        pain = int(pain_raw)
    elif isinstance(pain_raw, str):
        match = re.search(r"(\d+)", pain_raw)
        if match:
            pain = int(match.group(1))
    pain = max(1, min(10, pain))

    blood_raw = str(d.get("blood") or d.get("blood_presence") or "none").lower().strip()
    if any(w in blood_raw for w in ["alot", "a lot", "severe", "heavy", "high"]):
        blood = "alot"
    elif any(w in blood_raw for w in ["some", "trace", "mild", "yes", "true", "light"]):
        blood = "some"
    else:
        blood = "none"

    notes = str(d.get("notes") or d.get("note") or d.get("comment") or "")
    ts = d.get("timestamp") or d.get("date") or d.get("time") or d.get("created_at") or None

    return {
        "bristol": bristol,
        "pain": pain,
        "blood": blood,
        "notes": notes,
        "timestamp": ts
    }

@app.post("/api/logs/batch", status_code=status.HTTP_201_CREATED)
async def create_logs_batch(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None),
    key: Optional[str] = Query(None)
):
    verify_api_key(request, x_api_key, api_key, key)
    body_bytes = await request.body()
    if not body_bytes:
        print("[BATCH ERROR]: Empty body received", flush=True)
        return {"status": "success", "imported_count": 0, "message": "No data received."}
    
    text = body_bytes.decode("utf-8", errors="replace").strip()
    print(f"[BATCH INTAKE HEADERS]: {dict(request.headers)}", flush=True)
    print(f"[BATCH INTAKE RAW BODY]:\n{text}", flush=True)
    raw_entries = []
    
    # 1. Parse JSON (supports concatenated multi-line objects from iOS Shortcuts, arrays, and nested structures)
    decoder = json.JSONDecoder()
    pos = 0
    while pos < len(text):
        text_slice = text[pos:].lstrip()
        if not text_slice:
            break
        pos += len(text[pos:]) - len(text_slice)
        try:
            obj, end_pos = decoder.raw_decode(text, pos)
            if isinstance(obj, list):
                raw_entries.extend(obj)
            elif isinstance(obj, dict):
                nested = False
                for k in ["logs", "entries", "data", "items", "records", "movements"]:
                    if k in obj and isinstance(obj[k], list):
                        raw_entries.extend(obj[k])
                        nested = True
                        break
                if not nested:
                    raw_entries.append(obj)
            pos = end_pos
        except Exception:
            pos += 1

    # 2. If JSON parsing found nothing, fallback to CSV
    if not raw_entries:
        try:
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                if row:
                    raw_entries.append(row)
        except Exception:
            pass

    # Normalize entries
    entries = []
    for item in raw_entries:
        norm = _normalize_raw_entry(item)
        if norm:
            entries.append(norm)

    count = database.add_logs_batch(entries)
    return {
        "status": "success",
        "imported_count": count,
        "message": f"Successfully imported {count} offline log entries."
    }

@app.get("/api/today", response_model=TodayResponse)
def get_today(
    request: Request,
    date: Optional[str] = Query(None, description="Optional target date in YYYY-MM-DD"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None),
    key: Optional[str] = Query(None)
):
    verify_api_key(request, x_api_key, api_key, key)
    target_date = date or datetime.now().astimezone().strftime("%Y-%m-%d")
    logs = database.get_today_logs(target_date)
    return TodayResponse(
        today_count=len(logs),
        date=target_date,
        logs=logs
    )

@app.get("/api/stats", response_model=StatsResponse)
def get_stats(
    request: Request,
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None),
    key: Optional[str] = Query(None)
):
    verify_api_key(request, x_api_key, api_key, key)
    return database.get_stats(days=days)

@app.get("/api/export")
def export_logs(
    request: Request,
    format: str = Query("csv", pattern="^(csv|json)$"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None),
    key: Optional[str] = Query(None)
):
    verify_api_key(request, x_api_key, api_key, key)
    logs = database.get_all_logs(start_date=start_date, end_date=end_date)
    
    if format == "json":
        return JSONResponse(
            content=logs,
            headers={"Content-Disposition": 'attachment; filename="ibd_logs.json"'}
        )
        
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Timestamp", "Bristol_Score", "Pain_Level", "Blood_Presence", "Notes"])
    
    for row in logs:
        writer.writerow([
            row["id"],
            row["timestamp"],
            row["bristol"],
            row["pain"],
            row["blood"],
            row["notes"]
        ])
        
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="ibd_logs.csv"'}
    )

@app.delete("/api/logs/{log_id}")
def delete_log_entry(
    request: Request,
    log_id: int,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None),
    key: Optional[str] = Query(None)
):
    verify_api_key(request, x_api_key, api_key, key)
    deleted = database.delete_log(log_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Log entry not found")
    return {"status": "deleted", "id": log_id}

# Static assets and index.html serving
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
@app.head("/")
def serve_index(
    request: Request,
    key: Optional[str] = Query(None),
    api_key: Optional[str] = Query(None)
):
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        response = FileResponse(index_file)
        provided_key = key or api_key
        if provided_key:
            response.set_cookie(
                key="ibd_api_key",
                value=provided_key,
                max_age=31536000,
                httponly=False,
                samesite="lax"
            )
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response
    return {"message": "IBD Tracker API is active. Static UI files not found."}
