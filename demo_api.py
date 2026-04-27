#!/usr/bin/env python
"""
Demo script showing how to call the Route Fuel Planner API.
Run the server first: python manage.py runserver
Then run this script: python demo_api.py
"""

import json
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen


BASE_URL = "http://localhost:8000/api"

# Test routes with increasing distance
TEST_ROUTES = [
    {
        "name": "Short: San Francisco → Las Vegas",
        "start": "San Francisco, CA",
        "finish": "Las Vegas, NV",
        "description": "~570 miles. Should need 1-2 fuel stops.",
    },
    {
        "name": "Medium: Phoenix → Denver",
        "start": "Phoenix, AZ",
        "finish": "Denver, CO",
        "description": "~600 miles. Tests mountain fuel corridor.",
    },
    {
        "name": "Long: Chicago → Boston",
        "start": "Chicago, IL",
        "finish": "Boston, MA",
        "description": "~900 miles. Cross-regional route.",
    },
    {
        "name": "Epic: Los Angeles → New York",
        "start": "Los Angeles, CA",
        "finish": "New York, NY",
        "description": "~2800 miles. 5-6 fuel stops expected.",
    },
]


def test_health():
    """Check if the API is running."""
    try:
        req = Request(f"{BASE_URL}/health/")
        with urlopen(req, timeout=5) as response:
            result = json.loads(response.read().decode())
            print(f"✓ API is healthy: {result}\n")
            return True
    except (URLError, Exception) as exc:
        print(f"✗ API is not responding: {exc}")
        print("  Make sure to run: python manage.py runserver\n")
        return False


def plan_route(start: str, finish: str) -> dict:
    """Call the route planning API."""
    payload = json.dumps({"start": start, "finish": finish}).encode("utf-8")
    req = Request(
        f"{BASE_URL}/route-plan/",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode())


def display_result(route_test: dict, result: dict):
    """Pretty-print the route planning result."""
    print(f"\n{'='*70}")
    print(f"Route: {route_test['name']}")
    print(f"Description: {route_test['description']}")
    print(f"{'='*70}")

    # Summary
    route_info = result["route"]
    summary = result["summary"]
    print(f"\nRoute Summary:")
    print(f"  Distance: {route_info['distance_miles']} miles")
    print(f"  Duration: {route_info['duration_minutes']:.1f} minutes")
    print(f"  Fuel efficiency: {summary['fuel_efficiency_mpg']} mpg")
    print(f"  Tank range: {summary['tank_range_miles']} miles")

    # Fuel plan
    fuel_plan = result["fuel_plan"]
    print(f"\nFuel Plan ({len(fuel_plan)} stops):")
    for stop in fuel_plan:
        station = stop["station"]
        leg = stop["next_leg"]
        print(f"\n  Stop {stop['sequence']}: {station['name']}")
        print(f"    Position: {station['route_position_miles']} miles on route")
        print(f"    Price: ${station['price_per_gallon']:.2f}/gal")
        print(f"    → Next leg: {leg['destination']} ({leg['distance_miles']} mi)")
        print(f"    → Gallons to buy: {stop['gallons_purchased']:.1f} gal")
        print(f"    → Cost: ${stop['cost']:.2f}")

    # Total cost
    print(f"\nTotal Trip Cost:")
    print(f"  Gallons purchased: {summary['gallons_purchased']:.1f}")
    print(f"  Total fuel cost: ${summary['total_fuel_cost']:.2f}")

    # Map
    geom = route_info["map"]["geometry"]
    print(f"\nRoute Geometry:")
    print(f"  Type: {geom['type']}")
    print(f"  Points: {len(geom['coordinates'])}")
    print(f"  First point (lon, lat): {geom['coordinates'][0]}")
    print(f"  Last point (lon, lat): {geom['coordinates'][-1]}")


def main():
    print("Route Fuel Planner - API Demo")
    print("=" * 70)

    # Health check
    if not test_health():
        sys.exit(1)

    # Run test routes
    for route_test in TEST_ROUTES:
        try:
            print(f"Planning: {route_test['name']}...")
            result = plan_route(route_test["start"], route_test["finish"])
            display_result(route_test, result)
        except Exception as exc:
            print(f"✗ Error planning route: {exc}")

    print(f"\n{'='*70}")
    print("Demo complete!")


if __name__ == "__main__":
    main()
