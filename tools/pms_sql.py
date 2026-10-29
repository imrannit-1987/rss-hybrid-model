"""Transitions query for one project, with reporting gaps filled (up to 5 min). usage: pms_sql.py '<ProjectName>' from to"""
import sys
p,f,t=sys.argv[1:4]
print(f"""WITH g AS (
  SELECT bin(time, 1m) AS t, SiteName, avg(GeneratortotalKW) AS kw
  FROM "telemetrydb-new"."30LogIntervalTelemetry"
  WHERE ProjectName = '{p}' AND time >= '{f}' AND time < '{t}'
    AND (SiteName LIKE 'GS-%' OR SiteName LIKE 'CH-%') AND GeneratortotalKW IS NOT NULL
  GROUP BY bin(time, 1m), SiteName),
gens AS (SELECT DISTINCT SiteName FROM g),
grid AS (SELECT date_add('minute', mi, d) AS t
  FROM UNNEST(sequence(bin(timestamp '{f}', 1m), bin(timestamp '{t}', 1m) - 1d, 1d)) AS x(d)
  CROSS JOIN UNNEST(sequence(0, 1439)) AS y(mi)),
fl AS (
  SELECT grid.t, gens.SiteName, g.kw,
    max(g.kw) OVER (PARTITION BY gens.SiteName ORDER BY grid.t ROWS BETWEEN 10 PRECEDING AND CURRENT ROW) AS kwf,
    count(g.kw) OVER (PARTITION BY gens.SiteName ORDER BY grid.t ROWS BETWEEN 10 PRECEDING AND CURRENT ROW) AS seen
  FROM grid CROSS JOIN gens LEFT JOIN g ON g.t = grid.t AND g.SiteName = gens.SiteName),
f2 AS (SELECT t, SiteName, coalesce(kw, CASE WHEN seen > 0 THEN kwf END) AS kw, seen FROM fl),
s AS (
  SELECT t, sum(kw) AS kw,
    sum(CASE WHEN kw > 3 THEN cast(regexp_extract(SiteName, '-([0-9]+)-', 1) AS double) * 0.8 ELSE 0 END) AS rated_on,
    sum(CASE WHEN kw > 3 THEN 1 ELSE 0 END) AS n_on, sum(CASE WHEN seen > 0 THEN 1 ELSE 0 END) AS n_rep,
    array_join(array_sort(array_agg(CASE WHEN kw > 3 THEN SiteName END)), '|') AS on_list
  FROM f2 GROUP BY t),
w AS (
  SELECT t, kw, rated_on, n_on, n_rep, on_list,
    lag(n_on) OVER (ORDER BY t) AS n1, lag(n_rep) OVER (ORDER BY t) AS rep1, lag(kw) OVER (ORDER BY t) AS kw1, lag(rated_on) OVER (ORDER BY t) AS r1,
    lag(on_list) OVER (ORDER BY t) AS l1,
    max(kw / nullif(rated_on, 0)) OVER (ORDER BY t ROWS BETWEEN 6 PRECEDING AND 1 PRECEDING) AS ld_max5,
    avg(kw / nullif(rated_on, 0)) OVER (ORDER BY t ROWS BETWEEN 6 PRECEDING AND 1 PRECEDING) AS ld_avg5,
    min(kw / nullif(rated_on, 0)) OVER (ORDER BY t ROWS BETWEEN 6 PRECEDING AND 1 PRECEDING) AS ld_min5,
    min(n_on) OVER (ORDER BY t ROWS BETWEEN 1 FOLLOWING AND 10 FOLLOWING) AS n_min_next10,
    max(n_on) OVER (ORDER BY t ROWS BETWEEN 1 FOLLOWING AND 10 FOLLOWING) AS n_max_next10,
    avg(kw) OVER (ORDER BY t ROWS BETWEEN 3 FOLLOWING AND 8 FOLLOWING) AS kw_after
  FROM s)
SELECT * FROM w WHERE n_on <> n1 ORDER BY t""")