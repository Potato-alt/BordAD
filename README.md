# BordAD

Internal alternative board for a ForceAD attack-defense game. It works as an external HTTP client: reads the public ForceAD board API, accepts team flags locally, submits them to ForceAD in batches, and highlights attack/defense focus areas from scoreboard statistics.

## Features

- Batch flag submit to `PUT /flags` with `X-Team-Token`.
- ForceAD-compatible max batch size of `100` flags.
- Local flag queue with deduplication and submit history.
- Public board polling via `/api/client/*` endpoints.
- Attack recommendations based on other teams' `lost` growth.
- Defense recommendations based on our `lost` growth and global service heat.
- Single-process FastAPI app with SQLite, no Redis/Celery required.

## Setup

```bash
cp .env.example .env
```

Edit `.env`:

```env
FORCEAD_BASE_URL=https://board.example
FORCEAD_TEAM_TOKEN=your-forcead-team-token
APP_TOKEN=shared-token-for-tools
OUR_TEAM_ID=1
```

Run locally:

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or with Docker:

```bash
docker compose up --build
```

Open `http://127.0.0.1:8000/`.

## API For Team Tools

Submit JSON:

```bash
curl -X POST http://127.0.0.1:8000/api/flags \
  -H 'X-App-Token: shared-token-for-tools' \
  -H 'Content-Type: application/json' \
  -d '{"source":"exploit-notes","flags":["AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="]}'
```

Submit text:

```bash
curl -X POST 'http://127.0.0.1:8000/api/flags/text?source=manual-tool' \
  -H 'X-App-Token: shared-token-for-tools' \
  -H 'Content-Type: text/plain' \
  --data-binary @flags.txt
```

Read recommendations:

```bash
curl http://127.0.0.1:8000/api/board/recommendations \
  -H 'X-App-Token: shared-token-for-tools'
```

## ForceAD Assumptions

The service expects the original board to expose standard ForceAD endpoints:

- `GET /api/client/teams/`
- `GET /api/client/tasks/`
- `GET /api/client/config/`
- `GET /api/client/teams/<team_id>/`
- `PUT /flags`

If organizers customize or hide these endpoints, the poller will keep retrying and the dashboard will show the last polling error.
