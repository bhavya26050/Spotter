# Route Fuel Planner

Fuel-aware routing for US road trips. Send a start and finish location, get back the route geometry, the cheapest practical fuel stops along the way, and the estimated total fuel spend.
- Django 5.2
- Nominatim for geocoding
- OSRM for routing and route geometry
- Local CSV fuel-price dataset at `data/fuel_prices.csv`

## API Flow

    A[Client / Postman] --> B[POST /api/route-plan/]
    B --> C[Geocode start with Nominatim]
    B --> D[Geocode finish with Nominatim]

## Endpoint

`POST /api/route-plan/`
Example request:

{
  "start": "Los Angeles, CA",
  "finish": "New York, NY"
}
```

Example response highlights:

- `route.map.geometry` contains the trip as GeoJSON `LineString`
- `fuel_plan` lists each chosen stop and the next leg it funds
- `summary.total_fuel_cost` shows the total trip fuel spend

## Quick Start

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py test
python manage.py runserver
```

The API will be available at `http://localhost:8000/api/route-plan/`.

## Try It in Postman

1. Open Postman
2. Click **Import** and select `Route_Fuel_Planner_API.postman_collection.json`
3. Send one of the included requests:
   - **LA to New York** — long cross-country route with multiple stops
   - **San Francisco to Las Vegas** — shorter route with one or two stops
   - **Phoenix to Denver** — mountain corridor example
   - **Chicago to Boston** — Midwest-to-Northeast example
   - **Coordinates format** — same route using `lat,lon` input

## Response Shape

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
        "coordinates": [[-118.243683, 34.052235], [..]]
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
    "total_fuel_cost": 847.5,
    "gallons_purchased": 279.75,
    "tank_range_miles": 500,
    "fuel_efficiency_mpg": 10,
    "stops_required": 5
  }
}
```

## Project Structure

- `planner/services.py` contains geocoding, routing, station matching, and fuel optimization
- `planner/views.py` exposes the API endpoint
- `planner/tests.py` covers the planner logic and the view
- `demo_api.py` demonstrates the API from the terminal
- `Route_Fuel_Planner_API.postman_collection.json` is ready for import into Postman

## Notes

- The vehicle starts with a full tank and a 500 mile maximum range.
- Fuel efficiency is fixed at 10 mpg.
- The API makes one geocoding call per endpoint side and one routing call for the trip.
- Fuel stops are selected from the CSV and projected onto the route polyline using Haversine distance.
- The optimizer uses a forward shortest-path search to minimize fuel spend under the range constraint.
- The app is wired to `data/fuel-prices-for-be-assessment.csv` and expects these columns:
  - `station_id`
  - `name`
  - `city`
  - `state`
  - `latitude`
  - `longitude`
  - `price_per_gallon`
