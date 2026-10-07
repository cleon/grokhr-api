"""Vendored stand-in for the ``grokhr_shared`` employee contract.

NOTE: Production GrokHR API depends on cleon/grokhr-shared
(https://github.com/cleon/grokhr-shared). That repo does not publish an
employee model yet, so this module is a local compatible copy.
Sync field names, aliases, and EmployeeStatus from grokhr-shared when it lands.
"""

from datetime import date, datetime, timezone
from enum import Enum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_serializer, field_validator


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

    @field_validator("first_name", "last_name", "email", "department", "title")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(BaseModel):
    """Partial update. Omitted fields stay as they are. Null is rejected."""

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

    @field_validator("first_name", "last_name", "email", "department", "title")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _strip(value)


class Employee(EmployeeBase):
    id: int
    deactivated_at: AwareDatetime | None = Field(
        default=None,
        alias="deactivatedAt",
        description=(
            "UTC time of the latest soft-delete. Null until the employee is deactivated. "
            "Left in place if status is later set back to active."
        ),
    )

    @field_serializer("deactivated_at")
    def serialize_deactivated_at(self, value: datetime | None) -> str | None:
        # Clients get a Z suffix. The default encoder would emit +00:00.
        if value is None:
            return None
        value = value.astimezone(timezone.utc).replace(microsecond=0)
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
