# grokhr-api

GrokHR demo API. An HR person lists, creates, updates, and deactivates employees.

Fictional data only. No authentication. No real PII.

## Shared contract

Production would depend on [`cleon/grokhr-shared`](https://github.com/cleon/grokhr-shared) (`grokhr_shared`) for the employee contract. That repo does not publish a model yet. This demo vendors a compatible Pydantic model in `grokhr_shared.py`. Sync it from the shared repo when the contract lands (see the NOTE at the top of that file).

JSON fields: `id`, `firstName`, `lastName`, `email`, `department`, `title`, `hireDate`, `status` (`active` or `inactive`), `managerId` (optional string, omitted from cleon/grokhr-shared).

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
| `GET` | `/employees` | List employees. `?status=active` reads `active_roster`. `?status=inactive` filters the table. |
| `POST` | `/employees` | Create. Status defaults to `active`. Duplicate email returns 409. |
| `GET` | `/employees/{id}` | Fetch one employee, including inactive. |
| `PATCH` | `/employees/{id}` | Partial update, including `status`. |
| `POST` | `/employees/{id}/deactivate` | Set status to `inactive`. Requires header `X-Deactivate-Reason`. Already inactive returns 409. |

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
