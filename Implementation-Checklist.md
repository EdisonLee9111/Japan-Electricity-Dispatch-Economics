# Implementation Checklist

## 目标说明

本文件将 `JP-Power-Dispatch-Economics-DevPlan.md` 转化为一份可直接执行的中文实施计划，目标是在最短路径内完成一个可运行、可解释、可展示的日本电力调度经济性项目 MVP，并逐步扩展到情景分析、可视化和回测验证。

---

## 一、项目决策（先定规则，再写代码）

### 1.1 必须确认的项目决策

- [ ] **建模粒度**
  - [ ] 决定使用 **30分钟** 还是 **小时** 粒度
  - [ ] 建议：MVP 先聚合为小时，后续再扩展到 30 分钟
  - [ ] 在文档中明确写明粒度选择与理由

- [ ] **价格回测目标**
  - [ ] 决定以 `システムプライス` 作为主目标，还是以某个区域价格为主
  - [ ] 建议：优先以 `システムプライス` 做全国单节点回测
  - [ ] 如果后续增强，可增加 `エリアプライス東京`

- [ ] **空间建模假设**
  - [ ] 决定是否采用“全国单节点（copper plate）”
  - [ ] 建议：MVP 采用全国单节点，不建模区域联络线
  - [ ] 在 README 和偏差分析中说明忽略输电约束

- [ ] **机组建模粒度**
  - [ ] 决定按“燃料类型聚合 fleet”还是按单厂/单机组建模
  - [ ] 建议：MVP 按燃料类型聚合
  - [ ] 分类建议包括：
    - [ ] nuclear
    - [ ] coal
    - [ ] lng_ccgt
    - [ ] lng_ocgt
    - [ ] oil
    - [ ] hydro
    - [ ] solar
    - [ ] wind
    - [ ] biomass

- [ ] **求解器路线**
  - [ ] 第一阶段：simple merit-order dispatch
  - [ ] 第二阶段：LP / MILP unit commitment
  - [ ] 建议：先把 simple dispatch 全年跑通，再做增强版

- [ ] **单位体系**
  - [ ] 统一功率单位：`MW`
  - [ ] 统一电量单位：`MWh`
  - [ ] 统一价格单位：`JPY/kWh` 或 `JPY/MWh`
  - [ ] 建议：内部计算用 `JPY/MWh`，输出图表可转为 `JPY/kWh`

- [ ] **MVP 范围**
  - [ ] 只做：数据清洗、simple dispatch、情景分析、可视化、基础回测
  - [ ] 暂不做：全国多区域潮流、全年 UC、复杂策略报价建模

### 1.2 决策完成标准

- [ ] 在 README 或方法说明中写清核心建模假设
- [ ] 在 `config/settings.yaml` 中固化关键参数
- [ ] 后续开发不再频繁改变粒度、目标价格和模型边界

---

## 二、项目脚手架（先把工程骨架搭起来）

## Phase 0：初始化项目结构

### 2.1 创建目录结构

- [ ] 创建以下目录：
  - [ ] `config/`
  - [ ] `data/raw/`
  - [ ] `data/processed/`
  - [ ] `engine/`
  - [ ] `scenarios/`
  - [ ] `visualization/`
  - [ ] `backtest/`
  - [ ] `output/charts/`
  - [ ] `output/results/`
  - [ ] `notebooks/`

### 2.2 创建基础文件

- [ ] 创建以下文件：
  - [ ] `requirements.txt`
  - [ ] `main.py`
  - [ ] `README.md`
  - [ ] `config/settings.yaml`
  - [ ] 各模块的 `__init__.py`

### 2.3 依赖管理

- [ ] 在 `requirements.txt` 中加入：
  - [ ] `pandas>=2.0`
  - [ ] `numpy>=1.24`
  - [ ] `matplotlib>=3.7`
  - [ ] `seaborn>=0.12`
  - [ ] `pulp>=2.7`
  - [ ] `pyyaml>=6.0`
  - [ ] `openpyxl>=3.1`
  - [ ] `requests>=2.28`
  - [ ] `scipy>=1.10`

### 2.4 开发规范

- [ ] Python 版本固定为 3.11+（建议）
- [ ] 文件命名统一使用 `snake_case`
- [ ] DataFrame 字段名统一使用英文小写下划线
- [ ] 建立统一日志输出风格
- [ ] 设置 `.gitignore`
  - [ ] 忽略大文件原始数据
  - [ ] 忽略 `output/`
  - [ ] 忽略 notebook checkpoint
  - [ ] 忽略虚拟环境

