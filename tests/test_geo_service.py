from pathlib import Path

from geo_service.models import CrosswalkEntry
from geo_service.store import GeoStore, point_in_ring


ROOT = Path(__file__).resolve().parents[1]
WORKBOOK = ROOT / "forms/Full Bangladesh Division To Union (with map + boundaries).xlsx"


def test_hierarchy_counts_and_parent_filters(tmp_path):
    store = GeoStore(WORKBOOK, tmp_path / "crosswalk.json")
    assert len(store.areas) == 5588
    assert len(store.list_areas("division")) == 8
    dhaka = store.areas["div_30"]
    assert dhaka.name == "Dhaka"
    assert store.list_areas("district", "div_30")


def test_union_representative_point_resolves_to_its_boundary(tmp_path):
    store = GeoStore(WORKBOOK, tmp_path / "crosswalk.json")
    union = next(area for area in store.areas.values() if area.level == "union" and area.has_boundary)
    lineage = store.locate(union.latitude, union.longitude)
    assert lineage[-1].area_id == union.area_id
    assert [area.level for area in lineage] == ["division", "district", "upazila", "union"]


def test_point_in_ring():
    square = [(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)]
    assert point_in_ring(1, 1, square)
    assert not point_in_ring(3, 1, square)


def test_crosswalk_persists(tmp_path):
    path = tmp_path / "crosswalk.json"
    store = GeoStore(WORKBOOK, path)
    entry = CrosswalkEntry(area_id="div_30", dhis2_uid="Abcdef12345", dhis2_name="Dhaka Division")
    store.save_crosswalk(entry)
    reloaded = GeoStore(WORKBOOK, path)
    assert reloaded.crosswalk["div_30"] == entry
