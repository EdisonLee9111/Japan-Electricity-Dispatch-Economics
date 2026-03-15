# Japan Electricity Dispatch Economics — Development Plan

## 1. Project Identity

**Repository name:** `Japan-Electricity-Dispatch-Economics`

**One-line pitch:** A Python-based production cost model simulating hourly electricity dispatch across Japan's generation fleet, with scenario analysis focused on the duck curve dynamics created by rising solar penetration and seasonal demand bimodality.

**Core research question:** In Japan's dual-peak demand structure (summer cooling + winter heating) with accelerating solar PV deployment, how do the dispatch economics and capacity utilization of different generator types shift across seasons and time-of-day — and what happens to these dynamics under nuclear restart and fuel price shock scenarios?

---

## 2. Target Audience & Strategic Context

This project is built as a portfolio piece targeting the **Energy Market Analyst (Solution Modeling Services)** role at **Energy Exemplar** (Japan, Remote). The JD requires:

- Production cost modeling, capacity expansion, and market forecasting
- Scenario analysis and interpretation of model results
- Python/SQL scripting for data preprocessing and scenario generation
- Familiarity with ISO/RTO operations (OCCTO in Japan context)
- Exposure to optimization solvers (Gurobi, GAMS, CPLEX) is a plus

The project directly demonstrates these capabilities in a simplified but analytically rigorous form. It also complements the author's existing LNG market research portfolio (Global LNG Arbitrage Monitor, Structural Event Study Framework, LNG-Alpha-Feed) by extending the analytical chain into downstream power market dispatch — where LNG is consumed as fuel.

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  LAYER 1: DATA INGESTION & FLEET DATABASE               │
│  JEPX prices │ OCCTO capacity │ Fuel prices │ Demand    │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  LAYER 2: MERIT ORDER ENGINE                             │
│  Marginal cost calc │ Supply curve │ Dispatch solver     │
│  (includes startup cost logic & min stable generation)   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  LAYER 3: SCENARIO ANALYSIS                              │
│  Nuclear restart │ Fuel shock │ Renewable ramp           │
│  Parameterized via config; compare base vs counterfactual│
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│  LAYER 4: VISUALIZATION & OUTPUT                         │
│  Merit order curve │ Price duration │ Generation mix     │
│  Seasonal dispatch heatmap │ Backtest vs JEPX actuals    │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Data Sources (All Publicly Available)

| Data | Source | Format | Granularity | Notes |
|------|--------|--------|-------------|-------|
| Spot electricity prices | JEPX (Japan Electric Power Exchange) | CSV download from jepx.org | 30-min intervals | Day-ahead market; use as backtest target |
| Generation capacity by plant/fuel type | OCCTO (Organization for Cross-regional Coordination of Transmission Operators) | PDF/Excel from occto.or.jp | Plant-level | Annual supply plan data; aggregate to fleet-level by fuel type |
| Electricity demand (actual) | OCCTO / TEPCO/Kansai EP open data | CSV | 30-min or hourly | Regional demand profiles; can start with single-region (Tokyo area) |
| Fuel prices — LNG (JKM) | World Bank Commodity Prices (Pink Sheet) or IMF Primary Commodity Prices | Excel/CSV | Monthly | Free proxy for JKM; alternatively use hardcoded reasonable assumptions |
| Fuel prices — Coal | World Bank / globalcoaltracker | Monthly | Newcastle benchmark |
| Fuel prices — Uranium | Publicly available spot estimates | Monthly | Relatively stable; can use fixed assumption |
| Solar/Wind output profiles | METI / ISEP (Institute for Sustainable Energy Policies) | CSV | Hourly | Actual renewable output data for Japan |
| Generator technical parameters | METI power survey / academic literature | Various | Per fuel type | Heat rates, efficiency, min stable generation, startup costs, ramp rates |

**Data strategy:** If real-time API access is blocked or cumbersome, use representative historical datasets (e.g., FY2023 or FY2024) downloaded manually and stored in `data/raw/`. The analytical framework matters more than live data feeds for this portfolio project.