### 2.5 CLI 主入口骨架

- [ ] 在 `main.py` 中先定义执行步骤：
  - [ ] `load_inputs()`
  - [ ] `prepare_fleet()`
  - [ ] `run_base_dispatch()`
  - [ ] `run_scenarios()`
  - [ ] `generate_charts()`
  - [ ] `run_backtest()`
- [ ] 即使初期模块未完成，也先用 placeholder 保证主流程能串起来

### 2.6 项目脚手架完成标准

- [ ] 目录结构完整
- [ ] 依赖能成功安装
- [ ] `python main.py` 至少能运行到结束并打印流程日志
- [ ] 所有模块有清晰的输入输出边界

---

## 三、数据层任务（先保证模型有输入）

## Phase 1：数据采集、清洗与标准化

### 3.1 原始数据盘点

- [ ] 收集并放入 `data/raw/`：
  - [ ] JEPX spot 数据
  - [ ] demand 数据
  - [ ] fleet / capacity 数据
  - [ ] fuel price 数据
  - [ ] renewable profile 数据

- [ ] 为每份数据记录元信息：
  - [ ] 来源
  - [ ] 下载日期
  - [ ] 时间范围
  - [ ] 原始单位
  - [ ] 备注/限制

### 3.2 JEPX 数据审计

- [ ] 读取 `spot_summary_2025.csv`
- [ ] 检查：
  - [ ] 总行数
  - [ ] 日期范围
  - [ ] `時刻コード` 覆盖是否完整
  - [ ] 是否有重复记录
  - [ ] 是否有空值
  - [ ] 价格列是否都为数值类型
  - [ ] 成交量列是否都为数值类型

### 3.3 标准时间索引生成

- [ ] 将 `受渡日 + 時刻コード` 转换为统一 `timestamp`
- [ ] 明确是保留 30 分钟还是聚合为小时
- [ ] 若聚合为小时，写清规则：
  - [ ] 价格使用均值还是末值
  - [ ] 成交量使用求和还是均值
- [ ] 输出一个标准化时间字段，供后续 merge 使用

### 3.4 标准化 JEPX 价格表

- [ ] 提取核心列，重命名为英文：
  - [ ] `timestamp`
  - [ ] `system_price`
  - [ ] `tokyo_price`
  - [ ] `contract_volume`
  - [ ] `sell_bid_volume`
  - [ ] `buy_bid_volume`
- [ ] 保存为：
  - [ ] `data/processed/jepx_prices.csv`

### 3.5 需求数据处理

- [ ] 获取真实需求数据
- [ ] 如果暂时没有可用真实需求：
  - [ ] 使用 `約定総量` 作为需求代理
  - [ ] 在文档中明确声明这是代理变量
- [ ] 输出：
  - [ ] `data/processed/demand_profile.csv`

### 3.6 燃料价格数据处理

- [ ] 收集 LNG、Coal、Oil、Uranium 数据
- [ ] 至少做到月度价格
- [ ] 将月度价格映射到小时级或半小时级时间索引
- [ ] 输出：
  - [ ] `data/processed/fuel_prices.csv`

### 3.7 Fleet 数据库建设

- [ ] 建立 `fleet.csv`，字段至少包括：
  - [ ] `fuel_type`
  - [ ] `installed_capacity_mw`
  - [ ] `min_stable_generation_pct`
  - [ ] `heat_rate_mmbtu_per_mwh`
  - [ ] `variable_om`
  - [ ] `startup_cost_hot`
  - [ ] `startup_cost_warm`
  - [ ] `startup_cost_cold`
  - [ ] `min_up_time_hours`
  - [ ] `min_down_time_hours`
  - [ ] `ramp_rate_mw_per_hour`
  - [ ] `must_run`

- [ ] 对缺失的技术参数使用文献或合理假设填补
- [ ] 对所有假设保留来源说明或注释

### 3.8 Renewable profile 数据处理

- [ ] 获取或构造 solar / wind 容量因子
- [ ] 输出时序字段：
  - [ ] `timestamp`
  - [ ] `solar_cf`
  - [ ] `wind_cf`
- [ ] 保存为：
  - [ ] `data/processed/renewable_profiles.csv`

### 3.9 数据层完成标准

