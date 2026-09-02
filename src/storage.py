"""Validate the room master and atomically persist availability observations."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOM_PATTERN = re.compile(r"^[0-9]{3}$")
HISTORY_FIELDS = [
    "observed_at",
    "available_count",
    "preparing_count",
    "total_rooms",
    "available_rooms",
]
JST_OFFSET = timedelta(hours=9)


class StorageError(Exception):
    """Raised when master validation or persistence cannot be completed safely."""


def validate_room_master(entries: Any) -> list[dict[str, str]]:
    """Return a normalized, sorted room master or raise a descriptive error."""
    if not isinstance(entries, list) or not entries:
        raise StorageError("客室マスタのroomsは空でない配列である必要があります")

    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise StorageError(f"客室マスタの要素 {index} がオブジェクトではありません")

        room = entry.get("room")
        room_type = entry.get("type")
        if not isinstance(room, str) or not ROOM_PATTERN.fullmatch(room):
            raise StorageError(
                f"客室マスタのroomが3桁の数字ではありません: {room!r}"
            )
        if room in seen:
            raise StorageError(f"客室マスタに重複したroomがあります: {room}")
        if not isinstance(room_type, str) or not room_type.strip():
            raise StorageError(f"客室マスタのroom {room} にtypeがありません")

        seen.add(room)
        normalized.append({"room": room, "type": room_type.strip()})

    return sorted(normalized, key=lambda item: int(item["room"]))


def load_room_master(path: Path) -> list[dict[str, str]]:
    """Load and validate config/rooms.json."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StorageError(f"客室マスタが見つかりません: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise StorageError(f"客室マスタを読み込めません: {path}: {exc}") from exc

    if not isinstance(document, dict) or "rooms" not in document:
        raise StorageError("客室マスタのトップレベルにrooms配列がありません")
    return validate_room_master(document["rooms"])


def _validate_observed_at(value: Any) -> str:
    if not isinstance(value, str):
        raise StorageError("observed_atが文字列ではありません")
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError as exc:
        raise StorageError(f"observed_atがISO 8601形式ではありません: {value!r}") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != JST_OFFSET:
        raise StorageError(f"observed_atが日本時間（+09:00）ではありません: {value!r}")
    return value


def validate_observation(
    observation: dict[str, Any], master: list[dict[str, str]]
) -> None:
    """Validate Phase 1 output against the room master before any write."""
    if not isinstance(observation, dict):
        raise StorageError("観測データがオブジェクトではありません")
    _validate_observed_at(observation.get("observed_at"))

    available_count = observation.get("available_count")
    preparing_count = observation.get("preparing_count")
    available = observation.get("rooms")
    if not isinstance(available_count, int) or available_count < 0:
        raise StorageError("available_countが0以上の整数ではありません")
    if not isinstance(preparing_count, int) or preparing_count < 0:
        raise StorageError("preparing_countが0以上の整数ではありません")
    if not isinstance(available, list):
        raise StorageError("観測データのroomsが配列ではありません")
    if len(available) != available_count:
        raise StorageError(
            "available_countと観測データのrooms件数が一致しません: "
            f"available_count={available_count}, rooms={len(available)}"
        )

    master_by_room = {entry["room"]: entry["type"] for entry in master}
    seen: set[str] = set()
    for entry in available:
        if not isinstance(entry, dict):
            raise StorageError("観測データのroom要素がオブジェクトではありません")
        room = entry.get("room")
        room_type = entry.get("type")
        if not isinstance(room, str) or not ROOM_PATTERN.fullmatch(room):
            raise StorageError(f"観測データのroomが3桁の数字ではありません: {room!r}")
        if room in seen:
            raise StorageError(f"観測データに重複したroomがあります: {room}")
        seen.add(room)

        expected_type = master_by_room.get(room)
        if expected_type is None:
            raise StorageError(f"観測されたroomが客室マスタに存在しません: {room}")
        if room_type != expected_type:
            raise StorageError(
                f"room {room} のtypeが客室マスタと一致しません: "
                f"observed={room_type!r}, master={expected_type!r}"
            )


