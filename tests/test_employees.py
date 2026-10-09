import uuid

import pytest
from fastapi.testclient import TestClient

from app.db import SCHEMA_PATH, connect
from app.main import create_app

SEEDED = 7
SEEDED_ACTIVE = 6


@pytest.fixture(params=["memory", "file"])
def client(request, tmp_path):
    if request.param == "memory":
        database = f"file:grokhr-{uuid.uuid4().hex}?mode=memory&cache=shared"
    else:
        database = str(tmp_path / "grokhr.db")
    app = create_app(database=database)
    with TestClient(app) as test_client:
        yield test_client


def test_crud_happy_path(client: TestClient):
    listed = client.get("/employees")
    assert listed.status_code == 200
    listed_body = listed.json()
    assert listed_body["total"] == SEEDED
    assert len(listed_body["items"]) == SEEDED

    created = client.post(
        "/employees",
        json={
            "firstName": "Ada",
            "lastName": "Example",
            "email": "ada.example@example.com",
            "department": "Engineering",
            "title": "Engineer",
            "hireDate": "2024-05-06",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert set(body) == {
        "id",
        "firstName",
        "lastName",
        "email",
        "department",
        "title",
        "hireDate",
        "status",
    }
    assert body["status"] == "active"
    employee_id = body["id"]

    fetched = client.get(f"/employees/{employee_id}")
    assert fetched.status_code == 200
    assert fetched.json()["email"] == "ada.example@example.com"

    patched = client.patch(
        f"/employees/{employee_id}",
        json={"title": "Staff Engineer", "department": "Platform"},
    )
    assert patched.status_code == 200
    assert patched.json()["title"] == "Staff Engineer"
    assert patched.json()["lastName"] == "Example"

    deactivated = client.post(f"/employees/{employee_id}/deactivate")
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "inactive"
    deactivated_again = client.post(f"/employees/{employee_id}/deactivate")
    assert deactivated_again.status_code == 200
    assert deactivated_again.json()["status"] == "inactive"

    roster = client.get("/employees", params={"status": "active"})
    assert roster.status_code == 200
    assert employee_id not in [row["id"] for row in roster.json()["items"]]

    reactivated = client.patch(f"/employees/{employee_id}", json={"status": "active"})
    assert reactivated.status_code == 200
    assert reactivated.json()["status"] == "active"
    roster_again = client.get("/employees", params={"status": "active"})
    assert employee_id in [row["id"] for row in roster_again.json()["items"]]


def test_active_roster_matches_view(client: TestClient):
    conn = connect(client.app.state.database)
    try:
        kind = conn.execute(
            "SELECT type FROM sqlite_master WHERE name = 'active_roster'"
        ).fetchone()
        assert kind[0] == "view"
        view_ids = [row[0] for row in conn.execute("SELECT id FROM active_roster").fetchall()]
    finally:
        conn.close()

    response = client.get("/employees", params={"status": "active"})
    assert response.status_code == 200
    body = response.json()
    api_ids = [row["id"] for row in body["items"]]
    assert body["total"] == SEEDED_ACTIVE
    assert sorted(api_ids) == sorted(view_ids)
    assert len(api_ids) == SEEDED_ACTIVE
    emails = {row["email"] for row in body["items"]}
    assert "elena.voss@example.com" not in emails
    assert "maya.chen@example.com" in emails


def test_missing_employee(client: TestClient):
    assert client.get("/employees/9999").status_code == 404
    assert client.patch("/employees/9999", json={"title": "Nope"}).status_code == 404
    assert client.post("/employees/9999/deactivate").status_code == 404


def test_duplicate_email(client: TestClient):
    payload = {
        "firstName": "Maya",
        "lastName": "Chen",
        "email": "maya.chen@example.com",
        "department": "People",
        "title": "People Partner",
        "hireDate": "2019-03-12",
    }
    conflict = client.post("/employees", json=payload)
    assert conflict.status_code == 409


def test_create_rejects_incomplete_body(client: TestClient):
    response = client.post("/employees", json={"firstName": "Only"})
    assert response.status_code == 422


def test_openapi_documents_routes(client: TestClient):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    assert spec["info"]["title"] == "GrokHR API"
    paths = spec["paths"]
    assert "get" in paths["/employees"]
    assert "post" in paths["/employees"]
    assert "get" in paths["/employees/{employee_id}"]
    assert "patch" in paths["/employees/{employee_id}"]
    assert "post" in paths["/employees/{employee_id}/deactivate"]
    properties = spec["components"]["schemas"]["Employee"]["properties"]
    assert "firstName" in properties
    assert "hireDate" in properties
    assert "first_name" not in properties
    page_schema = spec["components"]["schemas"]["EmployeePage"]["properties"]
    assert set(page_schema) == {"items", "total", "page", "pageSize"}
    list_get = spec["paths"]["/employees"]["get"]
    assert list_get["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/EmployeePage"
    )
    params = {param["name"]: param["schema"] for param in list_get["parameters"]}
    assert params["page"]["default"] == 1
    assert params["page"]["minimum"] == 1
    assert params["pageSize"]["default"] == 25
    assert params["pageSize"]["minimum"] == 1
    assert params["pageSize"]["maximum"] == 100
    assert "search" in params
    assert "status" in params


def _names(rows: list[dict]) -> list[tuple[str, str, int]]:
    return [(row["lastName"], row["firstName"], row["id"]) for row in rows]


def test_list_defaults_and_sort(client: TestClient):
    response = client.get("/employees")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "total", "page", "pageSize"}
    assert body["page"] == 1
    assert body["pageSize"] == 25
    assert body["total"] == SEEDED
    assert len(body["items"]) == SEEDED
    assert _names(body["items"]) == [
        ("Blake", "Jonah", 4),
        ("Chen", "Maya", 1),
        ("Haddad", "Samira", 5),
        ("Nair", "Priya", 3),
        ("Ortega", "Luis", 2),
        ("Park", "Owen", 6),
        ("Voss", "Elena", 7),
    ]


def test_page_and_page_size_bounds(client: TestClient):
    assert client.get("/employees", params={"page": 0}).status_code == 422
    assert client.get("/employees", params={"page": -1}).status_code == 422
    assert client.get("/employees", params={"pageSize": 0}).status_code == 422
    assert client.get("/employees", params={"pageSize": 101}).status_code == 422

    widest = client.get("/employees", params={"pageSize": 100, "page": 1})
    assert widest.status_code == 200
    assert widest.json()["pageSize"] == 100
    assert widest.json()["total"] == SEEDED

    first = client.get("/employees", params={"pageSize": 1, "page": 1})
    assert first.status_code == 200
    assert first.json()["page"] == 1
    assert len(first.json()["items"]) == 1
    assert first.json()["items"][0]["lastName"] == "Blake"
    assert first.json()["total"] == SEEDED


def test_paging_total_is_before_the_page(client: TestClient):
    pages = [
        client.get("/employees", params={"page": page, "pageSize": 3}).json()
        for page in (1, 2, 3)
    ]
    assert [page["total"] for page in pages] == [SEEDED, SEEDED, SEEDED]
    assert [len(page["items"]) for page in pages] == [3, 3, 1]
    assert [page["page"] for page in pages] == [1, 2, 3]
    assert [page["pageSize"] for page in pages] == [3, 3, 3]
    combined = [row["id"] for page in pages for row in page["items"]]
    assert combined == [4, 1, 5, 3, 2, 6, 7]

    beyond = client.get("/employees", params={"page": 4, "pageSize": 3})
    assert beyond.status_code == 200
    assert beyond.json()["items"] == []
    assert beyond.json()["total"] == SEEDED
    assert beyond.json()["page"] == 4
    assert beyond.json()["pageSize"] == 3


def test_search_matches_name_or_email(client: TestClient):
    by_last = client.get("/employees", params={"search": "cHeN"})
    assert by_last.status_code == 200
    assert by_last.json()["total"] == 1
    assert by_last.json()["items"][0]["email"] == "maya.chen@example.com"

    by_first = client.get("/employees", params={"search": "  pRiYa "})
    assert by_first.json()["total"] == 1
    assert by_first.json()["items"][0]["lastName"] == "Nair"

    by_email = client.get("/employees", params={"search": "ORTEGA@EXAMPLE"})
    assert by_email.json()["total"] == 1
    assert by_email.json()["items"][0]["firstName"] == "Luis"

    middle = client.get("/employees", params={"search": "adda"})
    assert [row["lastName"] for row in middle.json()["items"]] == ["Haddad"]

    blank = client.get("/employees", params={"search": "   "})
    assert blank.json()["total"] == SEEDED

    none = client.get("/employees", params={"search": "zzznomatch"})
    assert none.json() == {"items": [], "total": 0, "page": 1, "pageSize": 25}

    # Department and title are not search fields. % and _ are literal characters.
    assert client.get("/employees", params={"search": "Payroll"}).json()["total"] == 0
    assert client.get("/employees", params={"search": "%"}).json()["total"] == 0
    assert client.get("/employees", params={"search": "_"}).json()["total"] == 0


def test_search_status_and_paging_combine(client: TestClient):
    active = client.get(
        "/employees",
        params={"status": "active", "search": "example.com", "page": 2, "pageSize": 2},
    )
    assert active.status_code == 200
    body = active.json()
    assert body["total"] == SEEDED_ACTIVE
    assert body["page"] == 2
    assert body["pageSize"] == 2
    assert _names(body["items"]) == [("Haddad", "Samira", 5), ("Nair", "Priya", 3)]
    assert all(row["status"] == "active" for row in body["items"])

    inactive = client.get(
        "/employees",
        params={"status": "inactive", "search": "voss"},
    )
    assert inactive.json()["total"] == 1
    assert inactive.json()["items"][0]["email"] == "elena.voss@example.com"

    hidden = client.get("/employees", params={"status": "active", "search": "voss"})
    assert hidden.json()["total"] == 0
    assert hidden.json()["items"] == []


def test_sort_tie_breaks_on_id(client: TestClient):
    created = []
    for first_name, email in (
        ("Ada", "ada.z1@example.com"),
        ("Ada", "ada.z2@example.com"),
        ("Aaron", "aaron.z@example.com"),
    ):
        response = client.post(
            "/employees",
            json={
                "firstName": first_name,
                "lastName": "Zephyr",
                "email": email,
                "department": "Engineering",
                "title": "Engineer",
                "hireDate": "2024-05-06",
            },
        )
        assert response.status_code == 201
        created.append(response.json())

    listed = client.get("/employees", params={"search": "Zephyr", "pageSize": 10})
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 3
    assert _names(body["items"]) == [
        ("Zephyr", "Aaron", created[2]["id"]),
        ("Zephyr", "Ada", created[0]["id"]),
        ("Zephyr", "Ada", created[1]["id"]),
    ]


def test_schema_file_defines_view():
    schema = SCHEMA_PATH.read_text()
    assert "CREATE VIEW" in schema
    assert "active_roster" in schema
    assert "CREATE TABLE" in schema