- [ ] `data/processed/` 至少包含：
  - [ ] `jepx_prices.csv`
  - [ ] `demand_profile.csv`
  - [ ] `fuel_prices.csv`
  - [ ] `fleet.csv`
  - [ ] `renewable_profiles.csv`
- [ ] 这些表都可以按 `timestamp` 或主键稳定关联
- [ ] 核心字段无关键缺失
- [ ] 可覆盖至少一个完整分析周期

---

## 四、MVP 引擎任务（先做能跑通的版本）

## Phase 2：Simple Merit-Order Dispatch

### 4.1 边际成本计算模块

- [ ] 编写统一函数计算边际成本：
  - [ ] `marginal_cost = fuel_price * heat_rate + variable_om`
- [ ] 对以下电源单独处理：
  - [ ] solar：零边际成本
  - [ ] wind：零边际成本
  - [ ] hydro：根据建模假设设置
  - [ ] nuclear：低边际成本 + must-run

- [ ] 建立单位转换辅助函数，避免 `JPY/kWh` 与 `JPY/MWh` 混淆

### 4.2 静态 Merit Order 构建

- [ ] 对任意给定时点：
  - [ ] 计算各 fuel 的边际成本
  - [ ] 按成本升序排序
  - [ ] 计算累计容量
- [ ] 产出可绘图的数据结构：
  - [ ] `fuel_type`
  - [ ] `installed_capacity_mw`
  - [ ] `marginal_cost`
  - [ ] `cumulative_capacity_mw`

### 4.3 Simple Dispatch Solver

- [ ] 对每个时点独立求解
- [ ] 调度逻辑顺序：
  - [ ] 先发 must-take renewable
  - [ ] 再发 must-run nuclear
  - [ ] 剩余需求由 thermal / hydro 按 merit order 补足
- [ ] 对每个时点输出：
  - [ ] 各 fuel 的发电量
  - [ ] 剩余需求
  - [ ] 边际机组
  - [ ] 模拟 clearing price

### 4.4 出清价格逻辑

- [ ] clearing price = 满足需求的最后一档边际电源成本
- [ ] 处理以下特殊情况：
  - [ ] 需求低于 must-run + renewable
  - [ ] 供给不足
  - [ ] 价格 floor / cap
  - [ ] renewable 过剩时的价格处理方式

### 4.5 样本测试顺序

- [ ] 先跑单小时测试
- [ ] 再跑 24 小时
- [ ] 再跑 1 周
- [ ] 最后跑 1 个月或全年

### 4.6 MVP 引擎验证清单

- [ ] 每时点总发电量与需求匹配
- [ ] 不出现负发电量
- [ ] 不超过装机容量
- [ ] clearing price 与 marginal unit 一致
- [ ] 输出结果可供图表和回测模块使用

### 4.7 MVP 完成标准

- [ ] 能稳定跑完至少一个月或全年时序
- [ ] 输出以下结果：
  - [ ] `base_dispatch.csv`
  - [ ] `base_prices.csv`
- [ ] 结果逻辑合理，可解释
- [ ] 可生成至少两张核心图

---

## 五、增强引擎任务（让模型更接近真实调度）

## Phase 3：Startup Cost + LP / UC Prototype

### 5.1 启停成本模块

- [ ] 实现 `compute_startup_cost()`：
  - [ ] hot start
  - [ ] warm start
  - [ ] cold start
- [ ] 根据机组离线时长判定成本档位
- [ ] 先对 thermal fleet 进行建模

### 5.2 最小稳定出力约束

- [ ] 在线 thermal fleet 不得低于 `min_stable_generation_pct`
- [ ] 确保机组在线时的发电量满足技术下限

### 5.3 LP / MILP 求解器原型

- [ ] 使用 `PuLP` 对代表性时间窗口建模
- [ ] 目标函数包括：
  - [ ] variable generation cost
  - [ ] startup cost

- [ ] 约束包括：
  - [ ] demand balance
  - [ ] capacity upper/lower bound
  - [ ] online/offline 状态
  - [ ] startup flag
  - [ ] min up time
  - [ ] min down time
  - [ ] ramping

### 5.4 增强版开发顺序

- [ ] 先跑 24 小时窗口
- [ ] 再跑 3 天
- [ ] 再跑 1 周
- [ ] 不要一开始就跑全年 UC

### 5.5 增强版完成标准

- [ ] 至少可对 1 周样本稳定求解
- [ ] startup、min stable generation、ramp 逻辑有效
- [ ] 能解释热机组在 duck curve 条件下为何“不断机”或“频繁启停”

