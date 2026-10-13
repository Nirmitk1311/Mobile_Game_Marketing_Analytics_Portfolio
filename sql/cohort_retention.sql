-- Mature-cohort retention D1-D14 by network and campaign.
-- A player only counts for day N once their install is at least N days old (dN_eligible = 1),
-- so young installs never drag the rate down.
SELECT
    source,
    campaign,
    COUNT(*)                                                            AS acquired_players,
    SUM(d1_eligible)                                                    AS d1_eligible,
    ROUND(1.0 * SUM(d1_returned)  / NULLIF(SUM(d1_eligible), 0), 4)     AS d1_retention,
    SUM(d3_eligible)                                                    AS d3_eligible,
    ROUND(1.0 * SUM(d3_returned)  / NULLIF(SUM(d3_eligible), 0), 4)     AS d3_retention,
    SUM(d7_eligible)                                                    AS d7_eligible,
    ROUND(1.0 * SUM(d7_returned)  / NULLIF(SUM(d7_eligible), 0), 4)     AS d7_retention,
    SUM(d14_eligible)                                                   AS d14_eligible,
    ROUND(1.0 * SUM(d14_returned) / NULLIF(SUM(d14_eligible), 0), 4)    AS d14_retention
FROM player_metrics
GROUP BY source, campaign
ORDER BY acquired_players DESC;
