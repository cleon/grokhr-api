"""Vendored stand-in for the ``grokhr_shared`` employee contract.

NOTE: Production GrokHR API depends on cleon/grokhr-shared
(https://github.com/cleon/grokhr-shared). That repo does not publish an
employee model yet, so this module is a local compatible copy.
Sync field names, aliases, and EmployeeStatus from grokhr-shared when it lands.
"""

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EmployeeStatus(str, Enum):
    active = "active"
    inactive = "inactive"


def _strip(value: str) -> str:
    return value.strip()


class EmployeeBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    first_name: str = Field(alias="firstName", min_length=1, max_length=80)
    last_name: str = Field(alias="lastName", min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    department: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=80)
    hire_date: date = Field(alias="hireDate")
    status: EmployeeStatus = EmployeeStatus.active
    manager_id: int | None = Field(
        default=None,
        alias="managerId",
        gt=0,
        description="Employee id of the reporting manager. Null when the employee has no manager.",
    )

    @field_validator("first_name", "last_name", "email", "department", "title")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    """Partial update. Omitted fields stay as they are.

    Null is rejected, except ``manager_id``, which clears the reporting line.
    """

    model_config = ConfigDict(populate_by_name=True)

    first_name: str | None = Field(default=None, alias="firstName", min_length=1, max_length=80)
    last_name: str | None = Field(default=None, alias="lastName", min_length=1, max_length=80)
    email: str | None = Field(
        default=None, min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )
    department: str | None = Field(default=None, min_length=1, max_length=80)
    title: str | None = Field(default=None, min_length=1, max_length=80)
    hire_date: date | None = Field(default=None, alias="hireDate")
    status: EmployeeStatus | None = None
    manager_id: int | None = Field(
        default=None,
        alias="managerId",
        gt=0,
        description="Employee id of the reporting manager. Null clears the reporting line.",
    )

    @field_validator("first_name", "last_name", "email", "department", "title")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _strip(value)


class Employee(EmployeeBase):
    id: int
