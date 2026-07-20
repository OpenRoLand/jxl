"""Tests for :mod:`siscadro_jxl.extractor` and the public convenience API."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import openpyxl
from siscadro_survey import database
from siscadro_survey.models import SurveyPoint
from siscadro_survey.records import IssueSeverity
from sqlalchemy.orm import Session

import siscadro_jxl
from siscadro_jxl.extractor import JxlExtractor


class TestJxlExtractorIdentity:
    """Tests for the extractor's protocol-facing identity attributes."""

    def test_format_name(self) -> None:
        assert JxlExtractor.format_name == "jxl"

    def test_extensions(self) -> None:
        assert JxlExtractor.extensions == (".jxl",)

    def test_can_read_matches_case_insensitively(self, tmp_path: Path) -> None:
        extractor = JxlExtractor()

        assert extractor.can_read(tmp_path / "job.JXL")
        assert extractor.can_read(tmp_path / "job.jxl")
        assert not extractor.can_read(tmp_path / "job.rw5")


class TestExtractUnqualifiedDocument:
    """Extraction of the minimal, no-namespace fixture."""

    def test_extracts_every_point(self, minimal_jxl: Path) -> None:
        result = JxlExtractor().extract(minimal_jxl)

        assert len(result.records) == 2

    def test_maps_canonical_fields(self, minimal_jxl: Path) -> None:
        result = JxlExtractor().extract(minimal_jxl)

        first = result.records[0]
        assert first.north == Decimal("500000.123")
        assert first.east == Decimal("300000.456")
        assert first.height == Decimal("120.789")
        assert first.name == "1"
        assert first.code == "TOP"
        assert first.description == "Boundary corner"
        assert first.method == "GPS"

    def test_source_metadata(self, minimal_jxl: Path) -> None:
        result = JxlExtractor().extract(minimal_jxl)

        assert result.source.source_type.value == "jxl"
        assert result.source.resolved_path == minimal_jxl.resolve()
        assert result.source.source_crs is None

    def test_has_no_issues(self, minimal_jxl: Path) -> None:
        result = JxlExtractor().extract(minimal_jxl)

        assert result.issues == ()


class TestExtractNamespacedDocument:
    """Extraction of the default-namespace fixture with field-book merge
    and Environment CRS metadata."""

    def test_merges_field_book_metadata(self, namespaced_jxl: Path) -> None:
        result = JxlExtractor().extract(namespaced_jxl)

        assert len(result.records) == 1
        record = result.records[0]
        assert record.code == "BM"
        assert record.description == "Benchmark near gate"

    def test_source_crs_from_environment(self, namespaced_jxl: Path) -> None:
        result = JxlExtractor().extract(namespaced_jxl)

        assert result.source.source_crs == "EPSG:3844"

    def test_source_record_id(self, namespaced_jxl: Path) -> None:
        result = JxlExtractor().extract(namespaced_jxl)

        assert result.records[0].source_record_id == "P100"


class TestExtractKeyedInAndMeasured:
    """Extraction of the mixed KeyedIn/measured/invalid fixture."""

    def test_excludes_keyed_in_by_default(
        self, keyed_in_and_measured_jxl: Path
    ) -> None:
        result = JxlExtractor().extract(keyed_in_and_measured_jxl)

        names = [record.name for record in result.records]
        assert "10" not in names
        assert "11" in names

    def test_includes_keyed_in_when_requested(
        self, keyed_in_and_measured_jxl: Path
    ) -> None:
        extractor = JxlExtractor(include_keyed_in=True)
        result = extractor.extract(keyed_in_and_measured_jxl)

        names = [record.name for record in result.records]
        assert "10" in names

    def test_skips_non_numeric_coordinate_with_warning(
        self, keyed_in_and_measured_jxl: Path
    ) -> None:
        result = JxlExtractor().extract(keyed_in_and_measured_jxl)

        names = [record.name for record in result.records]
        assert "12" not in names
        warnings = [
            issue
            for issue in result.issues
            if issue.severity == IssueSeverity.WARNING
        ]
        assert len(warnings) == 1
        assert warnings[0].record_id == "12"


class TestExtractPreservesFieldBookRawValues:
    """Field-book values with no canonical column land in ``source_values``."""

    def test_field_book_extras_are_nested(self, tmp_path: Path) -> None:
        source_path = tmp_path / "with_operator.jxl"
        source_path.write_bytes(b"""<?xml version="1.0"?>
<JOBFile>
  <FieldBook>
    <PointRecord>
      <ID>50</ID>
      <Operator>Jane</Operator>
    </PointRecord>
  </FieldBook>
  <Reductions>
    <Point>
      <ID>50</ID>
      <Grid>
        <North>1</North>
        <East>2</East>
        <Elevation>3</Elevation>
      </Grid>
    </Point>
  </Reductions>
</JOBFile>
""")

        result = JxlExtractor().extract(source_path)

        assert result.records[0].source_values["field_book"] == {
            "Operator": "Jane"
        }


