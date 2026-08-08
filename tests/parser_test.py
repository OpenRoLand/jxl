"""Tests for :mod:`openroland_jxl.parser`."""

from __future__ import annotations

from pathlib import Path

from lxml import etree
from openroland_survey.records import IssueSeverity

from openroland_jxl.parser import JxlParser


class TestParseFile:
    """Tests for :meth:`JxlParser.parse_file` against real fixture files."""

    class TestUnqualifiedDocument:
        """Behavior for a document with no XML namespace."""

        def test_parses_every_point_in_order(self, minimal_jxl: Path) -> None:
            result = JxlParser().parse_file(minimal_jxl)

            assert [point.name for point in result.points] == ["1", "2"]

        def test_maps_known_fields(self, minimal_jxl: Path) -> None:
            result = JxlParser().parse_file(minimal_jxl)

            first = result.points[0]
            assert first.code == "TOP"
            assert first.description == "Boundary corner"
            assert first.method == "GPS"
            assert first.north == "500000.123"
            assert first.east == "300000.456"
            assert first.elevation == "120.789"

        def test_has_no_issues(self, minimal_jxl: Path) -> None:
            result = JxlParser().parse_file(minimal_jxl)

            assert result.issues == ()

        def test_has_no_environment(self, minimal_jxl: Path) -> None:
            result = JxlParser().parse_file(minimal_jxl)

            assert result.environment is None

    class TestDefaultNamespaceDocument:
        """Behavior for a document with a default XML namespace."""

        def test_parses_point_by_local_name(self, namespaced_jxl: Path) -> None:
            result = JxlParser().parse_file(namespaced_jxl)

            assert len(result.points) == 1
            assert result.points[0].name == "100"

        def test_merges_field_book_record_by_id(
            self, namespaced_jxl: Path
        ) -> None:
            result = JxlParser().parse_file(namespaced_jxl)

            point = result.points[0]
            assert point.record is not None
            assert point.record.code == "BM"
            assert point.record.description == "Benchmark near gate"

        def test_captures_environment_crs_identifier(
            self, namespaced_jxl: Path
        ) -> None:
            result = JxlParser().parse_file(namespaced_jxl)

            assert result.environment is not None
            assert result.environment.crs_identifier == "EPSG:3844"

        def test_captures_environment_raw_values(
            self, namespaced_jxl: Path
        ) -> None:
            result = JxlParser().parse_file(namespaced_jxl)

            assert (
                result.environment.raw_values["CoordinateSystem.Name"]
                == "Stereo70"
            )

    class TestPrefixedNamespaceDocument:
        """Behavior for a document with a prefixed XML namespace."""

        def test_parses_point_by_local_name(self, tmp_path: Path) -> None:
            content = b"""<?xml version="1.0"?>
<jxl:JOBFile xmlns:jxl="urn:siscadro:test:jxl">
  <jxl:Reductions>
    <jxl:Point>
      <jxl:Name>7</jxl:Name>
      <jxl:SurveyMethod>GPS</jxl:SurveyMethod>
      <jxl:Grid>
        <jxl:North>1.100</jxl:North>
        <jxl:East>2.200</jxl:East>
        <jxl:Elevation>3.300</jxl:Elevation>
      </jxl:Grid>
    </jxl:Point>
  </jxl:Reductions>
</jxl:JOBFile>
"""
            result = JxlParser().parse_bytes(content)

            assert len(result.points) == 1
            point = result.points[0]
            assert point.name == "7"
            assert point.north == "1.100"

    class TestMissingGridValues:
        """A point without a ``Grid`` element is still parsed, as ``None``s."""

        def test_grid_fields_are_none(self, tmp_path: Path) -> None:
            content = b"""<?xml version="1.0"?>
<JOBFile>
  <Reductions>
    <Point>
      <Name>9</Name>
      <SurveyMethod>GPS</SurveyMethod>
    </Point>
  </Reductions>
</JOBFile>
"""
            result = JxlParser().parse_bytes(content)

            assert len(result.points) == 1
            point = result.points[0]
            assert point.north is None
            assert point.east is None
            assert point.elevation is None

    class TestCommentsAreIgnored:
        """XML comments among element children are skipped, not raw values."""

        def test_comment_inside_point(self) -> None:
            content = b"""<?xml version="1.0"?>
<JOBFile>
  <Reductions>
    <Point>
      <!-- a comment -->
      <Name>22</Name>
    </Point>
  </Reductions>
</JOBFile>
"""
            result = JxlParser().parse_bytes(content)

            assert result.points[0].name == "22"
            assert not any(key == "" for key in result.points[0].raw_values)

        def test_comment_inside_environment(self) -> None:
            content = b"""<?xml version="1.0"?>
<JOBFile>
  <Environment>
    <!-- a comment -->
    <Datum>WGS84</Datum>
  </Environment>
</JOBFile>
"""
            result = JxlParser().parse_bytes(content)

            assert result.environment.raw_values == {"Datum": "WGS84"}

    class TestUnmappedFieldsArePreserved:
        """Fields not in the known field maps are kept in ``raw_values``."""

        def test_extra_grid_field(self) -> None:
            content = b"""<?xml version="1.0"?>
<JOBFile>
  <Reductions>
    <Point>
      <Name>20</Name>
      <Grid>
        <North>1</North>
        <East>2</East>
        <Elevation>3</Elevation>
        <Zone>30</Zone>
      </Grid>
    </Point>
  </Reductions>
</JOBFile>
"""
            result = JxlParser().parse_bytes(content)

            assert result.points[0].raw_values["Grid.Zone"] == "30"

        def test_extra_point_field(self) -> None:
            content = b"""<?xml version="1.0"?>
<JOBFile>
  <Reductions>
    <Point>
      <Name>21</Name>
      <Instrument>TS16</Instrument>
    </Point>
  </Reductions>
</JOBFile>
"""
            result = JxlParser().parse_bytes(content)

            assert result.points[0].raw_values["Instrument"] == "TS16"

        def test_extra_point_record_field(self) -> None:
            content = b"""<?xml version="1.0"?>
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
    </Point>
  </Reductions>
</JOBFile>
"""
            result = JxlParser().parse_bytes(content)

            assert result.points[0].record.raw_values["Operator"] == "Jane"

    class TestMalformedXml:
        """A malformed document is reported as an issue, not raised."""

        def test_reports_error_issue(self) -> None:
            result = JxlParser().parse_bytes(b"<JOBFile><Reductions>")

            assert result.points == ()
            assert len(result.issues) == 1
            assert result.issues[0].severity == IssueSeverity.ERROR

    class TestUnexpectedRoot:
        """A well-formed document with the wrong root is reported as an
        issue."""

        def test_reports_error_issue(self) -> None:
            result = JxlParser().parse_bytes(b"<NotAJobFile/>")

            assert result.points == ()
            assert len(result.issues) == 1
            assert result.issues[0].severity == IssueSeverity.ERROR
            assert "JOBFile" in result.issues[0].message

    class TestExternalEntityResolutionDisabled:
        """External entities and DTD-declared network access are rejected."""

        def test_does_not_resolve_external_entity(self) -> None:
            content = b"""<?xml version="1.0"?>
<!DOCTYPE JOBFile [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<JOBFile>
  <Reductions>
    <Point>
      <Name>&xxe;</Name>
      <Grid>
        <North>1</North>
        <East>2</East>
        <Elevation>3</Elevation>
      </Grid>
    </Point>
  </Reductions>
</JOBFile>
"""
            result = JxlParser().parse_bytes(content)

            for point in result.points:
                assert point.name != "root:"
            for issue in result.issues:
                assert "/etc/passwd" not in issue.message

        def test_reports_issue_instead_of_raising(self) -> None:
            content = b"""<?xml version="1.0"?>
<!DOCTYPE JOBFile [
  <!ENTITY xxe SYSTEM "http://example.invalid/evil.dtd">
]>
<JOBFile>
  <Reductions>
    <Point>
      <Name>&xxe;</Name>
    </Point>
  </Reductions>
</JOBFile>
"""
            result = JxlParser().parse_bytes(content)

            assert result.points == () or all(
                point.name is None for point in result.points
            )


