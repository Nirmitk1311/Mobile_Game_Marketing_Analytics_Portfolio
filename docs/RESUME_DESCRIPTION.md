# Resume description

## Project title

Mobile Game Marketing Analytics & UA Optimization

## Resume line

**Mobile Game Marketing Analytics & UA Optimization:** Unified Singular MMP ad spend with Mixpanel telemetry in Python/SQL to analyze mature D1–D14 cohort retention and creative ROAS. Enforced kill/scale benchmarks (>30% baseline CPI) to curb ad waste and isolated an ad network with 40%+ ghost installs for billing dispute reconciliations. Stack: Python, SQL, Playwright, Pandas, Singular, Mixpanel.

Where to see each claim in this repository (fictional data): D1–D14 cohort retention and creative ROAS in `sql/` and `outputs/sql/`; the >30% baseline-CPI rule in `src/weekly_review.py` (`CPI_TOLERANCE = 1.30`); ghost installs in `outputs/sql/ghost_installs.csv` and `ghost_install_disputes` in each `outputs/weekly/<week>/summary.json`.

## Description

Built an end-to-end marketing analytics system that connects mobile acquisition data with player events. Created an identity-matching and data-quality pipeline, then evaluated campaign and creative performance using CPI, retained-user cost, engagement, monetization, ROAS and D1, D3, D7 and D14 retention. Produced management reports and dashboards that translate player quality into budget and creative recommendations.

## Resume bullets

- Built reproducible Python pipelines for synthetic data generation, cleaning, validation, cohort creation and marketing performance reporting.
- Connected acquisition records with player behavior through a device-to-person identity model and preserved zero-event users in acquisition denominators.
- Compared campaign and creative performance using acquisition cost, engagement, retention, revenue and cost per retained player.
- Created Excel dashboards, automated charts and management reports with documented metric definitions and data-quality checks.

## Interview note

The public repository is a clean-room reconstruction. It demonstrates the analytical workflow using fictional data and does not contain employer or client information.
