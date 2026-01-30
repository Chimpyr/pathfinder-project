# Docker Testing Guide

> Testing the async graph building pipeline with Docker Compose.

---

## Quick Start

```bash
# Start all containers
docker-compose up --build

# Access the app
http://localhost:5000
```

---

## Container Overview

| Container | Port | Purpose |
|-----------|------|---------|
| `scenic-api` | 5000 | Flask API server |
| `scenic-worker` | - | Celery worker (4 concurrent processes) |
| `scenic-redis` | 6379 | Message broker / result backend |
| `scenic-flower` | 5555 | Monitoring UI (optional) |

---

## Testing Concurrent Workers

### Method 1: Multiple curl Commands

Open separate terminal windows and run simultaneously:

```bash
# Terminal 1 - Oxford route
curl -X POST http://localhost:5000/api/route \
  -H "Content-Type: application/json" \
  -d '{"start_lat": 51.818, "start_lon": -1.286, "end_lat": 51.804, "end_lon": -1.275}'

# Terminal 2 - Bath route
curl -X POST http://localhost:5000/api/route \
  -H "Content-Type: application/json" \
  -d '{"start_lat": 51.378, "start_lon": -2.357, "end_lat": 51.381, "end_lon": -2.359}'

# Terminal 3 - Bristol route
curl -X POST http://localhost:5000/api/route \
  -H "Content-Type: application/json" \
  -d '{"start_lat": 51.454, "start_lon": -2.587, "end_lat": 51.450, "end_lon": -2.600}'
```

### Method 2: Parallel curl with xargs

```bash
# Fire 4 requests simultaneously
echo "51.818,-1.286,51.804,-1.275
51.378,-2.357,51.381,-2.359
51.454,-2.587,51.450,-2.600
52.200,-0.120,52.210,-0.130" | \
xargs -P4 -I {} sh -c 'echo {} | tr "," "\n" | xargs printf "{\"start_lat\":%s,\"start_lon\":%s,\"end_lat\":%s,\"end_lon\":%s}" | curl -X POST http://localhost:5000/api/route -H "Content-Type: application/json" -d @-'
```

### Method 3: PowerShell (Windows)

```powershell
# Fire multiple requests in parallel
$jobs = @(
    @{start_lat=51.818; start_lon=-1.286; end_lat=51.804; end_lon=-1.275},
    @{start_lat=51.378; start_lon=-2.357; end_lat=51.381; end_lon=-2.359}
) | ForEach-Object {
    Start-Job -ScriptBlock {
        param($body)
        Invoke-RestMethod -Uri "http://localhost:5000/api/route" `
            -Method POST `
            -ContentType "application/json" `
            -Body ($body | ConvertTo-Json)
    } -ArgumentList $_
}
$jobs | Wait-Job | Receive-Job
```

---

## Monitoring

### Docker Logs

Watch all containers:
```bash
docker-compose logs -f
```

Watch worker only:
```bash
docker-compose logs -f worker
```

### Flower Dashboard (Optional)

```bash
# Start with monitoring profile
docker-compose --profile monitoring up

# Access at http://localhost:5555
```

### Verify Concurrent Processing

Look for different `ForkPoolWorker-N` IDs in logs:

```
scenic-worker  | [INFO/ForkPoolWorker-1] Starting graph build for region: oxfordshire
scenic-worker  | [INFO/ForkPoolWorker-3] Starting graph build for region: somerset
```

---

## Cache Management

### Clear All Caches

```bash
# Unix/Mac
rm app/data/cache/*.pickle

# PowerShell
Remove-Item .\app\data\cache\*.pickle
```

### Clear Bbox-Specific Caches

```bash
rm app/data/cache/*bbox*.pickle
```

### Inspect Cache Files

```bash
ls -la app/data/cache/
```

Expected naming: `{region}_{greenness}_{elevation}_bbox_{hash}_v{version}.pickle`

---

## Troubleshooting

### Issue: 202 Response After Build Complete

**Symptom**: Routes return 202 (processing) even when cache exists.

**Fix**: Cache key mismatch. Clear old caches and restart:
```bash
rm app/data/cache/*bbox*.pickle
docker-compose restart worker
```

### Issue: OOM Errors

**Symptom**: Worker killed with memory error.

**Fix**: Increase Docker memory or reduce concurrency:
```yaml
# docker-compose.yml
worker:
  command: celery -A celery_app worker --concurrency=2  # Reduce from 4
```

### Issue: Connection Refused to Redis

**Symptom**: `Error connecting to redis://redis:6379`

**Fix**: Ensure Redis container is healthy:
```bash
docker-compose ps
docker-compose restart redis
```

---

## Performance Benchmarks

After bbox clipping implementation:

| Route | Nodes | Build Time | Cache Size |
|-------|-------|------------|------------|
| Bath (5km) | 62,001 | 72s | 98 MB |
| Oxford (5km) | 65,222 | 75s | 112 MB |
| Bristol (5km) | ~60,000 | ~70s | ~100 MB |

**Before**: 1.1M nodes, 15 min build, 2GB cache per region.