---

## 六、情景分析任务（把模型变成分析工具）

## Phase 4：Scenario Engine

### 6.1 场景配置框架

- [ ] 建立统一 `ScenarioConfig`
- [ ] 支持以下参数：
  - [ ] `nuclear_capacity_gw`
  - [ ] `solar_capacity_gw`
  - [ ] `wind_capacity_gw`
  - [ ] `lng_price_multiplier`
  - [ ] `coal_price_multiplier`
  - [ ] `oil_price_multiplier`
  - [ ] `demand_multiplier`

### 6.2 必做场景

- [ ] Base case
- [ ] Nuclear restart
- [ ] LNG price shock
- [ ] Solar doubling

### 6.3 场景执行任务

- [ ] 对同一时间窗口运行所有场景
- [ ] 保存每个场景的：
  - [ ] dispatch 结果
  - [ ] price 结果
  - [ ] summary 指标

### 6.4 场景比较指标

- [ ] 平均价格变化
- [ ] 各燃料发电量变化
- [ ] 容量因子变化
- [ ] thermal startup 次数变化
- [ ] 低价小时数变化
- [ ] LNG 边际时段变化
- [ ] solar curtailment proxy（可选）

### 6.5 情景模块完成标准

- [ ] 4 个场景可一键运行
- [ ] 结果格式统一，可直接进入图表模块
- [ ] 每个情景至少产出 3 个可解释结论

---

## 七、可视化任务（把结果讲清楚）

## Phase 5：核心图表输出

### 7.1 必做图表

- [ ] Merit order curve
- [ ] Duck curve
- [ ] Seasonal heatmap
- [ ] Dispatch stack（代表性日）
- [ ] Price duration curve
- [ ] Scenario comparison dashboard
- [ ] Simulated vs actual backtest chart

### 7.2 代表性日选择

- [ ] 冬季高峰日
- [ ] 夏季高峰日
- [ ] 春季高光伏日
- [ ] 秋季高光伏日

### 7.3 图表规范

- [ ] 统一 fuel color map：
  - [ ] Nuclear：purple
  - [ ] Coal：dark gray
  - [ ] LNG CCGT：orange
  - [ ] LNG OCGT：light orange
  - [ ] Oil：brown
  - [ ] Hydro：blue
  - [ ] Solar：gold/yellow
  - [ ] Wind：teal/light blue
  - [ ] Biomass：green

- [ ] 统一：
  - [ ] 标题格式
  - [ ] 单位
  - [ ] 图例位置
  - [ ] 导出尺寸和分辨率
  - [ ] 文件命名规则

### 7.4 可视化完成标准

- [ ] 核心图表都能自动输出到 `output/charts/`
- [ ] 图表无需人工修图即可放入 README
- [ ] 每张图都能支持一个明确分析观点

---

## 八、回测任务（建立可信度）

## Phase 6：Backtest Against JEPX

### 8.1 数据对齐

- [ ] 按 `timestamp` 对齐模拟价格和实际 JEPX 价格
- [ ] 明确实际价格口径：
  - [ ] system price
  - [ ] tokyo area price
- [ ] 检查错位、缺失与覆盖率问题

### 8.2 回测指标

- [ ] 计算：
  - [ ] RMSE
  - [ ] MAE
  - [ ] Correlation
  - [ ] Bias
  - [ ] R²（可选）
- [ ] 增加分组误差：
  - [ ] 分季节
  - [ ] 分月份
  - [ ] 分时段（白天 / 晚高峰 / 深夜）

### 8.3 偏差分析

- [ ] 分析模型偏差最大的时段
- [ ] 解释可能原因：
  - [ ] 忽略输电约束
  - [ ] 忽略战略报价
  - [ ] demand proxy 不准确
  - [ ] renewable output 处理粗糙
  - [ ] 储能/需求响应未建模
  - [ ] 区域价格分裂未建模

### 8.4 回测完成标准

- [ ] 能稳定输出 simulated vs actual 图
- [ ] 有至少 3 个核心误差指标
- [ ] 有书面偏差解释，而不仅是数字

---

## 九、文档与展示任务（让项目可读、可复现、可展示）

## Phase 7：README、方法说明与结果摘要

### 9.1 README 必写内容

