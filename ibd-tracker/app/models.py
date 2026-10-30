from typing import List, Literal, Optional, Dict
from pydantic import BaseModel, Field

BloodType = Literal["none", "some", "alot"]

class LogCreate(BaseModel):
    bristol: int = Field(..., ge=1, le=7, description="Bristol stool score (1-7)")
    pain: int = Field(..., ge=1, le=10, description="Pain rating (1-10)")
    blood: BloodType = Field(..., description="Presence of blood: none, some, alot")
    notes: Optional[str] = Field(default="", description="Optional note or context")
    timestamp: Optional[str] = Field(default=None, description="Optional ISO timestamp override")

class LogEntry(BaseModel):
    id: int
    timestamp: str
    bristol: int
    pain: int
    blood: BloodType
    notes: Optional[str] = ""

class LogCreateResponse(BaseModel):
    status: str
    id: int
    timestamp: str
    today_count: int
    message: str

class TodayResponse(BaseModel):
    today_count: int
    date: str
    logs: List[LogEntry]

class BloodEventsSummary(BaseModel):
    none: int = 0
    some: int = 0
    alot: int = 0

class SummaryStats(BaseModel):
    total_logs: int
    days_window: int
    avg_daily_count: float
    avg_bristol: Optional[float] = None
    avg_pain: Optional[float] = None
    blood_events: BloodEventsSummary
    blood_incidence_pct: float

class DailyBreakdown(BaseModel):
    date: str
    count: int
    avg_bristol: Optional[float] = None
    avg_pain: Optional[float] = None
    max_pain: Optional[int] = None
    blood_events: BloodEventsSummary

class StatsResponse(BaseModel):
    summary: SummaryStats
    daily_breakdown: List[DailyBreakdown]
    recent_logs: List[LogEntry]
