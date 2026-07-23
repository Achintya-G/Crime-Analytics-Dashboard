# DB Setup Steps

## Folder structure

```
Crime-Analytics-Dashboard\
├── docker-compose.yml
├── generate_mock_data.py
├── venv\
└── init-db\
    └── 01-init.sql
```

## Steps

1. Create venv in project root (not inside `init-db\`)

```powershell
cd D:\Crime-Analytics-Dashboard
python -m venv venv
venv\Scripts\activate
```

2. Install deps

```powershell
pip install faker numpy pandas sqlalchemy psycopg2-binary
```

3. `docker-compose.yml` must live in project root (one level above `init-db\`), not inside it.

4. If port 5432 is taken (native Postgres / WSL), remap in `docker-compose.yml`:

```yaml
ports:
  - "5433:5432"
```

5. Start the container

```powershell
docker compose up -d db
```

6. If reusing an old/broken setup, nuke it first

```powershell
docker compose down -v
docker ps -a                # check for orphaned containers
docker rm -f <container_id> # remove if name conflict
docker volume ls            # check for leftover volumes
docker volume rm <volume_name>
```

7. Verify container is healthy + env vars are correct

```powershell
docker compose ps
docker exec -it crime-db env | findstr POSTGRES
```

8. Verify init SQL actually ran (schema created)

```powershell
docker exec -it crime-db psql -U crime_admin -d crimedb -c "\dt"
```

9. Seed mock data (match the port you're using — 5432 or 5433)

```powershell
python generate_mock_data.py --num-cases 1000 --postgres "postgresql://crime_admin:devpass@localhost:5433/crimedb"
```

10. Verify data loaded

```powershell
docker exec -it crime-db psql -U crime_admin -d crimedb
```

```sql
SELECT COUNT(*) FROM case_master;
SELECT "CrimeMinorHead", COUNT(*) FROM case_master GROUP BY 1 ORDER BY 2 DESC;
\q
```

## Reset everything

```powershell
docker compose down -v
```
