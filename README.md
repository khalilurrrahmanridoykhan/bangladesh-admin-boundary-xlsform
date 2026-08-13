# Bangladesh Admin Boundary XLSForm

An ODK/XLSForm cascading-select form (Division → District → Upazila → Union)
for the full administrative geography of Bangladesh, where selecting an area
automatically shows it on a `geopoint` map — and, at the Union level, the map
becomes a tappable boundary shape instead of a plain list.

Built and verified live in **KoboCollect on Android**: selecting
Dhaka → Faridpur → Char Bhadrasan renders the real Char Bhadrasan union
boundary as a highlighted polygon on the map, tap-to-select, auto-populating
the location field. See `forms/` for the three progressively-capable versions.

## The three forms

| File | What it does |
|---|---|
| `Full Bangladesh Division To Union.xlsx` | The original cascading select (Division→Union), no map integration. |
| `Full Bangladesh Division To Union (with map).xlsx` | Adds an auto-updating `geopoint` that centers on the selected area at any level. |
| `Full Bangladesh Division To Union (with map + boundaries).xlsx` | Same, plus the Union question renders as a real tappable boundary-shape map (KoboCollect Android only — see "Platform support" below). |

## How the auto-centering map works

A `read_only` `geopoint` question at the end of the group, appearance `maps`,
with a `calculation` that falls back down the hierarchy — Union if answered,
else Upazila, else District, else Division:

```
if(${uni_}!='', concat(instance('uni_')/root/item[name=${uni_}]/latitude,' ',instance('uni_')/root/item[name=${uni_}]/longitude,' 0 0'),
if(${upa_}!='', concat(instance('upa_')/root/item[name=${upa_}]/latitude,' ',instance('upa_')/root/item[name=${upa_}]/longitude,' 0 0'),
if(${dis_}!='', concat(instance('dis_')/root/item[name=${dis_}]/latitude,' ',instance('dis_')/root/item[name=${dis_}]/longitude,' 0 0'),
if(${div_}!='', concat(instance('div_')/root/item[name=${div_}]/latitude,' ',instance('div_')/root/item[name=${div_}]/longitude,' 0 0'),
''))))
```

Two things make this work that are easy to miss:

