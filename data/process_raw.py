"""
data/process_raw.py
-------------------
将 data/raw/ 下的原始数据清洗并输出标准化 CSV 到 data/processed/。

执行方式：
    python data/process_raw.py

输出文件：
    data/processed/jepx_prices.csv       -- JEPX 30分钟现货价格
    data/processed/demand_profile.csv    -- 全国电力需求（30分钟 → 小时）
    data/processed/renewable_profiles.csv -- 光伏/风电容量因子时序
    data/processed/fuel_prices.csv       -- 燃料价格月度 → 小时填充
    data/processed/fleet.csv             -- 机组参数数据库（手工建立）

建模假设（均记录在此）：
    - 单节点（copper plate）：全国不建模区域联络线约束
    - 主回测目标：system_price（システムプライス）
    - 时间粒度：30分钟原始数据，聚合为1小时供 MVP 引擎使用
    - USD→JPY 汇率：150 JPY/USD（固定假设，FY2025 平均水平）
    - 光伏装机：80,000 MW；风电装机：5,000 MW（来自 DevPlan 估算）
    - LNG 价格：Japan CIF（$/MMBtu），World Bank Pink Sheet
    - 煤炭价格：Australian Newcastle（$/mt）
    - 原油价格：WTI（$/bbl），用于石油火力边际成本
    - 2026Q1 燃料价格：使用 2025M12 数据向前填充（Pink Sheet 截止 2025M12）
"""

import os
import sys

import numpy as np
import openpyxl
import pandas as pd

try:
    import yaml
except ImportError:
    yaml = None

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
ASSUMPTIONS_PATH = os.path.join(RAW_DIR, "assumptions.yml")
os.makedirs(PROCESSED_DIR, exist_ok=True)

# 固定假设
USD_JPY = 150.0  # JPY per USD
SOLAR_INSTALLED_MW = 80_000.0
WIND_INSTALLED_MW = 5_000.0


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def log(msg):
    print(f"[process_raw] {msg}")


