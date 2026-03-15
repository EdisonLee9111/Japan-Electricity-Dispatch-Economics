# Raw Data Manifest

本文件记录 `data/raw/` 下所有原始数据文件的来源、格式、时间范围与字段说明，供数据处理脚本和后续开发参考。

---

## 文件清单

### 1. `spot_summary_2025.csv`

| 属性 | 说明 |
|------|------|
| **来源** | JEPX（日本电力交易所）官网下载 |
| **编码** | Shift-JIS |
| **粒度** | 30 分钟（時刻コード 1–48） |
| **时间范围** | 2025/04/01 — 2026/03/15（FY2025 近全年） |
| **行数** | 16,752 行 |
| **用途** | 回测目标价格；系统价格 + 各地区价格 |

**主要字段：**

| 原始列名 | 英文映射 | 单位 | 说明 |
|----------|----------|------|------|
| 受渡日 | delivery_date | — | 交割日 YYYY/MM/DD |
| 時刻コード | time_code | 1–48 | 每格 30 分钟，1 = 00:00 |
| 売り入札量 | sell_bid_volume | kWh | 卖方申报量 |
| 買い入札量 | buy_bid_volume | kWh | 买方申报量 |
| 約定総量 | contract_volume | kWh | 成交量（可作需求代理） |
| システムプライス | system_price | 円/kWh | 全国系统价格（主回测目标） |
| エリアプライス北海道 | hokkaido_price | 円/kWh | 北海道区域价格 |
| エリアプライス東北 | tohoku_price | 円/kWh | 东北区域价格 |
| エリアプライス東京 | tokyo_price | 円/kWh | 东京区域价格 |
| エリアプライス中部 | chubu_price | 円/kWh | 中部区域价格 |
| エリアプライス北陸 | hokuriku_price | 円/kWh | 北陆区域价格 |
| エリアプライス関西 | kansai_price | 円/kWh | 关西区域价格 |
| エリアプライス中国 | chugoku_price | 円/kWh | 中国区域价格 |
| エリアプライス四国 | shikoku_price | 円/kWh | 四国区域价格 |
| エリアプライス九州 | kyushu_price | 円/kWh | 九州区域价格 |

**时间码换算：** `timestamp = delivery_date + (time_code - 1) × 30min`

---

### 2. `eria_jukyu_YYYYMM_03.csv`（12个月度文件）

| 属性 | 说明 |
|------|------|
| **来源** | OCCTO / ERIA（広域機関需給実績データ） |
| **编码** | UTF-8 |
| **粒度** | 30 分钟 MW 平均 |
| **时间范围** | 2025/04 — 2026/03（FY2025 全年） |
| **区域** | エリア **03 = 東京（TEPCO）** |
| **文件列表** | eria_jukyu_202504–202603_03.csv |
| **用途** | 补充参考：东京区域各燃料类型发电量 + 区域需求 |

**主要字段（UTF-8，第1行为元数据，第2行为列名）：**

| 原始列名 | 英文映射 | 单位 | 说明 |
|----------|----------|------|------|
| DATE | date | — | 日期 |
| TIME | time | — | 时刻 HH:MM（30分间隔） |
| エリア需要 | area_demand | MW | 东京区域需求 |
| 原子力 | nuclear | MW | 核能（东京区无运营核电） |
| 火力(LNG) | lng_thermal | MW | LNG 火力 |
| 火力(石炭) | coal_thermal | MW | 煤炭火力 |
| 火力(石油) | oil_thermal | MW | 石油火力 |
| 火力(その他) | other_thermal | MW | 其他火力 |
| 水力 | hydro | MW | 水力 |
| 地熱 | geothermal | MW | 地热 |
| バイオマス | biomass | MW | 生物质 |
| 太陽光発電実績 | solar_actual | MW | 光伏实际发电 |
| 太陽光出力制御量 | solar_curtailment | MW | 光伏弃电量 |
| 風力発電実績 | wind_actual | MW | 风电实际发电 |
| 風力出力制御量 | wind_curtailment | MW | 风电弃电量 |
| 揚水 | pumped_hydro | MW | 抽水蓄能（负值=充电） |
| 蓄電池 | battery | MW | 蓄电池 |
| 連系線 | interconnector | MW | 区域联络线 |
| その他 | other | MW | 其他 |
| 合計 | total | MW | 合计供给 |

---

### 3. `download.csv`

| 属性 | 说明 |
|------|------|
| **来源** | **自然エネルギー財団（JREF）** — 整合 OCCTO 全国需給実績 + JEPX スポット価格 |
| **编码** | UTF-8 with BOM（utf-8-sig） |
| **粒度** | 30 分钟 MW 平均 |
| **时间范围** | 2025/04/01 — 2026/03/07 |
| **行数** | 16,368 行（含标题行两行） |
| **用途** | **主要数据源**：全国需求、各燃料发电量、光伏风电实绩、スポット価格 |

