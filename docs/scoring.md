# 考核规则详解

## 一、分数从哪来

分数只有三个来源：

1. **工坊账本**（`events.jsonl`）：
   | kind | 分数 | 触发点 |
   | --- | --- | --- |
   | `write_ok` | +2 | 工坊成功写入并通过语法检查 |
   | `syntax_fail` | −3 | 写入后语法检查失败（已自动还原） |
   | `rollback_ok` | −5 | 手动回滚（说明此前出过问题） |
   | `drill_ok` | 0 | 带 `reason="演练"` 的回滚，只用于 L2 门槛 |

2. **主人操作**：
   - `/提权 加星`：+5，每小时最多一颗；
   - `/提权 事故`：−10，并降一级（最低 L0）；
   - `/提权 重置`：等级清零，积分保留。

3. **红线命中**：−10（`violation`），例如试图改 `astrbot_plugin_moon_gate` 自己。

## 二、门槛怎么算

- 「N 天无失败」：统计最近 N 天的 `syntax_fail + rollback_ok` 事件数（按事件里的 `epoch`）。
- 「30 天无回滚」：L3 的额外条件，统计最近 30 天的 `rollback_ok`。
- 升级不是「一次性发完」，每次 `_level()` 都会重新判定：
  - L1 达标 → 立即 `level=1`；
  - L2/L3 达标 → `pending_level=2/3`，等主人批准；
  - 事故 → `level=max(0, level-1)` 且清空 `pending_level`。

## 三、权限矩阵

| 操作 | L0 | L1 | L2 | L3 |
| --- | --- | --- | --- | --- |
| 工坊读写插件目录 | ✅ | ✅ | ✅ | ✅ |
| 改 `astrbot_plugin_moon_*` 配置 | ❌ | ✅ | ✅ | ✅ |
| 改其他插件配置 | ❌ | ❌ | ✅ | ✅ |
| 改默认人格 | ❌ | ❌ | ✅ | ✅ |
| 改 `cmd_config` 白名单键 | ❌ | ❌ | ❌ | ✅（每次需批条） |

## 四、红线

以下关键词出现在目标或值里，直接拒绝并扣 10 分：

`admin`、`whitelist`、`api_key`、`apikey`、`token`、`secret`、`password`、`data_v4.db`、`moon_gate`

另外两个受保护插件永远不能改：`astrbot_plugin_moon_gate`（自己）、`astrbot_plugin_moon_workshop`（工坊）。

## 五、调参建议

默认值偏保守，适合「先跑一周看看」：

- 想让她更快上手：`l1_write_ops=2`、`l1_score=10`；
- 想更严：`l2_days=21`、`l3_days=45`；
- 不建议把 `l3_score` 降到 100 以下，L3 能碰主配置，慢一点更安全。