def build_latest(
    observation: dict[str, Any], master: list[dict[str, str]]
) -> dict[str, Any]:
    """Build a full-room snapshot after validating observation and master."""
    normalized_master = validate_room_master(master)
    validate_observation(observation, normalized_master)
    available_rooms = sorted(
        (entry["room"] for entry in observation["rooms"]), key=int
    )
    available_set = set(available_rooms)

    return {
        "observed_at": observation["observed_at"],
        "available_count": observation["available_count"],
        "preparing_count": observation["preparing_count"],
        "total_rooms": len(normalized_master),
        "available_rooms": available_rooms,
        "rooms": [
            {
                "room": entry["room"],
                "type": entry["type"],
                "status": (
                    "available" if entry["room"] in available_set else "not_available"
                ),
            }
            for entry in normalized_master
        ],
    }


def _history_text(
    path: Path, latest: dict[str, Any]
) -> tuple[str, bool]:
    rows: list[dict[str, str]] = []
    if path.exists():
        try:
            existing = path.read_text(encoding="utf-8")
            reader = csv.DictReader(io.StringIO(existing, newline=""))
            if reader.fieldnames != HISTORY_FIELDS:
                raise StorageError(
                    f"history.csvのヘッダーが不正です: {reader.fieldnames!r}"
                )
            rows = list(reader)
        except StorageError:
            raise
        except (OSError, UnicodeError, csv.Error) as exc:
            raise StorageError(f"history.csvを読み込めません: {path}: {exc}") from exc

    observed_at = latest["observed_at"]
    appended = all(row.get("observed_at") != observed_at for row in rows)
    if appended:
        rows.append(
            {
                "observed_at": observed_at,
                "available_count": str(latest["available_count"]),
                "preparing_count": str(latest["preparing_count"]),
                "total_rooms": str(latest["total_rooms"]),
                "available_rooms": "|".join(latest["available_rooms"]),
            }
        )

    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=HISTORY_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue(), appended


def _stage_text(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            return Path(temporary.name)
    except OSError as exc:
        raise StorageError(f"一時ファイルを作成できません: {path}: {exc}") from exc


def _replace_staged(staged: dict[Path, Path]) -> None:
    originals: dict[Path, bytes | None] = {}
    replaced: list[Path] = []
    try:
        for destination in staged:
            originals[destination] = (
                destination.read_bytes() if destination.exists() else None
            )
        for destination, temporary in staged.items():
            os.replace(temporary, destination)
            replaced.append(destination)
    except OSError as exc:
        rollback_errors: list[str] = []
        for destination in reversed(replaced):
            original = originals[destination]
            try:
                if original is None:
                    destination.unlink(missing_ok=True)
                else:
                    restore = _stage_text(destination, original.decode("utf-8"))
                    os.replace(restore, destination)
            except (OSError, UnicodeError, StorageError) as rollback_exc:
                rollback_errors.append(f"{destination}: {rollback_exc}")
        detail = f"; rollback errors={rollback_errors}" if rollback_errors else ""
        raise StorageError(f"保存ファイルを安全に更新できません: {exc}{detail}") from exc
    finally:
        for temporary in staged.values():
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def save_observation(
    observation: dict[str, Any],
    master_path: Path,
    latest_path: Path,
    history_path: Path,
) -> tuple[dict[str, Any], bool]:
    """Validate, then atomically update latest.json and history.csv."""
    master = load_room_master(master_path)
    latest = build_latest(observation, master)
    history_content, appended = _history_text(history_path, latest)
    latest_content = json.dumps(latest, ensure_ascii=False, indent=2) + "\n"

    staged: dict[Path, Path] = {}
    try:
        staged[latest_path] = _stage_text(latest_path, latest_content)
        staged[history_path] = _stage_text(history_path, history_content)
    except StorageError:
        for temporary in staged.values():
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    _replace_staged(staged)
    return latest, appended
