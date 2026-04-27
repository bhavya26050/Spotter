from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import geonamescache

from django.conf import settings


class RoutePlanningError(Exception):
    pass


@dataclass(frozen=True)
class Coordinate:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class FuelStation:
    station_id: str
    name: str
    address: str
    city: str
    state: str
    latitude: float
    longitude: float
    price_per_gallon: float


@dataclass(frozen=True)
class RouteNode:
    node_id: str
    node_type: str
    label: str
    coordinate: Coordinate
    route_position_miles: float
    price_per_gallon: float | None = None
    distance_from_route_miles: float = 0.0


_COORDINATE_PATTERN = re.compile(r"^\s*(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)\s*$")
_WHITESPACE_PATTERN = re.compile(r"\s+")

CANADIAN_PROVINCE_ALIASES = {
    "ab": "01",
    "bc": "02",
    "mb": "03",
    "nb": "04",
    "nl": "05",
    "ns": "07",
    "nt": "13",
    "nu": "14",
    "on": "08",
    "pe": "09",
    "qc": "10",
    "sk": "11",
    "yt": "12",
}

CANADIAN_ADMIN1_TO_PROVINCE = {admin1: province for province, admin1 in CANADIAN_PROVINCE_ALIASES.items()}


def plan_route(start: str, finish: str) -> dict:
    start_coordinate = resolve_location(start)
    finish_coordinate = resolve_location(finish)

    route = fetch_route(start_coordinate, finish_coordinate)
    stations = load_fuel_stations()
    route_nodes = build_route_nodes(route["coordinates"], stations)
    plan = solve_fuel_path(
        route_nodes,
        route["distance_miles"],
        route["duration_seconds"],
        route["coordinates"][-1],
    )

    return {
        "input": {"start": start, "finish": finish},
        "start": coordinate_payload(start, start_coordinate),
        "finish": coordinate_payload(finish, finish_coordinate),
        "route": {
            "distance_miles": round(route["distance_miles"], 2),
            "duration_minutes": round(route["duration_seconds"] / 60, 1),
            "map": {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": route["coordinates"]},
                "properties": {
                    "source": "OpenStreetMap OSRM",
                    "start": start,
                    "finish": finish,
                },
            },
        },
        "fuel_plan": plan["stops"],
        "summary": {
            "total_fuel_cost": round(plan["total_cost"], 2),
            "gallons_purchased": round(plan["total_gallons"], 2),
            "tank_range_miles": 500,
            "fuel_efficiency_mpg": 10,
            "stops_required": len(plan["stops"]),
        },
        "assumptions": [
            "The trip starts with a full tank, so the initial 500 miles do not add trip fuel cost.",
            "Fuel stops are chosen from the provided price list and projected onto the route polyline.",
            "Costs are optimized with a forward shortest-path search over feasible stops.",
        ],
    }


@lru_cache(maxsize=256)
def resolve_location(value: str) -> Coordinate:
    coordinate = parse_coordinate(value)
    if coordinate is not None:
        return coordinate

    params = {
        "q": value,
        "format": "jsonv2",
        "limit": 1,
        "countrycodes": "us",
    }
    payload = fetch_json(
        f"{settings.NOMINATIM_BASE_URL}/search?{urlencode(params)}",
        headers={"User-Agent": "route-planner/1.0"},
    )
    if not payload:
        raise RoutePlanningError(f"Could not geocode location: {value}")

    first = payload[0]
    return Coordinate(latitude=float(first["lat"]), longitude=float(first["lon"]))


def parse_coordinate(value: str) -> Coordinate | None:
    match = _COORDINATE_PATTERN.match(value)
    if not match:
        return None
    return Coordinate(latitude=float(match.group(1)), longitude=float(match.group(2)))


