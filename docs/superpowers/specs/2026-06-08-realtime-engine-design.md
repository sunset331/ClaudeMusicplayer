# 实时推荐引擎 v2 — 设计文档

**日期**: 2026-06-08  
**状态**: 待审核  

## 1. 目标

将音乐播放器从"每天一次批处理推荐"升级为"实时互动推荐系统"。

### 核心变化

| 维度 | v1 (当前) | v2 (目标) |
|------|-----------|-----------|
| 推荐时机 | 每天跑一次 | 实时 + 每天兜底 |
| 候选池 | 50首歌静态列表 | 300-400首动态池 + 边播边扩展 |
| 反馈生效 | 下次跑 engine | Like/Skip 后立即重排 |
| 模式 | Rap + Focus/Chill | Rap + Mixed (基于用户真实歌单) |
| 交互 | 按钮 (Like/Skip) | 按钮 + AI 对话窗口 |
| 数据源 | 艺人/流派/排行榜 | + 用户种子歌单 + 相似歌曲 + Claude Picks 歌单 |

---

## 2. 数据源

### 2.1 种子歌单（一次性导入）

| 歌单 | 来源 | 模式 | 用途 |
|------|------|------|------|
| Eminem 专属歌单 | 网易云 (id:2973308371) | Rap | 核心口味基线 |
| QQ Rap 歌单 | QQ音乐 | Rap | Rap 补充 |
| QQ 大杂烩 | QQ音乐 | Mixed | 杂食口味基线 |
| QQ 风格歌单 | QQ音乐 | Mixed | 风格方向 |

### 2.2 动态源

- 网易云 API：`/search`（按艺人/流派搜索）、排行榜
- `/simi/artist`：种子艺人的相似艺人扩展
- `/simi/song`：播放中歌曲的相似歌曲（每10首触发一次）
- Claude Picks 歌单：用户在网易云手动加到这个歌单的歌曲 = 强信号

---

## 3. 数据结构

### 3.1 taste.json（重构为模式分区）

```json
{
  "modes": {
    "rap": {
      "seed_playlists": ["qq_rap", "ncm_eminem"],
      "top_artists": ["Eminem", "50 Cent", "Dr. Dre", ...],
      "artist_weights": {"Eminem": 0.95, "Dr. Dre": 0.7, ...},
      "genre_weights": {"hip-hop": 0.8, "lyrical": 0.7, ...}
    },
    "mixed": {
      "seed_playlists": ["qq_mixed", "qq_style"],
      "top_artists": ["李宗盛", "Coldplay", "Sia", ...],
      "artist_weights": { ... },
      "genre_weights": {}
    }
  },
  "claude_picks": {
    "playlist_id": null,
    "last_sync": null,
    "songs": [],
    "artist_counts": {}
  }
}
```

### 3.2 candidates_{mode}.json（新文件）

```json
{
  "mode": "rap",
  "built_at": "2026-06-08T22:30:00",
  "count": 350,
  "songs": [
    {
      "songname": "...",
      "songid": 123,
      "singer": [{"name": "..."}],
      "albumname": "...",
      "albumid": 123,
      "duration": 240000,
      "_sources": ["artist:Eminem", "genre:hip-hop"],
      "_score": 0.85,
      "_played": false,
      "_from_simi": false
    }
  ]
}
```

### 3.3 history.json（不变，增强）

在现有 `liked_artists` / `skipped_artists` 基础上增加：
```json
{
  "liked_artists": { ... },
  "skipped_artists": { ... },
  "chat_signals": [
    {"text": "今天想听安静一点的", "intent": "prefer_calm", "weight": 0.5, "time": "..."}
  ],
  "recommended_ids": [...],
  "dates": [...]
}
```

### 3.4 QQ 导入中间文件

```
data/
  qq_seed_rap.json       # QQ Rap 歌单导入结果
  qq_seed_mixed.json     # QQ 大杂烩导入结果
  qq_seed_style.json     # QQ 风格歌单导入结果
```

