# IBD Bowel Movement & Symptom Tracker — Implementation Plan

This implementation plan is designed for direct execution by **Devin CLI** on the Linux Mint 22 home server (**Hyperion**).

---

## 1. Project Overview & Objectives

Commercial symptom tracking apps are overly bloated, slow, and require excessive navigation. The goal of this project is a self-hosted, lightweight tracker running 24/7 on Hyperion in Docker:
- **Client (iPhone):** 1-tap logging via an **Apple Shortcut** on the lock screen or home screen. Total time to log: **< 4 seconds**.
  - **Bristol Scale Consistency:** 1 to 7
  - **Pain Scale:** 1 to 10
  - **Blood Presence:** `none`, `some`, `alot`
  - Automatic timestamp, optional short note.
- **Server (Hyperion / Linux Mint 22):**
  - Docker container running FastAPI + SQLite with persistent storage.
  - Aggregates daily sessions to compute:
    1. Total bowel movement count per day.
    2. Daily average Bristol consistency score.
    3. Daily pain progression & peak pain.
    4. Blood presence frequency over time.
- **Doctor Report Dashboard:**
  - Clean web UI reachable from browser.
  - Printable / PDF-friendly summary view designed to share directly with gastroenterologists (Dr. Vincent Aguirre) and colorectal surgeons (Dr. David Gould) at appointments.

---

## 2. Directory Structure to Build

When Devin CLI executes this plan, build the following files in `ibd-tracker/`:

```
ibd-tracker/
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── README.md
├── IOS_SHORTCUT_GUIDE.md
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application & routing
│   ├── database.py          # SQLite schema, connection, and queries
│   ├── models.py            # Pydantic schemas (LogEntry, StatsResponse, etc.)
│   └── static/
│       ├── index.html       # Doctor dashboard & manual entry UI
│       ├── style.css        # Clean, modern, responsive CSS & print stylesheet
│       └── app.js           # Chart.js integration & dashboard logic
└── data/                    # Persistent directory for tracker.db (git-ignored)
```

---

## 3. Database Specification (`app/database.py`)

SQLite database stored at `/app/data/tracker.db` (mounted to `./data/tracker.db` on host).

### Schema: `logs` table
```sql
CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    bristol INTEGER NOT NULL CHECK (bristol BETWEEN 1 AND 7),
    pain INTEGER NOT NULL CHECK (pain BETWEEN 1 AND 10),
    blood TEXT NOT NULL CHECK (blood IN ('none', 'some', 'alot')),
    notes TEXT DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp);
```

---

## 4. API Endpoints (`app/main.py`)

All endpoints support optional API Key verification via `X-API-Key` header (configurable in `.env` / `config.env`).

### `POST /api/log`
Quick intake endpoint for iOS Shortcuts and web UI.
* **Request Body:**
  ```json
  {
    "bristol": 4,
    "pain": 2,
    "blood": "none",
    "notes": "morning movement"
  }
  ```
* **Validation:**
  * `bristol`: Integer between 1 and 7.
  * `pain`: Integer between 1 and 10.
  * `blood`: String matching `none`, `some`, or `alot`.
* **Response (`201 Created`):**
  ```json
  {
    "status": "success",
    "id": 42,
    "timestamp": "2026-10-30T09:15:00",
    "today_count": 3,
    "message": "Logged successfully. Movement #3 today."
  }
  ```

### `GET /api/today`
Returns count and list of logs recorded today (based on server local time).

### `GET /api/stats?days=30`
Returns aggregated metrics for doctor analysis:
* `summary`: Total logs, average BMs/day, average Bristol, average pain, count of blood events (`none`, `some`, `alot`).
* `daily_breakdown`: Array of daily objects:
  ```json
  {
    "date": "2026-10-29",
    "count": 4,
    "avg_bristol": 4.5,
    "avg_pain": 2.2,
    "max_pain": 4,
    "blood_events": {"none": 3, "some": 1, "alot": 0}
  }
  ```
* `recent_logs`: Array of recent raw entries for inspection.

### `GET /api/export`
Exports raw data as downloadable CSV (`Content-Disposition: attachment; filename=ibd_logs.csv`) or JSON.