def load_assumptions():
    """
    读取 data/raw/assumptions.yml，并返回解析后的配置字典。
    若文件缺失、PyYAML 未安装或结构不合法，则抛出明确错误。
    """
    if yaml is None:
        raise ImportError(
            "缺少 PyYAML 依赖，无法读取 assumptions.yml。请先安装：pip install pyyaml"
        )

    if not os.path.exists(ASSUMPTIONS_PATH):
        raise FileNotFoundError(f"未找到 assumptions.yml: {ASSUMPTIONS_PATH}")

    with open(ASSUMPTIONS_PATH, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not isinstance(config, dict):
        raise ValueError("assumptions.yml 顶层结构必须是字典。")

    if "generators" not in config:
        raise ValueError("assumptions.yml 缺少顶层字段: generators")

    if "global_assumptions" not in config:
        raise ValueError("assumptions.yml 缺少顶层字段: global_assumptions")

    if not isinstance(config["generators"], dict) or not config["generators"]:
        raise ValueError("assumptions.yml 中 generators 必须是非空字典。")

    return config


# ---------------------------------------------------------------------------
# 1. JEPX 现货价格
# ---------------------------------------------------------------------------
def process_jepx():
    """
    读取 spot_summary_2025.csv（Shift-JIS），
    将 受渡日 + 時刻コード 转换为 timestamp（30分钟起始时刻），
    输出标准化价格表。
    """
    log("处理 JEPX 现货价格...")
    fpath = os.path.join(RAW_DIR, "spot_summary_2025.csv")
    df = pd.read_csv(fpath, encoding="shift-jis")

    # 重命名列（按位置，避免编码问题）
    col_map = {
        df.columns[0]: "delivery_date",
        df.columns[1]: "time_code",
        df.columns[2]: "sell_bid_volume_kwh",
        df.columns[3]: "buy_bid_volume_kwh",
        df.columns[4]: "contract_volume_kwh",
        df.columns[5]: "system_price_jpy_kwh",
        df.columns[6]: "hokkaido_price_jpy_kwh",
        df.columns[7]: "tohoku_price_jpy_kwh",
        df.columns[8]: "tokyo_price_jpy_kwh",
        df.columns[9]: "chubu_price_jpy_kwh",
        df.columns[10]: "hokuriku_price_jpy_kwh",
        df.columns[11]: "kansai_price_jpy_kwh",
        df.columns[12]: "chugoku_price_jpy_kwh",
        df.columns[13]: "shikoku_price_jpy_kwh",
        df.columns[14]: "kyushu_price_jpy_kwh",
        df.columns[15]: "sell_block_bid_kwh",
        df.columns[16]: "sell_block_contract_kwh",
        df.columns[17]: "buy_block_bid_kwh",
        df.columns[18]: "buy_block_contract_kwh",
    }
    df = df.rename(columns=col_map)

    # 构造 timestamp：time_code 1→00:00, 2→00:30, ..., 48→23:30
    df["delivery_date"] = pd.to_datetime(df["delivery_date"], format="%Y/%m/%d")
    df["timestamp"] = df["delivery_date"] + pd.to_timedelta(
        (df["time_code"] - 1) * 30, unit="min"
    )

    # 选取输出列
    out_cols = [
        "timestamp",
        "system_price_jpy_kwh",
        "hokkaido_price_jpy_kwh",
        "tohoku_price_jpy_kwh",
        "tokyo_price_jpy_kwh",
        "chubu_price_jpy_kwh",
        "hokuriku_price_jpy_kwh",
        "kansai_price_jpy_kwh",
        "chugoku_price_jpy_kwh",
        "shikoku_price_jpy_kwh",
        "kyushu_price_jpy_kwh",
        "contract_volume_kwh",
        "sell_bid_volume_kwh",
        "buy_bid_volume_kwh",
    ]
    out = df[out_cols].copy()

    # 同时生成 JPY/MWh 版本（模型内部单位）
    price_cols = [c for c in out_cols if c.endswith("_jpy_kwh")]
    for c in price_cols:
        out[c.replace("_jpy_kwh", "_jpy_mwh")] = out[c] * 1000.0

    # 排序并去重
    out = (
        out.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    )

    out_path = os.path.join(PROCESSED_DIR, "jepx_prices.csv")
    out.to_csv(out_path, index=False)
    log(
        f"  -> {out_path}  ({len(out)} 行，{out['timestamp'].min()} ~ {out['timestamp'].max()})"
    )
    return out


# ---------------------------------------------------------------------------
# 2. 全国需求 + 可再生能源实绩
# ---------------------------------------------------------------------------
def process_national_dispatch():
    """
    读取 download.csv（UTF-8 with BOM），
    解析全国需求 + 各燃料发电量 + JEPX 系统价格，
    输出 demand_profile.csv 和 renewable_profiles.csv。
    """
    log("处理全国需求与发电实绩（download.csv）...")
    fpath = os.path.join(RAW_DIR, "download.csv")

    # 第1行是"全国"标注，第2行是列名
    df = pd.read_csv(fpath, encoding="utf-8-sig", skiprows=1)

    # 重命名（按位置）
    col_map = {
        df.columns[0]: "date",
        df.columns[1]: "time",
        df.columns[2]: "other_misc",
        df.columns[3]: "nuclear",
        df.columns[4]: "lng",
        df.columns[5]: "hydro",
        df.columns[6]: "geothermal",
        df.columns[7]: "biomass",
        df.columns[8]: "solar",
        df.columns[9]: "wind",
        df.columns[10]: "pumped_hydro_charge",
        df.columns[11]: "pumped_hydro_gen",
        df.columns[12]: "interconnector_receive",
        df.columns[13]: "interconnector_send",
        df.columns[14]: "solar_curtailment",
        df.columns[15]: "wind_curtailment",
        df.columns[16]: "coal",
        df.columns[17]: "oil",
        df.columns[18]: "other_thermal",
        df.columns[19]: "battery_charge",
        df.columns[20]: "battery_discharge",
        df.columns[21]: "demand",
        df.columns[22]: "system_price_jpy_kwh",
    }
    df = df.rename(columns=col_map)

    # 构造 timestamp
    df["timestamp"] = pd.to_datetime(
        df["date"].astype(str) + " " + df["time"].astype(str), format="%Y/%m/%d %H:%M"
    )

    # 数值化（去除可能的字符串）
    num_cols = [
        "nuclear",
        "lng",
        "hydro",
        "geothermal",
        "biomass",
        "solar",
        "wind",
        "pumped_hydro_charge",
        "pumped_hydro_gen",
        "solar_curtailment",
        "wind_curtailment",
        "coal",
        "oil",
        "other_thermal",
        "battery_charge",
        "battery_discharge",
        "demand",
        "system_price_jpy_kwh",
        "other_misc",
        "interconnector_receive",
        "interconnector_send",
    ]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)

    # ---- 2a. demand_profile.csv ----
    demand_cols = [
        "timestamp",
        "demand",
        "nuclear",
        "lng",
        "coal",
        "oil",
        "hydro",
        "geothermal",
        "biomass",
        "solar",
        "wind",
        "solar_curtailment",
        "wind_curtailment",
        "pumped_hydro_charge",
        "pumped_hydro_gen",
        "battery_charge",
        "battery_discharge",
        "other_thermal",
        "other_misc",
        "interconnector_receive",
        "interconnector_send",
        "system_price_jpy_kwh",
    ]
    demand_out = df[demand_cols].copy()
    demand_path = os.path.join(PROCESSED_DIR, "demand_profile.csv")
    demand_out.to_csv(demand_path, index=False)
    log(f"  -> {demand_path}  ({len(demand_out)} 行)")

    # ---- 2b. renewable_profiles.csv ----
    # 容量因子 = 实际出力 / 装机容量
    # solar_available = solar + solar_curtailment（弃电前的可用量）
    ren = df[
        ["timestamp", "solar", "wind", "solar_curtailment", "wind_curtailment"]
    ].copy()
    ren["solar_available_mw"] = ren["solar"] + ren["solar_curtailment"]
    ren["wind_available_mw"] = ren["wind"] + ren["wind_curtailment"]
    ren["solar_cf"] = (ren["solar_available_mw"] / SOLAR_INSTALLED_MW).clip(0, 1)
    ren["wind_cf"] = (ren["wind_available_mw"] / WIND_INSTALLED_MW).clip(0, 1)
    ren["solar_actual_mw"] = ren["solar"]
    ren["wind_actual_mw"] = ren["wind"]

    ren_out = ren[
        [
            "timestamp",
            "solar_cf",
            "wind_cf",
            "solar_actual_mw",
            "wind_actual_mw",
            "solar_available_mw",
            "wind_available_mw",
        ]
    ].copy()
    ren_path = os.path.join(PROCESSED_DIR, "renewable_profiles.csv")
    ren_out.to_csv(ren_path, index=False)
    log(f"  -> {ren_path}  ({len(ren_out)} 行)")
    log(
        f"     solar_cf max={ren_out['solar_cf'].max():.3f}, wind_cf max={ren_out['wind_cf'].max():.3f}"
    )

    return demand_out, ren_out


