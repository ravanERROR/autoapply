# JobApply

Multi-platform job auto-apply platform combining a React dashboard, Express backend, and Python automation bots with Gemini AI.

## Stack
- **Frontend:** React 19 + Vite + Tailwind CSS v4
- **Backend:** Express + TypeScript
- **Automation:** Python Selenium (LinkedIn, Naukri, Indeed, Glassdoor, Foundit)
- **AI:** Google Gemini 2.0 Flash (form filling, smart filters)
- **Chrome CDP:** For Naukari deep automation

## Quick Start

```bash
npm install
cp configs/example.env .env        # edit credentials
python scripts/seed_filters.py

cd backend && npm install && npm run dev
cd frontend && npm install && npm run dev
```

Open http://localhost:3000

## Run bots
```bash
# LinkedIn
cd bots && python linkedin_bot.py

# Naukri
cd bots && python naukri_bot.py

# All (orchestrator)
cd bots && python orchestrator.py --platform all
```

## Project Structure
```
jobapply/
  frontend/    - React dashboard
  backend/     - Express REST API
  bots/        - Selenium/CDP bots per platform
  gemini/      - Gemini AI integration
  configs/     - Filter profiles and example credentials
  logs/        - Application CSV logs
  scripts/     - Setup and seeding utilities
```

## Features
- Real-time application dashboard with charts
- Multi-platform bot orchestration
- Per-platform filter profiles
- CSV export with full application history
- Headless/visible browser modes
- Easy Apply & standard form submission
- AI-assisted form field filling via Gemini
