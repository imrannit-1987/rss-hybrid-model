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

## v4 fuel model (11 Nov 2026) — weekly-report truth
  python3 model/build_fuel_dataset_v4.py outputs/gen_hourly.csv.gz outputs/site_day.csv outputs/month_truth.csv outputs/gen_families.csv data/reports/weekly_daily_all.csv outputs/fuel_dataset_v4_week.csv outputs/fuel_dataset_v4_month.csv
  python3 model/fit_fuel_v4.py outputs/fuel_dataset_v4_week.csv outputs/fuel_dataset_v4_month.csv outputs/fit_v4
  (cd outputs && python3 ../model/sim_all.py pms/pms_quarterly.csv sim/sim_all_monthly_v4.csv v4)
Same curve form as v3, trained on 1,525 site-weeks (weekly reports) instead of 384 site-months. LOSO on weekly truth: week |err| 3.2% (v3 4.5%), site 2.0% (3.6%), fleet +0.6% (+2.5%).
model/fuelfit4.py holds the fitter (options tested and rejected are still switchable there). outputs/fit_v4/coef_v4.json is the current coefficient set; 'rated_h|*','kwh|*' = fleet curve for engine families not in the data.
Note: weekly reports total ~2% less fuel than monthly reports for the same months.
