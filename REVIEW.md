# REVIEW.md

List every defect you found in the starter `app/main.py` (helpers and endpoints). For each one:

| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |
|---|---|---|---|---|
| 1 | `list_employees`, line `skip = page * page_size` | On page 1 it skipped the first 20 employees (1 * 20 = 20) but it should skip 0. We only have 6 employees, so nothing was left to show | `total` showed 6 but `items` was empty | Changed it to `skip = (page - 1) * page_size` | 
| 2 | `punch_in`, the line `emp = db.employees.find_one(...)`, and later `emp["shift_start"]` | The employee was not found, so `emp` was `None`. The code still tried to read `emp["shift_start"]` and crashed. The contract says it should answer 404 for an unknown employee | I punched in with `EMP9999`, who is not in the database. The browser showed 500 Internal Server Error and the terminal showed `TypeError: 'NoneType' object is not subscriptable` | I added `if not emp:` and `raise HTTPException(404, "employee not found")` right after the `find_one` line |
| 3 | `list_employees`, the line with `count_documents` | `total` counted all employees even with a department filter | I searched `Sales`. `items` showed 2 employees but `total` said 6 | I changed `count_documents({})` to `count_documents(q)` |
| 4 | `punch_in`, the `status` | It accepts any status, like `ABSENT`. The contract allows only three statuses | I sent `ABSENT` and got 201 | I added a check that gives 422 |
| 5 | `punch_in`, `datetime.now()` | It used my computer's time zone. Rule R1 says IST | No `+05:30` in the response | I passed `IST` in both places |
| 6 | `punch_in`, the `ts` line | The time had extra digits after the seconds. R1 says whole seconds | The response showed `.516404` | I added `ts = ts.replace(microsecond=0)` |
| 7 | `compute_late_minutes` | It cuts the seconds before checking "more than 10" | 09:40:01 gave 0, the rule wants 10 | I compare `seconds > 600` |
| 8 | `compute_work_hours`, the `round` | Python `round` is not half-up | 3618 seconds gave 1.0, the rule wants 1.01 | I used `Decimal` with `ROUND_HALF_UP` |
| 9 | `compute_overtime`, the last line | No 30 minutes minimum | 18:59:59 gave 29, the rule wants 0 | I return the minutes only if they are 30 or more |
| 10 | `punch_in`, the line `return doc` | It returns the time as text, but the contract wants epoch milliseconds | `punch_in` was `"2026-10-12T13:35:17+05:30"` | I changed it to `return to_api(doc)` |
| 11 | `list_attendance`, the end of the function | It loaded all records into Python, sorted there, and returned database dates. The contract wants MongoDB to sort and page, and epoch milliseconds | The dates came out in the order they were saved, not newest first | I used `count_documents(q)`, then `.sort`, `.skip`, `.limit`, and `to_api` |
| 12 | `to_api` | It didn't convert the dates inside `history`, and didn't add `half_day` and `history` when missing | `history` showed text dates, and the `EMP0002` record had no `history` | I added `history_to_api` and defaults |
| 13 | `punch_in`, the check followed by `insert_one` | It checks first and then saves, so two requests at the same moment could both save | I noticed it from reading the code, because the contract says that of two simultaneous punch-ins exactly one gets 201 | I added a unique index on `emp_code` and `date`, and I catch `DuplicateKeyError` and answer 409 |

Also note anything you looked at and decided was **not** a defect, and why.
