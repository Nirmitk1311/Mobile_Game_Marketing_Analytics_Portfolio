# Methodology

## Scope

The project contains two fictional paid-acquisition cohorts: August 2025 and September 2025. Each month includes campaign delivery, creative delivery, acquired-player records and post-install events.

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

Retention uses `session_start` on the exact calendar day after installation. A player enters a day-specific denominator only when the reporting month contains enough observation time for that player to mature to the requested day.

## Campaign analysis

Campaign reporting combines media delivery with player behavior. Metrics include impressions, clicks, acquired players, spend, CPI, CTR, CVR, D1/D3/D7/D14 retention, sessions per player, active days, levels completed, ad impressions, revenue, ROAS and cost per retained player.

Active and stopped campaign configurations remain separate. This prevents later delivery from being incorrectly assigned to an earlier configuration.

## Creative analysis

Creative reporting uses the creative assigned to each synthetic acquisition. It compares delivery, cost, engagement, D7 retention and revenue. Small samples should be treated as directional.

## Limitations

The data is intentionally simplified. It does not model privacy-framework postbacks, probabilistic attribution, currency conversion, fraud, delayed platform reporting or every production event family. Results are demonstrations of analysis design, not real commercial findings.
