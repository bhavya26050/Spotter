from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from .services import Coordinate, RouteNode, solve_fuel_path
from .views import RoutePlanView


class FuelPlanningTests(SimpleTestCase):
    def test_solver_prefers_cheaper_reachable_stop(self):
        nodes = [
            RouteNode(
                node_id="start",
                node_type="start",
                label="Trip start",
                coordinate=Coordinate(latitude=0.0, longitude=0.0),
                route_position_miles=0.0,
                price_per_gallon=0.0,
            ),
            RouteNode(
                node_id="expensive",
                node_type="fuel_stop",
                label="Expensive Stop",
                coordinate=Coordinate(latitude=0.0, longitude=1.0),
                route_position_miles=200.0,
                price_per_gallon=5.0,
            ),
            RouteNode(
                node_id="cheap",
                node_type="fuel_stop",
                label="Cheap Stop",
                coordinate=Coordinate(latitude=0.0, longitude=2.0),
                route_position_miles=450.0,
                price_per_gallon=3.0,
            ),
        ]

        result = solve_fuel_path(nodes, 600.0, 3600.0, (0.0, 3.0))

        self.assertEqual(len(result["stops"]), 1)
        self.assertEqual(result["stops"][0]["station"]["station_id"], "cheap")
        self.assertAlmostEqual(result["total_cost"], 45.0, places=2)

    def test_solver_supports_multiple_required_stops(self):
        nodes = [
            RouteNode(
                node_id="start",
                node_type="start",
                label="Trip start",
                coordinate=Coordinate(latitude=0.0, longitude=0.0),
                route_position_miles=0.0,
                price_per_gallon=0.0,
            ),
            RouteNode(
                node_id="first",
                node_type="fuel_stop",
                label="First Stop",
                coordinate=Coordinate(latitude=0.0, longitude=1.0),
                route_position_miles=300.0,
                price_per_gallon=5.0,
            ),
            RouteNode(
                node_id="second",
                node_type="fuel_stop",
                label="Second Stop",
                coordinate=Coordinate(latitude=0.0, longitude=2.0),
                route_position_miles=700.0,
                price_per_gallon=3.0,
            ),
        ]

        result = solve_fuel_path(nodes, 900.0, 5400.0, (0.0, 3.0))

        self.assertEqual(len(result["stops"]), 2)
        self.assertEqual([stop["station"]["station_id"] for stop in result["stops"]], ["first", "second"])
        self.assertAlmostEqual(result["total_cost"], 260.0, places=2)


class RoutePlanViewTests(SimpleTestCase):
    def test_route_plan_view_returns_json(self):
        factory = RequestFactory()
        request = factory.post(
            "/api/route-plan/",
            data='{"start": "A", "finish": "B"}',
            content_type="application/json",
        )

        with patch("planner.views.plan_route") as mocked_plan_route:
            mocked_plan_route.return_value = {"ok": True}
            response = RoutePlanView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {"ok": True})
