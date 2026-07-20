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

## Field mapping

| JXL element                         | Canonical field           |
| ------------------------------------ | -------------------------- |
| `Reductions/Point/Name` (or `FieldBook` fallback) | `name` |
| `Reductions/Point/Code` (or `FieldBook` fallback) | `code` |
| `Reductions/Point/Description1` (or `FieldBook Description` fallback) | `description` |
| `Reductions/Point/SurveyMethod`      | `method`                   |
| `Reductions/Point/Grid/North`        | `north`                    |
| `Reductions/Point/Grid/East`         | `east`                     |
| `Reductions/Point/Grid/Elevation`    | `height`                   |
| `Reductions/Point/ID`                | `source_record_id`         |

Any other value found on a point or its merged field-book record is
preserved in `source_values` (field-book values are nested under a
`field_book` key). Geographic and quality fields are left `None`: JXL
documents in this format do not provide them.

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