---

## 4. 模块设计

### 4.1 QQ 歌单导入 (`import_qq.py`，~100行)

**流程**：
1. 用户打开 QQ 歌单页面 → F12 → Network → 找到包含歌曲列表的 JSON 响应
2. 用户复制 JSON → 粘贴到 `import_qq.py` 指定的输入位置
3. 脚本解析 → 逐首在网易云 API 搜索匹配（歌名 + 歌手）
4. 匹配成功 → 写入 taste.json 对应模式分区
5. 未匹配的歌输出到 `qq_unmatched.json` 供手动 review

**匹配规则**：
- 搜索 `"{songname} {singer}"`，取前3个结果
- 歌手名模糊匹配（去除括号内容、大小写不敏感）
- 状态标记：`matched` / `partial`（歌名匹配、歌手不确定）/ `unmatched`
- 预估匹配率：80-90%

### 4.2 Engine 实时评分 (`engine.py` 重写)

**新接口**：

```
build_candidates(mode='rap')
  → 种子艺人搜索 (top 20, 每人25首)
  → /simi/artist 扩展 (每人3个相似艺人, 每人15首)
  → genre 关键词搜索 (20个查询, 每种25首)
  → 排行榜 (3-4个, 每种30首)
  → 去重 + 过滤已知歌
  → 写入 candidates_{mode}.json
  → 返回候选列表 (~300-400首)

score_all(candidates, taste, history, mode)
  → 全量打分
  → 写入 candidates 的 _score 字段
  → 返回排序后的列表

rescore(candidates, taste, history, mode)
  → 只重算 _played=false 的歌曲
  → 排序更新
  → app.py 调此函数触发列表重排

expand_from_simi(song_ids, candidates, mode)
  → 对 song_ids 中每首调 /simi/song
  → 拉5首相似 → 去重过滤 → 追加到候选池
  → 对新歌评分
  → 每10首播放触发一次
```

**Rap Mode 评分因子**：
- artist weight × 0.3（种子艺人 + history）
- genre keyword match（加权: hip-hop/rock/chinese 各有权重）
- storytelling boost（narrative/story/truth等关键词）
- collaboration bonus（feat 加分）
- source quality（artist > ecosystem > genre > chart）
- history feedback（liked_artists 加分, skipped_artists 减分）
- Claude Picks 艺人加分（+0.1）
- novelty boost（非种子艺人 +0.05）
- duration: 2-5分钟加分

**Mixed Mode 评分因子**：
- artist match × 0.3（种子艺人）
- genre keyword match（**纯计数，不加权**——不预设方向）
- history feedback（同 rap）
- Claude Picks 艺人（+0.1）
- novelty boost（+0.08，比 rap 高，鼓励探索）
- collaboration bonus
- duration: 2-6分钟加分

**Mixed Mode genre 查询**：
```
pop rock, alternative rock, indie pop, R&B soul, neo soul,
contemporary R&B, Chinese pop, Chinese folk, Cantonese classic,
Mandarin ballad, 90s Chinese pop, Chinese indie,
acoustic pop, singer-songwriter, folk pop, electronic pop,
synth pop, dream pop, classic rock, soft rock, pop punk,
funk, disco classic, Motown, jazz vocal, smooth jazz,
bossa nova, world music, Latin pop, reggae pop,
orchestral pop, film soundtrack, musical theatre
```

### 4.3 app.py 改造

**变化**：
- `_init_data`：改为调用 `build_candidates()` 而非 `subprocess.run engine.py`
- Like/Skip 后立即调 `rescore()` → `tkinter.after(0, _reload_list)` 更新 treeview
- `_watch_playback` 中跟踪播放计数 → 每10首触发 `expand_from_simi()`
- 底栏按钮："Rap Mode" / "Mixed Mode"（替换 Focus）
- 新增右侧 Chat 面板

