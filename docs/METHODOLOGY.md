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
- **14-day decisions:** when the week is complete each creative in the quality review gets a decision. **No decision is made under 10,000 impressions** in the 14 days ("Too early to judge"). Above that: no installs, fewer than 3 installs per 1,000 impressions, or ROAS below half the window average means deactivate; otherwise keep.
- **Incomplete last day:** at export time the latest day already has installs, but the ad networks report its spend and impressions about one day later, and the players' (US) day is still running. Its **full-day** impressions, clicks, installs and spend are therefore **estimated** per creative from the average of its days with impressions among the 3 complete days before it (never below what is already reported), and included in delivery, CPI, the minimum-data rules and every decision; `est_installs` / `est_spend_usd` show the estimated part and `summary.json` gives the totals. Player quality and ROAS use complete days only (`spend_data_through`), because estimated installs have no players or revenue yet. The real figures replace the estimate at the next refresh.
- **D30 ROAS:** revenue in each player's first 30 days divided by spend, per campaign, for the latest 14 install days whose players are at least 30 days old (`d30_roas.csv`, with the D7 ROAS of the same installs next to it). It covers an **older** group of installs than the 14-day window, is shown for payback context only, and is empty until such install days exist.
- **Unit of analysis:** the 14-day quality review judges the **ad (creative)**, because installs, retention and revenue are attributed to the ad. The 7-day new-creative test judges the **video file (asset)** wherever a network reports assets, because one ad can carry several cuts of a video (9x16, 4x5, 1x1, 16x9) and the network chooses one per placement. Networks without asset reporting are tested per creative. Player-quality metrics for an asset are those of its ad.
- **New-creative cost test (7 days ending on the week end):** no hand-made list is used. A campaign is identified by its **campaign ID** (a renamed campaign is the same campaign). A creative is new in a campaign when it has impressions in that campaign inside the 7 days and **no impressions in the same campaign** in the earlier days of the 14-day window; its first impression may come on any day of the week. A creative that ran in the same campaign before the week, paused and came back is **not new**: it is kept out of every new-creative figure and listed in `paused_resumed_7d.csv` with its days without impressions. Older history and impressions in a **different** campaign do not block a creative: a creative moved into another campaign counts as newly activated there, and only its impressions inside the 7 days are used. The 14-day creative quality review leaves out the new creatives, and leaves out a moved creative completely (also its rows in the old campaign). Assets the network reports without a name (for example search headline or description assets) are left out of the table, and `summary.json` gives their count and totals. Keep/deactivate decisions appear only when the 7 days are complete:
  - fewer than 50 installs or 5,000 impressions: extend by one week;
  - CPI more than 30% above the campaign's other creatives (with at least 10 installs behind that benchmark): deactivate;
  - otherwise: keep.
- **Traffic quality (14 days):** for each network and platform, the share of acquired players that sent any in-game event (**tracking coverage**) and the share flagged as **likely fraud**. Flagged players stay in every metric; they are counted and listed separately, never removed.

Two patterns from the live data are kept in the synthetic months:
- One network's Android traffic has much lower tracking coverage than every other network. Many of its attributed installs never send a single in-game event, a common sign of non-human installs, so it is worth investigating with the network.
- A small group of flagged installs shares one implausible hardware profile across several phone brands, plays one short session and completes no level, which is a device-farm pattern.

## Limitations

The data is intentionally simplified. It does not model privacy-framework postbacks, probabilistic attribution, currency conversion, delayed platform reporting or every production event family. Fraud appears only as a generic per-player flag (`quality_flag`) in the daily-refreshed months. Results are demonstrations of analysis design, not real commercial findings.
