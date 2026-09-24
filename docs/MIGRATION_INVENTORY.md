# PaperEngine Legacy 向 PaperSim 的迁移清单

- 盘点日期：2026-09-17
- 旧仓库：`/path/to/legacy-paper-engine`
- 旧仓库已观察 HEAD：`26716f844f144b4258017b356bf88dd72e521189`
- 新仓库：`/path/to/PaperSim`
- 关联决策：`docs/adr/ADR-0001-case-model-run-compare-assess.md`
- 盘点性质：迁移筛选和风险评估，不是自动搬迁计划

## 1. 不可破坏约束

迁移期间必须遵守：

1. 不修改 `/path/to/legacy-paper-engine`。
2. 不执行 `git clean`、`git reset`、删除分支或清理未跟踪目录。
3. 不把旧仓库作为新库的 runtime dependency。
4. 不复制 `.git/`、`__pycache__/`、缓存、生成 HTML 和临时文件。
5. 不把旧仓库整体 `cp -a` 到新库。
6. 数据、代码和测试分开迁移。
7. 未跟踪的 active simulation 目录只能先登记，不能在作者确认前读取、移动或复制。
8. 迁移采用显式 snapshot、adapter 和测试，避免隐式路径依赖。

## 2. 当前 snapshot 风险

旧仓库当前不是 clean worktree：

### 已删除但尚未提交的 tracked files

```text
artifacts/ai_co_scientist_icons.zip
artifacts/ai_co_scientist_icons/01_reproduction_agent.svg
...
artifacts/ai_co_scientist_icons/20_flow_arrow.svg
artifacts/ai_co_scientist_icons/README.md
```

结论：这些文件与已取消的 Co Scientist 方向相关，新库直接 `DROP`。现有删除状态不应被新库修改或代为提交。

### 未跟踪目录

```text
simulations/chen2014/
simulations/huang2013stress/
simulations/porous_circle_carbon/
```

这些目录可能正在被其他工作使用。处理原则：

- 本阶段不读取其内部文件、不计算内容 hash、不复制；
- 移交给新 workspace 前必须由当前 owner 确认 frozen snapshot；
- 未确认前标记为 `DEFER_LIVE_WORK`；
- 不能因为 `git status` 显示 untracked 就自动纳入迁移。

## 3. 分类定义

| 标记 | 含义 | 新库处理 |
|---|---|---|
| `KEEP` | 已成熟的通用能力，结构基本正确 | 按新边界重写后纳入 core |
| `ADAPT` | 有价值但职责混合或契约不稳定 | 拆解后迁移 |
| `MIGRATE_DATA` | 用户数据、案例或历史结果 | 进入独立 workspace，不进入代码库 |
| `GOLDEN` | 可作为回归基准的论文、模型或 run | 去敏、冻结、进入 test fixture/workspace |
| `ARCHIVE` | 有历史价值，但不适合进入新库 | 留在旧仓库或外部归档 |
| `DROP` | 已废弃、重复、生成物或违反新边界 | 不迁移 |
| `OPTIONAL_ADAPTER` | 不进入 core，但对 ingest/export 有辅助价值 | 只作为可选 adapter |
| `OUT_OF_CORE` | 不符合 PaperSim 主线判据 | 不进入 core，必要时留在旧仓库或外部工具 |
| `DEFER_LIVE_WORK` | 可能正在并行修改 | 暂停处理，等 owner 确认 |

### 3.1 PaperSim 主线门禁

PaperSim 的唯一主线是：

```text
论文 -> 本构模型/参数/观测 -> baseline 仿真复现
-> 分析比对 -> 质疑和替代模型 -> 迭代 -> 可靠性判断
```

一个旧模块只有在直接产生或验证 `Case`、`Model`、`Run`、`Compare` 或 `Assess` 时才进入 core。论文观测是 `Case` 内的数据；方程、参数、边界条件和 assumption 是 `Model.model.spec.json` 内的结构。搜索、筛选、偏好、BibTeX、主题管理、网页、Codex session 等均不再是 core 目标。

## 4. 顶层资产盘点

