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
| `GET` | `/employees` | List one page of employees. See query parameters and response shape below. |
| `POST` | `/employees` | Create. Status defaults to `active`. Duplicate email returns 409. |
| `GET` | `/employees/{id}` | Fetch one employee, including inactive. |
| `PATCH` | `/employees/{id}` | Partial update, including `status`. |
| `POST` | `/employees/{id}/deactivate` | Set status to `inactive`. Idempotent. |

### `GET /employees`

Query parameters:

| Name | Default | |
| --- | --- | --- |
| `status` | | `active` reads `active_roster`. `inactive` filters the table. Omit it to return both. |
| `search` | | Case-insensitive substring of first name, last name, or email. Blank is ignored. |
| `page` | `1` | 1-based. Values below 1 return 422. |
| `pageSize` | `25` | Maximum 100. Values below 1 or above 100 return 422. |

`status` and `search` combine. `total` is the match count before paging. `items` is that page, ordered by last name, first name, then id.

```json
{
  "items": [
    {
      "id": 4,
      "firstName": "Jonah",
      "lastName": "Blake",
      "email": "jonah.blake@example.com",
      "department": "Finance",
      "title": "Payroll Specialist",
      "hireDate": "2022-02-14",
      "status": "active"
    }
  ],
  "total": 7,
  "page": 1,
  "pageSize": 1
}
```

`GET /employees?page=1&pageSize=1` is the first row of the full directory. A page past the end returns `"items": []` and the same `total`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```
