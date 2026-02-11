# Promo Products BG 🇧🇬

Bulgarian deals & promotions aggregator — find the best prices across retailers.

## Vision

A centralized, user-friendly platform for Bulgarian consumers to:
- Compare prices across multiple retailers
- Track promotions and deals
- Get personalized alerts via Viber
- Navigate the BGN→EUR transition confidently

## Tech Stack

- **Frontend:** Expo + React Native Web (web, iOS, Android from single codebase)
- **Backend:** TBD (likely Node.js or Python FastAPI)
- **Data Pipeline:** Scrapy + OCR for brochure extraction
- **Notifications:** Viber Business API + Push

## Project Structure

```
promo_products_bg/
├── apps/
│   └── mobile/          # Expo app (web + native)
├── packages/
│   └── shared/          # Shared types, utils
├── services/
│   ├── scraper/         # Data acquisition pipeline
│   └── api/             # Backend API
├── data/
│   └── schemas/         # Data models
└── docs/
    └── research/        # Market research, competitor analysis
```

## Getting Started

TBD — project is in early planning phase.

## Team

- Martin
- Maria
- Cookie 🍪 (AI assistant)

## Status

🟡 **Planning Phase** — Defining MVP scope and data acquisition strategy.

## Links

- [Feasibility Study](./docs/research/feasibility-study.md)