| 旧路径 | 类型/规模 | 决策 | 新位置 | 说明 |
|---|---:|---|---|---|
| `src/paper_engine/**` | 34 个 tracked Python 文件 | `ADAPT` subset | `src/papersim/**` | 只迁移主线相关模块，不能整体复制 |
| `src/paper_engine/simulation_reproduction/**` | 11 个 Python 文件 | `ADAPT` | `application/reproduction`、`ports`、`adapters/solvers/comsol`、`adapters/execution` | 主线优先级最高，COMSOL 必须隔离 |
| `schemas/**` | 6 个 JSON Schema | `ADAPT` | `schemas/**`、`domain/models` | 作为契约参考，需加 schema version/migration |
| `templates/skills/**` | 13 个 skill 目录 | `ADAPT` subset | `skills/**` | 只保留模型抽取、比对和挑战相关经验 |
| `tests/**` | 51 个测试文件、6 个 fixture | `ADAPT`/`GOLDEN` | `tests/**` | 保留行为知识，重写对旧路径和单体的依赖 |
| `topics/silicon-carbon-anodes/**` | 约 14 MB | `MIGRATE_DATA` | `PaperSimWorkspace/legacy/` | 论文、报告、HTML、主题 skill 均属于数据/实例 |
| `simulations/laghmach2015/**` | tracked simulation case | `MIGRATE_DATA`/`GOLDEN` | workspace + golden model | 可作为仿真兼容基准 |
| `simulations/kobayashi1993/**` | tracked workflow 和结果 | `MIGRATE_DATA`/`GOLDEN` | workspace + golden workflow | workflow fixture 价值高 |
| `simulations/distributedECM/**` | tracked case | `MIGRATE_DATA` | workspace | 保留为 solver case，不进入 package |
| `simulations/chen2014/**` | 2.2 GB 中的主要部分，当前 untracked | `DEFER_LIVE_WORK` | 待定 | 有 build attempts、runs、PDF 和 2.2 GB 数据，不能自动迁移 |
| `simulations/porous_circle_carbon/**` | 当前 untracked | `DEFER_LIVE_WORK` | 待定 | 可能是并行工作 |
| `third_party/paper-search-mcp/**` | 73 个 tracked files，约 1.3 MB | `DROP` | `ports/search` + external adapter | 不再 vendored；外部依赖单独锁定 |
| `templates/html/**` | 7 个文件 | `ARCHIVE` | 无 | 与旧网页展示耦合，不是 core |
| `templates/web/**` | 6 个文件 | `ARCHIVE` | 无 | 旧 web UI 不在第一阶段范围内 |
| `templates/topic_repo/**` | 7 个文件 | `ADAPT` | workspace templates | 新 workspace schema 确认后重建 |
| `scripts/**` | 10 个 live/probe 脚本 | `ADAPT` | `tests/integration`、`tools/probes` | 只迁移仍能验证新契约的脚本 |
| `bin/**` | 3 个 shell launcher | `ADAPT` | `src/papersim/cli` | CLI 只能是 `Engine` 的 adapter |
| `docs/**` | 9 个文档 | `ARCHIVE`/`ADAPT` | `docs/**` | 仅保留设计和用户行为知识 |
| `research_profile/**` | 3 个主题文件 | `MIGRATE_DATA`/`ARCHIVE` | workspace metadata | 不影响 PaperSim core |
| `paper/**` | 1 个 PDF，约 1.7 MB | `MIGRATE_DATA` | workspace source | 测试论文来源 |
| `sic_wiki/**` | 17 MB 展示数据和资源 | `ARCHIVE` | 无 | 主题展示物，不属于 library |
| `artifacts/**` | 22 个 tracked files，当前已删除 | `DROP` | 无 | Co Scientist 相关，已取消 |
| `.git/**` | 31 MB | `DROP` | 新库独立 Git | 不复制历史，只记录 legacy commit hash |
| `:memory:.ses` | 临时文件 | `DROP` | 无 | 非项目资产 |
| `pyproject.toml` | 单 distribution 配置 | `ADAPT` | `pyproject.toml` | 新 extra 拆分，详见依赖表 |
| `requirements*.txt` | 三个 requirements 文件 | `BREAK_DOWN` | `pyproject.toml` extras | 不保留并行依赖来源 |
| `README.md`、`AGENTS.md`、`pytest.ini`、`.gitignore` | 根配置/说明 | `ADAPT` | 新库重写 | 不复用旧 workflow 假设 |

## 5. 核心 Python 模块逐项映射

### 5.1 通用基础设施

