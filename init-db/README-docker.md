# Docker DB Setup — Crime Analytics Platform

## Files
```
docker-compose.yml
init-db/01-init.sql       # auto-runs on first boot: enables PostGIS, creates schema
generate_mock_data.py     # seeds the DB once it's up
```

## 1. Start the database
```bash
docker compose up -d db
```
First boot takes a few extra seconds — Postgres runs `init-db/01-init.sql` automatically,
enabling PostGIS and creating `accused`, `case_master`, `act_section_association`.

Check it's healthy:
```bash
docker compose ps
# STATUS column should say "healthy"
```

## 2. (Optional) Start pgAdmin for a GUI
```bash
docker compose --profile tools up -d pgadmin
```
Open http://localhost:5050 → login `admin@local.dev` / `devpass` →
add a server pointing at host `db`, port `5432`, db `crimedb`, user `crime_admin`, pass `devpass`.
(Use `db` as the host, not `localhost` — pgAdmin is on the same Docker network.)

## 3. Seed with mock data
```bash
pip install faker numpy pandas sqlalchemy psycopg2-binary --break-system-packages

python generate_mock_data.py --num-cases 1000 \
  --postgres "postgresql://crime_admin:devpass@localhost:5432/crimedb"
```

## 4. Verify
```bash
docker exec -it crime-db psql -U crime_admin -d crimedb -c "SELECT COUNT(*) FROM case_master;"
docker exec -it crime-db psql -U crime_admin -d crimedb -c \
  "SELECT \"CrimeMinorHead\", COUNT(*) FROM case_master GROUP BY 1 ORDER BY 2 DESC;"
```

## Common issues
- **Port 5432 already in use** — you likely have a local Postgres running. Either stop it
  or change the left side of the port mapping in `docker-compose.yml`, e.g. `"5433:5432"`
  (and update your connection string to match).
- **Schema changes not applying** — `init-db/*.sql` only runs on a *fresh* volume. If you
  edit `01-init.sql` after the first run, wipe and reinit:
  ```bash
  docker compose down -v && docker compose up -d db
  ```
- **`psycopg2` install fails on macOS/Apple Silicon** — use `psycopg2-binary`, not `psycopg2`
  (already what's listed above).
- **FastAPI backend can't reach the DB** — if your backend also runs in Docker, use the
  service name `db` as the host instead of `localhost` (they share the Docker network
  Compose creates automatically). If your backend runs on your host machine directly
  (e.g. `uvicorn` outside Docker), use `localhost:5432` as shown above.

## Reset everything
```bash
docker compose down -v   # -v also deletes the data volume
```