**主要字段（第1行为"全国"标注，第2行为列名）：**

| 原始列名 | 英文映射 | 单位 | 说明 |
|----------|----------|------|------|
| 日付 | date | — | 日期 |
| 時刻 | time | — | 时刻 HH:MM |
| 原子力 | nuclear | MW | 核能 |
| LNG | lng | MW | LNG 火力 |
| 石炭 | coal | MW | 煤炭火力 |
| 石油 | oil | MW | 石油火力 |
| 水力 | hydro | MW | 水力 |
| 地熱 | geothermal | MW | 地热 |
| バイオエネルギー | biomass | MW | 生物质 |
| 太陽光 | solar | MW | 光伏实际发电 |
| 太陽光(出力制御) | solar_curtailment | MW | 光伏弃电 |
| 風力 | wind | MW | 风电实际发电 |
| 風力(出力制御) | wind_curtailment | MW | 风电弃电 |
| 揚水(充電) | pumped_hydro_charge | MW | 抽蓄充电（负荷） |
| 揚水(発電) | pumped_hydro_gen | MW | 抽蓄发电 |
| 連系線(受電) | interconnector_receive | MW | 联络线受电 |
| 連系線(給電) | interconnector_send | MW | 联络线送电 |
| 火力その他 | other_thermal | MW | 其他火力 |
| 蓄電池(充電) | battery_charge | MW | 蓄电池充电 |
| 蓄電池(放電) | battery_discharge | MW | 蓄电池放电 |
| 需要 | demand | MW | 全国实际需求 |
| 全国 | system_price | 円/kWh | JEPX 全国スポット価格 |

---

### 4. `CMO-Historical-Data-Monthly.xlsx`

| 属性 | 说明 |
|------|------|
| **来源** | World Bank Commodity Price Data（Pink Sheet） |
| **更新日期** | 2025 年 1 月 6 日（数据实际覆盖至 2025M12） |
| **粒度** | 月度 |
| **时间范围** | 1960M01 — 2025M12 |
| **工作表** | `Monthly Prices`（主用） |
| **用途** | LNG 日本 CIF 价格、澳大利亚煤炭价格、原油价格 |

**关键列（`Monthly Prices` sheet，第5行为列名，第7行起为数据）：**

| 列索引 | 列名 | 单位 | 用途 |
|--------|------|------|------|
| 0 | Period（YYYYMXX格式） | — | 时间索引 |
| 1 | Crude oil, average | $/bbl | 参考 |
| 4 | Crude oil, WTI | $/bbl | 石油边际成本 |
| 5 | Coal, Australian | $/mt | 煤炭边际成本 |
| 9 | Liquefied natural gas, Japan | $/MMBtu | **LNG 边际成本主要输入** |

**注意：** 数据截至 2025M12，2026Q1 需要用最近月份向前填充。

---

### 5. `CMO-Historical-Data-Annual.xlsx`

| 属性 | 说明 |
|------|------|
| **来源** | World Bank Commodity Price Data（Pink Sheet）年度版 |
| **用途** | 长期趋势参考，不用于模型主输入 |

---

## 数据覆盖汇总

| 数据类型 | 文件 | 覆盖期间 | 粒度 | 用于 processed |
|----------|------|----------|------|----------------|
| JEPX 价格 | spot_summary_2025.csv | FY2025（至3/15） | 30 min | jepx_prices.csv |
| 全国需求 + 发电 | download.csv | FY2025（至3/7） | 30 min | demand_profile.csv |
| 可再生能源出力 | download.csv | FY2025（至3/7） | 30 min | renewable_profiles.csv |
| 燃料价格 | CMO-Historical-Data-Monthly.xlsx | 至2025M12 | 月度 | fuel_prices.csv |
| 东京区域需求 | eria_jukyu_*_03.csv | FY2025（至3/14） | 30 min | （参考用，不主用） |
| 机组参数 | — | — | — | fleet.csv（手工建立） |

---

## 说明

- **主回测目标**：`system_price`（システムプライス / 全国スポット価格），采用全国单节点（copper plate）假设
- **建模粒度**：MVP 阶段聚合为**小时**（取每小时2个30分钟区间均值/求和）
- **需求来源**：`download.csv` 的 `需要` 列（全国实际需求，MW）
- **可再生能源容量因子**：`solar_cf = solar_actual_mw / solar_installed_mw`，其中 solar_installed = 80,000 MW，wind_installed = 5,000 MW
- **燃料价格单位体系**：内部计算统一用 `JPY/MWh`；USD→JPY 汇率使用固定假设（如 150 JPY/USD）