# ---------------------------------------------------------------------------
# 3. 燃料价格
# ---------------------------------------------------------------------------
def process_fuel_prices():
    """
    读取 CMO-Historical-Data-Monthly.xlsx（World Bank Pink Sheet），
    提取 LNG Japan、Australian Coal、WTI Oil 月度价格，
    映射到 FY2025（2025/04 - 2026/03）的 30 分钟时间序列，
    并换算为模型内部单位（JPY/MMBtu 或 JPY/mt 等，供边际成本计算使用）。
    """
    log("处理燃料价格（CMO Pink Sheet）...")
    fpath = os.path.join(RAW_DIR, "CMO-Historical-Data-Monthly.xlsx")

    wb = openpyxl.load_workbook(fpath, read_only=True, data_only=True)
    ws = wb["Monthly Prices"]
    rows = list(ws.iter_rows(values_only=True))

    # 行结构：行0-3=说明，行4=列名，行5=单位，行6+=数据
    headers = rows[4]
    data_rows = rows[6:]

    # 列索引（从 DATA_MANIFEST 确认）
    COL_PERIOD = 0
    COL_CRUDE_WTI = 4  # $/bbl
    COL_COAL_AUS = 5  # $/mt
    COL_LNG_JAPAN = 9  # $/MMBtu

    records = []
    for row in data_rows:
        period = row[COL_PERIOD]
        if not period or not isinstance(period, str):
            continue
        # 格式：2025M04
        try:
            year = int(period[:4])
            month = int(period[5:])
        except (ValueError, IndexError):
            continue
        records.append(
            {
                "year": year,
                "month": month,
                "lng_japan_usd_mmbtu": row[COL_LNG_JAPAN],
                "coal_aus_usd_mt": row[COL_COAL_AUS],
                "crude_wti_usd_bbl": row[COL_CRUDE_WTI],
            }
        )

    fuel_monthly = pd.DataFrame(records)
    fuel_monthly = fuel_monthly.dropna(subset=["lng_japan_usd_mmbtu"])
    fuel_monthly["date"] = pd.to_datetime(
        fuel_monthly["year"].astype(str)
        + "-"
        + fuel_monthly["month"].astype(str).str.zfill(2)
        + "-01"
    )

    # FY2025: 2025-04 to 2026-03
    # Pink Sheet 数据到 2025M12；2026Q1 用 2025M12 向前填充
    fy2025_months = pd.date_range("2025-04-01", "2026-03-01", freq="MS")
    monthly_indexed = fuel_monthly.set_index("date")[
        ["lng_japan_usd_mmbtu", "coal_aus_usd_mt", "crude_wti_usd_bbl"]
    ]

    # 对 FY2025 区间做重索引（向前填充缺失月份）
    monthly_fy = monthly_indexed.reindex(fy2025_months, method="ffill")
    monthly_fy.index.name = "month_start"
    monthly_fy = monthly_fy.reset_index()

    # 换算为 JPY（固定汇率 USD_JPY = 150）
    monthly_fy["lng_japan_jpy_mmbtu"] = monthly_fy["lng_japan_usd_mmbtu"] * USD_JPY
    monthly_fy["coal_aus_jpy_mt"] = monthly_fy["coal_aus_usd_mt"] * USD_JPY
    monthly_fy["crude_wti_jpy_bbl"] = monthly_fy["crude_wti_usd_bbl"] * USD_JPY

    # 将月度价格展开至 30 分钟时间序列（与 demand_profile 对齐）
    ts_index = pd.date_range("2025-04-01", "2026-03-31 23:30:00", freq="30min")
    ts_df = pd.DataFrame({"timestamp": ts_index})
    ts_df["month_start"] = (
        ts_df["timestamp"].values.astype("datetime64[M]").astype("datetime64[ns]")
    )

    merged = ts_df.merge(monthly_fy, on="month_start", how="left")

    # 选取输出列
    out_cols = [
        "timestamp",
        "lng_japan_usd_mmbtu",
        "coal_aus_usd_mt",
        "crude_wti_usd_bbl",
        "lng_japan_jpy_mmbtu",
        "coal_aus_jpy_mt",
        "crude_wti_jpy_bbl",
    ]
    out = merged[out_cols].copy()

    out_path = os.path.join(PROCESSED_DIR, "fuel_prices.csv")
    out.to_csv(out_path, index=False)
    log(f"  -> {out_path}  ({len(out)} 行)")
    log(f"     LNG Japan 均价: ${out['lng_japan_usd_mmbtu'].mean():.2f}/MMBtu")
    log(f"     Coal Aus 均价:  ${out['coal_aus_usd_mt'].mean():.2f}/mt")
    log(f"     Crude WTI 均价: ${out['crude_wti_usd_bbl'].mean():.2f}/bbl")

    # 同时输出月度汇总（便于检查）
    monthly_path = os.path.join(PROCESSED_DIR, "fuel_prices_monthly.csv")
    monthly_fy.to_csv(monthly_path, index=False)
    log(f"  -> {monthly_path}  (月度汇总)")

    return out


