# RSS hybrid site model — data and scripts

Snapshot 29 Oct 2026. Everything needed to refit the fuel model without touching the portal database.

- data/hourly/h_*.csv.gz   – portal 3600LogIntervalTelemetry per project, Aug 2024 → 28 Oct 2026 (counters: load/solar/DG meters, GeneratorKWhours, Engineruntime)
- data/daily/daily_all.csv.gz – portal 24hrLogIntervalAnalytics (daily load, solar, DG meter, fuel, efficiency)
- data/reports/monthly_all.csv – monthly Hybrid Performance Reports extracted (forecast vs actual per site-month)
- data/reports/generators.csv – generator list (make/model/engine/year/hours)
- outputs/ – gen_hourly.csv.gz, site_day.csv, month_truth.csv, fuel_dataset_v3.csv, fit_v3/ (coefficients, curves, LOSO), RSS_fuel_curves_v3.xlsx

Pipeline (run from this folder):
  python3 model/build_daily.py data/daily/daily_all.csv model/site_day.csv
  python3 model/gen_hourly.py data/hourly model/gen_hourly.csv.gz            (expects uncompressed h_*.csv)
  python3 tools/monthly_extract.py data/reports/monthly_all.csv <monthly report xlsx files...>
  python3 model/build_fuel_dataset_v3.py gen_hourly.csv.gz site_day.csv month_truth.csv gen_families.csv fuel_dataset_v3.csv
  python3 model/fit_fuel_v3.py fuel_dataset_v3.csv fit_v3
Portal pulls (tools/pull.py <sql> <csv>) go through the Grafana API; only needed to extend the data forward.
