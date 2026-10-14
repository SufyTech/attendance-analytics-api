# DECISIONS.md

## 1. Indexes

I made `emp_code` unique, `(emp_code, date)` unique, and `(date, emp_code)`. The unique `(emp_code, date)` means one employee can't have two records on the same day. The `(date, emp_code)` index serves the attendance list sort. I did not index `status` alone, because queries filter by date or employee first.

## 2. Punch-in race

If two punch-ins for the same employee and day arrive together, both can pass the `find_one` check and both try `insert_one`. The unique `(emp_code, date)` index lets only one save. The other gets `DuplicateKeyError`, and I return 409.

## 3. Ties in the leaderboard

Employees with the same total late minutes get the same rank, and the next rank is skipped (1, 2, 2, 4). I apply `limit` after ranking, so a tie at the edge can return more than `limit` rows.

## 4. Headcount

I start from the `employees` collection, not the logs, so an employee with no logs still counts. I use `$lookup` with `$unwind` and `preserveNullAndEmptyArrays`, then count distinct `emp_code`.

## 5. 100x data

With 100x data I would replace `skip` in `GET /attendance` with keyset pagination, using the last `(date, emp_code)` seen. A big `skip` gets slower on deeper pages, and my index already matches that sort.
