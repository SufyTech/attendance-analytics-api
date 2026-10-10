# REVIEW.md

List every defect you found in the starter `app/main.py` (helpers and endpoints). For each one:

| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |
|---|---|---|---|---|
| 1 | `list_employees`, line `skip = page * page_size` | On page 1 it skipped the first 20 employees (1 * 20 = 20) but it should skip 0. We only have 6 employees, so nothing was left to show | `total` showed 6 but `items` was empty | Changed it to `skip = (page - 1) * page_size` | 
| 2 | `punch_in`, the line `emp = db.employees.find_one(...)`, and later `emp["shift_start"]` | The employee was not found, so `emp` was `None`. The code still tried to read `emp["shift_start"]` and crashed. The contract says it should answer 404 for an unknown employee | I punched in with `EMP9999`, who is not in the database. The browser showed 500 Internal Server Error and the terminal showed `TypeError: 'NoneType' object is not subscriptable` | I added `if not emp:` and `raise HTTPException(404, "employee not found")` right after the `find_one` line |
| 3 | `list_employees`, the line with `count_documents` | `total` counted all employees even with a department filter | I searched `Sales`. `items` showed 2 employees but `total` said 6 | I changed `count_documents({})` to `count_documents(q)` |

Also note anything you looked at and decided was **not** a defect, and why.
