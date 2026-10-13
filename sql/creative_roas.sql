-- Creative ROAS: MMP ad spend per creative (creative_daily) joined to the revenue of the players each creative
-- acquired (player_metrics, built from in-game telemetry). ROAS = player revenue / ad spend.
WITH spend AS (
    SELECT source, campaign, creative,
           SUM(impressions) AS impressions,
           SUM(installs)    AS installs,
           SUM(spend_usd)   AS spend_usd
    FROM creative_daily
    GROUP BY source, campaign, creative
),
revenue AS (
    SELECT source, campaign, creative,
           COUNT(*)               AS acquired_players,
           SUM(total_revenue_usd) AS revenue_usd
    FROM player_metrics
    GROUP BY source, campaign, creative
)
SELECT
    s.source, s.campaign, s.creative,
    s.impressions, s.installs,
    ROUND(s.spend_usd, 2)                                         AS spend_usd,
    COALESCE(r.acquired_players, 0)                               AS acquired_players,
    ROUND(COALESCE(r.revenue_usd, 0), 2)                          AS revenue_usd,
    ROUND(s.spend_usd / NULLIF(s.installs, 0), 2)                 AS cpi_usd,
    ROUND(COALESCE(r.revenue_usd, 0) / NULLIF(s.spend_usd, 0), 4) AS roas
FROM spend s
LEFT JOIN revenue r USING (source, campaign, creative)
WHERE s.spend_usd > 0
ORDER BY s.spend_usd DESC;