**导入 engine 模块**：
不再用 `subprocess.run` 调 engine.py，改为直接 `import engine` 调函数。候选池缓存在内存，避免反复读写 JSON。

### 4.4 Mixed Mode 定义

定位：基于 QQ 大杂烩 + QQ 风格歌单的泛口味模式。不预设 genre 偏好——让 Like/Skip 驱动方向。核心差异：

| | Rap Mode | Mixed Mode |
|---|---|---|
| 种子歌单 | QQ Rap + Eminem 网易云 | QQ 大杂烩 + QQ 风格 |
| Genre 查询 | hip-hop / rap 系列 | pop / rock / R&B / 华语 / 民谣系列 |
| 评分偏置 | 有 genre_weights | 无，平等对待 |
| 新颖性 boost | +0.05 | +0.08 |
| 探索倾向 | 保守（在已知方向深挖） | 开放（多方向探索） |

### 4.5 AI 对话面板

**UI 布局**：窗口改为三栏式（歌曲列表 | 播放控制 | Chat）

**交互**：
- 自由文本输入 → send to DeepSeek API
- 上下文：当前歌曲信息 + 最近3条对话 + system prompt
- AI 自然回复（可聊歌曲感受、回忆、情绪等）
- 同时解析语义 → 抽取推荐信号

**信号抽取**（引擎侧，非 AI 侧）：
```
"好燃" / "爽" / "太炸了"       → like_artist(bonus=0.05)
"难听" / "太吵了" / "跳过吧"    → skip_artist(penalty=0.03)
"今天想听安静的" / "来点温柔的"  → prefer_calm(shift=0.1)
"有没有更老的歌" / "经典一点的"  → prefer_classic(boost=0.05)
"随便放" / "我没什么意见"       → increase_randomness
```

用关键词规则做语义解析（不额外调 API），结果写入 `history.chat_signals` 并立即触发 `rescore()`。

**成本**：对话部分走 DeepSeek API，~0.01元/次对话。

---

## 5. 文件结构（改后）

```
music_player/
├── app.py              # GUI (三栏式, 整合 engine 调用 + Chat)
├── engine.py           # 推荐引擎 (实时评分 + 候选池管理)
├── import_qq.py        # QQ歌单导入脚本 (新)
├── chat.py             # AI对话模块 (新)
├── mascot.py           # 桌面桌宠 (保持不变)
├── launcher.bat
├── data/
│   ├── taste.json          # 模式分区口味画像
│   ├── candidates_rap.json # Rap 候选池 (新)
│   ├── candidates_mixed.json # Mixed 候选池 (新)
│   ├── history.json        # 评分历史 + chat signals
│   ├── ncm_cookie.json     # 网易云登录
│   ├── qq_seed_rap.json    # QQ导入中间文件 (新)
│   ├── qq_seed_mixed.json  # QQ导入中间文件 (新)
│   ├── qq_seed_style.json  # QQ导入中间文件 (新)
│   ├── covers/
│   └── icon.ico
└── docs/
    └── superpowers/specs/
        └── 2026-06-08-realtime-engine-design.md
```

---

## 6. 实施顺序

1. **QQ 歌单导入** (`import_qq.py`) — 最优先，后续依赖种子数据
2. **taste.json 重构** — 数据迁移脚本，现有数据不丢
3. **engine.py 重写** — 候选池 + 实时评分 + simi 扩展
4. **app.py 适配** — 三栏布局 + 新 engine 接口 + Chat 面板
5. **chat.py** — AI 对话 + 信号抽取
6. **上线验证** — 完整链路测试

模块可增量推进：1-2 可独立做，3-4 需 1-2 完成，5 依赖 4 的 UI 框架。

---

## 7. 非目标（v2 不做）

- ❌ 多用户支持
- ❌ Web 版 / 手机适配
- ❌ 免 Docker 方案
- ❌ 播放引擎替换（ffplay 保持）
- ❌ 训练 ML 推荐模型（规则引擎足够）
