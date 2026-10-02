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
