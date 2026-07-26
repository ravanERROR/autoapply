#!/usr/bin/env bash
set -euo pipefail
echo "[setup] Bootstrapping jobapply..."
python3 scripts/seed_filters.py
cp configs/example.env .env
echo "[setup] Done. Navigate to:"
echo "  Frontend: cd frontend && npm install"
echo "  Backend:  cd backend && npm install"
echo "  Start:    npm run dev"
