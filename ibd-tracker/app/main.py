import csv
import io
import json
import os
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
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None)
):
    if not API_KEY:
        return True
    provided = x_api_key or api_key
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
    log_data: LogCreate,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None)
):
    verify_api_key(x_api_key, api_key)
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

@app.post("/api/logs/batch", status_code=status.HTTP_201_CREATED)
async def create_logs_batch(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None)
):
    verify_api_key(x_api_key, api_key)
    body_bytes = await request.body()
    if not body_bytes:
        return {"status": "success", "imported_count": 0, "message": "No data received."}
    
    text = body_bytes.decode("utf-8", errors="replace").strip()
    entries = []
    
    try:
        data = json.loads(text)
        if isinstance(data, list):
            entries = data
        elif isinstance(data, dict):
            if "logs" in data and isinstance(data["logs"], list):
                entries = data["logs"]
            elif "bristol" in data:
                entries = [data]
            else:
                entries = [data]
    except Exception:
        # Fallback: Parse line-by-line (e.g. newline-delimited JSON from repeated Shortcut appends)
        for line in text.splitlines():
            line = line.strip().rstrip(",")
            if line:
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        entries.append(obj)
                    elif isinstance(obj, list):
                        entries.extend(obj)
                except Exception:
                    continue

    count = database.add_logs_batch(entries)
    return {
        "status": "success",
        "imported_count": count,
        "message": f"Successfully imported {count} offline log entries."
    }

@app.get("/api/today", response_model=TodayResponse)
def get_today(
    date: Optional[str] = Query(None, description="Optional target date in YYYY-MM-DD"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None)
):
    verify_api_key(x_api_key, api_key)
    target_date = date or datetime.now().astimezone().strftime("%Y-%m-%d")
    logs = database.get_today_logs(target_date)
    return TodayResponse(
        today_count=len(logs),
        date=target_date,
        logs=logs
    )

@app.get("/api/stats", response_model=StatsResponse)
def get_stats(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None)
):
    verify_api_key(x_api_key, api_key)
    return database.get_stats(days=days)

@app.get("/api/export")
def export_logs(
    format: str = Query("csv", pattern="^(csv|json)$"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None)
):
    verify_api_key(x_api_key, api_key)
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
    log_id: int,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None)
):
    verify_api_key(x_api_key, api_key)
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
def serve_index():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "IBD Tracker API is active. Static UI files not found."}
