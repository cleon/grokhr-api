"""GrokHR demo API. No auth. Fictional employees only."""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.db import (
    connect,
    deactivate_employee,
    fetch_employee,
    fetch_employees,
    init_db,
    insert_employee,
    patch_employee,
)
from grokhr_shared import Employee, EmployeeCreate, EmployeeStatus, EmployeeUpdate

# Shared-cache memory DB. Override with a filesystem path to persist across restarts.
DEFAULT_DATABASE = "file:grokhr?mode=memory&cache=shared"
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
# (page - 1) * pageSize is bound as a SQLite INTEGER. Cap page so the largest
# pageSize still fits in a signed 64-bit integer; a larger page is a 422, not a 500.
MAX_PAGE = (2**63 - 1) // MAX_PAGE_SIZE + 1


class EmployeePage(BaseModel):
    """One page of employees. `total` counts the filtered set before paging."""

    model_config = ConfigDict(populate_by_name=True)

    items: list[Employee]
    total: int
    page: int
    page_size: int = Field(alias="pageSize")


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
            "GET /employees returns a page of employees "
            "(`items`, `total`, `page`, `pageSize`). "
            "`status=active` reads the active_roster SQL view."
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

    @app.get("/employees", response_model=EmployeePage, tags=["employees"])
    def list_employees(
        status: EmployeeStatus | None = Query(
            default=None,
            description="Filter by status. `active` reads the active_roster SQL view.",
        ),
        page: int = Query(
            default=1,
            ge=1,
            le=MAX_PAGE,
            description="1-based page index.",
        ),
        page_size: int = Query(
            default=DEFAULT_PAGE_SIZE,
            ge=1,
            le=MAX_PAGE_SIZE,
            alias="pageSize",
            title="pageSize",
            description="Employees per page. Maximum 100.",
        ),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> EmployeePage:
        items, total = fetch_employees(conn, status, page=page, page_size=page_size)
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
