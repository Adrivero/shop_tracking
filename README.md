# Shop Tracking

Scan shopping receipts and explore spending statistics in a private dashboard
running on your own computer. Docker contains Python, Tesseract OCR, the web UI,
and SQLite; no cloud account or remote server is required.

## Start the dashboard

Install Docker Desktop (macOS or Windows), or Docker Engine (Linux). From the
project directory, build the image:

```bash
docker build -t shop-tracking:local .
```

Then create the container once:

```bash
docker run \
  --name shop-tracking \
  --publish 127.0.0.1:8000:8000 \
  --env DATABASE_URL=sqlite:////var/lib/shop-tracking/shop_tracking.db \
  --volume "$PWD/data:/var/lib/shop-tracking" \
  shop-tracking:local
```

Open [http://localhost:8000](http://localhost:8000). The port is bound to
`127.0.0.1`, so the dashboard is available only from this computer.

### Manage it from Docker Desktop

After creating the container, Docker Desktop should show:

- one image: `shop-tracking:local`;
- one container: `shop-tracking`.

Use Docker Desktop's start/stop buttons from then on. If you prefer the terminal,
the equivalent commands are:

```bash
docker start shop-tracking
docker stop shop-tracking
```

The UI provides:

- drag-and-drop receipt scanning with images archived in `data/raw/` and
  optional database saving;
- total spend, average basket, product, store, and monthly statistics;
- searchable product analytics with frequency, quantity, and spend;
- receipt history with editable details and product lines;
- confirmed receipt deletion with automatic statistics refresh;
- a responsive layout for desktop, tablet, and mobile-sized windows.

Use the **Stop app** button in the dashboard or Docker Desktop's stop button.
Starting and stopping the dashboard does not remove its data.

## Local data

SQLite data lives in this project folder at `data/shop_tracking.db`. Docker
mounts `./data` into the container, so closing or rebuilding a container does
not delete the database file. If the file does not exist yet, the app creates it
there and applies migrations on startup.

Receipt images uploaded through the dashboard are saved in `data/raw/`. There
are no Docker named volumes or anonymous Docker volumes required for app data.

No separate Docker backup database or backup volume is configured. Periodically
copy `data/shop_tracking.db` somewhere outside this project folder to protect
against disk failure.

## Command-line scanning

Place images in `data/raw/` and run:

```bash
docker run --rm \
  --env DATABASE_URL=sqlite:////var/lib/shop-tracking/shop_tracking.db \
  --volume "$PWD/data:/var/lib/shop-tracking" \
  shop-tracking:local /var/lib/shop-tracking/raw/receipt_mercadona_01.jpeg

docker run --rm \
  --env DATABASE_URL=sqlite:////var/lib/shop-tracking/shop_tracking.db \
  --volume "$PWD/data:/var/lib/shop-tracking" \
  shop-tracking:local /var/lib/shop-tracking/raw/receipt_mercadona_01.jpeg --save
```

The first command previews parsed data. The second saves it to the same SQLite
volume used by the dashboard.

## Development

```bash
uv sync
uv run alembic upgrade head
uv run pytest -q
uv run python -m app.web
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000). Direct local OCR
requires Tesseract on the host; Docker already includes it.

The test suite covers parsers, real JPEG OCR, transactions, migrations,
backups, statistics, page rendering, uploads, and the complete save pipeline.
