# 大肥鱼的考核 · MoonGate

> 给 AstrBot 里的 AI 娘装一把「带锁的尺子」：她能在工坊里自由改插件，但要靠积分、等级和主人审批换来更大的权限。

[![CI](https://github.com/seek9527-open/dafeiyu-kaohe/actions/workflows/ci.yml/badge.svg)](https://github.com/seek9527-open/dafeiyu-kaohe/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)

> 本仓库同时是 AstrBot 插件 `astrbot_plugin_moon_gate` 的源码。设计目标不是「把她关起来」，而是**让她自己管自己**：先做对事，再拿权限；越线就掉分，出事就降级。

---

## 目录

- [这是什么](#这是什么)
- [核心特性](#核心特性)
- [积分与等级](#积分与等级)
- [命令与工具](#命令与工具)
- [安装](#安装)
- [配置](#配置)
- [目录结构](#目录结构)
- [开发与测试](#开发与测试)
- [安全模型（请先读）](#安全模型请先读)
- [路线图](#路线图)
- [许可证](#许可证)

---

## 这是什么

`大肥鱼的考核` 是一个 AstrBot 插件，配合「溟月的工坊」（受限读写 + 自动备份 + 语法检查 + 回滚）使用：

1. 工坊每完成一次写入 / 语法失败 / 回滚，就向 `events.jsonl` 追加一条事件；
2. 考核插件增量读取账本，换算成积分；
3. 积分、天数、成功次数达标后自动升到 **L1**；
4. **L2 / L3** 必须由主人（AstrBot 管理员）手动批准；
5. 越线、事故会扣分甚至降级，红线永远不开放。

一句话：**干得好就加权限，手滑就掉回去。**

## 核心特性

- **事件账本驱动**：只认工坊 `events.jsonl`，不猜、不虚构。
- **三级权限**：L1 自动、L2/L3 主人审批。
- **一次性批条**：L3 改主配置需要主人每次签发，且只放行白名单键。
- **红线熔断**：管理员、白名单、密钥、数据库等关键词直接拒绝并扣分。
- **人格托管**：L2 起可改人格，改前自动备份旧人格到 `backups/`。
- **配置直写 + 插件重载**：改插件配置后自动 `reload`，不用手点面板。
- **全中文提示**：状态、拒绝理由、升级条件都写成人话。
- **可测试**：纯逻辑单测覆盖积分、升级、审批、红线、批条。

## 积分与等级

| 事件 | 分数 |
| --- | --- |
| 工坊成功写入（`write_ok`） | **+2** |
| 语法检查失败（`syntax_fail`） | **−3** |
| 回滚（`rollback_ok`） | **−5** |
| 回滚演练（`drill_ok`） | 0 |
| 主人加星（`/提权 加星`） | **+5**（每小时 1 次） |
| 越线 / 事故（`violation` / `disconnect`） | **−10**（事故并降一级） |

| 等级 | 门槛 | 权限 |
| --- | --- | --- |
| **L0** | 初始 | 只能用工坊改插件目录 |
| **L1** | 20 分 · 7 天无失败 · 3 次成功写入 | 改 `astrbot_plugin_moon_*` 插件配置（自动通过） |
| **L2** | 60 分 · 14 天无失败 · 1 次回滚演练 | 改所有插件配置 + 人格（需 `/提权 批准`） |
| **L3** | 150 分 · 30 天无回滚 | 改 `cmd_config` 白名单键（每次需 `/提权 批配置`） |

> 失败 = `syntax_fail` + `rollback_ok`（不含演练）。
> L3 白名单键默认只有 `platform_settings.wake_prefix` 与 `platform_settings.reply_prefix`，代码内可改。

## 命令与工具

**命令（仅管理员）**

| 命令 | 作用 |
| --- | --- |
| `/提权` | 查看积分、等级、各项计数、待批等级与下一级条件 |
| `/提权 批准` | 批准待批的 L2 / L3 |
| `/提权 加星` | 给 AI 加一颗星（+5 分，1 小时冷却） |
| `/提权 批配置` | L3 专用：签发一张一次性主配置批条 |
| `/提权 事故` | 记一次事故：−10 分并降一级 |
| `/提权 重置` | 等级清零（积分保留） |

**LLM 工具（AI 自己调用）**

| 工具 | 说明 |
| --- | --- |
| `gate_status` | 读自己的考核状态 |
| `gate_config_set(plugin, key, value)` | 在自己等级允许范围内改插件配置，成功后重载插件 |
| `gate_persona_set(system_prompt)` | L2 起可改默认人格，改前备份 |

## 安装

1. 把 `astrbot_plugin_moon_gate/` 整个目录放进 AstrBot 的 `data/plugins/`；
2. 确保工坊插件 `astrbot_plugin_moon_workshop` 已安装并会写 `data/plugin_data/moon_workshop/events.jsonl`；
3. 重启 AstrBot，日志出现：

```
[moon_gate] 大肥鱼的考核已加载（score=0 level=0）
```

4. 私聊机器人发送 `/提权` 验证。

> 数据位置：`data/plugin_data/astrbot_plugin_moon_gate/gate.json`，备份在 `backups/`。

## 配置

`_conf_schema.json` 暴露以下阈值（面板可改，代码内也有默认值）：

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `l1_score` | 20 | L1 所需积分 |
| `l1_days` | 7 | L1 要求最近 N 天无失败 |
| `l1_write_ops` | 3 | L1 要求成功写入次数 |
| `l2_score` | 60 | L2 所需积分 |
| `l2_days` | 14 | L2 要求最近 N 天无失败 |
| `l3_score` | 150 | L3 所需积分 |
| `l3_days` | 30 | L3 要求最近 N 天无回滚 |

## 目录结构

```
.
├── astrbot_plugin_moon_gate/     # 插件本体
│   ├── main.py
│   ├── _conf_schema.json
│   └── metadata.yaml
├── docs/                         # 设计、评分、安全、部署与 FAQ
├── tests/                        # 可独立运行的单元测试
├── .github/                      # CI、Issue / PR 模板
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
└── LICENSE
```

## 开发与测试

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate  |  macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
ruff check --select E9,F .
pytest -q
```

测试不依赖 AstrBot：`tests/conftest.py` 会注入最小桩模块，`tests/test_gate.py` 用临时目录模拟账本、配置与人格库。

## 安全模型（请先读）

- 这是**自律机制**，不是安全沙箱。工坊本身能写插件目录，理论上存在绕过路径；本插件的价值是让 AI 有明确的「做事—积分—权限」路径，并把越权尝试记录在案。
- 红线关键词是**防手滑**，不是加密边界。真正的硬边界应由容器、文件权限与 AstrBot 管理员机制保证。
- 请把数据库、密钥、`cmd_config.json` 的写权限留在主人手里；本插件默认拒绝这些目标。
- 更完整威胁模型见 [docs/security.md](docs/security.md)。

## 路线图

- [ ] 事件账本签名，防止手改 jsonl
- [ ] 多主人 / 多 AI 实例的独立账本
- [ ] L3 配置变更的 diff 预览与二次确认
- [ ] Web 面板展示积分曲线

## 许可证

[MIT](LICENSE) © 2026 大肥鱼