**Fallback:** For any data that proves too difficult to obtain in clean form, construct synthetic but realistic datasets based on published statistics (e.g., METI energy white paper figures for installed capacity by fuel type). Document all assumptions explicitly.

---

## 5. Module Specifications

### 5.1 Module: `data/` — Data Ingestion & Fleet Database

**Purpose:** Load, clean, and structure all input data into a consistent internal format.

**Files:**
```
data/
├── raw/                    # Original downloaded files (gitignored if large)
├── processed/              # Cleaned CSVs ready for model consumption
├── fleet_database.py       # Generator fleet construction
├── demand_loader.py        # Demand profile loading and processing
├── fuel_prices.py          # Fuel price time series
└── renewable_profiles.py   # Solar/wind capacity factor profiles
```

**`fleet_database.py` — Core data structure:**

```python
# Each generator "unit" is actually a fleet-level aggregate by fuel type
# This is a deliberate simplification — we model fuel-type fleets, not individual plants

@dataclass
class GeneratorFleet:
    fuel_type: str           # "nuclear", "coal", "lng_ccgt", "lng_ocgt", "oil", "hydro", "solar", "wind", "biomass"
    installed_capacity_mw: float
    min_stable_generation_pct: float   # e.g., 0.40 for coal, 0.50 for nuclear, 0.30 for CCGT
    heat_rate_mmbtu_per_mwh: float     # Conversion efficiency (lower = more efficient)
    variable_om_usd_per_mwh: float     # Variable O&M cost
    startup_cost_cold_usd: float       # Cost per MW to cold-start the fleet
    startup_cost_warm_usd: float       # Cost per MW for warm restart (< 8 hours off)
    startup_cost_hot_usd: float        # Cost per MW for hot restart (< 2 hours off)
    min_up_time_hours: int             # Minimum hours online once started
    min_down_time_hours: int           # Minimum hours offline once shut down
    ramp_rate_mw_per_hour: float       # Max ramp up/down per hour
    must_run: bool                     # True for nuclear, run-of-river hydro
    marginal_cost_usd_per_mwh: float   # Computed: fuel_price / efficiency + variable_om
```

**Japan fleet composition (approximate, for reference):**

| Fuel Type | Installed Capacity (GW) | Typical Heat Rate | Min Stable Gen | Must-Run |
|-----------|------------------------|-------------------|----------------|----------|
| Nuclear | ~10 (currently operational) | 10.5 MMBtu/MWh | 50% | Yes |
| Coal | ~45 | 9.5 MMBtu/MWh | 40% | No |
| LNG CCGT | ~65 | 7.0 MMBtu/MWh | 30% | No |
| LNG OCGT | ~15 | 10.0 MMBtu/MWh | 20% | No |
| Oil | ~15 | 11.0 MMBtu/MWh | 20% | No |
| Hydro (dispatchable) | ~22 | N/A (zero marginal) | 0% | No |
| Solar PV | ~80 | N/A (zero marginal) | N/A | Must-take |
| Wind | ~5 | N/A (zero marginal) | N/A | Must-take |
| Biomass | ~5 | 12.0 MMBtu/MWh | 30% | No |

These numbers should be validated against the latest OCCTO/METI data during implementation.

---

### 5.2 Module: `engine/` — Merit Order & Dispatch Solver

**Purpose:** The analytical core. Takes fleet data + demand + fuel prices → outputs hourly dispatch schedule and clearing prices.

**Files:**
```
engine/
├── merit_order.py          # Static merit order curve construction
├── dispatch_solver.py      # Hourly dispatch with unit commitment constraints
├── startup_cost.py         # Startup cost calculation logic
└── clearing_price.py       # Market clearing price determination
```

**`merit_order.py` — Static merit order:**

For each hour, compute marginal cost per fuel type:
```
marginal_cost = (fuel_price_per_mmbtu × heat_rate_mmbtu_per_mwh) + variable_om
```

