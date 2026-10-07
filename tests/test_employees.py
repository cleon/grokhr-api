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
    assert listed_body["page"] == 1
    assert listed_body["pageSize"] == 25
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
    assert roster.json()["total"] == SEEDED_ACTIVE
    assert employee_id not in [row["id"] for row in roster.json()["items"]]

    reactivated = client.patch(f"/employees/{employee_id}", json={"status": "active"})
    assert reactivated.status_code == 200
    assert reactivated.json()["status"] == "active"
    roster_again = client.get("/employees", params={"status": "active"})
    assert roster_again.json()["total"] == SEEDED_ACTIVE + 1
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


def test_list_page_defaults_and_bounds(client: TestClient):
    response = client.get("/employees")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "total", "page", "pageSize"}
    assert body["page"] == 1
    assert body["pageSize"] == 25
    assert body["total"] == SEEDED
    assert len(body["items"]) == SEEDED

    for params in (
        {"page": 0},
        {"page": -1},
        {"pageSize": 0},
        {"pageSize": 101},
        {"pageSize": -1},
        {"page": "nope"},
        {"pageSize": "nope"},
        {"page": 2**63},
        {"page": 10**18, "pageSize": 100},
    ):
        rejected = client.get("/employees", params=params)
        assert rejected.status_code == 422, params

    # Largest page whose offset still fits a SQLite INTEGER at pageSize 100.
    max_page = (2**63 - 1) // 100 + 1
    capped = client.get("/employees", params={"page": max_page, "pageSize": 100})
    assert capped.status_code == 200
    assert capped.json()["page"] == max_page
    assert capped.json()["items"] == []
    assert capped.json()["total"] == SEEDED

    smallest = client.get("/employees", params={"page": 1, "pageSize": 1})
    assert smallest.status_code == 200
    assert smallest.json()["pageSize"] == 1
    assert smallest.json()["total"] == SEEDED
    assert len(smallest.json()["items"]) == 1

    largest = client.get("/employees", params={"pageSize": 100})
    assert largest.status_code == 200
    assert largest.json()["pageSize"] == 100
    assert largest.json()["total"] == SEEDED
    assert len(largest.json()["items"]) == SEEDED


def test_list_pages_cover_total_in_stable_order(client: TestClient):
    page_size = 3
    pages = [
        client.get("/employees", params={"page": number, "pageSize": page_size})
        for number in (1, 2, 3, 4)
    ]
    assert [page.status_code for page in pages] == [200, 200, 200, 200]
    bodies = [page.json() for page in pages]
    for index, body in enumerate(bodies, start=1):
        assert body["page"] == index
        assert body["pageSize"] == page_size
        assert body["total"] == SEEDED
    assert [len(body["items"]) for body in bodies] == [3, 3, 1, 0]
    collected = [row for body in bodies for row in body["items"]]
    assert len({row["id"] for row in collected}) == SEEDED
    order = [(row["lastName"], row["firstName"], row["id"]) for row in collected]
    assert order == sorted(order)


def test_list_page_keeps_status_filter(client: TestClient):
    first = client.get("/employees", params={"status": "active", "page": 1, "pageSize": 2})
    second = client.get("/employees", params={"status": "active", "page": 2, "pageSize": 2})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["total"] == SEEDED_ACTIVE
    assert second.json()["total"] == SEEDED_ACTIVE
    assert len(first.json()["items"]) == 2
    assert len(second.json()["items"]) == 2
    assert {row["status"] for row in first.json()["items"] + second.json()["items"]} == {"active"}
    first_ids = {row["id"] for row in first.json()["items"]}
    second_ids = {row["id"] for row in second.json()["items"]}
    assert first_ids.isdisjoint(second_ids)

    inactive = client.get("/employees", params={"status": "inactive", "pageSize": 10})
    assert inactive.status_code == 200
    inactive_body = inactive.json()
    assert inactive_body["total"] == SEEDED - SEEDED_ACTIVE
    assert [row["email"] for row in inactive_body["items"]] == ["elena.voss@example.com"]


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
    list_params = {param["name"]: param for param in paths["/employees"]["get"]["parameters"]}
    assert list_params["page"]["schema"]["default"] == 1
    assert list_params["page"]["schema"]["minimum"] == 1
    assert list_params["page"]["schema"]["maximum"] == (2**63 - 1) // 100 + 1
    assert list_params["pageSize"]["schema"]["default"] == 25
    assert list_params["pageSize"]["schema"]["minimum"] == 1
    assert list_params["pageSize"]["schema"]["maximum"] == 100
    page_properties = spec["components"]["schemas"]["EmployeePage"]["properties"]
    assert set(page_properties) == {"items", "total", "page", "pageSize"}


def test_schema_file_defines_view():
    schema = SCHEMA_PATH.read_text()
    assert "CREATE VIEW" in schema
    assert "active_roster" in schema
    assert "CREATE TABLE" in schema