@lru_cache(maxsize=64)
def load_fuel_stations() -> tuple[FuelStation, ...]:
    path = Path(settings.FUEL_PRICES_CSV)
    if not path.exists():
        raise RoutePlanningError(
            f"Fuel price file not found at {path}. Provide a CSV with station metadata and prices."
        )

    grouped_rows: dict[tuple[str, str, str, str, str], dict[str, str | float]] = {}
    with path.open(newline="", encoding="utf-8") as file_handle:
        reader = csv.DictReader(file_handle)
        required_fields = {"OPIS Truckstop ID", "Truckstop Name", "Address", "City", "State", "Rack ID", "Retail Price"}
        missing_fields = required_fields - set(reader.fieldnames or [])
        if missing_fields:
            raise RoutePlanningError(
                f"Fuel price CSV is missing required columns: {', '.join(sorted(missing_fields))}"
            )

        for row in reader:
            station_id = row["OPIS Truckstop ID"].strip()
            name = normalize_text_field(row["Truckstop Name"])
            address = normalize_text_field(row["Address"])
            city = normalize_text_field(row["City"])
            state = normalize_text_field(row["State"]).upper()
            price_per_gallon = float(row["Retail Price"])

            key = (station_id, name, address, city, state)
            existing = grouped_rows.get(key)
            if existing is None or price_per_gallon < float(existing["price_per_gallon"]):
                grouped_rows[key] = {
                    "station_id": station_id,
                    "name": name,
                    "address": address,
                    "city": city,
                    "state": state,
                    "price_per_gallon": price_per_gallon,
                }

    if not grouped_rows:
        raise RoutePlanningError("Fuel price CSV did not contain any usable rows.")

    stations: list[FuelStation] = []
    for record in grouped_rows.values():
        coordinate = resolve_station_coordinate(
            city=str(record["city"]),
            state=str(record["state"]),
            address=str(record["address"]),
            station_name=str(record["name"]),
        )
        stations.append(
            FuelStation(
                station_id=str(record["station_id"]),
                name=str(record["name"]),
                address=str(record["address"]),
                city=str(record["city"]),
                state=str(record["state"]),
                latitude=coordinate.latitude,
                longitude=coordinate.longitude,
                price_per_gallon=float(record["price_per_gallon"]),
            )
        )

    return tuple(stations)


@lru_cache(maxsize=1)
def build_city_lookup() -> dict[tuple[str, str], Coordinate]:
    cache = geonamescache.GeonamesCache()
    city_index: dict[tuple[str, str], tuple[int, Coordinate]] = {}

    for city in cache.get_cities().values():
        key = (normalize_key(str(city.get("name", ""))), normalize_key(str(city.get("admin1code", ""))))
        coordinate = Coordinate(latitude=float(city["latitude"]), longitude=float(city["longitude"]))
        population = int(city.get("population") or 0)
        existing = city_index.get(key)
        if existing is None or population > existing[0]:
            city_index[key] = (population, coordinate)

        country_code = str(city.get("countrycode", "")).upper()
        if country_code == "CA":
            province_alias = CANADIAN_ADMIN1_TO_PROVINCE.get(normalize_key(str(city.get("admin1code", ""))))
            if province_alias:
                alias_key = (normalize_key(str(city.get("name", ""))), province_alias)
                existing = city_index.get(alias_key)
                if existing is None or population > existing[0]:
                    city_index[alias_key] = (population, coordinate)

    return {key: value[1] for key, value in city_index.items()}


@lru_cache(maxsize=1)
def build_state_fallback_lookup() -> dict[str, Coordinate]:
    cache = geonamescache.GeonamesCache()
    state_index: dict[str, tuple[int, Coordinate]] = {}

    for city in cache.get_cities().values():
        state_key = normalize_key(str(city.get("admin1code", "")))
        population = int(city.get("population") or 0)
        coordinate = Coordinate(latitude=float(city["latitude"]), longitude=float(city["longitude"]))
        existing = state_index.get(state_key)
        if existing is None or population > existing[0]:
            state_index[state_key] = (population, coordinate)

        country_code = str(city.get("countrycode", "")).upper()
        if country_code == "CA":
            province_alias = CANADIAN_ADMIN1_TO_PROVINCE.get(normalize_key(str(city.get("admin1code", ""))))
            if province_alias:
                existing = state_index.get(province_alias)
                if existing is None or population > existing[0]:
                    state_index[province_alias] = (population, coordinate)

    return {key: value[1] for key, value in state_index.items()}


def resolve_station_coordinate(city: str, state: str, address: str, station_name: str) -> Coordinate:
    city_lookup = build_city_lookup()
    city_key = (normalize_key(city), normalize_key(state))
    if city_key in city_lookup:
        return city_lookup[city_key]

    state_lookup = build_state_fallback_lookup()
    state_coordinate = state_lookup.get(normalize_key(state))
    if state_coordinate is not None:
        return state_coordinate

    raise RoutePlanningError(f"Could not resolve station location for {station_name}, {city}, {state}")


def normalize_text_field(value: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", value or "").strip()


def normalize_key(value: str) -> str:
    return normalize_text_field(value).casefold()


def fetch_route(start: Coordinate, finish: Coordinate) -> dict:
    route_url = (
        f"{settings.OSRM_BASE_URL}/route/v1/driving/"
        f"{start.longitude},{start.latitude};{finish.longitude},{finish.latitude}"
        f"?overview=full&geometries=geojson&steps=false&annotations=false"
    )
    payload = fetch_json(route_url)
    routes = payload.get("routes") or []
    if not routes:
        raise RoutePlanningError("Routing API did not return a route.")

    route = routes[0]
    coordinates = [tuple(point) for point in route["geometry"]["coordinates"]]
    if len(coordinates) < 2:
        raise RoutePlanningError("Routing API returned an invalid geometry.")

    return {
        "coordinates": coordinates,
        "distance_miles": float(route["distance"]) / 1609.344,
        "duration_seconds": float(route["duration"]),
    }


def fetch_json(url: str, headers: dict[str, str] | None = None) -> dict | list:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=settings.REQUEST_TIMEOUT_SECONDS) as response:
        body = response.read().decode("utf-8")
    return json.loads(body)