class TestExtractMissingOrNonFiniteCoordinates:
    """A point with missing or non-finite Grid coordinates is skipped."""

    def test_missing_grid_produces_warning(self, tmp_path: Path) -> None:
        source_path = tmp_path / "no_grid.jxl"
        source_path.write_bytes(b"""<?xml version="1.0"?>
<JOBFile>
  <Reductions>
    <Point>
      <Name>30</Name>
    </Point>
  </Reductions>
</JOBFile>
""")

        result = JxlExtractor().extract(source_path)

        assert result.records == ()
        assert len(result.issues) == 1
        assert result.issues[0].severity == IssueSeverity.WARNING

    def test_non_finite_grid_value_produces_warning(
        self, tmp_path: Path
    ) -> None:
        source_path = tmp_path / "nan_grid.jxl"
        source_path.write_bytes(b"""<?xml version="1.0"?>
<JOBFile>
  <Reductions>
    <Point>
      <Name>31</Name>
      <Grid>
        <North>1</North>
        <East>NaN</East>
        <Elevation>3</Elevation>
      </Grid>
    </Point>
  </Reductions>
</JOBFile>
""")

        result = JxlExtractor().extract(source_path)

        assert result.records == ()
        assert len(result.issues) == 1
        assert result.issues[0].severity == IssueSeverity.WARNING


class TestExtractPointsConvenienceFunction:
    """Tests for the top-level :func:`siscadro_jxl.extract_points`."""

    def test_default_excludes_keyed_in(
        self, keyed_in_and_measured_jxl: Path
    ) -> None:
        result = siscadro_jxl.extract_points(keyed_in_and_measured_jxl)

        names = [record.name for record in result.records]
        assert "10" not in names

    def test_include_keyed_in_option(
        self, keyed_in_and_measured_jxl: Path
    ) -> None:
        result = siscadro_jxl.extract_points(
            keyed_in_and_measured_jxl, include_keyed_in=True
        )

        names = [record.name for record in result.records]
        assert "10" in names


class TestExportToXlsxConvenienceFunction:
    """Tests for the top-level :func:`siscadro_jxl.export_to_xlsx`."""

    def test_writes_expected_row_count(
        self, minimal_jxl: Path, tmp_path: Path
    ) -> None:
        output_path = tmp_path / "out.xlsx"

        summary = siscadro_jxl.export_to_xlsx(minimal_jxl, output_path)

        assert summary.written_row_count == 2
        assert output_path.exists()

    def test_workbook_contains_points_sheet(
        self, minimal_jxl: Path, tmp_path: Path
    ) -> None:
        output_path = tmp_path / "out.xlsx"
        siscadro_jxl.export_to_xlsx(minimal_jxl, output_path)

        workbook = openpyxl.load_workbook(output_path)
        try:
            assert "Points" in workbook.sheetnames
            assert "Source" in workbook.sheetnames
        finally:
            workbook.close()


class TestExportToDatabaseConvenienceFunction:
    """Tests for the top-level :func:`siscadro_jxl.export_to_database`."""

    def test_imports_expected_point_count(
        self, minimal_jxl: Path, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "survey.sqlite3"

        summary = siscadro_jxl.export_to_database(
            minimal_jxl, db_path, source_crs="EPSG:3844"
        )

        assert summary.unique_points_inserted == 2
        assert summary.source_count == 1

    def test_points_are_queryable_afterwards(
        self, namespaced_jxl: Path, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "survey.sqlite3"

        siscadro_jxl.export_to_database(namespaced_jxl, db_path)

        engine = database.create_engine(db_path)
        try:
            with Session(engine) as session:
                points = session.query(SurveyPoint).all()
                assert len(points) == 1
                assert points[0].code == "BM"
        finally:
            engine.dispose()

    def test_accepts_an_existing_engine(
        self, minimal_jxl: Path, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "survey.sqlite3"
        engine = database.create_engine(db_path)
        try:
            summary = siscadro_jxl.export_to_database(
                minimal_jxl, engine, source_crs="EPSG:3844"
            )
            assert summary.unique_points_inserted == 2
        finally:
            engine.dispose()