- [ ] 项目简介
- [ ] 研究问题
- [ ] 方法框架
- [ ] 数据来源
- [ ] 建模假设
- [ ] 如何运行
- [ ] 核心图表
- [ ] 关键发现
- [ ] 模型限制
- [ ] 后续扩展方向

### 9.2 补充文档

- [ ] assumptions 清单
- [ ] 数据字典
- [ ] 场景定义说明
- [ ] 输出指标说明
- [ ] 偏差来源说明

### 9.3 文档完成标准

- [ ] 新读者 5 分钟内能明白项目在做什么
- [ ] 新读者 15 分钟内能知道如何运行
- [ ] 面试官能快速看懂：
  - [ ] 研究问题
  - [ ] 方法
  - [ ] 结果
  - [ ] 局限性
  - [ ] 扩展空间

---

## 十、推荐执行顺序（按最稳妥路径推进）

1. [ ] 确定建模粒度、价格目标、单位体系
2. [ ] 搭好项目脚手架与主入口
3. [ ] 清洗 JEPX 数据并生成标准化价格表
4. [ ] 构建 demand、fleet、fuel price、renewable profile 四张核心输入表
5. [ ] 先完成单小时 marginal cost + merit order
6. [ ] 完成 simple dispatch 并对小样本测试
7. [ ] 跑通月度或全年 base case
8. [ ] 输出第一批图表
9. [ ] 接入 scenario engine
10. [ ] 做 backtest 与偏差分析
11. [ ] 最后再做 startup / LP / UC 增强版
12. [ ] 完成 README 和结果摘要包装

> 原则：**先打通闭环，再提高真实度；先做可解释结果，再做复杂优化。**

---

## 十一、Done Criteria（完成定义）

### 11.1 数据模块 Done

- [ ] 所有核心输入都有 processed 版本
- [ ] 所有表可按时间或主键稳定 join
- [ ] 没有关键缺失字段
- [ ] 至少覆盖一个完整分析周期

### 11.2 调度模块 Done

- [ ] simple dispatch 可稳定运行
- [ ] 每时点满足供需平衡
- [ ] 不超容量、不出现负值
- [ ] 价格逻辑可解释

### 11.3 情景模块 Done

- [ ] 新场景只改配置，不改主逻辑
- [ ] 所有场景输出格式一致
- [ ] 有统一 summary table

### 11.4 可视化模块 Done

- [ ] 至少 5 张核心图可自动生成
- [ ] 图表风格统一
- [ ] 能直接用于 README 或汇报

### 11.5 回测模块 Done

- [ ] 模拟值与实际值对齐正确
- [ ] 指标计算稳定
- [ ] 偏差原因有解释

### 11.6 项目整体 Done

- [ ] 从原始数据到结果图可通过主入口执行
- [ ] README 能说明方法与结论
- [ ] 项目结果足以支撑作品集展示或面试讲解

---

## 十二、前 8 个最优先的立即动作（Top 8 Immediate Next Steps）

- [ ] **1. 确定 MVP 使用小时还是 30 分钟粒度**
- [ ] **2. 确定主回测目标是 `system_price` 还是 `tokyo_price`**
- [ ] **3. 清洗 `spot_summary_2025.csv` 并生成标准化价格表**
- [ ] **4. 用 `約定総量` 或真实负荷数据建立需求表**
- [ ] **5. 手工建立第一版 `fleet.csv`**
- [ ] **6. 手工建立第一版 `fuel_prices.csv`**
- [ ] **7. 编写 marginal cost + merit order + simple dispatch**
- [ ] **8. 跑出 base case 的第一版全年或月度结果**

---

## 十三、执行提醒（避免返工）

- [ ] 不要一开始就做全年 MILP
- [ ] 不要一开始就做全国多区域网络约束
- [ ] 不要等所有真实参数齐全才开始编码
- [ ] 先用可解释假设补齐，再逐步替换成真实数据
- [ ] 每完成一个阶段都保存 processed 数据和结果文件
- [ ] 每引入一个新约束，先在小样本上验证
- [ ] 把“解释 dispatch economics”放在比“拟合价格”更高的位置

---

## 十四、最终交付物清单

- [ ] 完整的 Python 项目结构
- [ ] 标准化输入数据表
- [ ] MVP 调度引擎
- [ ] 增强版调度引擎（至少代表性窗口）
- [ ] 4 个标准情景
- [ ] 7 类核心图表
- [ ] JEPX 回测结果
- [ ] README 与方法说明
- [ ] 可用于展示/面试的项目结论摘要