def coordinate_payload(label: str, coordinate: Coordinate) -> dict:
    return {
        "label": label,
        "latitude": round(coordinate.latitude, 6),
        "longitude": round(coordinate.longitude, 6),
    }


def build_route_nodes(route_coordinates: list[tuple[float, float]], stations: Iterable[FuelStation]) -> list[RouteNode]:
    cumulative_miles = cumulative_route_miles(route_coordinates)
    nodes = [
        RouteNode(
            node_id="start",
            node_type="start",
            label="Trip start",
            coordinate=Coordinate(latitude=route_coordinates[0][1], longitude=route_coordinates[0][0]),
            route_position_miles=0.0,
            price_per_gallon=0.0,
            distance_from_route_miles=0.0,
        ),
    ]

    for station in stations:
        route_position, distance_from_route = nearest_route_position(
            route_coordinates=route_coordinates,
            cumulative_miles=cumulative_miles,
            station=station,
        )
        # Consider stations that are reasonably near the route. Increase
        # the threshold so sparse datasets still provide feasible stops.
        if distance_from_route > 100:
            continue
        nodes.append(
            RouteNode(
                node_id=station.station_id,
                node_type="fuel_stop",
                label=f"{station.name}, {station.city}, {station.state}",
                coordinate=Coordinate(latitude=station.latitude, longitude=station.longitude),
                route_position_miles=route_position,
                price_per_gallon=station.price_per_gallon,
                distance_from_route_miles=distance_from_route,
            )
        )

    nodes = sorted(nodes, key=lambda node: (node.route_position_miles, node.node_type != "start"))
    return deduplicate_nodes(nodes)


def cumulative_route_miles(route_coordinates: list[tuple[float, float]]) -> list[float]:
    cumulative = [0.0]
    for index in range(1, len(route_coordinates)):
        cumulative.append(cumulative[-1] + haversine_miles(route_coordinates[index - 1], route_coordinates[index]))
    return cumulative


def nearest_route_position(
    route_coordinates: list[tuple[float, float]],
    cumulative_miles: list[float],
    station: FuelStation,
) -> tuple[float, float]:
    best_position = 0.0
    best_distance = float("inf")

    for index in range(len(route_coordinates) - 1):
        start_point = route_coordinates[index]
        end_point = route_coordinates[index + 1]
        projected_position, projected_distance = project_onto_segment(
            point=(station.longitude, station.latitude),
            segment_start=start_point,
            segment_end=end_point,
            segment_start_miles=cumulative_miles[index],
            segment_length_miles=cumulative_miles[index + 1] - cumulative_miles[index],
        )
        if projected_distance < best_distance:
            best_distance = projected_distance
            best_position = projected_position

    return best_position, best_distance


def project_onto_segment(
    point: tuple[float, float],
    segment_start: tuple[float, float],
    segment_end: tuple[float, float],
    segment_start_miles: float,
    segment_length_miles: float,
) -> tuple[float, float]:
    point_x, point_y = lon_lat_to_local_miles(point)
    start_x, start_y = lon_lat_to_local_miles(segment_start)
    end_x, end_y = lon_lat_to_local_miles(segment_end)

    segment_dx = end_x - start_x
    segment_dy = end_y - start_y
    segment_length_squared = segment_dx * segment_dx + segment_dy * segment_dy
    if segment_length_squared == 0:
        distance = math.dist((point_x, point_y), (start_x, start_y))
        return segment_start_miles, distance

    raw_t = ((point_x - start_x) * segment_dx + (point_y - start_y) * segment_dy) / segment_length_squared
    clamped_t = max(0.0, min(1.0, raw_t))
    projected_x = start_x + clamped_t * segment_dx
    projected_y = start_y + clamped_t * segment_dy
    projected_distance = math.dist((point_x, point_y), (projected_x, projected_y))
    projected_position_miles = segment_start_miles + clamped_t * segment_length_miles
    return projected_position_miles, projected_distance


