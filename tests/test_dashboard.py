from __future__ import annotations

import json
from html.parser import HTMLParser
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
PAGES_WORKFLOW = ROOT / ".github" / "workflows" / "pages.yml"


class IdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        if attributes.get("id"):
            self.ids.append(attributes["id"])


def test_dashboard_files_and_primary_sections_exist() -> None:
    index = (WEB / "index.html").read_text(encoding="utf-8")

    assert 'name="viewport"' in index
    assert "viewport-fit=cover" in index
    assert '<html lang="ja">' in index
    assert '<main>' in index
    assert '<link rel="stylesheet" href="./styles.css?v=4.2.1">' in index
    assert '<script type="module" src="./app.js?v=4.2.1"></script>' in index
    for element_id in [
        "available-count",
        "total-rooms",
        "featured-rooms",
        "facility-filters",
        "filter-result-summary",
        "available-rooms",
        "type-summary",
        "availability-chart",
        "analysis-period-tabs",
        "analysis-summary",
        "availability-heatmap",
        "facility-insights",
        "ranking-filters",
        "room-ranking",
        "view-tabs",
        "now-panel",
        "trends-panel",
        "history-state",
        "trends-content",
        "time-view-tabs",
    ]:
        assert f'id="{element_id}"' in index

    parser = IdCollector()
    parser.feed(index)
    assert len(parser.ids) == len(set(parser.ids))
    assert (WEB / "styles.css").is_file()
    assert (WEB / "app.js").is_file()
    assert (WEB / "data-utils.js").is_file()
    assert (WEB / "facility-meta.js").is_file()
    assert (WEB / "analytics-utils.js").is_file()
    assert (WEB / "favicon.svg").is_file()


def test_dashboard_css_is_mobile_first_and_safe_area_aware() -> None:
    styles = (WEB / "styles.css").read_text(encoding="utf-8")

    assert "min-width: 320px" in styles
    assert "overflow-x: hidden" in styles
    assert "env(safe-area-inset-top)" in styles
    assert "env(safe-area-inset-bottom)" in styles
    assert "min-height: 44px" in styles
    assert "@media (min-width: 620px)" in styles
    assert ".heatmap-scroll" in styles
    assert "overflow-x: auto" in styles
    assert ".facility-chip" in styles
    assert ".facility-filter.active" in styles
    assert ".facility-filters" in styles
    assert "flex-wrap: wrap" in styles
    assert ".analysis-summary" in styles
    assert ".room-ranking" in styles
    assert "position: sticky" in styles
    assert "panel-from-right" in styles
    assert "panel-from-left" in styles


def test_dashboard_uses_same_origin_data_and_periodic_cache_busting() -> None:
    app = (WEB / "app.js").read_text(encoding="utf-8")

    assert 'latest: "./data/latest.json"' in app
    assert 'history: "./data/history.csv"' in app
    assert 'rooms: "./config/rooms.json"' in app
    assert 'cache: "no-store"' in app
    assert "Date.now()" in app
    assert 'from "./analytics-utils.js?v=4.2.1"' in app
    assert 'from "./data-utils.js?v=4.2.1"' in app
    assert "setInterval(pollLatest, 300000)" in app
    assert "raw.githubusercontent.com" not in app


def test_dashboard_data_utilities_cover_required_aggregations() -> None:
    utilities = (WEB / "data-utils.js").read_text(encoding="utf-8")

    for export_name in [
        "parseCsv",
        "parseHistory",
        "summarizeTypes",
        "tokyoDateKey",
        "todaysHistory",
        "roomTimeline",
        "roomsWithFacility",
        "filterAvailableRooms",
    ]:
        assert f"export function {export_name}" in utilities
    assert 'const JST_TIME_ZONE = "Asia/Tokyo"' in utilities
    assert 'values[4].split("|")' in utilities


def test_dashboard_history_ui_uses_rolling_analysis_and_separate_filters() -> None:
    index = (WEB / "index.html").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")

    assert "直近24時間の空室数推移" in index
    assert "AVAILABILITY INSIGHTS" in index
    assert 'data-hours="168"' in index
    assert 'data-hours="720"' in index
    assert "空室表示率" in index
    assert "実際の客室利用率や予約成功率を示すものではありません" in index
    assert "filterHistoryByRollingHours(state.history, 24, now)" in app
    assert "state.activeFacility" in app
    assert "state.rankingFacility" in app
    assert "本日の空室数推移" not in index
    assert "featured-timeline" not in index


def test_dashboard_has_accessible_now_and_trends_tabs() -> None:
    index = (WEB / "index.html").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")

    assert 'role="tablist"' in index
    assert 'id="view-now-tab"' in index
    assert 'aria-selected="true"' in index
    assert 'aria-controls="now-panel"' in index
    assert 'id="view-trends-tab"' in index
    assert 'aria-selected="false"' in index
    assert 'aria-controls="trends-panel"' in index
    assert 'id="trends-panel"' in index and "hidden" in index
    assert 'role="tabpanel"' in index
    assert 'state.activeView = view' in app
    assert 'event.key === "ArrowRight"' in app
    assert 'event.key === "ArrowLeft"' in app
    assert 'event.key === "Home"' in app
    assert 'event.key === "End"' in app