Sort all generator fleets by marginal cost ascending. Renewables and nuclear (must-run/must-take) are placed at the bottom of the stack with zero or near-zero marginal cost.

Output: A supply curve — cumulative MW capacity on x-axis, marginal cost on y-axis. The intersection with demand gives the clearing price.

**`dispatch_solver.py` — The core solver (TWO implementation levels):**

**Level 1 (MVP — implement first): Simple merit order dispatch**
- For each hour: sort generators by marginal cost, dispatch lowest-cost first until demand is met.
- Clearing price = marginal cost of the last dispatched unit (the marginal generator).
- Renewables dispatched first as must-take (output = installed_capacity × capacity_factor_for_hour).
- Nuclear dispatched as must-run at constant output.
- No inter-temporal constraints (each hour solved independently).

**Level 2 (Full — implement after MVP works): LP-based unit commitment**
- Use `PuLP` (open-source LP solver, pip install pulp) to formulate as optimization:
  - **Objective:** Minimize total system cost = Σ(generation_mw × marginal_cost) + Σ(startup_costs)
  - **Constraints:**
    - Demand balance: Σ generation = demand for each hour
    - Capacity limits: min_stable_gen ≤ generation ≤ installed_capacity (when online)
    - Binary on/off status per fleet per hour
    - Startup cost triggered when status changes from 0→1
    - Min up time / min down time constraints
    - Ramp rate constraints between consecutive hours
  - **Decision variables:** generation_mw[fleet, hour], online_status[fleet, hour] (binary)

This LP formulation is a simplified version of what PLEXOS solves — demonstrating familiarity with the optimization approach without needing Gurobi/CPLEX.

**`startup_cost.py` — Startup cost logic:**

```python
def compute_startup_cost(fleet: GeneratorFleet, hours_offline: int) -> float:
    """
    Startup cost depends on how long the unit has been offline.
    - Hot start: offline < 2 hours (boiler still warm)
    - Warm start: offline 2-8 hours
    - Cold start: offline > 8 hours (full restart needed)

    This matters most for LNG and coal units that cycle on/off
    during duck curve conditions (solar noon surplus).
    """
    if hours_offline < 2:
        return fleet.startup_cost_hot_usd * fleet.installed_capacity_mw
    elif hours_offline < 8:
        return fleet.startup_cost_warm_usd * fleet.installed_capacity_mw
    else:
        return fleet.startup_cost_cold_usd * fleet.installed_capacity_mw
```

**Why this matters analytically:** During spring/autumn solar-rich hours, LNG CCGT units face a choice: shut down for 4-6 hours (incurring warm/cold restart costs) or keep running at minimum stable generation even when the clearing price is below their marginal cost. The LP solver captures this trade-off. The simple merit order dispatch (Level 1) does NOT — which is why Level 2 exists and why explaining this difference is valuable in an interview.

**`clearing_price.py`:**
- In simple dispatch: price = marginal cost of the last dispatched unit.
- In LP dispatch: price = shadow price (dual variable) of the demand balance constraint — the marginal cost of serving one more MW of demand.
- Handle edge cases: price floor at 0 (or allow negative prices if modeling curtailment), price cap at JEPX maximum (99.99 JPY/kWh historically).

---

### 5.3 Module: `scenarios/` — Scenario Analysis Engine

**Purpose:** Define and execute counterfactual scenarios, comparing against a base case.

**Files:**
```
scenarios/
├── config.py               # Scenario parameter definitions
├── runner.py               # Execute base + scenarios, collect results
└── comparator.py           # Compute deltas and summary statistics
```

**`config.py` — Scenario definitions:**

```python
@dataclass
class ScenarioConfig:
    name: str
    description: str
    # Fleet modifications
    nuclear_capacity_gw: float = 10.0    # Base: ~10 GW operational
    solar_capacity_gw: float = 80.0      # Base: ~80 GW installed
    wind_capacity_gw: float = 5.0        # Base: ~5 GW installed
    # Fuel price multipliers (1.0 = no change)
    lng_price_multiplier: float = 1.0
    coal_price_multiplier: float = 1.0
    oil_price_multiplier: float = 1.0
    # Demand multiplier
    demand_multiplier: float = 1.0
```

