-- Ghost installs: attributed installs (MMP) that never send a single in-game telemetry event (tracked = 0).
-- A network/platform with 40%+ ghost installs (and at least 20 installs) is flagged for billing-dispute
-- reconciliation with the network.
SELECT
    source,
    platform,
    COUNT(*)                                        AS acquired_players,
    SUM(CASE WHEN tracked = 0 THEN 1 ELSE 0 END)    AS ghost_installs,
    ROUND(1.0 * SUM(CASE WHEN tracked = 0 THEN 1 ELSE 0 END) / COUNT(*), 4) AS ghost_share,
    CASE WHEN COUNT(*) >= 20
          AND 1.0 * SUM(CASE WHEN tracked = 0 THEN 1 ELSE 0 END) / COUNT(*) >= 0.40
         THEN 'dispute with network' ELSE '' END    AS billing_action
FROM player_metrics
GROUP BY source, platform
ORDER BY ghost_share DESC, acquired_players DESC;