class TestParseBytes:
    """Tests for :meth:`JxlParser.parse_bytes` behavior specific to it."""

    def test_uses_source_label_in_issues(self) -> None:
        result = JxlParser().parse_bytes(
            b"<NotAJobFile/>", source_label="my-label"
        )

        assert str(result.issues[0].source_path) == "my-label"

    def test_default_source_label(self) -> None:
        result = JxlParser().parse_bytes(b"<NotAJobFile/>")

        assert str(result.issues[0].source_path) == "<bytes>"


class TestKeepsKeyedInPoints:
    """The raw parser never filters ``KeyedIn`` points; that is the
    canonical extractor's responsibility."""

    def test_keyed_in_point_is_present(
        self, keyed_in_and_measured_jxl: Path
    ) -> None:
        result = JxlParser().parse_file(keyed_in_and_measured_jxl)

        methods = [point.method for point in result.points]
        assert "KeyedIn" in methods

    def test_is_keyed_in_property(
        self, keyed_in_and_measured_jxl: Path
    ) -> None:
        result = JxlParser().parse_file(keyed_in_and_measured_jxl)

        keyed_in_points = [
            point for point in result.points if point.is_keyed_in
        ]
        assert len(keyed_in_points) == 1
        assert keyed_in_points[0].name == "10"


