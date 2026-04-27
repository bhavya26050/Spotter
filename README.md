# Route Fuel Planner

A Django API that accepts a US start and finish location, fetches a route from OpenStreetMap's public OSRM service, and computes cost-aware refueling stops using a local fuel-price CSV.

## What it uses

- Django for the API
- Nominatim for geocoding free-form US locations
- OSRM for routing and route geometry
- A CSV fuel-price file stored at `data/fuel_prices.csv`

## Endpoint

`POST /api/route-plan/`

Example request:

```json
{
  "start": "Los Angeles, CA",
  "finish": "New York, NY"
}
```

Example response fields:

- `route.map.geometry` contains the route as GeoJSON
- `fuel_plan` lists each chosen fuel stop and the gallons/cost for the next leg
- `summary.total_fuel_cost` returns the total trip fuel spend

## Run locally

### Install and start

```bash
pip install -r requirements.txt
python manage.py check
python manage.py test
python manage.py runserver
```

The API will be available at `http://localhost:8000/api/route-plan/`.

### Demo with Postman

1. Open Postman
2. Click **Import** and select `Route_Fuel_Planner_API.postman_collection.json`
3. Use the included requests to test:
   - **LA to New York** — 2800+ mile cross-country route with 5–6 stops
   - **San Francisco to Las Vegas** — 570 mile route with 1–2 stops
   - **Phoenix to Denver** — 600 mile mountain route
   - **Chicago to Boston** — 900 mile Midwest-to-Northeast route
   - **Coordinates format** — Same LA-to-NYC using lat,lon instead of city names

Each request returns the route geometry (GeoJSON), chosen fuel stops, gallons needed, costs per stop, and total trip fuel spend.

## Response structure

```json
{
  "input": {
    "start": "Los Angeles, CA",
    "finish": "New York, NY"
  },
  "start": {
    "label": "Los Angeles, CA",
    "latitude": 34.052235,
    "longitude": -118.243683
  },
  "finish": {
    "label": "New York, NY",
    "latitude": 40.712776,
    "longitude": -74.005974
  },
  "route": {
    "distance_miles": 2799.23,
    "duration_minutes": 2444.5,
    "map": {
      "type": "Feature",
      "geometry": {
        "type": "LineString",
        "coordinates": [[-118.243683, 34.052235], ...]
      }
    }
  },
  "fuel_plan": [
    {
      "sequence": 1,
      "station": {
        "station_id": "az_phx_001",
        "name": "Valley Fuel, Phoenix, AZ",
        "latitude": 33.4484,
        "longitude": -112.074,
        "route_position_miles": 312.45,
        "price_per_gallon": 4.19
      },
      "next_leg": {
        "destination": "Trip finish",
        "distance_miles": 287.32,
        "gallons_needed": 28.73
      },
      "gallons_purchased": 28.73,
      "cost": 120.32
    }
  ],
  "summary": {
    "total_fuel_cost": 847.50,
    "gallons_purchased": 279.75,
    "tank_range_miles": 500,
    "fuel_efficiency_mpg": 10,
    "stops_required": 5
  }
}
```

## Notes

- The vehicle is modeled as starting with a full tank and a 500 mile maximum range.
- Fuel efficiency is fixed at 10 mpg.
- The API makes only **one geocoding call per endpoint** (start and finish) and **one routing call** for the trip.
- Fuel stops are selected from the provided CSV and projected onto the route polyline using Haversine distance.
- The cost optimizer uses a forward shortest-path search to minimize fuel spend subject to the 500-mile range constraint.
- If you have the exercise's attached fuel-price file, replace `data/fuel_prices.csv` with that file using these columns:
  - `station_id`
  - `name`
  - `city`
  - `state`
  - `latitude`
  - `longitude`
  - `price_per_gallon`
