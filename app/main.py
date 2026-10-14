"""
Employee Attendance & Analytics API - STARTER

Run:  uvicorn app.main:app --port 8000
Env:  MONGO_URI, MONGO_DB (a local .env is loaded for convenience)

This file was written quickly by a colleague who has left the company. The happy path
works, but nobody has reviewed it. Read PROBLEM_STATEMENT.docx for what is expected of you,
openapi.yaml for the contract and DATA_MODEL.md for what is stored in MongoDB.
"""
import os
import calendar
import re
import json
from bson import json_util
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from decimal import Decimal, ROUND_HALF_UP

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = client[os.getenv("MONGO_DB", "attendance_db")]

IST = timezone(timedelta(hours=5, minutes=30))
ALL_STATUSES = ["PRESENT", "WFH", "ON_DUTY", "ABSENT", "LEAVE"]

app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0")

db.employees.create_index("emp_code", unique=True)
db.attendance_logs.create_index([("emp_code", 1), ("date", 1)], unique=True)
db.attendance_logs.create_index([("date", -1), ("emp_code", 1)])
db.attendance_logs.create_index([("emp_code", 1), ("punch_in", -1)])
db.employees.create_index("joined_on")
db.employees.create_index([("department", 1), ("joined_on", 1)])

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def compute_late_minutes(punch_in: datetime, shift_start: str) -> int:
    h, m = map(int, shift_start.split(":"))
    start = punch_in.replace(hour=h, minute=m, second=0, microsecond=0)
    seconds = int((punch_in - start).total_seconds())
    return seconds // 60 if seconds > 600 else 0


