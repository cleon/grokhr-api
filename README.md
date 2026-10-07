# grokhr-api

GrokHR demo API. An HR person lists, creates, updates, and deactivates employees.

Fictional data only. No authentication. No real PII.

## Shared contract

Production would depend on [`cleon/grokhr-shared`](https://github.com/cleon/grokhr-shared) (`grokhr_shared`) for the employee contract. That repo does not publish a model yet. This demo vendors a compatible Pydantic model in `grokhr_shared.py`. Sync it from the shared repo when the contract lands (see the NOTE at the top of that file).

JSON fields: `id`, `firstName`, `lastName`, `email`, `department`, `title`, `hireDate`, `status` (`active` or `inactive`).

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

Schema lives in `sql/schema.sql`: an `employees` table and an `active_roster` view (employees whose status is `active`). `sql/seed.sql` loads seven fictional employees on first init.

## Endpoints

| Method | Path | |
| --- | --- | --- |
| `GET` | `/employees` | One page of employees. Query: `page` (default 1), `pageSize` (default 25, max 100), optional `status`. |
| `POST` | `/employees` | Create. Status defaults to `active`. Duplicate email returns 409. |
| `GET` | `/employees/{id}` | Fetch one employee, including inactive. |
| `PATCH` | `/employees/{id}` | Partial update, including `status`. |
| `POST` | `/employees/{id}/deactivate` | Set status to `inactive`. Idempotent. |

`GET /employees` returns an object with `items`, `total`, `page`, and `pageSize`. `items` is the employees for that page, ordered by last name, first name, then id. `total` is the number of employees matching the filter before paging. `page` starts at 1. `pageSize` must be from 1 through 100. A `page` below 1, a `page` whose offset does not fit in a 64-bit signed integer, or a `pageSize` outside 1 through 100 returns 422. A page past the end returns an empty `items` list and the same `total`.

`?status=active` reads the `active_roster` view. `?status=inactive` filters the table. The status filter and pagination apply together: `total` counts only the filtered rows.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