### `GET /health`
Simple health check returning `{"status": "ok"}`.

---

## 5. Doctor Dashboard & Web Interface (`app/static/`)

Accessible at `http://<server-ip>:8080/`.

### Key Features:
1. **Quick Overview Stats:**
   * Today's movement count
   * 7-day average daily frequency (e.g., 3.8 / day)
   * Average Bristol score (with color rating: Constipation 1–2, Normal 3–4, Diarrhea 5–7)
   * Average pain level (1–10)
   * Blood incidence percentage
2. **Interactive Progression Charts (via Chart.js):**
   * **Daily Frequency Chart:** Bar chart showing number of bowel movements per day.
   * **Consistency & Pain Trend:** Dual line chart tracking Bristol consistency and pain severity over time.
   * **Blood Presence Tracker:** Color-coded indicators/markers for days with blood reported.
3. **Doctor Visit Printable Report Mode:**
   * Date range selector (7 days, 14 days, 30 days, 90 days, or custom).
   * Generates a clean, professional, high-contrast summary table and trend summary.
   * Includes a 1-click **"Print / Save PDF"** button formatted cleanly for GI consultations.
4. **Manual Entry Modal:**
   * Fallback quick-log modal on the web interface with large touch buttons in case logging from a laptop or desktop.

---

## 6. Docker & Deployment Specification

### `Dockerfile`
```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### `docker-compose.yml`
```yaml
services:
  ibd-tracker:
    build: .
    container_name: ibd-tracker
    restart: unless-stopped
    ports:
      - "${IBD_TRACKER_PORT:-8080}:8080"
    environment:
      - TZ=${TIMEZONE:-America/New_York}
      - API_KEY=${IBD_TRACKER_API_KEY:-}
    volumes:
      - ./data:/app/data
```

### `requirements.txt`
```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.8.0
python-multipart>=0.0.9
```

---

## 7. iOS Shortcut Setup Specification (`IOS_SHORTCUT_GUIDE.md`)

Document the exact Apple Shortcuts workflow for iPhone:

1. **Prompt 1: Consistency (Bristol Scale):**
   * Action: `Choose from Menu`
   * Options:
     * `1 - Separate hard lumps`
     * `2 - Lumpy and sausage-like`
     * `3 - Sausage with cracks`
     * `4 - Smooth, soft snake (Normal)`
     * `5 - Soft blobs with clear edges`
     * `6 - Mushy, ragged edges (Diarrhea)`
     * `7 - Entirely liquid / watery`
   * Set variable `Consistency` to integer `1` through `7`.
2. **Prompt 2: Pain Level:**
   * Action: `Ask for Number` or `Choose from Menu` (1 to 10).
   * Set variable `Pain`.
3. **Prompt 3: Blood:**
   * Action: `Choose from Menu`
   * Options:
     * `None` -> value `"none"`
     * `Some / Trace` -> value `"some"`
     * `A lot` -> value `"alot"`
   * Set variable `Blood`.
4. **Network Request:**
   * Action: `Get Contents of URL`
   * URL: `http://<HYPERION_HOST>:8080/api/log`
   * Method: `POST`
   * Headers:
     * `Content-Type: application/json`
     * `X-API-Key: <optional-key>`
   * Request Body: `JSON`
     * `bristol`: `Consistency` (Number)
     * `pain`: `Pain` (Number)
     * `blood`: `Blood` (Text)
5. **Confirmation Banner:**
   * Action: `Show Notification`
   * Message: `Logged! BM today: [today_count]`

---

## 8. Verification Steps for Devin CLI

When executing this plan on the Linux server:
1. Build the Docker container: `docker compose build`.
2. Launch the container: `docker compose up -d`.
3. Send a test log entry:
   ```bash
   curl -X POST http://localhost:8080/api/log \
     -H "Content-Type: application/json" \
     -d '{"bristol": 4, "pain": 1, "blood": "none"}'
   ```
4. Verify response contains `status: "success"` and `today_count: 1`.
5. Verify `GET http://localhost:8080/api/stats` returns accurate calculations.
6. Verify the dashboard loads at `http://localhost:8080/` with status 200.
