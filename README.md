# Japan Electricity Dispatch Economics

A Python-based production cost model simulating half-hourly electricity dispatch across Japan's generation fleet, with scenario analysis focused on the duck-curve dynamics created by rising solar penetration and seasonal demand bimodality.

## Research Question

> In Japan's dual-peak demand structure (summer cooling + winter heating) with accelerating solar PV deployment, how do the dispatch economics and capacity utilization of different generator types shift across seasons and time-of-day — and what happens under nuclear restart and fuel price shock scenarios?

## Method

The model implements a **simple merit-order dispatch** engine:

1. **Data ingestion** — Public data from JEPX, OCCTO/JREF, and the World Bank Pink Sheet are cleaned into five standardised input tables.
2. **Merit-order construction** — For each 30-minute interval, each fleet's marginal cost is computed as `fuel_price × heat_rate + variable_O&M`, then sorted ascending.
3. **Dispatch** — Renewables (solar, wind) dispatch first as must-take; nuclear dispatches as must-run; residual demand is filled by thermal/hydro fleets in merit order.
4. **Clearing price** — Set by the marginal cost of the last dispatched fleet, with floor (0) and cap (99.99 JPY/kWh) logic for oversupply/shortage.
5. **Backtest** — Simulated prices are compared against actual JEPX system prices.

### Modeling Assumptions

| Assumption | Value | Rationale |
|---|---|---|
| Spatial model | Single national node (copper plate) | MVP simplification; ignores inter-regional transmission |
| Temporal granularity | 30-minute intervals | Matches raw data resolution |
| Fleet aggregation | By fuel type (9 categories) | Not individual plant-level |
| Backtest target | System price (システムプライス) | National clearing price |
| USD/JPY | 150 (fixed) | Approximate FY2025 average |
| Solar installed | 80,000 MW | METI reference |
| Wind installed | 5,000 MW | METI reference |

## Data Sources

All data are publicly available.

