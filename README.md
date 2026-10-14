# Mobile Game Marketing Analytics & UA Optimization

An end-to-end portfolio project that unifies MMP ad spend (Singular-style media and creative delivery) with in-game telemetry (Mixpanel-style player events) in Python and SQL, to evaluate mature D1–D14 cohort retention, creative ROAS, cost and player quality, and to turn them into kill/scale decisions for user acquisition.

> **Privacy note:** Every company name, campaign, creative, identifier, event record, financial value and finding in this repository is synthetic. No employer or client data is included.

## Daily refresh (from October 2025)

From October 2025 the repository is refreshed every weekday. A private production pipeline (Python, Pandas, Playwright browser automation for the MMP exports, the MMP reporting API and the product-analytics export API) produces **pattern-only synthetic data**: it keeps the general shape of a live marketing dataset (campaign mix over time, retention decay, engagement, weekday rhythm) while volumes, costs, revenue and retention levels are rescaled by undisclosed factors, noise is added, all names are fictional, dates are moved to a demonstration period and no real identifier is copied. The repository's own pipeline then rebuilds the analysis and charts. [`data/synthetic/live_status.json`](data/synthetic/live_status.json) shows the latest demonstration date. A month's Word report is added once its first cohort reaches Day 7.

## What this project demonstrates

- Deterministic synthetic data generation for two monthly cohorts
- Campaign-to-player identity matching
- Data cleaning, reconciliation and automated validation
- D1, D3, D7 and D14 mature-cohort retention
- CPI, CTR, CVR, retained-user cost and ROAS
- Session, active-day, level and ad-engagement analysis
- Campaign lifecycle and creative-quality comparison
- Management-ready Word reports, Excel dashboards and charts
- Weekly creative review: 14-day creative quality with creative ROAS, a 7-day new-creative cost test based on first impressions per campaign, and traffic quality (tracking coverage and likely-fraud share by network)
- Kill/scale benchmarks: a new creative is deactivated when its CPI is more than 30% above the baseline CPI of the campaign's other creatives
- Ghost-install detection: networks where 40%+ of attributed installs never send any in-game telemetry are flagged for billing-dispute reconciliation
- SQL layer (SQLite): cohort retention D1–D14, creative ROAS and ghost installs by network ([`sql/`](sql/), results in `outputs/sql/`)

## Repository structure

```text
data/synthetic/          Generated fictional campaign, creative, player and event data
src/                     Data generation, cleaning, analysis, SQL runner, chart and report scripts
sql/                     SQL queries: cohort retention, creative ROAS, ghost installs
outputs/analysis/        Clean data, campaign summaries and validation results
outputs/weekly/          Weekly creative quality, new-creative test and traffic-quality tables
outputs/sql/             Results of the SQL queries
outputs/charts/          Portfolio-ready PNG charts
outputs/dashboards/      August and September Excel dashboards
outputs/reports/         August and September management reports
tests/                   Automated pipeline checks
docs/                    Methodology, data dictionary and privacy design
run_pipeline.py          Rebuilds data, analysis, charts and Word reports
```

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python run_pipeline.py
python -m unittest discover -s tests
```

The committed Excel files are curated dashboard artifacts. The Python pipeline reproduces the synthetic CSV analysis, charts and Word reports.

## Sample output

![August retention curve](outputs/charts/2025-08/retention_curve.png)

![September acquisition cost and return](outputs/charts/2025-09/cpi_vs_roas.png)

## Analytical flow

```text
Synthetic media delivery ─┐
Synthetic creative data ──┼─> cleaning and validation ─> identity join ─> player metrics
Synthetic player/events ──┘                                      │
                                                                 └─> campaigns, creatives,
                                                                     dashboards and reports
```

## Main metric definitions

- **CPI:** spend divided by acquired players.
- **CTR:** clicks divided by impressions.
- **CVR:** reported installs divided by clicks.
- **Retention:** players with a session on the exact return day divided by players mature enough to reach that day.
- **ROAS:** synthetic ad revenue plus synthetic purchase revenue divided by synthetic spend (also per creative: creative ROAS).
- **Ghost install:** an attributed install that never sends a single in-game telemetry event; ghost share = ghost installs / attributed installs.
- **Kill/scale benchmark:** a creative's CPI against the baseline CPI of its campaign's other creatives; more than 30% above it (with weak installs per 1,000 views) means deactivate.
- **Cost per D7 retained player:** spend divided by players returning on Day 7.

## Portfolio discussion points

The weekly review adds an operating view. It shows which creatives are genuinely new this week, keeps decisions until a creative has a full week of delivery, and shows how much of each network's traffic actually reaches in-game tracking. Low tracking coverage on one network is a traffic-quality warning that cost metrics alone would hide: in the October demonstration data one ad network delivers 40%+ ghost installs, which is isolated and listed for a billing-dispute reconciliation with that network.

The project shows how acquisition efficiency can differ from downstream player quality. A low-cost campaign may produce weak retention, while a higher-cost campaign may create more valuable players. The reporting layer therefore combines acquisition, engagement, retention and monetization rather than ranking campaigns by installs alone.

See [docs/METHODOLOGY.md](docs/METHODOLOGY.md) for the complete workflow and [docs/PRIVACY.md](docs/PRIVACY.md) for the safeguards used.

## License

MIT. The dataset is fictional and may be reused for learning and portfolio demonstrations.
