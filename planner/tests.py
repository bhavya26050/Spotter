from unittest.mock import patch
import time

from django.test import RequestFactory, SimpleTestCase

from .services import (
    Coordinate,
    FuelStation,
    RouteNode,
    cumulative_route_miles,
    build_route_nodes,
    nearest_route_position,
    project_onto_segment,
    solve_fuel_path,
)
from .views import RoutePlanView


class FuelPlanningTests(SimpleTestCase):
    def test_project_onto_segment_uses_midpoint_projection(self):
        route_position, distance = project_onto_segment(
            point=(5.0, 0.5),
            segment_start=(0.0, 0.0),
            segment_end=(10.0, 0.0),
            segment_start_miles=0.0,
            segment_length_miles=691.72,
        )

        self.assertAlmostEqual(route_position, 345.86, places=1)
        self.assertAlmostEqual(distance, 34.586, places=1)

    def test_nearest_route_position_prefers_closest_segment(self):
        route_coordinates = [(0.0, 0.0), (0.0, 10.0), (10.0, 10.0)]
        cumulative_miles = cumulative_route_miles(route_coordinates)
        station = FuelStation(
            station_id="1",
            name="Test Station",
            address="",
            city="",
            state="",
            latitude=10.1,
            longitude=9.0,
            price_per_gallon=3.5,
        )

        route_position, distance = nearest_route_position(route_coordinates, cumulative_miles, station)

        self.assertGreater(route_position, cumulative_miles[1])
        self.assertLess(distance, 10.0)

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


class RoutePerformanceTests(SimpleTestCase):
    def test_build_route_nodes_runs_quickly_for_short_route(self):
        route = [
            (index * 0.05, index * 0.03)
            for index in range(300)
        ]
        stations = [
            FuelStation(
                station_id=str(index),
                name=f"Station {index}",
                address="",
                city="Test City",
                state="TS",
                latitude=index * 0.03,
                longitude=index * 0.05,
                price_per_gallon=3.5 + (index % 5) * 0.01,
            )
            for index in range(200)
        ]

        start_time = time.perf_counter()
        nodes = build_route_nodes(route, stations)
        elapsed = time.perf_counter() - start_time

        self.assertLess(elapsed, 5.0)
        self.assertGreater(len(nodes), 2)