**Pre-built scenarios (minimum 3, implement all):**

1. **Base case:** Current fleet composition and fuel prices.
2. **Nuclear restart (aggressive):** Nuclear capacity from 10 GW → 25 GW (reflecting restart of additional idled reactors). Expected impact: lower clearing prices, increased solar curtailment risk during low-demand hours, reduced LNG fleet utilization.
3. **LNG price shock:** LNG price × 1.5 (simulating supply disruption or Asian premium spike). Expected impact: LNG units move up the merit order, coal becomes more competitive, clearing prices rise significantly during LNG-marginal hours.
4. **Solar doubling:** Solar capacity from 80 GW → 160 GW (2030 trajectory). Expected impact: deeper duck curve, more hours of near-zero prices, increased cycling burden on thermal units.

**`runner.py`:** Runs the dispatch solver for each scenario over the same demand profile (full year, 8760 hours). Stores results in structured format for comparison.

**`comparator.py`:** For each scenario vs base:
- Annual average clearing price change
- Change in generation mix (TWh by fuel type)
- Change in capacity factor by fuel type
- Change in number of startup events for thermal units
- Change in hours where price < marginal cost of LNG CCGT (proxy for duck curve severity)

---

### 5.4 Module: `visualization/` — Charts & Output

**Purpose:** Generate publication-quality charts that tell the analytical story.

**Files:**
```
visualization/
├── merit_order_chart.py       # Static merit order curve
├── dispatch_stack.py          # Stacked area chart of hourly dispatch
├── price_duration.py          # Price duration curve
├── seasonal_heatmap.py        # Dispatch pattern heatmap (hour × month)
├── duck_curve.py              # Net load curve showing duck shape
├── scenario_comparison.py     # Side-by-side scenario results
└── backtest.py                # Simulated vs actual JEPX price comparison
```

**Required charts (minimum — all must be in final repo):**

1. **Merit order curve:** X = cumulative capacity (GW), Y = marginal cost (JPY/kWh or USD/MWh). Color-coded by fuel type. This is the signature chart of production cost modeling.

2. **Duck curve visualization:** Net load (demand minus solar/wind) plotted for a typical spring day, showing the "belly" during solar noon and evening ramp. Overlay with actual dispatch to show which units fill the belly and which handle the ramp.

3. **Seasonal dispatch heatmap:** 24 hours (x-axis) × 12 months (y-axis), colored by dominant fuel type or by clearing price. Should visually show how LNG shifts from baseload in winter to peaker in spring.

4. **Dispatch stack (representative days):** Stacked area chart showing hourly generation by fuel type for 4 representative days: winter peak, summer peak, spring solar-rich, autumn solar-rich. Y-axis = MW, X-axis = hour of day.

5. **Price duration curve:** All 8760 hourly prices sorted descending. Shows how many hours per year the price exceeds various thresholds. Compare base vs scenario overlaid.

6. **Scenario comparison dashboard:** Bar charts comparing key metrics (average price, generation mix, capacity factors) across scenarios.

7. **Backtest chart:** Simulated clearing price vs actual JEPX spot price, time series. Include correlation coefficient and RMSE. Explain deviations (interconnector constraints, renewables forecast error, strategic bidding not modeled, etc.).

**Library:** Use `matplotlib` for all charts. Consistent color scheme for fuel types across all charts:
- Nuclear: purple
- Coal: dark gray
- LNG CCGT: orange
- LNG OCGT: light orange
- Oil: brown
- Hydro: blue
- Solar: gold/yellow
- Wind: light blue/teal
- Biomass: green

---

### 5.5 Module: `backtest/` — Validation Against JEPX

**Purpose:** Compare model output to actual market prices to establish credibility.

**Files:**
```
backtest/
├── price_comparison.py     # Simulated vs actual price time series
├── metrics.py              # RMSE, MAE, correlation, R²
└── deviation_analysis.py   # Analyze when and why model diverges
```

