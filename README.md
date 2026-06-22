# Mi Fitness MCP CN

小米运动健康 / Mi Fitness 数据本地 MCP Server。

本项目基于 `kubulashvili/mi-fitness-mcp` 修改，增加中国区小米健康云适配，并补充睡眠与运动记录同步能力。

> 非小米官方项目，仅用于读取和分析你自己的健康数据。数据默认同步到本地 SQLite。

## 功能

- 读取小米运动健康云端数据
- 本地 SQLite 缓存
- MCP Server 支持
- 支持中国区：`--region cn`
- 支持数据类型：
  - `daily_activity`：步数、距离、活动卡路里
  - `heart_rate`：心率采样
  - `sleep`：睡眠记录
  - `workouts`：运动记录
  - `body_measurements`：体重 / 身体成分，视账号数据而定

## 已逆向验证的接口

### 健康数据接口

```text
POST https://hlth.io.mi.com/app/v1/data/get_fitness_data_by_time
```

常用 key：

```text
steps
calories
heart_rate
weight
sleep
```

睡眠请求示例：

```json
{
  "start_time": 1767225600,
  "end_time": 1782086399,
  "key": "sleep"
}
```

### 运动记录接口

```text
POST https://hlth.io.mi.com/app/v1/data/get_sport_records_by_time
```

请求示例：

```json
{
  "start_time": 1767225600,
  "end_time": 1782086399,
  "limit": 50
}
```

返回字段通常包含：

```text
sport_records
has_more
next_key
```

每条运动记录的 `value` 是 JSON 字符串，包含 `start_time`、`end_time`、`duration`、`distance`、`calories`、`avg_hrm`、`max_hrm` 等字段。

## 安装

```bash
git clone git@github.com:binglua/mi-fitness-mcp-cn.git
cd mi-fitness-mcp-cn
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

如果当前环境没有系统 keyring，可安装：

```bash
pip install keyrings.alt
```

注意：`keyrings.alt` 可能以明文文件方式保存凭据。

## 配置

需要从 `https://account.xiaomi.com` 登录后的 Cookie 中获取：

- `userId`
- `passToken`

中国区账号建议：

```bash
mi-fitness-mcp setup \
  --mode mi_fitness_cloud \
  --user-id "<userId>" \
  --pass-token "<passToken>" \
  --region cn
```

检查连接：

```bash
mi-fitness-mcp doctor
```

## 同步数据

同步全部可探测数据：

```bash
mi-fitness-mcp sync --start-date 2026-01-01 --end-date 2026-06-21
```

按类型同步：

```bash
mi-fitness-mcp sync --type daily_activity --start-date 2026-01-01 --end-date 2026-06-21
mi-fitness-mcp sync --type heart_rate --start-date 2026-01-01 --end-date 2026-06-21
mi-fitness-mcp sync --type sleep --start-date 2026-01-01 --end-date 2026-06-21
mi-fitness-mcp sync --type workouts --start-date 2026-01-01 --end-date 2026-06-21
mi-fitness-mcp sync --type body_measurements --start-date 2026-01-01 --end-date 2026-06-21
```

## 启动 MCP Server

```bash
mi-fitness-mcp serve
```

Claude Desktop 配置示例：

```json
{
  "mcpServers": {
    "mi-fitness": {
      "command": "mi-fitness-mcp",
      "args": ["serve"]
    }
  }
}
```

## MCP 工具

- `get_connection_status`
- `sync_data`
- `get_profile`
- `get_daily_summary`
- `query_metric_series`
- `query_heart_rate`
- `query_body_measurements`
- `query_sleep`
- `query_workouts`
- `get_data_coverage`

## 本地数据库

默认位置：

```text
~/.local/share/mi-fitness-mcp/mi_fitness.db
```

主要表：

```text
daily_activity
heart_rate_samples
sleep_sessions
workouts
body_measurements
sync_state
```

## 安全说明

- `passToken` 是敏感凭据，不要泄露。
- 不要提交本地配置、数据库、keyring 文件。
- 如果 token 泄露，建议退出小米账号并重新登录刷新。

## 免责声明

本项目与小米公司无关。请仅用于读取和分析你自己的健康数据。



### 新增健康指标

本分支额外逆向并验证了以下小米运动健康云端 key，并已接入 CLI 同步、本地 SQLite 缓存和 MCP 查询工具：

- `resting_heart_rate`：静息心率，合并到 `query_heart_rate(sample_type="resting")`。
- `spo2`：血氧饱和度，CLI 类型 `spo2`，MCP 工具 `query_spo2`。
- `stress`：压力值，CLI 类型 `stress`，MCP 工具 `query_stress`。
- `abnormal_heart_beat`：异常心跳事件，CLI 类型 `abnormal_heart_beat`，MCP 工具 `query_abnormal_heart_beat`。

示例：

```bash
mi-fitness-mcp sync --type spo2 --start-date 2026-06-01 --end-date 2026-06-22
mi-fitness-mcp sync --type stress --start-date 2026-06-01 --end-date 2026-06-22
mi-fitness-mcp sync --type abnormal_heart_beat --start-date 2026-06-01 --end-date 2026-06-22
```

## License

MIT
