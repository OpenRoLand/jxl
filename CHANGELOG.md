# Changelog

## [Unreleased]

### Added

- Initial `siscadro-jxl` package: a secure, namespace-agnostic, streaming
  `lxml`-based parser for JXL job-file (`JOBFile`) documents
  (`siscadro_jxl.parser.JxlParser`), producing the raw `JxlPoint`,
  `JxlPointRecord`, and `JxlEnvironment` models in `siscadro_jxl.models`.
  External entity resolution and DTD network access are disabled.
- `siscadro_jxl.extractor.JxlExtractor`, a canonical
  `siscadro_survey.extractors.SurveyPointExtractor` adapter registered
  under the `siscadro_survey.extractors` entry-point group as `jxl`. It
  excludes `KeyedIn` points by default (with an `include_keyed_in`
  override), merges `FieldBook/PointRecord` metadata into matching
  reduced points, resolves a coordinate reference system from the
  `Environment` section when recognizable, and reports incomplete or
  non-numeric Grid coordinates as parse issues instead of zero-valued
  points.
- Public top-level convenience functions `extract_points`,
  `export_to_xlsx`, and `export_to_database` in `siscadro_jxl`, delegating
  workbook and database mechanics to `siscadro-survey`.
- Synthetic `.jxl` fixtures (unqualified, default-namespace with
  `FieldBook`/`Environment` metadata, and mixed `KeyedIn`/measured/
  invalid-coordinate points) and a parser/extractor test suite covering
  namespace handling, streaming of multiple points, field-book merge,
  EPSG recognition, malformed XML, missing Grid values, KeyedIn
  inclusion/exclusion, and XXE/network-resolution rejection.

### Changed

### Fixed
