from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import Depends, FastAPI, Header, HTTPException

from .models import Area, CrosswalkEntry, DHIS2SyncRequest, DHIS2SyncResult, LocateRequest
from .store import GeoStore


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = Path(os.getenv("GEO_WORKBOOK", ROOT / "forms/Full Bangladesh Division To Union (with map + boundaries).xlsx"))
CROSSWALK = Path(os.getenv("GEO_CROSSWALK", ROOT / "data/dhis2_crosswalk.json"))
store = GeoStore(WORKBOOK, CROSSWALK)

app = FastAPI(
    title="Bangladesh Geo Service",
    version="1.0.0",
    description="Administrative hierarchy, point lookup, and DHIS2 organisation-unit crosswalk API.",
    root_path=os.getenv("GEO_ROOT_PATH", ""),
)


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("GEO_ADMIN_KEY")
    if not expected:
        raise HTTPException(503, "Write operations are disabled until GEO_ADMIN_KEY is configured")
    if x_admin_key != expected:
        raise HTTPException(401, "Invalid administrative key")


@app.get("/health")
def health():
    return {"status": "ok", "areas": len(store.areas), "boundaries": len(store.boundaries)}


@app.get("/divisions", response_model=list[Area])
def divisions():
    return store.list_areas("division")


@app.get("/districts", response_model=list[Area])
def districts(division_code: str):
    return store.list_areas("district", division_code)


@app.get("/upazilas", response_model=list[Area])
def upazilas(district_code: str):
    return store.list_areas("upazila", district_code)


@app.get("/unions", response_model=list[Area])
def unions(upazila_code: str):
    return store.list_areas("union", upazila_code)


@app.get("/areas/{area_id}", response_model=Area)
def area(area_id: str):
    result = store.areas.get(area_id)
    if not result:
        raise HTTPException(404, "Geographic code not found")
    return result


@app.get("/areas/{area_id}/lineage", response_model=list[Area])
def lineage(area_id: str):
    result = store.lineage(area_id)
    if not result:
        raise HTTPException(404, "Geographic code not found")
    return result


@app.post("/locate", response_model=list[Area])
def locate(request: LocateRequest):
    result = store.locate(request.latitude, request.longitude)
    if not result:
        raise HTTPException(404, "Coordinate is outside the available Union boundaries")
    return result


@app.get("/dhis2/crosswalk/{area_id}", response_model=CrosswalkEntry)
def get_crosswalk(area_id: str):
    result = store.crosswalk.get(area_id)
    if not result:
        raise HTTPException(404, "No DHIS2 crosswalk exists for this geographic code")
    return result


@app.put("/dhis2/crosswalk/{area_id}", response_model=CrosswalkEntry, dependencies=[Depends(require_admin)])
def put_crosswalk(area_id: str, entry: CrosswalkEntry):
    if area_id != entry.area_id:
        raise HTTPException(400, "Path and payload geographic codes must match")
    try:
        return store.save_crosswalk(entry)
    except KeyError:
        raise HTTPException(404, "Geographic code not found")


def fetch_dhis2_org_units(request: DHIS2SyncRequest) -> list[dict]:
    params = urlencode({"paging": "false", "fields": f"id,name,{request.code_attribute}"})
    http_request = Request(f"{request.base_url.rstrip('/')}/api/organisationUnits.json?{params}")
    if request.token:
        http_request.add_header("Authorization", f"ApiToken {request.token}")
    elif request.username and request.password:
        credentials = base64.b64encode(f"{request.username}:{request.password}".encode()).decode()
        http_request.add_header("Authorization", f"Basic {credentials}")
    else:
        raise HTTPException(400, "Provide a DHIS2 API token or username and password")
    try:
        with urlopen(http_request, timeout=30) as response:
            return json.load(response).get("organisationUnits", [])
    except Exception as exc:
        raise HTTPException(502, f"DHIS2 request failed: {exc}") from exc


@app.post("/dhis2/sync", response_model=DHIS2SyncResult, dependencies=[Depends(require_admin)])
def sync_dhis2(request: DHIS2SyncRequest):
    units = fetch_dhis2_org_units(request)
    matched = 0
    for unit in units:
        area_id = str(unit.get(request.code_attribute) or "").strip()
        if area_id in store.areas:
            store.save_crosswalk(CrosswalkEntry(area_id=area_id, dhis2_uid=unit["id"], dhis2_name=unit.get("name")))
            matched += 1
    return DHIS2SyncResult(
        received=len(units), matched=matched, unmatched=len(units) - matched, crosswalk_size=len(store.crosswalk)
    )
