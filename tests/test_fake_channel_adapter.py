from __future__ import annotations

from deadline_agent.adapters.fake_channel import parse_duration


def test_parse_duration_hours():
    assert parse_duration("6h") == {"hours": 6}


def test_parse_duration_combined():
    assert parse_duration("2d 3h") == {"days": 2, "hours": 3}


def test_parse_duration_no_spaces():
    assert parse_duration("1h30m") == {"hours": 1, "minutes": 30}


def test_parse_duration_case_insensitive():
    assert parse_duration("2D") == {"days": 2}


def test_parse_duration_empty_is_empty():
    assert parse_duration("") == {}
    assert parse_duration("nonsense") == {}


def test_parse_duration_repeated_unit_sums():
    assert parse_duration("1h 1h") == {"hours": 2}
