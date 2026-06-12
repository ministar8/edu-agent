from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import TestCase

from app.services.tracking_query_service import _aggregate_daily_points, _format_time_ago, _history_point


class TrackingQueryServiceTests(TestCase):
    def test_format_time_ago(self) -> None:
        self.assertEqual(_format_time_ago(0), "刚刚")
        self.assertEqual(_format_time_ago(0.5), "30分钟前")
        self.assertEqual(_format_time_ago(3), "3小时前")
        self.assertEqual(_format_time_ago(48), "2天前")

    def test_history_point_maps_labels(self) -> None:
        row = SimpleNamespace(
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            mastery=0.4567,
            confidence=0.8912,
            effective_score=0.3219,
            delta=-0.126,
            event_type="quiz_wrong",
            source="quiz",
        )

        point = _history_point(row)

        self.assertEqual(point["event_label"], "练习错误")
        self.assertEqual(point["source"], "练习")
        self.assertEqual(point["mastery"], 0.457)

    def test_aggregate_daily_points_groups_rows(self) -> None:
        rows = [
            SimpleNamespace(created_at=datetime(2026, 1, 1, 1, tzinfo=timezone.utc), mastery=0.2, effective_score=0.1, event_type="a"),
            SimpleNamespace(created_at=datetime(2026, 1, 1, 2, tzinfo=timezone.utc), mastery=0.4, effective_score=0.3, event_type="b"),
        ]

        points = _aggregate_daily_points(rows)

        self.assertEqual(points, [{
            "date": "2026-01-01",
            "avg_mastery": 0.3,
            "avg_effective_score": 0.2,
            "event_count": 2,
            "event_types": ["a", "b"],
        }])