def compute_work_hours(punch_in: datetime, punch_out: datetime) -> float:
       seconds = int((punch_out - punch_in).total_seconds())
       hours = Decimal(seconds) / Decimal(3600)
       return float(hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def to_ms(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt - datetime(1970, 1, 1, tzinfo=timezone.utc)) // timedelta(milliseconds=1)


def history_to_api(entry):
    out = dict(entry)
    out["at"] = to_ms(entry.get("at"))
    changes = {}
    for field, change in entry.get("changes", {}).items():
        if field in ("punch_in", "punch_out"):
            changes[field] = {"from": to_ms(change.get("from")), "to": to_ms(change.get("to"))}
        else:
            changes[field] = change
    out["changes"] = changes
    return out


def to_api(rec):
    out = {k: v for k, v in rec.items() if k != "_id"}
    out["punch_in"] = to_ms(rec.get("punch_in"))
    out["punch_out"] = to_ms(rec.get("punch_out"))
    out["half_day"] = rec.get("half_day", False)
    out["history"] = [history_to_api(h) for h in rec.get("history", [])]
    return out

def from_ms(ms):
    if ms < 100000000000 or ms > 4102444800000:
        raise HTTPException(422, "time must be epoch milliseconds")
    return datetime.fromtimestamp(ms / 1000, IST).replace(microsecond=0)


def to_aware(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(IST)

def compute_overtime(punch_out: datetime, shift_end: str, date_str: str) -> int:
    h, m = map(int, shift_end.split(":"))
    end = datetime.fromisoformat(date_str).replace(hour=h, minute=m, tzinfo=IST)
    minutes = int((punch_out - end).total_seconds() // 60)
    return minutes if minutes >= 30 else 0

def count_weekdays(start: str, end: str) -> int:
    d = datetime.fromisoformat(start)
    last = datetime.fromisoformat(end)
    count = 0
    while d <= last:
        if d.weekday() < 5:  # Monday to Friday
            count += 1
        d += timedelta(days=1)
    return count

# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class EmployeeIn(BaseModel):
    emp_code: str
    name: str
    email: str
    department: str
    shift_start: str = "09:30"
    shift_end: str = "18:30"
    joined_on: str


class PunchInIn(BaseModel):
    emp_code: str
    punched_at: Optional[int] = None
    status: str = "PRESENT"

class PunchOutIn(BaseModel):
    emp_code: str
    punched_at: Optional[int] = None
    
    
class RegularizeIn(BaseModel):
    status: Optional[str] = None
    punch_in: Optional[int] = None
    punch_out: Optional[int] = None
    reason: str = Field(min_length=5, max_length=200)
    regularized_by: str = Field(min_length=1, max_length=50)

# --------------------------------------------------------------------------- #
# Endpoints provided
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    if db.employees.find_one({"emp_code": body.emp_code}):
        raise HTTPException(409, "emp_code already exists")
    doc = body.model_dump()
    doc["created_at"] = datetime.now()
    db.employees.insert_one(doc)
    doc.pop("_id", None)
    return doc


@app.get("/employees")
def list_employees(department: Optional[str] = None, page: int = 1, page_size: int = 20):
    q = {}
    if department:
        q["department"] = department
    skip = (page - 1) * page_size
    total = db.employees.count_documents(q)
    items = list(db.employees.find(q, {"_id": 0}).skip(skip).limit(page_size))
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(404, "employee not found")
    if body.status not in ["PRESENT", "WFH", "ON_DUTY"]:
        raise HTTPException(422, "status must be PRESENT, WFH or ON_DUTY")
    ts = datetime.fromtimestamp(body.punched_at / 1000, IST) if body.punched_at else datetime.now(IST)
    ts = ts.replace(microsecond=0)
    d = ts.date().isoformat()
    if db.attendance_logs.find_one({"emp_code": body.emp_code, "date": d}):
        raise HTTPException(409, "already punched in for this date")
    doc = {
        "emp_code": body.emp_code,
        "date": d,
        "status": body.status,
        "punch_in": ts,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": compute_late_minutes(ts, emp["shift_start"]),
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }
    try:
        res = db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "already punched in for this date")


    doc["id"] = str(res.inserted_id)
    doc.pop("_id", None)
    return to_api(doc)

def build_attendance_query(emp_code, date_from, date_to, status):
    q = {}
    if emp_code:
        q["emp_code"] = emp_code
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to
    if status:
        q["status"] = status
    return q


@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    q = build_attendance_query(emp_code, date_from, date_to, status)
    skip = (page - 1) * page_size
    total = db.attendance_logs.count_documents(q)
    cursor = db.attendance_logs.find(q, {"_id": 0}).sort([("date", -1), ("emp_code", 1)]).skip(skip).limit(page_size)
    items = [to_api(d) for d in cursor]
    return {"items": items, "total": total, "page": page, "page_size": page_size}

@app.post("/attendance/punch-out")
def punch_out(body: PunchOutIn):
    emp = db.employees.find_one({"emp_code": body.emp_code})
    if not emp:
        raise HTTPException(404, "employee not found")
    ts = datetime.fromtimestamp(body.punched_at / 1000, IST) if body.punched_at else datetime.now(IST)
    ts = ts.replace(microsecond=0)
    rec = db.attendance_logs.find_one(
        {"emp_code": body.emp_code, "punch_in": {"$lte": ts}},
        sort=[("punch_in", -1)],
    )
    if not rec:
        raise HTTPException(404, "no punch-in found")
    if rec.get("punch_out") is not None:
        raise HTTPException(409, "already punched out")
    pin = rec["punch_in"].replace(tzinfo=timezone.utc)
    if ts <= pin or ts - pin > timedelta(hours=24):
        raise HTTPException(422, "punched_at must be after punch_in and within 24 hours")
    work_hours = compute_work_hours(pin, ts)
    overtime = compute_overtime(ts, emp["shift_end"], rec["date"])
    res = db.attendance_logs.update_one(
        {"_id": rec["_id"], "punch_out": None},
        {"$set": {
            "punch_out": ts,
            "work_hours": work_hours,
            "overtime_minutes": overtime,
            "half_day": work_hours < 4.5,
        }},
    )
    if res.modified_count == 0:
        raise HTTPException(409, "already punched out")
    rec = db.attendance_logs.find_one({"_id": rec["_id"]})
    return to_api(rec)

@app.patch("/attendance/{emp_code}/{date}")
def regularize(emp_code: str, date: str, body: RegularizeIn):
    emp = db.employees.find_one({"emp_code": emp_code})
    if not emp:
        raise HTTPException(404, "employee not found")
    rec = db.attendance_logs.find_one({"emp_code": emp_code, "date": date})
    if not rec:
        raise HTTPException(404, "no record for that date")
    new_status = body.status or rec["status"]
    if new_status not in ALL_STATUSES:
        raise HTTPException(422, "invalid status")
    if new_status in ["ABSENT", "LEAVE"]:
        if body.punch_in is not None or body.punch_out is not None:
            raise HTTPException(422, "this status cannot have punch times")
        new_in = None
        new_out = None
    else:
        new_in = from_ms(body.punch_in) if body.punch_in is not None else to_aware(rec.get("punch_in"))
        new_out = from_ms(body.punch_out) if body.punch_out is not None else to_aware(rec.get("punch_out"))
        if new_in is None:
            raise HTTPException(422, "a presence status needs a punch_in")
        if body.punch_in is not None and new_in.date().isoformat() != date:
            raise HTTPException(422, "punch_in must stay on the record's date")
        if new_out is not None and (new_out <= new_in or new_out - new_in > timedelta(hours=24)):
            raise HTTPException(422, "punch_out must be after punch_in and within 24 hours")
    new_late = 0
    new_hours = None
    new_overtime = 0
    new_half = False
    if new_in is not None:
        new_late = compute_late_minutes(new_in, emp["shift_start"])
        if new_out is not None:
            new_hours = compute_work_hours(new_in, new_out)
            new_overtime = compute_overtime(new_out, emp["shift_end"], date)
            new_half = new_hours < 4.5
    new_values = {
        "status": new_status,
        "punch_in": new_in,
        "punch_out": new_out,
        "work_hours": new_hours,
        "late_minutes": new_late,
        "overtime_minutes": new_overtime,
        "half_day": new_half,
    }
    changes = {}
    for field, new_value in new_values.items():
        old_value = rec.get(field)
        if field in ("punch_in", "punch_out"):
            old_value = to_aware(old_value)
        if field == "half_day":
            old_value = bool(old_value)
        if old_value != new_value:
            changes[field] = {"from": rec.get(field), "to": new_value}
    if not changes:
        raise HTTPException(422, "nothing to change")
    entry = {
        "at": datetime.now(IST).replace(microsecond=0),
        "by": body.regularized_by,
        "reason": body.reason,
        "changes": changes,
    }
    n = len(rec.get("history", []))
    res = db.attendance_logs.update_one(
        {"_id": rec["_id"], f"history.{n}": {"$exists": False}},
        {"$set": new_values, "$push": {"history": entry}},
    )
    if res.modified_count == 0:
        raise HTTPException(409, "the record was changed by someone else, try again")
    return to_api(db.attendance_logs.find_one({"_id": rec["_id"]}))

@app.get("/analytics/employees/{emp_code}/monthly")
def employee_monthly(emp_code: str, month: str):
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", month):
        raise HTTPException(422, "month must be YYYY-MM")
    emp = db.employees.find_one({"emp_code": emp_code})
    if not emp:
        raise HTTPException(404, "employee not found")
    year, mon = int(month[:4]), int(month[5:])
    last_day = calendar.monthrange(year, mon)[1]
    first = f"{month}-01"
    last = f"{month}-{last_day:02d}"
    start = max(first, emp["joined_on"])
    working_days = count_weekdays(start, last)
    pipeline = [
        {"$match": {"emp_code": emp_code, "date": {"$gte": first, "$lte": last}}},
        {"$group": {
            "_id": None,
            "leave_days": {"$sum": {"$cond": [{"$eq": ["$status", "LEAVE"]}, 1, 0]}},
            "present_days": {"$sum": {"$cond": [
                {"$and": [
                    {"$in": ["$status", ["PRESENT", "WFH", "ON_DUTY"]]},
                    {"$in": [{"$dayOfWeek": {"$dateFromString": {"dateString": "$date"}}}, [2, 3, 4, 5, 6]]},
                ]},
                {"$cond": [{"$eq": [{"$ifNull": ["$half_day", False]}, True]}, 0.5, 1]},
                0,
            ]}},
            "late_count": {"$sum": {"$cond": [{"$gt": ["$late_minutes", 0]}, 1, 0]}},
            "total_late_minutes": {"$sum": "$late_minutes"},
            "total_overtime_minutes": {"$sum": "$overtime_minutes"},
        }},
    ]
    result = list(db.attendance_logs.aggregate(pipeline))
    s = result[0] if result else {}
    
    present = Decimal(str(s.get("present_days", 0)))
    if working_days == 0:
        attendance_pct = None
    else:
        attendance_pct = float((present * 100 / Decimal(str(working_days))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return {
        "emp_code": emp_code,
        "month": month,
        "working_days": working_days,
        "present_days": s.get("present_days", 0),
        "leave_days": s.get("leave_days", 0),
        "late_count": s.get("late_count", 0),
        "total_late_minutes": s.get("total_late_minutes", 0),
        "total_overtime_minutes": s.get("total_overtime_minutes", 0),
        "attendance_pct": attendance_pct,
    }
    
@app.get("/analytics/departments/summary")
def department_summary(month: str, department: Optional[str] = None):
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", month):
        raise HTTPException(422, "month must be YYYY-MM")
    year, mon = int(month[:4]), int(month[5:])
    last = f"{month}-{calendar.monthrange(year, mon)[1]:02d}"
    emp_match = {"joined_on": {"$lte": last}}
    if department:
        emp_match["department"] = department
    first = f"{month}-01"
    pipeline = [
        {"$match": emp_match},
        {"$lookup": {
            "from": "attendance_logs",
            "localField": "emp_code",
            "foreignField": "emp_code",
            "pipeline": [{"$match": {"date": {"$gte": first, "$lte": last}}}],
            "as": "logs",
        }},
        {"$unwind": {"path": "$logs", "preserveNullAndEmptyArrays": True}},
                {"$addFields": {"has_hours": {"$and": [
            {"$in": ["$logs.status", ["PRESENT", "WFH", "ON_DUTY"]]},
            {"$ne": [{"$ifNull": ["$logs.work_hours", None]}, None]},
        ]}}},
        {"$group": {
            "_id": "$department",
            "emps": {"$addToSet": "$emp_code"},
            "present_days": {"$sum": {"$cond": [
                {"$and": [
                    {"$in": ["$logs.status", ["PRESENT", "WFH", "ON_DUTY"]]},
                    {"$in": [{"$dayOfWeek": {"$dateFromString": {"dateString": "$logs.date"}}}, [2, 3, 4, 5, 6]]},
                ]},
                {"$cond": [{"$eq": [{"$ifNull": ["$logs.half_day", False]}, True]}, 0.5, 1]},
                0,
            ]}},
            "late_count": {"$sum": {"$cond": [{"$gt": ["$logs.late_minutes", 0]}, 1, 0]}},
            "total_late_minutes": {"$sum": "$logs.late_minutes"},
            "leave_count": {"$sum": {"$cond": [{"$eq": ["$logs.status", "LEAVE"]}, 1, 0]}},
            "on_duty_count": {"$sum": {"$cond": [{"$eq": ["$logs.status", "ON_DUTY"]}, 1, 0]}},
            "hours_sum": {"$sum": {"$cond": ["$has_hours", "$logs.work_hours", 0]}},
            "hours_count": {"$sum": {"$cond": ["$has_hours", 1, 0]}},
        }},
        {"$sort": {"_id": 1}},
    ]
    rows = list(db.employees.aggregate(pipeline))
    items = []
    for r in rows:
        if r["hours_count"] == 0:
            avg_hours = None
        else:
            avg_hours = float((Decimal(str(round(r["hours_sum"], 2))) / Decimal(r["hours_count"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        items.append({
            "department": r["_id"],
            "headcount": len(r["emps"]),
            "avg_work_hours": avg_hours,
            "present_days": r["present_days"],
            "late_count": r["late_count"],
            "total_late_minutes": r["total_late_minutes"],
            "leave_count": r["leave_count"],
            "on_duty_count": r["on_duty_count"],
        })
    return {"month": month, "items": items}
   
@app.get("/admin/explain/{endpoint}")
def explain_endpoint(
    endpoint: str,
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    month: Optional[str] = None,
    limit: int = 10,
    department: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    if endpoint == "late_leaderboard":
        if not month or not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", month):
            raise HTTPException(422, "month must be YYYY-MM")
        if limit < 1 or limit > 50:
          raise HTTPException(422, "limit must be between 1 and 50")
        year, mon = int(month[:4]), int(month[5:])
        first = f"{month}-01"
        last = f"{month}-{calendar.monthrange(year, mon)[1]:02d}"
        pipeline = build_leaderboard_pipeline(first, last, department)
        command = {
            "explain": {"aggregate": "attendance_logs", "pipeline": pipeline, "cursor": {}},
            "verbosity": "executionStats",
        }
        result = db.command(command)
        return {
            "endpoint": endpoint,
            "collection": "attendance_logs",
            "explain": json.loads(json_util.dumps(result)),
        }
    if endpoint != "attendance_list":
        raise HTTPException(422, "this endpoint is not supported yet")
    q = build_attendance_query(emp_code, date_from, date_to, status)
    command = {
        "explain": {
            "find": "attendance_logs",
            "filter": q,
            "sort": {"date": -1, "emp_code": 1},
            "skip": (page - 1) * page_size,
            "limit": page_size,
        },
        "verbosity": "executionStats",
    }
    result = db.command(command)
    return {
        "endpoint": endpoint,
        "collection": "attendance_logs",
        "explain": json.loads(json_util.dumps(result)),
    }

def build_leaderboard_pipeline(first, last, department):
    pipeline = [
        {"$match": {"date": {"$gte": first, "$lte": last}}},
        {"$group": {
            "_id": "$emp_code",
            "total_late_minutes": {"$sum": "$late_minutes"},
            "late_count": {"$sum": {"$cond": [{"$gt": ["$late_minutes", 0]}, 1, 0]}},
        }},
        {"$match": {"total_late_minutes": {"$gt": 0}}},
        {"$lookup": {"from": "employees", "localField": "_id", "foreignField": "emp_code", "as": "emp"}},
        {"$unwind": "$emp"},
    ]
    if department:
        pipeline.append({"$match": {"emp.department": department}})
    pipeline.append({"$sort": {"total_late_minutes": -1, "_id": 1}})
    return pipeline

@app.get("/analytics/leaderboard/late")
def late_leaderboard(month: str, limit: int = 10, department: Optional[str] = None):
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", month):
        raise HTTPException(422, "month must be YYYY-MM")
    if limit < 1 or limit > 50:
        raise HTTPException(422, "limit must be between 1 and 50")
    year, mon = int(month[:4]), int(month[5:])
    first = f"{month}-01"
    last = f"{month}-{calendar.monthrange(year, mon)[1]:02d}"
    pipeline = build_leaderboard_pipeline(first, last, department)
    rows = list(db.attendance_logs.aggregate(pipeline))
    items = []
    rank = 0
    previous_total = None
    for position, r in enumerate(rows, start=1):
        if r["total_late_minutes"] != previous_total:
            rank = position
            previous_total = r["total_late_minutes"]
        if rank > limit:
            break
        items.append({
            "rank": rank,
            "emp_code": r["_id"],
            "name": r["emp"]["name"],
            "department": r["emp"]["department"],
            "total_late_minutes": r["total_late_minutes"],
            "late_count": r["late_count"],
        })
    return {"month": month, "items": items}