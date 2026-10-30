# 部署指南

## 前置条件

- AstrBot 4.x（依赖 `context.persona_manager`、`_star_manager.reload`、`StarTools.get_data_dir`）；
- Python 3.10+；
- 如果要让计分自动流入，需要配合 [溟月的工坊](../README.md#配套插件溟月的工坊)（本仓库已附带）或任何按相同格式写 `events.jsonl` 的组件。

## 安装

把 `astrbot_plugin_moon_gate/` 与 `astrbot_plugin_moon_workshop/` 两个目录一起放进 AstrBot 的插件目录：

```bash
# 容器部署
docker cp astrbot_plugin_moon_workshop astrbot:/AstrBot/data/plugins/
docker cp astrbot_plugin_moon_gate astrbot:/AstrBot/data/plugins/
docker restart astrbot
```

或手动放入 `data/plugins/astrbot_plugin_moon_gate/` 与 `data/plugins/astrbot_plugin_moon_workshop/` 后重启 AstrBot。

启动日志应出现：

```
[moon_gate] 大肥鱼的考核已加载（score=0 level=0）
```

## 配置

首次启动后会在 `data/config/astrbot_plugin_moon_gate_config.json` 生成默认配置：

```json
{
  "l1_score": 20,
  "l1_days": 7,
  "l1_write_ops": 3,
  "l2_score": 60,
  "l2_days": 14,
  "l3_score": 150,
  "l3_days": 30
}
```

改完重启 AstrBot 生效。状态文件在 `data/plugin_data/astrbot_plugin_moon_gate/gate.json`，不随配置重置。

## 与工坊的关系

本插件消费工坊的账本 `data/plugin_data/moon_workshop/events.jsonl`，只认四种事件：

```jsonl
{"ts": "2026-10-31 01:00:00", "kind": "write_ok", "path": "..."}
{"ts": "2026-10-31 01:00:00", "kind": "syntax_fail", "path": "..."}
{"ts": "2026-10-31 01:00:00", "kind": "rollback_ok", "path": "..."}
{"ts": "2026-10-31 01:00:00", "kind": "drill_ok", "path": "..."}
```

没有工坊时，考核仍可运行，只是分数只能靠主人加星累积。

## 首次上线检查

1. 私聊机器人发 `/提权`，应回复「积分 0｜等级 0」。
2. 让 AI 调用 `gate_status` 工具，应返回同样内容。
3. 把 `gate.json` 里的 `score` 临时改到 20 不会直接升级——必须先有一次 `write_ok` 事件流入（`_consume_workshop` 只在账本变化时触发）。想手动演示可以用 `/提权 加星`。
4. 检查 `docker logs astrbot` 无 `[moon_gate]` 报错。

## 升级

- 直接替换 `astrbot_plugin_moon_gate/` 目录，重启；
- `gate.json` 向前兼容：`_load()` 会给缺失字段补默认值；
- 升级前建议备份 `gate.json` 与 `backups/`。

## 卸载

删除插件目录并重启。`gate.json`、`backups/` 留在 `plugin_data` 下不会自动清理，需要可手动删。

## 常见部署问题

**插件加载了但 `/提权` 没反应**
检查 AstrBot 的 `wake_prefix`（默认 `/`），以及发消息的账号是否在 `admins_id` 里。

**改了配置但机器人行为没变**
`gate_config_set` 会尝试 `_star_manager.reload(plugin)`；如果插件没有实现 `reload` 或缓存了配置，需要重启 AstrBot。

**日志里 `[moon_gate] 状态文件坏了`**
`gate.json` 不是合法 JSON 时会重来，旧文件不会自动备份。建议定期备份。

## 沙箱 runner（可选）

`ws_sandbox_test` 需要一个宿主上的小服务：它把插件目录打包，丢进一次性容器里做语法 / JSON / 单测检查。沙箱容器 `--network=none`、根文件系统只读、只挂一个 tmpfs、去掉全部 capabilities、用完即毁，不碰宿主的 `/AstrBot/data`。

部署（Docker 宿主机上）：

```bash
mkdir -p /root/moon_sandbox && cd /root/moon_sandbox
# runner.py / Dockerfile / run.sh 见仓库同目录
head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n' > token
docker build -q -t moon-sandbox:1 .
nohup python3 runner.py > runner.log 2>&1 &
curl -s http://172.17.0.1:8791/health
```

然后在工坊配置 `data/config/astrbot_plugin_moon_workshop_config.json` 里填：

```json
{"sandbox_url": "http://172.17.0.1:8791/run", "sandbox_token": "<token 文件内容>"}
```

说明：

- runner 默认只监听 `172.17.0.1:8791`（Docker bridge 网关），公网访问不到；所有请求要带 `X-Token`。
- 容器命令固定为 `sh /opt/harness/run.sh`，不接受任意 shell；超时强杀。
- runner 本身以 root 运行 docker，属于信任边界内组件；不要把它暴露到公网，也不要在里面执行用户提交的任意命令。
- 更彻底的做法是把「写代码」和「上线代码」拆成两个目录（staging → promote），沙箱只测 staging，promote 走人工或审批。这一点目前留给部署方按需实现。
