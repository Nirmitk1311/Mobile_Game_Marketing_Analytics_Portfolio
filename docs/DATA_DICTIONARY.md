# Data dictionary

## Campaign daily data

| Field | Meaning |
|---|---|
| month | Synthetic cohort month |
| date | Delivery date |
| source | Fictional acquisition network |
| campaign | Fictional campaign name |
| platform | Android or iOS |
| lifecycle | Active or stopped configuration |
| impressions | Synthetic ad impressions |
| clicks | Synthetic clicks |
| reported_installs | Platform-reported installs |
| spend_usd | Synthetic spend in USD |

## Players

| Field | Meaning |
|---|---|
| device_id | Synthetic acquisition identity |
| person_id | Synthetic account identity |
| install_timestamp | Fictional install time |
| creative | Fictional creative assignment |
| region_group | Broad fictional region grouping |
| is_test_market | Exclusion flag used by cleaning |
| tracking_available | Whether qualifying events were generated |
| quality_flag | Daily-refreshed months only. Empty = not flagged; `network_flag` = the network's fraud check marked the install suspicious; `device_pattern` = implausible hardware profile; both are joined by `;`. Flagged players stay in all metrics |

## Creative first impressions

`data/synthetic/creative_first_impressions.csv`, one row per network and creative:

| Field | Meaning |
|---|---|
| source, creative | Fictional network and creative |
| first_impression_date | First day with impressions across the network's whole history (demonstration calendar) |
| seen_on_first_history_day | True when the creative already had impressions on the first day of the history, so it may have started earlier |
| has_name | False when the network reports no name for the asset; such assets are summarised, not listed, in the new-creative test |

## Events

| Field | Meaning |
|---|---|
| event_id | Synthetic event identity |
| event_timestamp | Fictional event time |
| event_name | session_start, level_completed, ad_impression or purchase_complete |
| level_value | Level completion count contribution |
| revenue_usd | Synthetic ad or purchase revenue |

## Derived outputs

`player_metrics.csv` contains one row per acquired device. `campaign_summary.csv` and `creative_summary.csv` contain aggregated acquisition, engagement, retention and return metrics. `validation.json` records cleaning results.

Weekly outputs, in `outputs/weekly/<week_end>/` (see [METHODOLOGY.md](METHODOLOGY.md)):

| File | Contents |
|---|---|
| creative_quality_14d.csv | Per creative, 14 days: impressions, clicks, installs, spend, CPI, IPM, CTR, days live, acquired/tracked/flagged players, D1/D7 retention, levels and revenue per player |
| new_creatives_7d.csv | Creatives whose first impression is inside the 7 days: first-impression date, days live, delivery and cost, campaign CPI benchmark, status, and the decision once the week is complete |
| traffic_quality.csv | Per network and platform, 14 days: acquired players, tracking coverage, flagged share, D1/D7 retention, levels and revenue per player |
| summary.json | Windows, completeness, counts, overall tracking coverage and flagged share, lowest-coverage network, unnamed new assets |