def lon_lat_to_local_miles(point: tuple[float, float]) -> tuple[float, float]:
    longitude, latitude = point
    miles_per_degree_lat = 69.172
    miles_per_degree_lon = 69.172 * math.cos(math.radians(latitude))
    return longitude * miles_per_degree_lon, latitude * miles_per_degree_lat


def deduplicate_nodes(nodes: list[RouteNode]) -> list[RouteNode]:
    deduplicated: list[RouteNode] = []
    seen_positions: set[tuple[float, str]] = set()
    for node in nodes:
        key = (round(node.route_position_miles, 3), node.node_type)
        if key in seen_positions:
            continue
        seen_positions.add(key)
        deduplicated.append(node)
    return deduplicated


def solve_fuel_path(
    nodes: list[RouteNode],
    route_distance_miles: float,
    route_duration_seconds: float,
    finish_coordinate: tuple[float, float],
) -> dict:
    reachable_nodes = nodes + [
        RouteNode(
            node_id="destination",
            node_type="finish",
            label="Trip finish",
            coordinate=Coordinate(latitude=finish_coordinate[1], longitude=finish_coordinate[0]),
            route_position_miles=route_distance_miles,
            price_per_gallon=None,
            distance_from_route_miles=0.0,
        )
    ]
    reachable_nodes = sorted(reachable_nodes, key=lambda node: node.route_position_miles)

    costs = [float("inf")] * len(reachable_nodes)
    previous = [-1] * len(reachable_nodes)
    costs[0] = 0.0

    for index, source in enumerate(reachable_nodes):
        if costs[index] == float("inf"):
            continue
        for next_index in range(index + 1, len(reachable_nodes)):
            destination = reachable_nodes[next_index]
            leg_distance = destination.route_position_miles - source.route_position_miles
            if leg_distance > 500:
                break
            edge_cost = 0.0
            if source.node_type != "start":
                edge_cost = (leg_distance / 10.0) * float(source.price_per_gallon or 0.0)
            new_cost = costs[index] + edge_cost
            if new_cost < costs[next_index]:
                costs[next_index] = new_cost
                previous[next_index] = index

    destination_index = len(reachable_nodes) - 1
    if costs[destination_index] == float("inf"):
        raise RoutePlanningError(
            "Unable to build a feasible fuel plan with the provided fuel stations and 500 mile range."
        )

    path_indexes = reconstruct_path(previous, destination_index)
    stops = build_stop_details(reachable_nodes, path_indexes)

    total_gallons = sum(stop["gallons_purchased"] for stop in stops)
    total_cost = costs[destination_index]

    return {
        "stops": stops,
        "total_gallons": total_gallons,
        "total_cost": total_cost,
        "duration_seconds": route_duration_seconds,
    }


def reconstruct_path(previous: list[int], destination_index: int) -> list[int]:
    path = []
    current = destination_index
    while current != -1:
        path.append(current)
        current = previous[current]
    return list(reversed(path))


def build_stop_details(nodes: list[RouteNode], path_indexes: list[int]) -> list[dict]:
    stops: list[dict] = []
    for position, node_index in enumerate(path_indexes[:-1]):
        source = nodes[node_index]
        destination = nodes[path_indexes[position + 1]]
        if source.node_type == "start":
            continue

        leg_distance = destination.route_position_miles - source.route_position_miles
        gallons = leg_distance / 10.0
        cost = gallons * float(source.price_per_gallon or 0.0)
        stops.append(
            {
                "sequence": len(stops) + 1,
                "station": {
                    "station_id": source.node_id,
                    "name": source.label,
                    "latitude": round(source.coordinate.latitude, 6),
                    "longitude": round(source.coordinate.longitude, 6),
                    "distance_from_route_miles": round(source.distance_from_route_miles, 2),
                    "route_position_miles": round(source.route_position_miles, 2),
                    "price_per_gallon": round(float(source.price_per_gallon or 0.0), 3),
                },
                "next_leg": {
                    "destination": destination.label,
                    "distance_miles": round(leg_distance, 2),
                    "gallons_needed": round(gallons, 2),
                },
                "gallons_purchased": round(gallons, 2),
                "cost": round(cost, 2),
            }
        )
    return stops


def haversine_miles(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
    longitude_a, latitude_a = point_a
    longitude_b, latitude_b = point_b
    radius_miles = 3958.7613
    delta_latitude = math.radians(latitude_b - latitude_a)
    delta_longitude = math.radians(longitude_b - longitude_a)
    latitude_a = math.radians(latitude_a)
    latitude_b = math.radians(latitude_b)
    haversine = (
        math.sin(delta_latitude / 2) ** 2
        + math.cos(latitude_a) * math.cos(latitude_b) * math.sin(delta_longitude / 2) ** 2
    )
    return 2 * radius_miles * math.asin(math.sqrt(haversine))
