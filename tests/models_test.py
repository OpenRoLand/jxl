"""Tests for :mod:`siscadro_jxl.models`."""

from __future__ import annotations

from siscadro_jxl.models import JxlEnvironment, JxlPoint, JxlPointRecord


class TestJxlPointRecordMergeKey:
    """Tests for :attr:`JxlPointRecord.merge_key`."""

    def test_prefers_point_id(self) -> None:
        record = JxlPointRecord(point_id="P1", name="1")

        assert record.merge_key == "P1"

    def test_falls_back_to_name(self) -> None:
        record = JxlPointRecord(name="1")

        assert record.merge_key == "1"

    def test_none_when_neither_is_available(self) -> None:
        record = JxlPointRecord()

        assert record.merge_key is None


class TestJxlPointMergeKey:
    """Tests for :attr:`JxlPoint.merge_key`."""

    def test_prefers_point_id(self) -> None:
        point = JxlPoint(point_id="P1", name="1")

        assert point.merge_key == "P1"

    def test_falls_back_to_name(self) -> None:
        point = JxlPoint(name="1")

        assert point.merge_key == "1"

    def test_none_when_neither_is_available(self) -> None:
        point = JxlPoint()

        assert point.merge_key is None


class TestJxlPointIsKeyedIn:
    """Tests for :attr:`JxlPoint.is_keyed_in`."""

    def test_true_for_keyed_in(self) -> None:
        assert JxlPoint(method="KeyedIn").is_keyed_in

    def test_true_case_insensitively(self) -> None:
        assert JxlPoint(method="keyedin").is_keyed_in

    def test_false_for_other_method(self) -> None:
        assert not JxlPoint(method="GPS").is_keyed_in

    def test_false_when_method_is_none(self) -> None:
        assert not JxlPoint().is_keyed_in


class TestFreezeMappingDefaults:
    """Every raw-value mapping defaults to an empty, read-only mapping."""

    def test_point_record_raw_values_default(self) -> None:
        record = JxlPointRecord(raw_values=None)

        assert dict(record.raw_values) == {}

    def test_point_raw_values_default(self) -> None:
        point = JxlPoint(raw_values=None)

        assert dict(point.raw_values) == {}

    def test_environment_raw_values_default(self) -> None:
        environment = JxlEnvironment(raw_values=None)

        assert dict(environment.raw_values) == {}