# ---------------------------------------------------------------------------
# 4. 机组参数数据库（fleet.csv）
# ---------------------------------------------------------------------------
def build_fleet():
    """
    从 data/raw/assumptions.yml 读取 fleet 技术与经济假设，
    构建 data/processed/fleet.csv。

    说明：
    - 输入配置使用 USD 计价
    - 输出 fleet.csv 保留原项目主要字段，并补充 USD 原始字段
    - ramp_rate_pct_per_hour 会转换为 ramp_rate_mw_per_hour
    """
    log("构建机组参数数据库（fleet.csv，来源：assumptions.yml）...")

    config = load_assumptions()
    generators = config["generators"]
    global_assumptions = config.get("global_assumptions", {})

    fx = float(global_assumptions.get("currency_exchange_rate_jpy_usd", USD_JPY))

    required_fields = [
        "installed_capacity_mw",
        "min_stable_generation_pct",
        "heat_rate_mmbtu_per_mwh",
        "variable_om_usd_per_mwh",
        "startup_cost_cold_usd_per_mw",
        "startup_cost_warm_usd_per_mw",
        "startup_cost_hot_usd_per_mw",
        "min_up_time_hours",
        "min_down_time_hours",
        "ramp_rate_pct_per_hour",
        "must_run",
        "capital_cost_usd_per_kw",
        "fixed_om_usd_per_kw_yr",
        "fuel_cost_usd_per_mmbtu",
    ]

    fleet_rows = []

    for fuel_type, params in generators.items():
        missing = [field for field in required_fields if field not in params]
        if missing:
            raise ValueError(
                f"assumptions.yml 中机组 `{fuel_type}` 缺少字段: {missing}"
            )

        installed_capacity_mw = float(params["installed_capacity_mw"])
        forced_outage_rate = float(params.get("forced_outage_rate", 0.0))
        planned_outage_rate = float(params.get("planned_outage_rate", 0.0))
        # Annual average availability (for backward compat / summary)
        availability_factor = 1.0 - forced_outage_rate - planned_outage_rate
        available_capacity_mw = installed_capacity_mw * availability_factor
        ramp_rate_pct_per_hour = float(params["ramp_rate_pct_per_hour"])
        must_run_mw = float(params.get("must_run_mw", 0.0))

        row = {
            "fuel_type": fuel_type,
            "installed_capacity_mw": installed_capacity_mw,
            "forced_outage_rate": forced_outage_rate,
            "planned_outage_rate": planned_outage_rate,
            "availability_factor": availability_factor,
            "available_capacity_mw": available_capacity_mw,
            "must_run_mw": must_run_mw,
            "min_stable_generation_pct": float(params["min_stable_generation_pct"]),
            "heat_rate_mmbtu_per_mwh": float(params["heat_rate_mmbtu_per_mwh"]),
            "variable_om_usd_per_mwh": float(params["variable_om_usd_per_mwh"]),
            "startup_cost_hot_usd_per_mw": float(params["startup_cost_hot_usd_per_mw"]),
            "startup_cost_warm_usd_per_mw": float(
                params["startup_cost_warm_usd_per_mw"]
            ),
            "startup_cost_cold_usd_per_mw": float(
                params["startup_cost_cold_usd_per_mw"]
            ),
            "capital_cost_usd_per_kw": float(params["capital_cost_usd_per_kw"]),
            "fixed_om_usd_per_kw_yr": float(params["fixed_om_usd_per_kw_yr"]),
            "fuel_cost_usd_per_mmbtu": float(params["fuel_cost_usd_per_mmbtu"]),
            "variable_om_jpy_mwh": float(params["variable_om_usd_per_mwh"]) * fx,
            "startup_cost_hot_jpy_per_mw": float(params["startup_cost_hot_usd_per_mw"])
            * fx,
            "startup_cost_warm_jpy_per_mw": float(
                params["startup_cost_warm_usd_per_mw"]
            )
            * fx,
            "startup_cost_cold_jpy_per_mw": float(
                params["startup_cost_cold_usd_per_mw"]
            )
            * fx,
            "min_up_time_hours": int(params["min_up_time_hours"]),
            "min_down_time_hours": int(params["min_down_time_hours"]),
            "ramp_rate_pct_per_hour": ramp_rate_pct_per_hour,
            "ramp_rate_mw_per_hour": installed_capacity_mw * ramp_rate_pct_per_hour,
            "must_run": bool(params["must_run"]),
            "notes": (
                f"Loaded from assumptions.yml; "
                f"fx={fx:.1f} JPY/USD; "
                f"ramp={ramp_rate_pct_per_hour:.2f} p.u./hour"
            ),
        }

        fleet_rows.append(row)

    fleet = pd.DataFrame(fleet_rows)

    # ── Carbon cost (GX-ETS) ─────────────────────────────────────────────
    carbon_price_jpy = float(global_assumptions.get("carbon_price_jpy_per_ton", 0.0))
    emission_factors = config.get("emission_factors_tco2_per_mwh", {})
    fleet["emission_factor_tco2_per_mwh"] = fleet["fuel_type"].map(
        lambda ft: float(emission_factors.get(ft, 0.0))
    )
    fleet["carbon_cost_jpy_per_mwh"] = (
        fleet["emission_factor_tco2_per_mwh"] * carbon_price_jpy
    )
    log(f"     碳价：{carbon_price_jpy:.0f} JPY/tCO2 (GX-ETS)")

    # 按 merit order 参考排序（must-run 优先，再按 heat rate 升序）
    fleet = fleet.sort_values(
        ["must_run", "heat_rate_mmbtu_per_mwh"], ascending=[False, True]
    ).reset_index(drop=True)

    out_path = os.path.join(PROCESSED_DIR, "fleet.csv")
    fleet.to_csv(out_path, index=False)
    log(f"  -> {out_path}  ({len(fleet)} 机组类型)")
    log(f"     总装机：{fleet['installed_capacity_mw'].sum():,.0f} MW")
    log(f"     汇率：{fx:.1f} JPY/USD")
    return fleet