**Expected model performance:** A simplified merit order model will NOT perfectly match JEPX prices. This is expected and analytically valuable. Key sources of deviation:

1. **Interconnector constraints:** Japan has 10 grid regions with limited interconnection. The model treats Japan as a single copper-plate (no transmission constraints). When actual congestion occurs, regional prices diverge — the model can't capture this.
2. **Strategic bidding:** JEPX participants bid strategically, not at marginal cost. The model assumes competitive marginal cost bidding.
3. **Renewable forecast error:** The model uses actual solar/wind output (perfect hindsight). Real dispatch uses forecasts, which create imbalances.
4. **Demand response and storage:** Not modeled.
5. **Balancing market:** Only day-ahead modeled; real-time balancing market interactions ignored.

**The value is in explaining the deviations, not in achieving high R².** Being able to articulate WHY the model diverges from reality — and what additional features would close the gap — demonstrates deeper understanding than a black-box high-accuracy model.

---

## 6. Directory Structure (Final)

```
Japan-Electricity-Dispatch-Economics/
├── README.md                   # Project overview, methodology, key findings
├── requirements.txt            # Python dependencies
├── config/
│   └── settings.yaml           # Global config (paths, units, color schemes)
├── data/
│   ├── raw/                    # Original data files
│   ├── processed/              # Cleaned model-ready data
│   ├── fleet_database.py
│   ├── demand_loader.py
│   ├── fuel_prices.py
│   └── renewable_profiles.py
├── engine/
│   ├── merit_order.py
│   ├── dispatch_solver.py
│   ├── startup_cost.py
│   └── clearing_price.py
├── scenarios/
│   ├── config.py
│   ├── runner.py
│   └── comparator.py
├── visualization/
│   ├── merit_order_chart.py
│   ├── dispatch_stack.py
│   ├── price_duration.py
│   ├── seasonal_heatmap.py
│   ├── duck_curve.py
│   ├── scenario_comparison.py
│   └── backtest.py
├── backtest/
│   ├── price_comparison.py
│   ├── metrics.py
│   └── deviation_analysis.py
├── notebooks/                  # Jupyter notebooks for exploration (optional)
│   └── exploration.ipynb
├── output/                     # Generated charts and results (gitignored)
│   ├── charts/
│   └── results/
└── main.py                     # CLI entry point: run dispatch + scenarios + charts
```

---

## 7. Dependencies

```
# requirements.txt
pandas>=2.0
numpy>=1.24
matplotlib>=3.7
seaborn>=0.12
pulp>=2.7                  # LP solver for unit commitment
pyyaml>=6.0                # Config loading
openpyxl>=3.1              # Excel data reading
requests>=2.28             # Data download (if applicable)
scipy>=1.10                # Statistical analysis for backtest
```

---

## 8. Development Schedule (7 Days)

| Day | Focus | Deliverable | Acceptance Criteria |
|-----|-------|-------------|---------------------|
| 1 | Data acquisition & cleaning | `data/` module complete | Fleet database constructed; demand profiles loaded; fuel price time series ready. All stored in `data/processed/`. |
| 2 | Merit order engine (Level 1 — simple dispatch) | `engine/merit_order.py` + `engine/clearing_price.py` | Can compute marginal costs, build supply curve, find clearing price for a single hour. Unit tests pass. |
| 3 | Full-year dispatch (Level 1) + startup cost logic | `engine/dispatch_solver.py` (simple) + `engine/startup_cost.py` | 8760-hour dispatch runs in < 2 minutes. Startup cost computed but not yet optimized. |
| 4 | LP-based dispatch (Level 2) + scenario engine | `engine/dispatch_solver.py` (LP) + `scenarios/` module | PuLP solver runs for representative week. All 4 scenarios defined and executable. |
| 5 | Visualization — core charts | `visualization/` module (charts 1-5) | Merit order curve, duck curve, seasonal heatmap, dispatch stack, price duration curve all generate correctly. |
| 6 | Scenario comparison + backtest | Remaining `visualization/` + `backtest/` | Scenario comparison dashboard complete. Backtest correlation computed and deviation analysis documented. |
| 7 | README, polish, repo launch | Final README with methodology + findings | Repository is public, README tells a clear analytical story, all charts render, code runs end-to-end from `main.py`. |