| Data | Source | Granularity |
|---|---|---|
| Spot electricity prices | [JEPX](https://www.jepx.org/) | 30-min |
| National demand + generation mix | [JREF](https://www.renewable-ei.org/) (via OCCTO) | 30-min |
| Tokyo area supply-demand | OCCTO ERIA data | 30-min |
| LNG / Coal / Oil prices | [World Bank Pink Sheet](https://www.worldbank.org/en/research/commodity-markets) | Monthly |
| Generator technical parameters | NREL ATB, IEA WEO, Lazard LCOE | Literature-based |

Analysis period: **FY2025** (April 2025 – March 2026).

## Key Results (Base Case)

### Generation Mix (805 TWh total)

| Fuel | Generation (TWh) | Share | Capacity (GW) | Capacity Factor |
|---|---|---|---|---|
| Coal | 332.9 | 41.4% | 45.0 | 84.6% |
| Hydro | 179.4 | 22.3% | 22.0 | 93.2% |
| Solar | 91.4 | 11.4% | 80.0 | 13.1% |
| LNG CCGT | 82.4 | 10.2% | 65.0 | 14.5% |
| Nuclear | 81.8 | 10.2% | 10.0 | 93.5% |
| Biomass | 25.0 | 3.1% | 5.0 | 57.1% |
| Wind | 12.2 | 1.5% | 5.0 | 27.9% |

LNG OCGT and oil were not dispatched — the merit order placed them above the demand curve in all intervals.

### Simulated Clearing Price

| Metric | Value |
|---|---|
| Mean | 11.63 JPY/kWh |
| Std dev | 3.03 JPY/kWh |
| Min | 0.00 JPY/kWh |
| Max | 15.31 JPY/kWh |
| Marginal fuel (most frequent) | LNG CCGT (56%), Coal (33%), Biomass (10%) |

### Backtest vs JEPX Actuals

| Metric | Value |
|---|---|
| RMSE | 3.08 JPY/kWh |
| MAE | 2.44 JPY/kWh |
| Correlation | 0.617 |
| Bias | +0.69 JPY/kWh (slight overestimate) |

The model captures the broad price level and diurnal pattern, but underpredicts price spikes and overpredicts off-peak prices. Expected deviation sources include:

- **Strategic bidding** — JEPX is a bid-based market; marginal-cost dispatch ignores markup behaviour
- **Transmission constraints** — Regional price separation (area prices ≠ system price) is not modelled
- **Storage & demand response** — Pumped hydro and battery arbitrage are excluded
- **Renewable forecast error** — Actual curtailment and forecast deviations are not captured
- **Hydro dispatch** — Modelled as baseload, but real hydro is dispatchable with reservoir constraints

## Project Structure

```
Japan Electric Market/
├── main.py                      # Pipeline entry point
├── config/
│   └── settings.yaml            # Modeling decisions & parameters
├── data/
│   ├── raw/                     # Original source files
│   │   ├── spot_summary_2025.csv
│   │   ├── download.csv
│   │   ├── eria_jukyu_*_03.csv
│   │   ├── CMO-Historical-Data-Monthly.xlsx
│   │   ├── assumptions.yml
│   │   └── DATA_MANIFEST.md
│   ├── processed/               # Cleaned model inputs
│   │   ├── jepx_prices.csv
│   │   ├── demand_profile.csv
│   │   ├── renewable_profiles.csv
│   │   ├── fuel_prices.csv
│   │   └── fleet.csv
│   └── process_raw.py           # Raw → processed ETL
├── engine/                      # Dispatch engine
│   ├── merit_order.py           # Marginal cost & merit-order builder
│   ├── dispatch_solver.py       # Hourly dispatch solver
│   └── clearing_price.py        # Price floor/cap logic
├── scenarios/                   # Scenario engine (planned)
├── visualization/               # Chart generation (planned)
├── backtest/                    # JEPX backtest (planned)
├── output/
│   ├── results/                 # Dispatch & price CSVs
│   └── charts/                  # Generated figures
├── notebooks/                   # Analysis notebooks
├── requirements.txt
└── JP-Power-Dispatch-Economics-DevPlan.md
```

## How to Run

### Prerequisites

- Python 3.11+
- Dependencies: `pip install -r requirements.txt`

### Process raw data

```bash
python -X utf8 data/process_raw.py
```

This reads from `data/raw/` and writes standardised CSVs to `data/processed/`.

### Run the full pipeline

```bash
python main.py
```

This loads inputs, runs dispatch for all ~16,000 half-hourly intervals, and writes results to `output/results/`.

To run only specific stages:

```bash
python main.py --steps load       # validate inputs only
python main.py --steps dispatch   # load + dispatch
```

### Run the dispatch engine directly

```bash
python -m engine.dispatch_solver
```

## Model Limitations

1. **Copper plate** — No transmission network; cannot reproduce regional price divergence
2. **No unit commitment** — Startup costs, min up/down times, and ramping constraints are ignored in Level 1
3. **Hydro as baseload** — Real hydro is reservoir-constrained and dispatchable; modelled as always-available
4. **Fixed fleet** — No seasonal maintenance outages or forced outage rates
5. **No storage** — Pumped hydro and battery storage are excluded
6. **Fuel price granularity** — Monthly prices mapped to half-hourly; no intra-month volatility

## Planned Enhancements

- **Scenario engine** — Nuclear restart, LNG price shock, solar doubling, demand growth
- **LP/MILP unit commitment** — Startup costs, min stable generation, ramping via PuLP
- **Visualisation suite** — Merit-order curves, duck curves, seasonal heatmaps, dispatch stacks
- **Formal backtest module** — Seasonal/hourly error decomposition, bias attribution
- **Multi-region** — Regional nodes with interconnector capacity constraints

## License

This project is an analytical portfolio piece for educational and demonstration purposes. Raw data sources retain their original licenses.
