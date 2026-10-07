# grokhr-api

GrokHR demo API. An HR person lists, creates, updates, and deactivates employees.

Fictional data only. No authentication. No real PII.

## Shared contract

Production would depend on [`cleon/grokhr-shared`](https://github.com/cleon/grokhr-shared) (`grokhr_shared`) for the employee contract. That repo does not publish a model yet. This demo vendors a compatible Pydantic model in `grokhr_shared.py`. Sync it from the shared repo when the contract lands (see the NOTE at the top of that file).

JSON fields: `id`, `firstName`, `lastName`, `email`, `department`, `title`, `hireDate`, `status` (`active` or `inactive`), `deactivatedAt` (UTC time of the latest soft-delete, or null).

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Swagger UI: http://127.0.0.1:8000/docs
- OpenAPI: http://127.0.0.1:8000/openapi.json

The database is SQLite in process memory (`file:grokhr?mode=memory&cache=shared`). It is created and seeded on startup and discarded when the process exits. One uvicorn process only; extra workers would each get their own empty memory database.

To keep a file instead:

```bash
GROKHR_DATABASE=grokhr.db uvicorn app.main:app --reload
```

Schema lives in `sql/schema.sql`: an `employees` table (including nullable `deactivated_at`) and an `active_roster` view (employees whose status is `active`). `sql/seed.sql` loads seven fictional employees on first init, one of them inactive with a `deactivated_at`. Startup adds `deactivated_at` to an existing database file that predates the column, then recreates the view. Rows that were already inactive are left with a null timestamp rather than an invented one.

## Endpoints

| Method | Path | |
| --- | --- | --- |
| `GET` | `/employees` | Active employees only. `?includeInactive=true` returns everyone. `?status=active` reads `active_roster`. `?status=inactive` returns inactive employees. An explicit `status` is the whole filter. |
| `POST` | `/employees` | Create. Status defaults to `active`. `deactivatedAt` is null. Duplicate email returns 409. |
| `GET` | `/employees/{id}` | Fetch one employee, including inactive, with `deactivatedAt`. |
| `PATCH` | `/employees/{id}` | Partial update, including `status`. Does not change `deactivatedAt`. |
| `DELETE` | `/employees/{id}` | Soft-delete. Sets `status` to `inactive` and `deactivatedAt` to the current UTC time. Returns 204. The row is not removed. Already inactive: 204 and the timestamp stays. Unknown id: 404. |
| `POST` | `/employees/{id}/deactivate` | Same soft-delete as `DELETE`, returning the employee. |

`deactivatedAt` remains when a later `PATCH` sets `status` back to `active`, so the departure stays on the record. A delete of that active employee writes a new timestamp. A delete of someone who is already inactive does not.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