# ---------------------------------------------------------------------------
# 5. 合并东京区域 ERIA 文件（参考用）
# ---------------------------------------------------------------------------
def process_eria_tokyo():
    """
    合并 eria_jukyu_YYYYMM_03.csv（东京区域），
    输出 eria_tokyo_area.csv 供区域分析参考。
    注意：模型主输入使用全国数据（download.csv），本文件仅作参考。
    """
    log("合并东京区域 ERIA 文件（参考）...")
    import glob

    files = sorted(glob.glob(os.path.join(RAW_DIR, "eria_jukyu_*_03.csv")))

    frames = []
    for f in files:
        df = pd.read_csv(f, encoding="utf-8", skiprows=1)
        df.columns = [
            "date",
            "time",
            "area_demand",
            "nuclear",
            "lng_thermal",
            "coal_thermal",
            "oil_thermal",
            "other_thermal",
            "hydro",
            "geothermal",
            "biomass",
            "solar_actual",
            "solar_curtailment",
            "wind_actual",
            "wind_curtailment",
            "pumped_hydro",
            "battery",
            "interconnector",
            "other",
            "total",
        ]
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)

    # 构造 timestamp
    combined["timestamp"] = pd.to_datetime(
        combined["date"].astype(str) + " " + combined["time"].astype(str),
        format="%Y/%m/%d %H:%M",
    )

    # 数值化
    num_cols = combined.columns.difference(["date", "time", "timestamp"])
    for c in num_cols:
        combined[c] = pd.to_numeric(combined[c], errors="coerce")

    combined = (
        combined.sort_values("timestamp")
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )

    # 选取输出列
    out_cols = [
        "timestamp",
        "area_demand",
        "nuclear",
        "lng_thermal",
        "coal_thermal",
        "oil_thermal",
        "other_thermal",
        "hydro",
        "geothermal",
        "biomass",
        "solar_actual",
        "solar_curtailment",
        "wind_actual",
        "wind_curtailment",
        "pumped_hydro",
        "battery",
        "interconnector",
        "other",
        "total",
    ]
    out = combined[out_cols]
    out_path = os.path.join(PROCESSED_DIR, "eria_tokyo_area.csv")
    out.to_csv(out_path, index=False)
    log(f"  -> {out_path}  ({len(out)} 行，东京区域参考数据)")
    return out


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    log("=" * 60)
    log("开始原始数据处理")
    log("=" * 60)

    jepx = process_jepx()
    demand, renewable = process_national_dispatch()
    fuel = process_fuel_prices()
    fleet = build_fleet()
    eria = process_eria_tokyo()

    log("=" * 60)
    log("所有处理完成。data/processed/ 文件清单：")
    for fname in sorted(os.listdir(PROCESSED_DIR)):
        fpath = os.path.join(PROCESSED_DIR, fname)
        size_kb = os.path.getsize(fpath) / 1024
        log(f"  {fname:<40} {size_kb:>8.1f} KB")
    log("=" * 60)

    # 基础数据审计
    log("数据覆盖审计：")
    log(
        f"  JEPX:    {jepx['timestamp'].min()} ~ {jepx['timestamp'].max()}  ({len(jepx)} 行)"
    )
    log(
        f"  Demand:  {demand['timestamp'].min()} ~ {demand['timestamp'].max()}  ({len(demand)} 行)"
    )
    log(
        f"  Renew:   {renewable['timestamp'].min()} ~ {renewable['timestamp'].max()}  ({len(renewable)} 行)"
    )
    log(
        f"  Fuel:    {fuel['timestamp'].min()} ~ {fuel['timestamp'].max()}  ({len(fuel)} 行)"
    )
    log(
        f"  Fleet:   {len(fleet)} 燃料类型，总装机 {fleet['installed_capacity_mw'].sum():,.0f} MW"
    )

    # 检查 JEPX 与 Demand 时间对齐
    jepx_ts = set(jepx["timestamp"])
    demand_ts = set(demand["timestamp"])
    overlap = len(jepx_ts & demand_ts)
    log(
        f"  JEPX ∩ Demand 重叠时间点：{overlap} 个（共 {len(jepx_ts)} / {len(demand_ts)}）"
    )


if __name__ == "__main__":
    main()