---

## 9. README Structure (Final Deliverable)

The README is the most important file in the repo — it's what the hiring manager reads. Structure:

1. **Title + one-line description**
2. **Research question** (2-3 sentences)
3. **Key findings** (3-4 bullet points with chart thumbnails — e.g., "LNG CCGT capacity factor drops from X% in winter to Y% in spring due to solar displacement")
4. **Methodology** (brief: merit order dispatch → LP unit commitment → scenario analysis)
5. **Data sources** (table with links)
6. **How to run** (`pip install -r requirements.txt` → `python main.py`)
7. **Charts gallery** (embedded PNGs of all 7 chart types)
8. **Model limitations & future work** (interconnector constraints, unit-level optimization, capacity market simulation)
9. **About the author** (link to other LNG projects)

---

## 10. Deferred Features (If Time Permits / Future Development)

These are explicitly out of scope for the initial one-week build but documented as potential extensions:

1. **Interconnector constraints:** Model Japan's 10 grid regions with transmission capacity limits between them. Would require regional demand/supply data and a network flow model.
2. **Unit-level optimization:** Disaggregate fleet-level to individual plant-level dispatch. Much larger LP problem but more realistic.
3. **Capacity market simulation:** Model Japan's planned capacity market mechanism; analyze whether peaking units recover fixed costs.
4. **Battery storage dispatch:** Add utility-scale storage as a dispatchable resource that charges during solar noon and discharges during evening peak.
5. **Demand response:** Model price-responsive demand that reduces during high-price hours.
6. **Carbon pricing scenario:** Add CO2 cost component to marginal costs; analyze fuel switching dynamics.

---

## 11. Key Technical Decisions & Rationale

| Decision | Rationale |
|----------|-----------|
| Fleet-level aggregation (not plant-level) | Reduces data requirements and solver complexity. Sufficient to demonstrate dispatch dynamics and scenario analysis. Plant-level is a documented future extension. |
| Single copper-plate (no regional transmission) | Avoids network flow modeling complexity. Most duck curve dynamics are visible at national level. Deviation from JEPX prices is documented and explained. |
| PuLP over Gurobi/CPLEX | Open-source, zero cost, pip-installable. JD lists commercial solvers as "a plus" — using PuLP demonstrates optimization thinking without licensing barriers. Can mention Gurobi familiarity in interview. |
| Python over Julia/GAMS | JD explicitly lists Python. Maximizes accessibility for reviewers. |
| Matplotlib over Plotly/Dash | Static charts in README are more portable than interactive dashboards for GitHub portfolio. Can add Jupyter notebook with interactive plots as optional extra. |
| Yearly simulation (8760h) | Full year captures seasonal variation — the core analytical dimension. Shorter periods miss the winter-summer contrast. |

---

## 12. Interview Talking Points (Prepared from Project)

The project should enable the author to speak fluently on:

1. **"Walk me through how you built the dispatch model."** → Data ingestion, marginal cost calculation, merit order stacking, LP formulation with PuLP, startup cost logic.
2. **"Why does your model deviate from actual JEPX prices?"** → Copper-plate assumption, competitive bidding assumption, perfect foresight on renewables. Each deviation maps to a real modeling challenge that PLEXOS addresses.
3. **"What happens when Japan restarts more nuclear?"** → Clearing prices drop, duck curve deepens, LNG capacity factor collapses, missing money problem for peakers.
4. **"How would you improve this model?"** → Regional transmission (→ PLEXOS zonal model), unit-level commitment (→ larger MILP), battery storage, capacity market. Each maps to an Energy Exemplar product feature.
5. **"What's the duck curve and why does it matter for Japan?"** → Solar noon surplus, evening ramp, thermal cycling costs, implications for fuel procurement planning.