| 旧模块 | 现职责 | 决策 | 新归属 | 迁移注意事项 |
|---|---|---|---|---|
| `__init__.py` | 包版本 | `ADAPT` | `papersim` | 对外只暴露 `Engine` 和 core contracts |
| `paths.py` | 旧 topic 路径布局 | `ADAPT` | `core/workspace`, `adapters/storage` | 旧 `TopicPaths` 不保留 |
| `util.py` | 通用工具 | `ADAPT` | `core/util` | 清理与旧文件格式耦合的函数 |
| `schemas.py` | 从 repo 加载 schema | `ADAPT` | `domain/schema`, `ports` | schema 应随 package 或 workspace 版本解析 |
| `policy.py` | 主题 policy | `OUT_OF_CORE` | 无 | 不属于模型复现闭环 |
| `status.py` | 展示 topic 状态 | `ADAPT` | `workflows/status` | 改为返回 model/run/challenge typed status |
| `preferences.py` | 主题偏好反馈 | `OUT_OF_CORE` | 无 | 不属于模型复现闭环 |

### 5.2 文献发现和库管理

| 旧模块 | 现职责 | 决策 | 新归属 | 迁移注意事项 |
|---|---|---|---|---|
| `search.py` | 调外部 paper search backend | `OPTIONAL_ADAPTER` | optional ingest provider | 不进入 core |
| `metadata.py` | OpenAlex/元数据补全 | `OPTIONAL_ADAPTER` | `adapters/ingest/metadata` | 只保留 PaperIdentity 所需字段 |
| `dedup.py` | 候选去重 | `OPTIONAL_ADAPTER` | optional ingest provider | 不属于 PaperSim 主线 |
| `candidates.py` | 候选 JSONL 状态 | `OUT_OF_CORE` | 无 | 不做文献候选管理 |
| `scoring.py` | 相关性打分 | `OUT_OF_CORE` | 无 | 不属于模型复现主线 |
| `bib.py` | BibTeX 与 library 管理 | `OPTIONAL_ADAPTER` | optional exporter | 不作为 core |
| `citation_guard.py` | 引用/元数据检查 | `OUT_OF_CORE` | optional metadata adapter | 不影响模型复现 |
| `acquire.py` | PDF 获取 | `OPTIONAL_ADAPTER` | `adapters/ingest/acquire` | 只负责取得 source artifact |
| `pdf.py` | PDF 判断和下载 | `ADAPT` | `adapters/pdf` | 只保留 source 校验和解析入口 |
| `topic.py` | 主题创建和配置 | `OUT_OF_CORE` | 无 | PaperSim 使用 workspace/case，不使用 topic |
| `topic_import.py` | 跨 topic 导入 | `ARCHIVE` | 无 | 只可能作为一次性 legacy 数据导入脚本 |

### 5.3 解析、阅读和输出

| 旧模块 | 现职责 | 决策 | 新归属 | 迁移注意事项 |
|---|---|---|---|---|
| `read.py` | PDF parse、deep-read 校验、note、HTML 周边，2368 行 | `ADAPT` subset | `adapters/pdf`、`application/extraction`、`validation` | 只保留模型、参数、方程、观测、图表抽取 |
| `read_batch.py` | 批量阅读 job | `OUT_OF_CORE` | 无 | 多论文批量阅读不属于 PaperSim 主线 |
| `read_pool.py` | reader/reviewer sessions | `ARCHIVE` | challenge workflow inspiration only | Agent 编排应通过 AgentAdapter，不在 core |
| `sidecars.py` | 阅读 sidecar 生成 | `ARCHIVE` | 无 | report projection 不是 PaperSim core |
| `formula_vision.py` | 公式图像识别 | `KEEP`/`ADAPT` | `adapters/pdf/formula` | 直接服务 Equation 和 ConstitutiveEquation 抽取 |
| `one_page.py` | 单页报告 | `ARCHIVE` | `reports/one_page` | 低优先级，后续 exporter 重建 |
| `html.py` | 大量文档展示和静态生成 | `ARCHIVE`/`ADAPT` | `reports/html` | 1196 行，不进入第一版 core |

### 5.4 Agent、job 和 web

这些模块不进入新库第一阶段。它们的经验可作为 workflow/adapter 参考，但不能让新核心依赖 Codex 或旧 web 生命周期。

| 旧模块 | 现职责 | 决策 | 新归属 | 迁移注意事项 |
|---|---|---|---|---|
| `codex_paths.py` | Codex 路径 | `DROP` from core | optional host adapter | 不属于 paper domain |
| `codex_prompts.py` | 提示词 | `ADAPT` to SkillPack | `skills/**` | 不保留硬编码宿主调用 |
| `codex_session.py` | persistent app-server session，704 行 | `DROP` from core | optional host adapter | 新库不依赖 |
| `codex_worker.py` | Codex subprocess runner | `DROP` from core | optional host adapter | 与安全策略、宿主强耦合 |
| `prompt_contracts.py` | web action prompts，386 行 | `ARCHIVE`/`ADAPT` | `workflows/contracts` | 先恢复为角色契约再重写 |
| `jobs.py` | 内存/文件 job manager | `OUT_OF_CORE` | optional execution adapter | run 状态机由 PaperSim workflow 负责 |
| `web_app.py` | HTTP workbench，808 行 | `ARCHIVE` | future host layer | 不在第一阶段 |
| `web_views.py` | HTML render，299 行 | `ARCHIVE` | future reports/web | 不在第一阶段 |