def test_history_is_loaded_only_after_trends_is_requested() -> None:
    app = (WEB / "app.js").read_text(encoding="utf-8")

    assert "historyLoaded: false" in app
    assert "historyLoading: false" in app
    assert "historyRequest: null" in app
    assert 'if (view === "trends") ensureHistoryLoaded();' in app
    assert "if (state.historyLoaded && !force)" in app
    assert "if (state.historyLoading) return state.historyRequest" in app
    assert "if (state.historyLoaded) await ensureHistoryLoaded({ force: true });" in app
    assert "renderCurrentData();\n    if (state.historyLoaded)" in app
    assert 'fetchFresh(DATA_URLS.history, "text")' in app
    assert "現在の空室は表示できましたが" not in app


def test_time_trend_modes_are_independent_from_period_tabs() -> None:
    index = (WEB / "index.html").read_text(encoding="utf-8")
    app = (WEB / "app.js").read_text(encoding="utf-8")

    assert "時間帯別の空室傾向" in index
    assert 'data-time-view="evening"' in index
    assert 'data-time-view="all-day"' in index
    assert "18–24時" in index
    assert "全日" in index
    assert 'timeViewMode: "evening"' in app
    assert "state.analysisHours = Number(button.dataset.hours)" in app
    assert "state.timeViewMode = button.dataset.timeView" in app
    assert "analysis.eveningTime" in app
    assert "analysis.allDayTime" in app
    assert "cellData.bucketCount < 3" in app


def test_facility_ui_uses_central_metadata_and_accessible_filter_state() -> None:
    app = (WEB / "app.js").read_text(encoding="utf-8")
    metadata = (WEB / "facility-meta.js").read_text(encoding="utf-8")

    for key in [
        "sauna",
        "karaoke",
        "bath_tv",
        "massage_chair",
        "collagen_machine",
        "blower_bath",
        "rainbow_blower_bath",
    ]:
        assert f"{key}:" in metadata
    assert 'setAttribute("aria-pressed", String(isActive))' in app
    assert 'className = "facility-chips"' in app
    assert 'className = "facility-chip"' in app
    assert "renderFacilityFilters();" in app


def test_current_public_data_matches_dashboard_contract() -> None:
    latest = json.loads((ROOT / "data" / "latest.json").read_text(encoding="utf-8"))
    rooms = json.loads((ROOT / "config" / "rooms.json").read_text(encoding="utf-8"))["rooms"]

    assert latest["total_rooms"] == len(rooms) == 50
    assert latest["available_count"] == len(latest["available_rooms"])
    assert {room["room"] for room in rooms}.issuperset({"611", "612", "615"})
    assert [room["room"] for room in latest["rooms"]] == sorted(
        (room["room"] for room in latest["rooms"]), key=int
    )


def test_pages_workflow_builds_same_origin_artifact_with_minimum_permissions() -> None:
    text = PAGES_WORKFLOW.read_text(encoding="utf-8")
    workflow = yaml.load(text, Loader=yaml.BaseLoader)

    triggers = workflow["on"]
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["push"]["paths"] == [
        "web/**",
        "data/**",
        "config/**",
        ".github/workflows/pages.yml",
    ]
    assert "workflow_dispatch" in triggers
    assert triggers["workflow_run"]["workflows"] == ["Collect room availability"]
    assert triggers["workflow_run"]["types"] == ["completed"]
    assert workflow["permissions"] == {}
    assert workflow["concurrency"] == {
        "group": "github-pages",
        "cancel-in-progress": "true",
    }

    build = workflow["jobs"]["build"]
    deploy = workflow["jobs"]["deploy"]
    assert build["permissions"] == {"contents": "read"}
    assert deploy["permissions"] == {"pages": "write", "id-token": "write"}
    assert build["if"] == "github.event_name != 'workflow_run' || github.event.workflow_run.conclusion == 'success'"
    assert build["steps"][0]["uses"] == "actions/checkout@v6"
    assert build["steps"][1]["uses"] == "actions/configure-pages@v6"
    assert build["steps"][3]["uses"] == "actions/upload-pages-artifact@v5"
    assert build["steps"][3]["with"]["path"] == "_site"
    assert deploy["steps"][0]["uses"] == "actions/deploy-pages@v5"

    assemble = build["steps"][2]["run"]
    assert "cp -R web/. _site/" in assemble
    assert "cp data/latest.json data/history.csv _site/data/" in assemble
    assert "cp config/rooms.json _site/config/" in assemble
    assert "PAT" not in text
    assert "force" not in text.lower()
