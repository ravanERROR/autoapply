# Backend Commit Verification

## What was added:
- Express 4 server with full routing
- Applications API (GET /, POST /log, GET /export, DELETE /clear) backed by CSV
- Filters API (GET /, GET /:name, POST /:name) backed by JSON files in configs/filters/
- Bot orchestration API (GET /active, POST /start, POST /:id/stop)
- Status endpoint (GET /) returning uptime, memory, env
- Request logging middleware

## Run:
  cd backend && npm install && npm run dev