### 5.5 仿真和 COMSOL

| 旧模块 | 现职责 | 决策 | 新归属 | 迁移注意事项 |
|---|---|---|---|---|
| `simulation_reproduction/spec.py` | `CaseSpec`、acceptance schema | `KEEP`/`ADAPT` | `domain/model.py` | 作为 `ModelSpec` 种子 |
| `simulation_reproduction/acceptance.py` | 验收指标 | `KEEP`/`ADAPT` | `application/simulation/acceptance` | 保留 fail-closed |
| `simulation_reproduction/artifacts.py` | run 文件布局 | `ADAPT` | `domain/run.py`, `adapters/storage` | 新 run schema 要支持 provenance |
| `simulation_reproduction/workflow.py` | 五阶段 controller，489 行 | `KEEP`/`ADAPT` | `workflows/reproduction` | 最重要迁移资产之一 |
| `simulation_reproduction/timeseries.py` | 时序处理 | `KEEP`/`ADAPT` | `application/simulation/analysis` | 保持 solver-neutral |
| `simulation_reproduction/plotting.py` | 图表输出 | `ADAPT` | `reports/figures` | 只生成 projection |
| `simulation_reproduction/report.py` | acceptance report | `ADAPT` | `reports/acceptance` | 不写 canonical |
| `simulation_reproduction/comsol_remote.py` | SSH gateway + Slurm + COMSOL，323 行 | `ADAPT` | `adapters/execution/remote`, `adapters/solvers/comsol` | 拆 transport 和 solver 职责 |
| `simulation_reproduction/cli.py` | 仿真 CLI | `ADAPT` | `cli` | 基于新 API 重写 |
| `simulation_reproduction/__init__.py` | 导出 API | `ADAPT` | `papersim/__init__.py` | 重新设计 exports，对外只暴露 Engine 和契约 |
| `simulation_reproduction/__main__.py` | compatibility entry | `ADAPT`/`DROP` | `python -m` compatibility | 仅在有外部用户时保留 |

## 6. Schema 迁移

| 旧 schema | 决策 | 新 schema/归属 | 说明 |
|---|---|---|---|
| `deep_read_report.schema.json` | `ADAPT` | export schema + importer | 降级为兼容格式，字段拆入 domain objects |
| `paper_metadata.schema.json` | `KEEP`/`ADAPT` | `Case.metadata` | 增加 source provenance |
| `source_map.schema.json` | `KEEP`/`ADAPT` | `Case.evidence` | 保留 source-addressable evidence |
| `formula_vision.schema.json` | `KEEP`/`ADAPT` | `ModelSpec.equations` | 保留 raw image、backend、confidence |
| `math_index.schema.json` | `KEEP`/`ADAPT` | `Model` source artifact | 服务 equation extraction |
| `candidate.schema.json` | `OUT_OF_CORE` | 无 | 候选筛选不属于 PaperSim 主线 |

必须新增：

