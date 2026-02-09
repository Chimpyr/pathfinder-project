# Useful Docker Commands

## Build and Run

```bash
docker-compose up --build
```

## Show all running containers

```bash
docker ps
```

## Restart a container

```bash
docker restart <container_name>
```

## Restart a SERVICE

```bash
docker-compose restart <service_name>
```

e.g., `docker-compose restart api`
Given: 
```
NAME            IMAGE                     COMMAND                  SERVICE   CREATED          STATUS                    PORTS
scenic-api      scenicpathfinder-api      "python run.py"          api       54 minutes ago   Up 54 minutes             0.0.0.0:5000->5000/tcp, [::]:5000->5000/tcp
scenic-redis    redis:7-alpine            "docker-entrypoint.s…"   redis     8 days ago       Up 54 minutes (healthy)   0.0.0.0:6379->6379/tcp, [::]:6379->6379/tcp
scenic-worker   scenicpathfinder-worker   "celery -A celery_ap…"   worker    54 minutes ago   Up 54 minutes             5000/tcp
```

## Look at logs

```bash
docker compose logs worker | Select-String "TILE:"
```
or all logs from all containers

```bash
docker compose logs
```

## Clear cache

```bash
docker compose exec api rm -rf /app/app/data/cache/*
```

## Attach container to terminal console

```bash
docker attach <container_name>
or
docker container attach <container_name>
```

## Detach container from terminal console

```bash
docker detach <container_name>
```