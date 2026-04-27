# Route Fuel Planner - Quick Start

## Prerequisites

- Python 3.7+
- pip

## Start the API

### Windows

```bash
run-server.bat
```

### macOS / Linux

```bash
chmod +x run-server.sh
./run-server.sh
```

### Manual start

```bash
pip install -r requirements.txt
python manage.py runserver
```

The API will be ready at `http://localhost:8000/api/route-plan/`.

## Import the Postman Collection

1. Open Postman
2. Click **Import** button
3. Select the file `Route_Fuel_Planner_API.postman_collection.json`
4. Use the pre-built requests to test various routes

## Test a Route

```bash
curl -X POST http://localhost:8000/api/route-plan/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Los Angeles, CA", "finish": "New York, NY"}'
```

## Response Includes

- **Route geometry** as GeoJSON LineString
- **Fuel stops** with costs and station details
- **Total fuel spend** for the trip
- **Route distance** and estimated duration

---

See [README.md](README.md) for full documentation.