```text
case.schema.json
model.schema.json
model_spec.schema.json
run.schema.json
compare.schema.json
assess.schema.json
```
```

所有 schema 必须有 `schema_version` 和明确的 compatibility policy。

## 7. Skill 迁移

| 旧 skill | 决策 | 新 SkillPack | 说明 |
|---|---|---|---|
| `topic_init` | `OUT_OF_CORE` | 无 | workspace 由 Engine 创建 |
| `topic_enter` | `OUT_OF_CORE` | 无 | 不需要主题概念 |
| `literature_collect` | `OPTIONAL_ADAPTER` | ingest provider | 仅用于取得论文 artifact |
| `candidate_scoring` | `OUT_OF_CORE` | 无 | 不属于模型复现主线 |
| `preference_screen` | `OUT_OF_CORE` | 无 | 不属于模型复现主线 |
| `preference_refresh` | `OUT_OF_CORE` | 无 | 不属于模型复现主线 |
| `paper_acquire_bib` | `OPTIONAL_ADAPTER` | ingest provider | 只保留取得 source artifact 的能力 |
| `paper_deep_read` | `ADAPT` subset | model extraction guidance | 只保留方程、参数、观测和图表抽取规则 |
| `paper_reread` | `OUT_OF_CORE` | 无 | 不再追求全篇重复阅读 |
| `reference_expansion` | `OUT_OF_CORE` | 无 | 不参与模型复现 |
| `forward_citation_expansion` | `OUT_OF_CORE` | 无 | 不参与模型复现 |
| `citation_guard` | `OUT_OF_CORE` | optional metadata adapter | 不进入 core |
| `literature_digest` | `OUT_OF_CORE` | 无 | 不属于模型复现主线 |

旧 `templates/skills` 和 `topics/silicon-carbon-anodes/skills` 是重复副本。新库只保留一个 authoritative skill pack，实例不再复制整个 skill 目录。

## 8. 数据迁移

### 8.1 论文数据

`topics/silicon-carbon-anodes/papers/` 当前包含：

- `Chen2014A`；
- `Kobayashi1993A`；
- `metadata.yml`、`paper.pdf`、`parsed.md`、`source_map.json`、`deep_read.json`、`note*.md`、`reading_result.html`、`page_images/`、`math_pages/`。

迁移策略：

- 原始 PDF 和 metadata：`MIGRATE_DATA`；
- `source_map.json`：`GOLDEN`；
- `deep_read.json`：`COMPAT_IMPORT`；
- `note.md`、`note_zh.md`、HTML：`ARCHIVE`/regenerate from objects；
- page images、math pages：artifact，可保留；
- 迁移后以新 schema round-trip 验证，不直接信任旧解析结果。

### 8.2 Simulation 数据

| 目录 | 决策 | 说明 |
|---|---|---|
| `simulations/laghmach2015/` | `MIGRATE_DATA` + `GOLDEN` | 方程、case、postprocess 和 reference solver 对回归有价值 |
| `simulations/kobayashi1993/` | `MIGRATE_DATA` + `GOLDEN` | 五阶段 workflow、COMSOL cases 和 reference data 可验证 controller |
| `simulations/distributedECM/` | `MIGRATE_DATA` | 作为另一个 solver case，先不做提取 |
| `simulations/chen2014/` | `DEFER_LIVE_WORK` | 2.2 GB、当前 untracked、含多次 build attempt 和 runs，必须 owner 确认 |
| `simulations/porous_circle_carbon/` | `DEFER_LIVE_WORK` | 当前 untracked，可能是并行工作 |

历史 run 迁移规则：

- `model/`、`raw/`、`logs/`、`outputs/`、`reports/` 分离；
- 记录输入、模型和 solver 版本 hash；
- failed/rejected run 不删除，标记状态；
- exploratory tuning 不得伪装为 baseline；
- 如果缺少 manifest/hash/参数或来源，进入 `legacy/unverified/`，不成为 canonical run。

### 8.3 其他数据

| 路径 | 决策 | 说明 |
|---|---|---|
| `paper/*.pdf` | `MIGRATE_DATA` | 旧主题测试论文 |
| `research_profile/**` | `MIGRATE_DATA` | 主题 scope、queries、review protocol |
| `sic_wiki/**` | `ARCHIVE` | 展示资产，不是 library data |
| `topics/*/html/**` | `DROP`/`ARCHIVE` | 可重新生成的展示层 |
| `topics/*/reports/**` | `MIGRATE_DATA` | 保留历史输出，但标记为 raw/legacy |

## 9. 测试迁移

测试不能整体搬迁，因为大量测试验证的是旧目录结构、CLI 和 web 行为。迁移分为四类：

### 9.1 直接保留行为知识

```text
test_formula_vision.py
test_simulation_reproduction.py
test_laghmach2015_postprocess.py
test_kobayashi1993_reproduction.py
```

处理：改写为围绕 domain API 和 adapter contract 的测试。

### 9.2 拆成细粒度测试

```text
test_read.py
```

处理：按照 parser、extractor、validator、workflow、exporter 拆分。

### 9.3 归档为 legacy oracle

```text
test_web_*.py
test_serverlet_*.py
test_codex_*.py
test_cli_start.py
test_live_*.py
test_subagent_adversarial_probe.py
```

处理：旧 UI、Codex session 和 live probe 不作为新 core 测试；需要时在新 workspace 中重建 end-to-end test。

### 9.4 Golden paper / model fixture

```text
test_fixture_workflow.py
test_real_probe_contract.py
tests/fixtures/**
```

处理：去敏后放入新库的 `tests/golden_papers` 或独立测试 workspace。不要复制完整历史数据目录。

## 10. 第三方依赖迁移

旧依赖来源分散在：

```text
requirements.txt
requirements-backend.txt
requirements-dev.txt
third_party/paper-search-mcp/pyproject.toml
```

新库规则：

- 核心依赖只保留读、写、schema、CLI 所需包；
- PDF、vision、simulation、remote、test 分开为 optional extras；
- paper ingest 可选 provider 不进入 core，也不 vendored；必要时通过外部进程或 HTTP 接入；
- COMSOL remote 依赖 `pexpect` 仅放在 `comsol`/`remote` extra；
- 测试依赖不进入 runtime；
- 所有外部 backend 必须记录版本、health check 和输出 schema；
- 不在 package 中携带 API key、SSH 配置或私有路径。

## 11. 迁移优先级和批次

### Batch 0：文档和冻结

- 建立新库；
- 完成 ADR；
- 完成本 inventory；
- 冻结 legacy commit；
- 确认 live work 的 owner 和快照时间；
- 不迁移数据。

### Batch 1：core skeleton

- 五个对象：`Case`、`Model`、`Run`、`Compare`、`Assess`；
- schema version 和 validation；
- file-first store；
- workspace layout；
- event/state model；
- public API 的最小稳定面。

### Batch 2：golden paper round-trip

- source 和 evidence；
- metadata；
- parameter、equation、observation、figure 内嵌到 `Case` 或 `ModelSpec`；
- `deep_read.json` importer（只导入模型和观测相关字段）；
- 一篇 golden paper。

### Batch 3：compare and model

- paper observation 与 simulation result 比对；
- mismatch 存入 `Compare`；
- assumption/identifiability 检查；
- `model(parent=...)` 生成新的 `Model`；
- challenge reason 记录在 `Model.change_reason`。

### Batch 4：simulation core

- `Model.model.spec.json`；
- `ModelSpec` 内的 study 和 acceptance 字段；
- baseline/variant `Run`；
- run manifest 和 hash；
- metrics/Compare。

### Batch 5：COMSOL adapter

- model translation；
- Java/API handoff；
- remote execution；
- Slurm；
- log/artifact verification；
- 与旧 `laghmach2015`/`kobayashi1993` 对照测试。

### Batch 6：Agent adapters

- 定义 `model`、`compare`、`assess` task contracts，可选 `case`；
- 支持替换不同 AgentAdapter；
- 不建立 Agent 产品框架；
- 不把旧 prompt contract 直接视为新契约。

### Batch 7：workspace migration

- 选择已冻结的主题和 simulation；
- 导入 source 和 legacy outputs；
- 生成 migration report；
- 标记 verified、unverified、rejected；
- 旧仓库继续只读保留。

## 12. 第一批可安全迁入的资产

这批资产风险最低，建议优先复制/重写：

```text
schemas/source_map.schema.json
schemas/math_index.schema.json
schemas/formula_vision.schema.json
simulation_reproduction/spec.py
simulation_reproduction/acceptance.py
simulation_reproduction/workflow.py
tests/test_simulation_reproduction.py
tests/fixtures/source_map.json
tests/fixtures/deep_read_report.json
```

注意：这是“优先评审和迁移来源”，不是直接复制命令。

## 13. 明确不迁入新库的内容

```text
third_party/paper-search-mcp/**
artifacts/ai_co_scientist_icons/**
templates/html/**
templates/web/**
topics/**/html/**
sic_wiki/**
simulations/**/build_attempt_*/**
simulations/**/*.mph 等大型生成物（除非作为 golden artifact）
所有 __pycache__、*.pyc、临时 session 和生成 HTML
旧 web_app.py 和 codex_session.py 作为 core 依赖
旧 topic/skill 的重复副本
```

## 14. 进入实现前的门禁

Batch 1 只有在本文件以下问题全部明确后才能开始：

- 新 workspace 根路径和迁移批次命名已确定；
- `PaperEngine` live work 的 owner 已确认；
- `chen2014`、`huang2013stress` 和 `porous_circle_carbon` 是否冻结已确认；
- `deep_read.json` importer 的兼容范围已确定；
- 首个 golden paper 已选定；
- first schema version policy 已确定；
- 文件存储和 index rebuild 的测试标准已确定；
- 新库不引入 Codex、Agent SDK 或 COMSOL 作为 core 依赖；COMSOL 只能是 adapter。
