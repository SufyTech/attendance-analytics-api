# Employee Attendance & Analytics API

My submission for the attendance assignment. FastAPI + MongoDB, all code in `app/main.py`.

## Run it

1. `python -m venv .venv`, then `.venv\Scripts\activate` (on Mac/Linux: `source .venv/bin/activate`)
2. `pip install -r requirements.txt`
3. Make a `.env` file with `MONGO_URI` and `MONGO_DB`
4. `python sample_seed.py`
5. `uvicorn app.main:app --port 8000`
6. Open http://localhost:8000/docs

## What works

- Create and list employees (input checks, sorted, paged)
- Punch-in, punch-out, and HR corrections with history
- Attendance list with filters and paging
- Monthly report per employee, department summary, late leaderboard
- `/admin/explain` for 4 endpoints
- `/health` pings the database

I tested these on a real MongoDB with the sample data.

## What I did not finish

- Overnight shifts (like 22:00-06:00) work when the punch-in is on the shift's start date. A punch-in after midnight gets the next day as its record date, so that case is still wrong.
- The department trend endpoint is not built.

## Notes

- `REVIEW.md` has the bugs I found in the starter and how I fixed them.
- `DECISIONS.md` has my answers on indexes, races, ties, headcount and scale.

## AI use

I used AI for reference and for review. I typed the changes myself, and I can explain every part of the code.
