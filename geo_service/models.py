from typing import Literal

from pydantic import BaseModel, Field


Level = Literal["division", "district", "upazila", "union"]


class Area(BaseModel):
    area_id: str
    geo_code: str
    level: Level
    name: str
    latitude: float
    longitude: float
    parent_area_id: str | None = None
    has_boundary: bool = False


class LocateRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class CrosswalkEntry(BaseModel):
    area_id: str
    dhis2_uid: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9]{10}$")
    dhis2_name: str | None = None


class DHIS2SyncRequest(BaseModel):
    base_url: str
    token: str | None = None
    username: str | None = None
    password: str | None = None
    code_attribute: str = "code"


class DHIS2SyncResult(BaseModel):
    received: int
    matched: int
    unmatched: int
    crosswalk_size: int
