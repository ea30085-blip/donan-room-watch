from __future__ import annotations

import csv
import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scraper import parse_availability  # noqa: E402
from storage import (  # noqa: E402
    HISTORY_FIELDS,
    StorageError,
    build_latest,
    load_room_master,
    save_observation,
    validate_observation,
    validate_room_master,
)

FIXTURES = Path(__file__).parent / "fixtures"
OBSERVED_AT = "2026-09-02T03:00:00+09:00"


def small_master() -> list[dict[str, str]]:
    return [
        {"room": "101", "type": "A"},
        {"room": "213", "type": "D"},
        {"room": "516", "type": "E"},
    ]


def observation(
    rooms: list[dict[str, str]] | None = None,
    *,
    observed_at: str = OBSERVED_AT,
    preparing_count: int = 0,
) -> dict[str, object]:
    available = rooms if rooms is not None else [
        {"room": "516", "type": "E"},
        {"room": "213", "type": "D"},
    ]
    return {
        "observed_at": observed_at,
        "available_count": len(available),
        "preparing_count": preparing_count,
        "rooms": available,
    }


def write_master(path: Path, rooms: list[dict[str, str]] | None = None) -> None:
    path.write_text(
        json.dumps({"rooms": rooms if rooms is not None else small_master()}),
        encoding="utf-8",
    )


def test_official_room_master_has_50_valid_unique_sorted_rooms() -> None:
    master = load_room_master(ROOT / "config" / "rooms.json")

    assert len(master) == 50
    assert len({entry["room"] for entry in master}) == 50
    assert all(len(entry["room"]) == 3 and entry["room"].isdigit() for entry in master)
    assert all(entry["type"] for entry in master)
    assert [entry["room"] for entry in master] == sorted(
        (entry["room"] for entry in master), key=int
    )


@pytest.mark.parametrize(
    ("rooms", "message"),
    [
        ([{"room": "101", "type": "A"}, {"room": "101", "type": "A"}], "重複"),
        ([{"room": "10A", "type": "A"}], "3桁"),
        ([{"room": "101", "type": ""}], "type"),
    ],
)
def test_invalid_room_master_is_rejected(
    rooms: list[dict[str, str]], message: str
) -> None:
    with pytest.raises(StorageError, match=message):
        validate_room_master(rooms)


def test_phase1_fixture_matches_official_room_master() -> None:
    html = (FIXTURES / "available.html").read_text(encoding="utf-8")
    parsed = parse_availability(
        html, datetime(2026, 9, 2, 3, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
    )
    master = load_room_master(ROOT / "config" / "rooms.json")

    validate_observation(parsed, master)


def test_latest_contains_every_room_with_status_and_sorted_order() -> None:
    latest = build_latest(observation(), small_master())

    assert latest["total_rooms"] == 3
    assert latest["available_rooms"] == ["213", "516"]
    assert latest["rooms"] == [
        {"room": "101", "type": "A", "status": "not_available"},
        {"room": "213", "type": "D", "status": "available"},
        {"room": "516", "type": "E", "status": "available"},
    ]


def test_history_initial_creation_has_one_header_and_one_observation(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "rooms.json"
    latest_path = tmp_path / "data" / "latest.json"
    history_path = tmp_path / "data" / "history.csv"
    write_master(master_path)

    latest, appended = save_observation(
        observation(), master_path, latest_path, history_path
    )

    assert appended is True
    assert json.loads(latest_path.read_text(encoding="utf-8")) == latest
    lines = history_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(HISTORY_FIELDS)
    assert len(lines) == 2
    with history_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [
        {
            "observed_at": OBSERVED_AT,
            "available_count": "2",
            "preparing_count": "0",
            "total_rooms": "3",
            "available_rooms": "213|516",
        }
    ]


def test_duplicate_observed_at_is_not_appended_and_header_stays_once(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "rooms.json"
    latest_path = tmp_path / "latest.json"
    history_path = tmp_path / "history.csv"
    write_master(master_path)

    save_observation(observation(), master_path, latest_path, history_path)
    _, appended = save_observation(
        observation(), master_path, latest_path, history_path
    )

    lines = history_path.read_text(encoding="utf-8").splitlines()
    assert appended is False
    assert len(lines) == 2
    assert lines.count(",".join(HISTORY_FIELDS)) == 1


def test_zero_available_rooms_are_saved_as_empty_csv_field(tmp_path: Path) -> None:
    master_path = tmp_path / "rooms.json"
    latest_path = tmp_path / "latest.json"
    history_path = tmp_path / "history.csv"
    write_master(master_path)

    latest, appended = save_observation(
        observation([], preparing_count=2), master_path, latest_path, history_path
    )

    assert appended is True
    assert latest["available_count"] == 0
    assert latest["available_rooms"] == []
    with history_path.open(encoding="utf-8", newline="") as handle:
        row = next(csv.DictReader(handle))
    assert row["available_rooms"] == ""


@pytest.mark.parametrize("failure", ["unknown_room", "type_mismatch", "count_mismatch"])
def test_invalid_observation_does_not_change_latest_or_history(
    tmp_path: Path, failure: str
) -> None:
    master_path = tmp_path / "rooms.json"
    latest_path = tmp_path / "latest.json"
    history_path = tmp_path / "history.csv"
    write_master(master_path)
    save_observation(observation(), master_path, latest_path, history_path)
    latest_before = latest_path.read_bytes()
    history_before = history_path.read_bytes()

    invalid = deepcopy(observation(observed_at="2026-09-02T03:05:00+09:00"))
    if failure == "unknown_room":
        invalid["rooms"] = [{"room": "999", "type": "Z"}]
        invalid["available_count"] = 1
    elif failure == "type_mismatch":
        invalid["rooms"] = [{"room": "213", "type": "E"}]
        invalid["available_count"] = 1
    else:
        invalid["available_count"] = 3

    with pytest.raises(StorageError):
        save_observation(invalid, master_path, latest_path, history_path)

    assert latest_path.read_bytes() == latest_before
    assert history_path.read_bytes() == history_before
