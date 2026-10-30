# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。

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
