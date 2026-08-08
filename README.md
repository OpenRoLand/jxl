# siscadro-jxl

Secure, streaming parser and canonical extractor adapter for Leica/Trimble
JXL job-file (`JOBFile`) XML documents, built on top of the shared
`siscadro-survey` core.

This library never imports `cad_server` and has no DXF or CAD geometry
behavior. `cad-server` depends on this library instead of embedding its own
JXL parser.

## Installation

This is a private, unpublished package. Install it editably alongside its
`siscadro-survey` dependency:

```bash
python -m pip install -e "..\siscadro-survey"
python -m pip install -e ".[dev]"
```

## Supported documents

- `.jxl` job files, with or without an XML namespace (default or prefixed).
- `JOBFile/Reductions/Point` reduced points, including their `Grid`
  north/east/elevation values.
- `JOBFile/FieldBook/PointRecord` metadata, merged into the matching
  reduced point by point ID (falling back to name) so a code or
  description recorded only in the field book still reaches the canonical
  record.
- `JOBFile/Environment` coordinate-system metadata. A recognizable EPSG
  code (an `EPSG`/`EPSGCode` leaf element) becomes the extraction's
  `source_crs`.

External entity resolution and DTD network access are disabled while
parsing, so an untrusted `.jxl` file cannot trigger an XXE or SSRF.

## Parsed model (plane 1)

The low-level parser returns typed attrs models independent of the
canonical survey record:

| JobXML source | Parsed model field |
| --- | --- |
| `FieldBook/PointRecord/@ID` or child `ID` | `JxlPointRecord.point_id` |
| `FieldBook/PointRecord/@TimeStamp` | `JxlPointRecord.timestamp` |
| `FieldBook/PointRecord/Method` | `JxlPointRecord.creation_method` |
| `FieldBook/PointRecord/SurveyMethod` | `JxlPointRecord.survey_method` |
| `FieldBook/PointRecord/Precision` | `JxlPointRecord.precision` |
| `FieldBook/PointRecord/QualityControl1` | `JxlPointRecord.quality_control_1` |
| `FieldBook/PointRecord/QualityControl2` | `JxlPointRecord.quality_control_2` |
| `FieldBook/PointRecord/ECEFDeltas` | `JxlPointRecord.ecef_deltas` |
| `Reductions/Point/Grid` | `JxlPoint.grid` (`north`/`east`/`elevation` properties) |
| `Reductions/Point/WGS84` | `JxlPoint.wgs84` |
| merged field book | `JxlPoint.record` |

Unrecognized leaf elements remain in each object's `raw_values` mapping.

## Canonical mapping (plane 2)

| Typed JXL source | Canonical field |
| --- | --- |
| `JxlPoint.grid` NEH | `north` / `east` / `height` |
| `JxlPoint.wgs84` (or record fallback) | `latitude` / `longitude` / `wgs84_altitude` |
| `record.quality_control_1.start_time` | `observed_at_utc` |
| `record.precision` H/V | `hrms` / `vrms` |
| QC1 PDOP/HDOP/VDOP / satellites | `pdop` / `hdop` / `vdop` / `satellite_count` |
| SurveyMethod (`Fix` → status) + record `Method` | `status` + `method` |
| `Reductions/Point/ID` | `source_record_id` |
| `Name` / `Code` / `Description` (point or record) | `name` / `code` / `description` |

Compact trace fields (`SurveyMethod`, `TimeStamp`, `Method`, unrecognized
field-book extras) are kept in `source_values`.

`KeyedIn` points (manually entered, not measured GPS observations) are
excluded by default. Pass `include_keyed_in=True` to keep them.

A point whose Grid coordinates are missing or non-numeric is skipped and
reported as a `WARNING` parse issue instead of becoming a zero-valued
point.

## Usage

```python
from siscadro_jxl import extract_points, export_to_xlsx, export_to_database

# Canonical records only, in memory.
result = extract_points("job.jxl")
for record in result.records:
    print(record.name, record.north, record.east, record.height)

# One JXL file to one XLSX workbook.
export_to_xlsx("job.jxl", "job.xlsx")

# One JXL file into a canonical SQLite database, transforming projected
# coordinates with the given source CRS when the file has no EPSG hint.
export_to_database("job.jxl", "survey.sqlite3", source_crs="EPSG:3844")
```

Lower-level access is also available for callers that only need the raw
JXL structure, without going through the canonical survey model:

```python
from siscadro_jxl.parser import JxlParser

result = JxlParser().parse_file("job.jxl")
for point in result.points:
    print(point.name, point.north, point.east, point.elevation, point.method)
```

## Development

```bash
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e "..\siscadro-survey"
python -m pip install -e ".[dev]"
pre-commit install
```

Run formatting, linting, type checking, and tests:

```bash
make delint
make lint
make typecheck
make test
```
