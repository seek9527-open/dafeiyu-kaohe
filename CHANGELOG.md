# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

## [1.4.3] - 2026-10-31

### 修复

- 工坊的路径检查先认「目录」再谈后缀：`ws_sandbox_test` 传插件目录时不再被「只允许 .py / .json / .md / .txt」误拦。
- 写文件后缀白名单加入 `.yaml` / `.yml`，`metadata.yaml` 可以正常读写了；读文件不再限制后缀（仍在白名单根目录内）。
- 沙箱打包不再丢弃 `metadata.yaml`、`LICENSE` 等非白名单后缀的正当文件，同时跳过 `.env`、`*.db` 与 `data/`。
- `ws_list_files` 也能列暂存区与工坊数据目录，方便查看待批草稿。
- `astrbot_plugin_moon_workshop` 升至 1.3.3，作者仍为「溟月和主人」。
- 新增 4 条回归测试：目录读放行、目录写拒绝、`metadata.yaml` 可写、沙箱包包含辅助文件但不含秘密。
## [1.4.2] - 2026-10-31

### 新增

- 两个插件首次对话时互相检测：对端未安装则记一条 WARNING，并提示「两个插件要一起装」。
- `/提权` 状态与 `/工坊 状态` 增加「配套插件」一行，直接显示对端是否已安装。
- `astrbot_plugin_moon_gate` 升至 1.1.2，`astrbot_plugin_moon_workshop` 升至 1.3.2。

## [1.4.1] - 2026-10-31

### 变更

- 作者署名由「溟月」改为「溟月和主人」：`pyproject.toml`、两个插件的 `@register` 与 `metadata.yaml`。
- `astrbot_plugin_moon_gate` 升至 1.1.1，`astrbot_plugin_moon_workshop` 升至 1.3.1（仅署名与版本号变化，无行为改动）。

## [1.4.0] - 2026-10-31

### 变更

- 项目显示名从「大肥鱼的考核」改为「溟汐的考核」：README、插件显示名、文档与许可证署名统一。
- `astrbot_plugin_moon_gate` 版本升至 1.1.0（仅改名，无行为变化）。
- 仓库名保持 `dafeiyu-kaohe`（GitHub 仓库名只支持 ASCII，公开链接不变）。

## [1.3.0] - 2026-10-31

### 新增

- 工坊新增「暂存 + 审批上线」流水线：`staging_required` 开启后，直接写生产插件目录会被自动转进 `staging/<插件>/`，生产目录不动。
- 新增 `ws_stage_status`（查看待批草稿）与 `ws_promote`（上线）：上线前校验沙箱通过时间与主人批准时间，批准在草稿改动后作废、默认 30 分钟过期；上线逐文件备份 + 再检查，失败整体还原。
- 新增主人命令 `/工坊`：`状态`、`批准 <插件>`、`拒绝 <插件>`。
- `events.jsonl` 事件补充 `epoch` 时间戳，新增 `stage_write` / `promote_ok` 事件。
- 新增暂存审批链路的单元测试。

## [1.2.0] - 2026-10-31

### 新增

- 工坊新增 `ws_sandbox_test`：把插件目录送进一次性沙箱容器跑语法、JSON 与单测，沙箱无网络、不挂宿主目录、用完即毁。
- 仓库附带沙箱 runner（`moon_sandbox/`：`runner.py`、`Dockerfile`、`run.sh`）与部署说明。

## [1.1.0] - 2026-10-31

### 新增

- 仓库收录配套插件「溟月的工坊」(`astrbot_plugin_moon_workshop`)：受限读写、自动备份、语法检查、回滚与事件账本。
- 新增工坊单元测试：路径白名单、备份清单、语法失败还原、回滚演练、每轮限流与管理员校验。

## [1.0.0] - 2026-10-31

### 新增

- 三级考核体系：L1 自动、L2/L3 主人审批。
- 工坊事件账本 `events.jsonl` 增量消费，支持 `write_ok` / `syntax_fail` / `rollback_ok` / `drill_ok`。
- 主人加星、事故扣分与降级。
- 红线关键词熔断：管理员、白名单、密钥、数据库、本插件自身。
- L2 人格托管：改前备份旧人格，失败自动回滚。
- L3 一次性批条与 `cmd_config` 白名单键。
- 管理员命令 `/提权` 及子命令：批准 / 加星 / 批配置 / 事故 / 重置。
- 三个 LLM 工具：`gate_status`、`gate_config_set`、`gate_persona_set`。
- 单元测试与 GitHub Actions CI。
