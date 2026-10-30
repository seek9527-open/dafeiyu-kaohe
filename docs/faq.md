# FAQ

## 这是什么？给谁用的？

给「允许 AI 自己写插件、改配置」的 AstrBot 玩家用的。它考核 AI 的自主操作历史，达标后逐级放开权限，出事能手动降级。

## 为什么积分不涨？

三个原因，按概率排序：

1. 工坊账本没有新事件（AI 没写过文件，或工坊没成功写入）；
2. `consumed_ledger` 偏移已经追上文件末尾（只消费增量，不重复计分）；
3. 分数被事故或红线扣回了 0。

## 为什么到了 60 分还没到 L2？

L2 是审批制：达标后只会把 `pending_level` 设为 2，需要主人发 `/提权 批准`。L3 同理。

## 为什么「批准」了还是不能改？

检查目标是否命中受保护名单（`astrbot_plugin_moon_gate`、`astrbot_plugin_moon_workshop`）、红线词，或 `cmd_config` 键是否在白名单里。

## 人格改了没生效？

`gate_persona_set` 调的是 `persona_manager.update_persona`，正常会立即刷新内存；如果群里还是旧口吻，可能是会话绑定了其他人格，或者需要重启。

## 会不会被 AI 刷分？

会。它写文件、过语法检查就能拿分，这是设计意图——我们希望它多写、写对。真正防刷的是「失败扣分」和「主人随时能收权」。

## 能用在别的 bot 上吗？

核部分依赖 AstrBot 的 `Star`/`filter`/`persona_manager`。逻辑可以照抄，接口需要替换。

## 数据存在哪？

- 状态：`data/plugin_data/astrbot_plugin_moon_gate/gate.json`
- 备份：同目录 `backups/`
- 工坊账本：`data/plugin_data/moon_workshop/events.jsonl`

## 怎么清空重来？

删 `gate.json` 并重启，或发 `/提权 重置`（只清等级，保留积分）。想连积分一起清就删文件。

## 为什么仓库名不是「溟汐的考核」？

GitHub 仓库名只支持 ASCII，中文标题放在仓库的 Display Name / About 和 README 里。仓库名用 `dafeiyu-kaohe`，避免与已有的 `moon-gate` 系列项目撞车。

## 和 moon-gate 是同一个东西吗？

不是。`moon-gate` 多是 API 网关类项目；本项目是「AI 自我提权的考核」，名字里的 MoonGate 只是内部代号。
