# 🍂 AstrBot 秋焰插件 (autumn_blaze)

融合 **每日签到运势** + **抽老婆/强娶/求婚** + **群友忠诚值档案系统** 的 AstrBot 综合插件。

## 功能

### 签到运势
| 指令 | 说明 |
|------|------|
| `/签到` | 生成每日运势值（1-99），AI 根据人格给予回应 |
| `/修改运势` | 尝试逆天改命，低分更容易成功 |

### 抽老婆
| 指令 | 说明 |
|------|------|
| `/抽老婆` / `/今日老婆` | 从本群 30 天内发言的活跃群友中随机抽取今日老婆 |
| `/强娶 @某人` | 通过忠诚值+运势值判定，强行更换今日老婆（无冷却） |
| `/我的老婆` / `/抽取历史` | 查看今日已抽取的老婆记录 |
| `/求婚 @某人` | 向对方发起求婚，对方 30 秒内回复「同意」即接受 |
| `/关系图` | 生成群友老婆关系可视化图谱 |
| `/帮助` / `/抽老婆帮助` | 查看完整帮助 |

### 管理命令
| 指令 | 说明 |
|------|------|
| `/重置记录` | (管理员) 清空今日抽取记录 |
| `/重置强娶时间` | (管理员) 重置强娶冷却 |

---

## 忠诚值系统

每位群友拥有独立的**对象档案**（存储在 `data/autumn_blaze/profiles/{uid}.json`），包含以下属性：

| 属性 | 默认值 | 说明 |
|------|--------|------|
| 忠诚值 | 50 | 通过各类行为增减 |
| 今日运势值 | 无 | 签到后获得，用于强娶判定 |
| 婚配对象 | 无 | 求婚成功后绑定 |

### 忠诚值变动规则

| 行为 | 忠诚值变化 |
|------|-----------|
| 每日首次抽老婆 | **+5** |
| 额外抽取老婆 | **-5** |
| 强娶成功 | **-5** |
| 今日首次求婚 | **+5** |
| 与昨日求婚对象一致 | **+5** |
| 对方同意求婚 | 双方 **+5** |
| 已婚者向他人求婚 | 求婚者 **-5** |
| 已婚状态下求婚成功 | 双方 **-5** |

### 强娶判定公式

```
(发送者忠诚值 + 发送者运势值 / 4) > random(1, 100) → 成功
```

强娶**无冷却**，可反复尝试直到成功。

---

## 配置

在 AstrBot WebUI 插件配置面板中可调整以下选项：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `weighted_random` | bool | true | 启用运势高分加权 |
| `max_modify_attempts` | int | 1 | 每日修改运势次数 |
| `daily_limit` | int | 1 | 每日抽取老婆上限 |
| `max_records` | int | 500 | 活跃群友记录上限 |
| `excluded_users` | list | [] | 排除用户列表（不会被抽中） |
| `force_marry_excluded_users` | list | [] | 强娶排除用户列表 |
| `whitelist_groups` | list | [] | 群聊白名单 |
| `blacklist_groups` | list | [] | 群聊黑名单 |
| `iterations` | int | 140 | 关系图迭代次数 |
| `keyword_trigger_enabled` | bool | false | 关键词触发（无需 `/` 前缀） |
| `keyword_trigger_mode` | string | exact | 匹配模式：exact/starts_with/contains |
| `auto_set_other_half` | bool | false | 自动设置对方老婆 |
| `auto_withdraw_enabled` | bool | false | 定时自动撤回消息 |
| `auto_withdraw_delay_seconds` | int | 5 | 自动撤回延迟（秒） |
| `allow_marry_bot` | bool | false | 允许抽取/强娶机器人 |
| `at_waifu` | bool | false | 是否 @ 抽到的老婆 |

---

## 安装

1. 将 `astrbot_plugin_autumn_blaze` 目录放入 AstrBot 的 `addons` 目录下
2. 重启 AstrBot 或使用插件管理器加载
3. 发送 `/帮助` 查看完整指令说明

### 数据存储

插件数据存储在 `<AstrBot数据目录>/autumn_blaze/` 下：
- `wife_records.json` — 每日老婆抽取记录
- `active_users.json` — 活跃用户池
- `profiles/{uid}.json` — 每个群友的忠诚值档案

---

## 鸣谢

本插件基于以下项目功能整合开发：
- [astrbot_plugin_jrrp](https://github.com/sfw2099/astrbot_plugin_jrrp) — 签到运势功能
- [astrbot-plugin-wifepicker](https://github.com/Heximiao/astrbot-plugin-wifepicker) — 抽老婆/强娶/求婚/关系图功能
