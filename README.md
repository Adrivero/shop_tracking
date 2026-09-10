# Shop Tracking

Scan shopping receipts and explore spending statistics in a private dashboard
running on your own computer. Docker contains Python, Tesseract OCR, the web UI,
and SQLite; no cloud account or remote server is required.

## Start the dashboard

Install Docker Desktop (macOS or Windows), or Docker Engine (Linux). From the
project directory, start the app with Docker Compose:

```bash
docker compose up --build
```

The command is the same in PowerShell, Command Prompt, macOS shells, and Linux
shells. It avoids shell-specific volume syntax such as `"$PWD/data"`.

Open [http://localhost:8000](http://localhost:8000). The port is bound to
`127.0.0.1`, so the dashboard is available only from this computer.

### Manage it from Docker Desktop

After starting the app, Docker Desktop should show:

- one image: `shop-tracking:local`;
- one container: `shop-tracking`.

Use Docker Desktop's start/stop buttons from then on. If you prefer the terminal,
the equivalent commands are:

```bash
docker compose up
docker compose stop
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

## Optional local LLM corrections

The scan screen includes a **Local LLM corrections** switch. It stays disabled
until a local model is configured. With Ollama running on the host, open
**Settings** in the sidebar and use:

- model: `llama3.1:8b`;
- base URL: `http://host.docker.internal:11434`;
- timeout: `20`.

Save the settings, then enable **Local LLM corrections** on the scan screen.

You can still preconfigure startup defaults with `OCR_LLM_MODEL`,
`OCR_LLM_ENABLED`, `OCR_LLM_BASE_URL`, and `OCR_LLM_TIMEOUT_SECONDS`. The LLM is
used only after OCR to correct the structured receipt result; if the model is
unavailable or returns invalid data, the app keeps the deterministic OCR result.

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
docker compose run --rm dashboard /var/lib/shop-tracking/raw/receipt_mercadona_01.jpeg

docker compose run --rm dashboard /var/lib/shop-tracking/raw/receipt_mercadona_01.jpeg --save
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
