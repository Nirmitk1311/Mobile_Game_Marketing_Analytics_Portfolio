# Methodology

## Scope

The project contains two clean-room fictional paid-acquisition cohorts (August 2025 and September 2025) and, from October 2025, pattern-only synthetic months refreshed every weekday (see [PRIVACY.md](PRIVACY.md)). Each month includes campaign delivery, creative delivery, acquired-player records and post-install events.

## Cleaning

The pipeline:

1. Excludes explicitly marked test-market players.
2. Keeps one acquisition row per synthetic device.
3. Retains zero-event acquired players in the acquisition population.
4. Removes duplicate event identifiers.
5. Removes events timestamped before installation.
6. Audits orphan devices, duplicate player IDs and negative spend.

## Identity model

`device_id` is the acquisition and behavioral join key. `person_id` demonstrates the account-level namespace. Both use a visibly synthetic prefix and have no relationship to production identifiers.

## Cohort rules

Retention uses `session_start` on the exact calendar day after installation. A player enters a day-specific denominator only when the reporting month contains enough observation time for that player to mature to the requested day. For a month that is still refreshing daily, a player counts for Day N only after Day N has been fully observed.

## Campaign analysis

Campaign reporting combines media delivery with player behavior. Metrics include impressions, clicks, acquired players, spend, CPI, CTR, CVR, D1/D3/D7/D14 retention, sessions per player, active days, levels completed, ad impressions, revenue, ROAS and cost per retained player.

Active and stopped campaign configurations remain separate. This prevents later delivery from being incorrectly assigned to an earlier configuration.

## Creative analysis

Creative reporting uses the creative assigned to each synthetic acquisition. It compares delivery, cost, engagement, D7 retention and revenue. Small samples should be treated as directional.

## Weekly creative review (daily-refreshed months)

`src/weekly_review.py` adds a weekly operating cadence on top of the monthly analysis. A reporting week ends on a Wednesday in the demonstration calendar and is named by that day. Outputs go to `outputs/weekly/<week_end>/` and are rebuilt every refresh, marked in progress until the week is complete.

- **Creative quality (14 days ending on the week end):** delivery and cost per creative (CPI, IPM, CTR, days live) next to the quality of the players it acquired: D1/D7 retention (mature players only), levels per player, revenue per player, tracking coverage and the flagged share.
- **New-creative cost test (7 days ending on the week end):** no hand-made list is used. A creative is new when its **first impression** across the network's whole history falls inside the 7 days and it had **no impressions in the earlier days of the 14-day window**. First-impression dates come from `data/synthetic/creative_first_impressions.csv`, because a creative can start before the visible data does. Assets the network reports without a name (for example search headline or description assets) are left out of the table, and `summary.json` gives their count and totals. Keep/deactivate decisions appear only when the 7 days are complete:
  - fewer than 50 installs or 10,000 impressions: extend by one week;
  - CPI more than 30% above the campaign's other creatives (with at least 10 installs behind that benchmark): deactivate;
  - otherwise: keep.
- **Traffic quality (14 days):** for each network and platform, the share of acquired players that sent any in-game event (**tracking coverage**) and the share flagged as **likely fraud**. Flagged players stay in every metric; they are counted and listed separately, never removed.

Two patterns from the live data are kept in the synthetic months:
- One network's Android traffic has much lower tracking coverage than every other network. Many of its attributed installs never send a single in-game event, a common sign of non-human installs, so it is worth investigating with the network.
- A small group of flagged installs shares one implausible hardware profile across several phone brands, plays one short session and completes no level, which is a device-farm pattern.

## Limitations

The data is intentionally simplified. It does not model privacy-framework postbacks, probabilistic attribution, currency conversion, delayed platform reporting or every production event family. Fraud appears only as a generic per-player flag (`quality_flag`) in the daily-refreshed months. Results are demonstrations of analysis design, not real commercial findings.
