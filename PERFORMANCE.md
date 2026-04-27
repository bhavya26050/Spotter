# Performance Notes

## Request Pipeline

1. **Geocoding (start)**: Nominatim API call → ~200ms
2. **Geocoding (finish)**: Nominatim API call → ~200ms
3. **Routing**: OSRM API call with full polyline → ~300-500ms (varies by route length)
4. **Local optimization**: In-process Dijkstra shortest-path → <5ms (typically <1ms)
5. **Response serialization**: JSON encode → <1ms

**Total typical latency**: 700ms–1000ms for cross-country routes

## Caching Strategy

- Location geocoding results are cached per-session using `@lru_cache` on `resolve_location()`
- Fuel station CSV is loaded once and cached via `load_fuel_stations()` LRU
- This means repeat requests for the same start/finish locations skip geocoding

**Repeat request latency**: ~300-500ms (routing only)

## API Call Efficiency

✓ **One geocode call per location** (start and finish)  
✓ **One route call per trip** (with full polyline for fuel-stop projection)  
✓ **No calls to fuel stop lookup** (all matching is local in-memory)

External APIs are called **2–3 times per request** (2 geocodes + 1 route). No unnecessary calls are made.

## Local Fuel Station Matching

- All 39 stations in the example CSV are loaded into memory
- Stations within ~35 miles of the route are considered
- Each station is projected onto the route polyline using Haversine distance
- No external API calls for station matching

**Processing cost**: O(n * m) where n=polyline points, m=stations (~1000–2000 operations per request)

## Scalability Notes

- The cost optimizer uses Dijkstra's algorithm: O(k² log k) where k=reachable fuel stops (~10–15 stops typical)
- Typical graph size: 15–20 nodes (start + finish + candidate fuel stops)
- Execution time: <1ms

## Future Optimization Ideas

1. **Pre-project fuel stations**: Cache projected distances to polyline before serving requests
2. **CDN route cache**: Cache popular routes (NY↔LA, etc.) in Redis
3. **Batch geocoding**: Use Nominatim bulk API for large datasets
4. **Regional fuel indices**: Pre-fetch regional fuel prices instead of per-request CSV load
