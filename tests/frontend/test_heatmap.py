"""Unit tests for frontend callback logic (no browser required)."""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# show_date_status
# ---------------------------------------------------------------------------


class TestShowDateStatus:
    def _call(self, start: str | None, end: str | None) -> str:
        from frontend.callbacks.graph_callbacks import show_date_status

        return show_date_status(start, end)

    def test_returns_empty_when_no_dates(self) -> None:
        assert self._call(None, None) == ""

    def test_returns_empty_when_start_missing(self) -> None:
        assert self._call(None, "2020-12-31") == ""

    def test_single_day_range(self) -> None:
        result = self._call("2020-12-31", "2020-12-31")
        assert "1 days" in result
        assert "✓" in result

    def test_multi_day_range(self) -> None:
        result = self._call("2020-12-01", "2020-12-31")
        assert "31 days" in result
        assert "✓" in result

    def test_over_180_days_shows_warning(self) -> None:
        result = self._call("2020-01-01", "2020-07-30")
        assert "⚠" in result
        assert "Max allowed: 180 days" in result

    def test_exactly_180_days_is_valid(self) -> None:
        result = self._call("2020-01-01", "2020-06-28")
        assert "✓" in result


# ---------------------------------------------------------------------------
# toggle_graph_visibility
# ---------------------------------------------------------------------------


class TestToggleGraphVisibility:
    def _call(
        self,
        clicked_data: dict | None,
        close_clicks: int | None,
        trigger: str,
        render_clicks: int | None = None,
    ) -> dict:
        mock_ctx = MagicMock()
        mock_ctx.triggered = [{"prop_id": f"{trigger}.n_clicks"}]

        with patch("frontend.callbacks.graph_callbacks.callback_context", mock_ctx):
            from frontend.callbacks.graph_callbacks import toggle_graph_visibility

            return toggle_graph_visibility(clicked_data, close_clicks, render_clicks)

    def test_close_button_hides_graph(self) -> None:
        result = self._call({"lat": 1.0, "lon": 2.0}, 1, "close-graph-btn")
        assert result["height"] == "0%"
        assert result["display"] == "none"

    def test_render_button_hides_graph(self) -> None:
        result = self._call({"lat": 1.0, "lon": 2.0}, None, "render-btn", 1)
        assert result["height"] == "0%"
        assert result["display"] == "none"

    def test_coordinate_click_shows_graph(self) -> None:
        result = self._call({"lat": 1.0, "lon": 2.0}, None, "clicked-coordinate")
        assert result["height"] == "32%"
        assert result["display"] == "block"

    def test_no_data_hides_graph(self) -> None:
        result = self._call(None, None, "clicked-coordinate")
        assert result["height"] == "0%"
        assert result["display"] == "none"

    def test_returns_all_required_style_keys(self) -> None:
        result = self._call({"lat": 1.0, "lon": 2.0}, None, "clicked-coordinate")
        for key in (
            "borderTop",
            "background",
            "padding",
            "overflow",
            "transition",
            "position",
        ):
            assert key in result


# ---------------------------------------------------------------------------
# update_timeseries_graph — edge cases that don't need a live API
# ---------------------------------------------------------------------------


class TestUpdateTimeseriesGraph:
    def _call(self, clicked_coord: dict | None, raster_trigger: dict | None):  # type: ignore[no-untyped-def]
        from frontend.callbacks.graph_callbacks import update_timeseries_graph

        return update_timeseries_graph(clicked_coord, raster_trigger)

    def test_returns_empty_figure_when_no_coord(self) -> None:
        import plotly.graph_objects as go

        fig = self._call(None, {"date": "2020-12-31", "tempType": "mean"})
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 0

    def test_returns_empty_figure_when_no_trigger(self) -> None:
        import plotly.graph_objects as go

        fig = self._call({"lat": 0.0, "lon": 0.0}, None)
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 0

    def test_returns_error_figure_on_api_failure(self) -> None:
        import plotly.graph_objects as go
        import requests

        with patch("frontend.callbacks.graph_callbacks.requests.get") as mock_get:
            mock_get.side_effect = requests.ConnectionError("backend offline")
            fig = self._call(
                {"lat": 52.0, "lon": 5.0},
                {
                    "date": "2020-12-31",
                    "dateRange": {"start": "2020-12-30", "end": "2020-12-31"},
                    "tempType": "mean",
                },
            )
        assert isinstance(fig, go.Figure)
        assert any("Error" in str(ann.text) for ann in fig.layout.annotations)

    def test_successful_api_response_builds_figure(self) -> None:
        from unittest.mock import MagicMock

        import plotly.graph_objects as go

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "data": [
                {"date": "2020-12-30", "value": 275.15},
                {"date": "2020-12-31", "value": 278.15},
            ]
        }

        with patch(
            "frontend.callbacks.graph_callbacks.requests.get",
            return_value=mock_response,
        ):
            fig = self._call(
                {"lat": 52.0, "lon": 5.0},
                {
                    "date": "2020-12-30",
                    "dateRange": {"start": "2020-12-30", "end": "2020-12-31"},
                    "tempType": "mean",
                },
            )

        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 1
        # Values converted from K to °C
        assert list(fig.data[0].y) == pytest.approx([275.15 - 273.15, 278.15 - 273.15])
