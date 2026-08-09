# Changelog

## [Unreleased]

### Added

- ``make init`` now creates and uses a local ``venv`` (Python 3.14)
  automatically instead of installing into whatever interpreter happens to
  be active; delete ``venv/`` to force a rebuild.
- Public GitHub Actions CI workflow (``.github/workflows/ci.yml``) running
  lint, typecheck (via ``make test``), and test.
- Public release workflow (``.github/workflows/python-publish.yml``)
  publishing to PyPI on a published GitHub release (needs the
  ``PYPI_API_TOKEN`` repository secret).
- Typed JobXML models ``JxlGrid``, ``JxlWgs84``, ``JxlPrecision``,
  ``JxlGpsTime``, ``JxlQualityControl1``, ``JxlQualityControl2``, and
  ``JxlEcefDeltas``; ``JxlPointRecord`` and ``JxlPoint`` expose explicit
  nested fields instead of dumping QC/WGS84 into ``raw_values``.
- Parse Survey Pro ``PointRecord/@ID`` and ``@TimeStamp`` attributes;
  merge field-book records into ``Reductions/Point`` by ID; skip
  ``Deleted=true`` records.
- Map merged field-book quality and WGS84 onto canonical
  ``SurveyPointRecord`` (``observed_at_utc`` from QC1 GPS ``StartTime``,
  ``hrms``/``vrms``, DOPs, satellite count, lat/lon/ellipsoidal height;
  ``Fix`` SurveyMethod → ``status=FIXED`` with creation ``Method`` on
  ``method``).
- Initial `openroland-jxl` package: a secure, namespace-agnostic, streaming
  `lxml`-based parser for JXL job-file (`JOBFile`) documents
  (`openroland_jxl.parser.JxlParser`), producing the raw `JxlPoint`,
  `JxlPointRecord`, and `JxlEnvironment` models in `openroland_jxl.models`.
  External entity resolution and DTD network access are disabled.
- `openroland_jxl.extractor.JxlExtractor`, a canonical
  `openroland_survey.extractors.SurveyPointExtractor` adapter registered
  under the `openroland_survey.extractors` entry-point group as `jxl`. It
  excludes `KeyedIn` points by default (with an `include_keyed_in`
  override), merges `FieldBook/PointRecord` metadata into matching
  reduced points, resolves a coordinate reference system from the
  `Environment` section when recognizable, and reports incomplete or
  non-numeric Grid coordinates as parse issues instead of zero-valued
  points.
- Public top-level convenience functions `extract_points`,
  `export_to_xlsx`, and `export_to_database` in `openroland_jxl`, delegating
  workbook and database mechanics to `openroland-survey-core`.
- Synthetic `.jxl` fixtures (unqualified, default-namespace with
  `FieldBook`/`Environment` metadata, and mixed `KeyedIn`/measured/
  invalid-coordinate points) and a parser/extractor test suite covering
  namespace handling, streaming of multiple points, field-book merge,
  EPSG recognition, malformed XML, missing Grid values, KeyedIn
  inclusion/exclusion, and XXE/network-resolution rejection.

### Changed

- JXL extractor maps measured ``SurveyMethod`` quality tokens onto
  ``status`` (``Fix``/``NetworkFix`` → ``FIXED``, ``Float``/``NetworkFloat``
  → ``FLOAT``) and clears ``method``. Coord-only ``Code`` becomes
  ``kind=imported`` with null method and status. Base / reference-station
  tokens (``Base``, ``Base Station``, ``Reference``, …) become
  ``kind=base`` with null method/status, matching RW5 base-setup Type.
  Raw ``SurveyMethod`` remains in ``source_values``.
- JXL parser logs a DEBUG summary after a successful parse
  (``parsed N survey points from path``), matching Cube/RW5.