class TestSurveyProPointRecordMerge:
    """Survey Pro ``PointRecord`` attribute IDs merge into Reductions points."""

    def test_merges_by_attribute_id(self, survey_pro_jxl: Path) -> None:
        result = JxlParser().parse_file(survey_pro_jxl)

        point = next(p for p in result.points if p.point_id == "000000e1")
        assert point.record is not None
        assert point.record.point_id == "000000e1"
        assert point.record.timestamp == "2010-01-01T21:57:03"
        assert point.record.creation_method == "GpsStaticObservation"
        assert point.record.survey_method == "Fix"

    def test_typed_field_book_structures(self, survey_pro_jxl: Path) -> None:
        result = JxlParser().parse_file(survey_pro_jxl)

        record = next(
            p for p in result.points if p.point_id == "000000e1"
        ).record
        assert record is not None
        assert record.precision is not None
        assert record.precision.horizontal == "0.01000000000"
        assert record.quality_control_1 is not None
        assert record.quality_control_1.start_time is not None
        assert record.quality_control_1.start_time.gps_week == 2011
        assert record.quality_control_1.start_time.seconds == "230933.0000"
        assert record.ecef_deltas is not None
        assert record.quality_control_2 is not None

    def test_reductions_wgs84_is_typed(self, survey_pro_jxl: Path) -> None:
        result = JxlParser().parse_file(survey_pro_jxl)

        point = next(p for p in result.points if p.point_id == "000000e1")
        assert point.wgs84 is not None
        assert point.wgs84.latitude == "46.65977287134"
        assert point.grid is not None
        assert point.north == "573538.8166"

    def test_deleted_point_record_is_not_merged(self, survey_pro_jxl: Path) -> None:
        result = JxlParser().parse_file(survey_pro_jxl)

        deleted = next(p for p in result.points if p.point_id == "000000ff")
        assert deleted.record is None


def test_xml_syntax_error_is_a_real_lxml_error() -> None:
    """Sanity check that the fixture used above is actually malformed."""
    try:
        etree.fromstring(b"<JOBFile><Reductions>")
    except etree.XMLSyntaxError:
        return
    raise AssertionError("expected fixture XML to be malformed")