- **`calculation` + `read_only: yes`, not `default`.** `default` only
  evaluates once, before the cascading selects are typically answered — it
  can't follow later answers. `calculation` re-evaluates on every dependency
  change, but XLSForm only applies it reliably to a field that's read-only.
  Confirmed against the community-documented pattern on the
  [ODK Forum](https://forum.getodk.org/t/default-geopoint-using-select-one-and-calculate).
- **`choice_filter: true()` on the Division question.** With no filter at
  all, pyxform won't generate the secondary XML instance that the
  `instance('div_')/...` lookups above depend on. `true()` (always-true)
  forces that instance into existence without actually filtering anything.

## How the boundary map works

The Union question's `appearance` is `map`, and its `choices` rows carry a
`geometry` column — an XForms `geoshape` string:

```
lat1 lon1 alt1 acc1;lat2 lon2 alt2 acc2;...;lat1 lon1 alt1 acc1
```

(semicolon-separated points, ring closed by repeating the first point —
format confirmed against the [ODK XForms
spec](https://getodk.github.io/xforms-spec/).) This is the real,
[documented](https://support.kobotoolbox.org/select_from_map_xls.html)
"select choice from map" mechanism — not a custom hack.

### Platform support (read this before you file a bug)

Map-based `select_one` choice rendering is **KoboCollect (Android) only**.
In any browser — Enketo web preview, the Kobo web form, ODK Central web
forms — it deliberately falls back to a normal radio-button list. That's
documented, correct behavior, not broken rendering. If you need to see the
boundary shapes, test in the KoboCollect app on a phone/tablet, not a
browser.

## Data source

Built from official Bangladesh administrative boundary shapefiles
(`bgd_adm0`–`bgd_adm4`, dated 31/12/2025) covering Division through
Union/Municipality, plus separate Ward and Village boundary/centroid sets
(not yet used here). The raw shapefiles are **not included in this repo** —
they're large (the Union set alone is hundreds of MB) and their
redistribution terms weren't independently verified, so regenerate the
choices sheet from your own copy of the source data if you need to update it
(see `scripts/`).

**Why the choices sheet was rebuilt from the shapefile instead of hand-edited:**
the original form's choice names (English-slug-based, e.g. `union_Amtali`)
only matched the shapefile's own names by exact string comparison for 67% of
unions (87% of upazilas, 95% of districts) — good enough to look like it
works, not good enough to trust. The rebuilt choices use the shapefile's own
`GEO_CODE` as the choice name (e.g. `uni_100409109`), so the dropdown list
and the map geometry can never drift apart — they're generated from the same
source in the same pass.

**A real data-quality issue this surfaced:** 10 upazilas in the source
shapefile are split across two rows sharing the same `GEO_CODE` (disconnected
exclave/char pieces stored as separate features). pyxform's own choice-name
uniqueness validator caught this on the first build attempt. Fixed by
dissolving all four admin levels by their code before building the choice
list — see `scripts/build_choices_from_shapefiles.py`.

## Known simplifications, stated plainly

- **79 of 4,926 unions are MultiPolygons** (real disconnected river-char
  fragments). The boundary shown is the largest sub-polygon by area only —
  smaller detached pieces are dropped from the map shape (they're still
  correctly attributed in the underlying data, just not drawn).
- **Boundaries are simplified to ~111m tolerance** (`simplify(0.001,
  preserve_topology=True)`) to keep the compiled form loadable — the raw,
  unsimplified boundaries totaled 3.4 million vertices across all unions,
  which is impractical for a form enumerators load on a phone. The
  boundaries version compiles to ~7.3MB, noticeably larger than the ~1.4MB
  no-boundaries version — worth testing on your actual field connectivity
  before committing to it for real data collection.
- **The auto-centering `geopoint` is read-only.** It shows the selected
  area's location but can't be independently repositioned by the enumerator
  — a deliberate tradeoff for reliable live-updating (see above).

## Bangladesh Geo Service and DHIS2 crosswalk API

The repository also includes a small FastAPI service that turns the same
committed XLSForm geography into a shared lookup API. It supports cascading
geographic lookups, reverse point-in-Union lookup, hierarchy lineage, and a
persistent geographic-code ↔ DHIS2 organisation-unit crosswalk.

The workbook contains 5,588 geographic choices: 8 divisions, 64 districts,
590 upazilas, and 4,926 unions/municipalities.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn geo_service.main:app --reload
```

Interactive API documentation is then available at `http://127.0.0.1:8000/docs`.

Read endpoints:

- `GET /divisions`
- `GET /districts?division_code=div_30`
- `GET /upazilas?district_code=dis_3029`
- `GET /unions?upazila_code=upa_302947`
- `GET /areas/{area_id}` and `/areas/{area_id}/lineage`
- `POST /locate` with `{"latitude": 23.7, "longitude": 90.4}`
- `GET /dhis2/crosswalk/{area_id}`

Crosswalk writes and DHIS2 synchronization are disabled unless
`GEO_ADMIN_KEY` is set. Send that value in the `X-Admin-Key` header when
calling `PUT /dhis2/crosswalk/{area_id}` or `POST /dhis2/sync`. The sync
endpoint reads DHIS2 organisation units and matches their configured `code`
field to this project's stable, level-qualified area IDs (for example
`div_30` or `uni_100409109`). The raw official code remains available as
`geo_code` in every API response. Never commit a
DHIS2 token or password; provide credentials only in the request to a service
you control, over HTTPS.

The default writable crosswalk is `data/dhis2_crosswalk.json` and is ignored
by Git. Set `GEO_CROSSWALK` to use a mounted persistent path in production.
An example record is provided in `data/dhis2_crosswalk.example.json`.

### Production container

`Dockerfile` and `compose.production.yml` run the API as an unprivileged,
read-only container. Configure `GEO_ADMIN_KEY` in a local `.env.production`
file, then start it with:

```bash
docker compose --env-file .env.production -f compose.production.yml up -d --build
```

The Compose service joins the existing `onehealth-platform_default` proxy
network and expects a reverse proxy to strip `/geo-api` before forwarding to
`geo-service:8000`. Change `GEO_ROOT_PATH` if deploying at another prefix.

## Validation

Both map-enabled forms compile cleanly with `pyxform` (`xls2xform_convert(...,
validate=True)` returns zero errors) and were confirmed working live in
KoboCollect on Android: cascading selects populate correctly at every level,
the auto-centering geopoint lands on the correct coordinates, and the Union
boundary map correctly highlights and selects (verified against Char
Bhadrasan upazila/union, Faridpur district, Dhaka division).

## Rebuilding the choices sheet

```
pip install geopandas pandas
python scripts/build_choices_from_shapefiles.py \
    --adm-dir /path/to/your/bgd_adm_shapefiles \
    --out choices.csv \
    --with-boundaries \
    --simplify-tolerance 0.001
```

Then paste the resulting CSV into the `choices` sheet of the xlsx (columns:
`list_name, name, label, div_filter, dis_filter, upa_filter, latitude,
longitude[, geometry]`), and validate with `pyxform`.

## License

Code in `scripts/` is MIT-licensed (see `LICENSE`). The `.xlsx` forms
contain geometry and place names derived from third-party administrative
boundary data — verify redistribution terms with your own source before
reusing the boundary data itself outside this project.
