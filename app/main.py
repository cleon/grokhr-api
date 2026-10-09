"""GrokHR demo API. No auth. Fictional employees only."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request

from app.db import (
    connect,
    deactivate_employee,
    fetch_employee,
    fetch_employees,
    init_db,
    insert_employee,
    patch_employee,
)
from grokhr_shared import Employee, EmployeeCreate, EmployeePage, EmployeeStatus, EmployeeUpdate

# Shared-cache memory DB. Override with a filesystem path to persist across restarts.
DEFAULT_DATABASE = "file:grokhr?mode=memory&cache=shared"


def create_app(database: str | None = None) -> FastAPI:
    db_path = database or os.environ.get("GROKHR_DATABASE", DEFAULT_DATABASE)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Hold one connection so the in-memory database survives between requests.
        keeper = connect(db_path)
        init_db(keeper)
        app.state.keeper = keeper
        try:
            yield
        finally:
            keeper.close()

    app = FastAPI(
        title="GrokHR API",
        version="0.1.0",
        summary="Manage fictional employees for the GrokHR demo.",
        description=(
            "HR person lists, creates, updates, and deactivates employees. "
            "Fictional data only. No authentication. No real PII. "
            "Production would depend on cleon/grokhr-shared; this demo vendors "
            "a compatible model in grokhr_shared.py. "
            "GET /employees returns { items, total, page, pageSize }. "
            "status=active reads the active_roster SQL view."
        ),
        lifespan=lifespan,
    )
    app.state.database = db_path

    def get_db(request: Request) -> Iterator[sqlite3.Connection]:
        conn = connect(request.app.state.database)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def require_employee(employee: Employee | None) -> Employee:
        if employee is None:
            raise HTTPException(status_code=404, detail="employee not found")
        return employee

    @app.get(
        "/employees",
        response_model=EmployeePage,
        tags=["employees"],
        summary="List employees",
        description=(
            "One page of employees ordered by last name, first name, then id. "
            "The body is `{ items, total, page, pageSize }`. "
            "`total` counts matches before paging. "
            "`status=active` reads the active_roster SQL view."
        ),
    )
    def list_employees(
        status: EmployeeStatus | None = Query(
            default=None,
            description="Filter by status. `active` reads the active_roster SQL view.",
        ),
        search: str | None = Query(
            default=None,
            description="Case-insensitive substring of first name, last name, or email.",
        ),
        page: int = Query(default=1, ge=1, description="1-based page index."),
        page_size: int = Query(
            default=25,
            alias="pageSize",
            ge=1,
            le=100,
            description="Page size. Maximum 100.",
        ),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> EmployeePage:
        term = search.strip() if search is not None else None
        if not term:
            term = None
        items, total = fetch_employees(conn, status, term, page, page_size)
        return EmployeePage(items=items, total=total, page=page, page_size=page_size)

    @app.post("/employees", response_model=Employee, status_code=201, tags=["employees"])
    def create_employee(
        body: EmployeeCreate,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Employee:
        try:
            return insert_employee(conn, body.model_dump())
        except sqlite3.IntegrityError as exc:
            if "employees.email" in str(exc):
                raise HTTPException(status_code=409, detail="email already exists") from exc
            raise HTTPException(status_code=400, detail="invalid employee") from exc

    @app.get("/employees/{employee_id}", response_model=Employee, tags=["employees"])
    def get_employee(
        employee_id: int,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Employee:
        return require_employee(fetch_employee(conn, employee_id))

    @app.patch("/employees/{employee_id}", response_model=Employee, tags=["employees"])
    def update_employee(
        employee_id: int,
        body: EmployeeUpdate,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Employee:
        fields = body.model_dump(exclude_unset=True)
        if any(value is None for value in fields.values()):
            raise HTTPException(status_code=422, detail="fields cannot be null")
        try:
            return require_employee(patch_employee(conn, employee_id, fields))
        except sqlite3.IntegrityError as exc:
            if "employees.email" in str(exc):
                raise HTTPException(status_code=409, detail="email already exists") from exc
            raise HTTPException(status_code=400, detail="invalid employee") from exc

    @app.post(
        "/employees/{employee_id}/deactivate",
        response_model=Employee,
        tags=["employees"],
    )
    def deactivate(
        employee_id: int,
        conn: sqlite3.Connection = Depends(get_db),
    ) -> Employee:
        # Idempotent: deactivating an already inactive employee returns that row.
        return require_employee(deactivate_employee(conn, employee_id))

    return app


app = create_app()
