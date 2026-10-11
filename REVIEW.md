# REVIEW.md

List every defect you found in the starter `app/main.py` (helpers and endpoints). For each one:

| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |
|---|---|---|---|---|
| 1 | `list_employees`, line `skip = page * page_size` | On page 1 it skipped the first 20 employees (1 * 20 = 20) but it should skip 0. We only have 6 employees, so nothing was left to show | `total` showed 6 but `items` was empty | Changed it to `skip = (page - 1) * page_size` | 
| 2 | `punch_in`, the line `emp = db.employees.find_one(...)`, and later `emp["shift_start"]` | The employee was not found, so `emp` was `None`. The code still tried to read `emp["shift_start"]` and crashed. The contract says it should answer 404 for an unknown employee | I punched in with `EMP9999`, who is not in the database. The browser showed 500 Internal Server Error and the terminal showed `TypeError: 'NoneType' object is not subscriptable` | I added `if not emp:` and `raise HTTPException(404, "employee not found")` right after the `find_one` line |
| 3 | `list_employees`, the line with `count_documents` | `total` counted all employees even with a department filter | I searched `Sales`. `items` showed 2 employees but `total` said 6 | I changed `count_documents({})` to `count_documents(q)` |
| 4 | `punch_in`, the `status` value (`body.status`) | It accepted any status, even `ABSENT`. The contract says punch-in allows only `PRESENT`, `WFH` and `ON_DUTY`, and anything else should be 422 | I sent `"status": "ABSENT"` and got 201, and the record was saved with `ABSENT` | I added `if body.status not in ["PRESENT", "WFH", "ON_DUTY"]:` and `raise HTTPException(422, ...)`, placed after the 404 check and before the 409 check |
| 5 | `punch_in`, the line with `datetime.now()` and `datetime.fromtimestamp(...)` | It used the server's own time zone, but rule R1 says dates and shift times are IST. On a UTC server the record's `date` could be wrong | The response had no `+05:30`, and the record date followed my computer's time zone, not UTC | I passed `IST` to both `datetime.fromtimestamp(..., IST)` and `datetime.now(IST)` |
| 6 | `punch_in`, the line after `ts = datetime...` | The punch-in time kept the digits after the seconds. Rule R1 says the time must be cut to whole seconds before any calculation, and the cut value is what is stored and returned | The response showed `01:21:12.516404` | I added `ts = ts.replace(microsecond=0)` right after the `ts` line and before `d = ts.date().isoformat()` |

Also note anything you looked at and decided was **not** a defect, and why.
