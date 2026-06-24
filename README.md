# Claude Music · 赛博朋克音乐播放器

> **原生 tkinter 主力桌面应用** + FastAPI Web 远程控制台 + 网易云音乐 + DeepSeek AI 伴侣  
> "不只是播放器，是懂你品味的音乐伙伴"

---

## 🎯 核心体验

| 维度 | 描述 |
|------|------|
| 🎧 **三模式** | RAP 模式（说唱） / Mixed 模式（混合） / Focus 模式（专注），独立候选池+评分 |
| 🧠 **推荐引擎** | ε-greedy bandit + 8维评分（艺人/流派/新颖性/历史反馈/时长/AI信号/来源/探索） |
| 🐰 **AI 伴侣沧溟** | DeepSeek 驱动，实时聊天+切歌+情绪感应+点歌+Smart DJ主动推送 |
| 🎨 **赛博朋克设计** | 萌系赛博朋克，紫粉蓝渐变，暗色原生 tkinter UI，毛玻璃专辑封面 |
| 📊 **Web 远程控制台** | 手机/平板浏览器访问 `:8765`，远程遥控 + 数据看板 |

---

## 🏗️ 架构

```
┌─ 主力桌面应用 (tkinter + ffplay) ────────────────────────────┐
│  app.py             主入口 (~2700行)，赛博朋克全功能 UI          │
│  engine.py           推荐引擎 (~1230行)                          │
│  chat.py             AI 聊天 (~490行)                            │
│  smart_dj.py         Smart DJ + Mood Radio (~300行)              │
│  mascot.py           桌面吉祥物 Mochi 🐰                          │
│  mini_player.py      Mini 播放器 + 桌面歌词                       │
│  tray.py             系统托盘 + Toast 通知                        │
│  hotkeys.py          全局热键 + 媒体键                            │
│  api/ncm_client.py   网易云 API 客户端                            │
│                                                                │
│  Session Bridge ── session.json ── (共享状态文件)               │
│                                                                │
├─ Web 远程控制台 (FastAPI + React) ────────────────────────────┤
│  backend/server.py   FastAPI 入口 + now-playing 状态桥接       │
│  backend/routes/     API 路由 (playback/queue/chat/lyrics)     │
│  desktop/src/        React 远程控制台 (简化版)                   │
│  desktop/dist/       Vite 构建产物                               │
└────────────────────────────────────────────────────────────────┘
```

---

## ✨ 功能清单

### Phase 0 — 核心播放
- [x] ffplay 流式播放（后端代理网易云 URL + Referer）
- [x] 播放/暂停/上一首/下一首
- [x] 可拖拽进度条（鼠标 seek）
- [x] 键盘快进快退
- [x] LRC 歌词解析 + 同步高亮（Canvas + 桌面歌词）
- [x] 专辑封面（`data/covers/` 缓存，PIL 高斯模糊背景）
- [x] 音量滑块 + 静音
- [x] 会话持久化（`session.json`，含播放状态 + Mood Radio 状态）
- [x] ffplay 子进程管理，退出时自动清理

### Phase 0 — 推荐引擎
- [x] **三种模式**: RAP / Mixed / Focus（独立候选池 + 独立歌单）
- [x] 候选池: top artist → similar artist → genre → charts
- [x] 8 维评分: 历史反馈 / 标签匹配 / 艺人匹配 / AI 信号 / 探索奖励 / 来源质量 / 时长偏好 / 聊天信号
- [x] ε-greedy bandit（智能探索 vs 利用，自适应调整）
- [x] 每 10 首扩展相似歌曲
- [x] 歌单去重（已加入歌单的不再推荐）
- [x] 口味画像持久化（`taste.json`，按模式分区，v2 格式）
- [x] 评分明细 UI（实时柱状图）

### Phase 0 — AI 伴侣沧溟
- [x] DeepSeek API（`deepseek-v4-flash`）
- [x] 切歌/喜欢/跳过 系统事件自动评论
- [x] `[切歌]` 标签 → AI 可主动跳过当前歌曲
- [x] 真实数据上下文（播放次数、上次收听、喜欢/跳过记录、艺人偏好）
- [x] 聊天信号提取（16 条规则 → 影响推荐评分）
- [x] 点歌系统（"我要听五首王菲的歌" → 队列 5 首 + 提升权重）
- [x] 歌曲选择器（多结果时弹出对话框供选择）
- [x] API 指数退避重试（3次尝试：0s / 2s / 4s）
- [x] 禁止编造（system prompt 约束：不编造歌曲故事/背景）

### Phase 1 — 系统托盘 + Toast + 全局媒体键
- [x] **系统托盘**: pystray 图标，关闭→最小化到托盘不退出
- [x] **托盘菜单**: 播放/暂停、下一首、上一首、显示/隐藏、退出
- [x] **Toast 通知**: 切歌时右下角弹出歌名+艺人（winotify → PowerShell 降级）
- [x] **任务栏进度条**: 绿色播放进度 + 黄色暂停状态（ITaskbarList3）
- [x] **全局媒体键**: 键盘多媒体键（Play/Pause/Next/Previous）
- [x] **全局热键**: `Ctrl+Alt+←→Space L S`

### Phase 2 — 桌面歌词
- [x] **桌面歌词**: 透明无边框悬浮窗，卡拉 OK 渐变色（按进度紫→粉）
- [x] 歌词可拖拽，滚轮调字号（14-48pt）
- [x] 双行显示：当前行 + 下一行
- [x] 独立线程运行，不阻塞主 UI

### Phase 3 — AI 深度能力
- [x] **Smart DJ**: 每 5 首后 AI 点评 + 推荐方向（temperature=1.2）
- [x] Smart DJ **主动推送**：DJ 推荐 genre 时自动搜索 3 首歌曲插入队列
- [x] Smart DJ 会话弧线追踪（记录每首播放 + 反馈）
- [x] **Mood Radio**: 6 种情绪电台，聊天触发
  - 💔 疗愈电台（失恋/难过/emo）
  - 🎉 庆祝模式（开心/兴奋/嗨）
  - 📚 专注模式（学习/加班/coding）
  - 🌙 助眠模式（睡觉/放松/chill）
  - 💪 运动模式（跑步/健身/workout）
  - 🏮 华语经典（中国风/古风/老歌）
- [x] Mood Radio 评分调整（匹配 mood 的歌曲自动 boost）
- [x] Mood Radio 自动结束（10首后返回普通模式）
- [x] Mood Radio 状态持久化（`session.json`，重启后恢复）
- [x] Focus 模式候选池持久化（`data/today_focus.json`）
- [x] **听歌报告**: `/报告` `/月度` `/统计` 命令
  - 总播放次数/时长/首数
  - Top 10 艺人/歌曲
  - 喜欢率/跳过率
  - 曲风分布
  - 艺人权重 TOP 8
  - AI 互动信号统计

### Phase 4 — 硬核体验
- [x] **睡眠定时器 UI**: `🌙 定时` 按钮，15/30/45/60分钟预设，3秒淡出停止
- [x] **模式切换强制重建**: 切换模式时跳过缓存，完全重建候选池
- [x] **AI 点歌立即刷新**: 点歌后候选池正确排序，9.99分歌曲排到顶部
- [ ] 交叉淡入淡出（Crossfade，3s afade）
- [ ] 10 段均衡器（Bass Boost/Vocal/Treble 预设）
- [ ] 主题市场（8 套配色热切换）

### Phase 5 — Web 远程控制台
- [x] **Now Playing 状态桥接**: FastAPI 实时读取 `session.json` 获取播放状态
- [x] **远程控制台**: React 页面简化，聚焦手机/平板远程遥控
- [x] 三模式切换 + 刷新 + 基础播放控制
- [ ] SSE 实时状态推送
- [ ] 听歌报告可视化图表

### 歌单管理
- [x] 网易云扫码登录
- [x] 自动创建 `Claude Rap` + `Claude Picks` + `Claude Focus` 歌单
- [x] 一键加入歌单
- [x] 导入网易云歌单到播放队列
- [x] Smart Insert（行为触发自动插入相似/不同歌曲）
- [x] 历史回溯（按日期浏览候选池快照）

---

## ⌨️ 快捷键

| 按键 | 功能 |
|------|------|
| `Space` | 播放/暂停 |
| `←` `→` | 上一首/下一首 |
| `+` `-` | 音量 ±5% |
| `L` | 喜欢当前歌曲 |
| `S` | 跳过当前歌曲 |
| `Ctrl+F` | 聚焦聊天输入框 |

### 全局热键（窗口失焦也生效）

| 按键 | 功能 |
|------|------|
| `▶⏸` 媒体键 | 播放/暂停 |
| `⏭` 媒体键 | 下一首 |
| `⏮` 媒体键 | 上一首 |
| `Ctrl+Alt+Space` | 播放/暂停 |
| `Ctrl+Alt+←` `Ctrl+Alt+→` | 上一首/下一首 |
| `Ctrl+Alt+L` | 喜欢 |
| `Ctrl+Alt+S` | 跳过 |

---

## 🚀 快速开始

### 环境要求
- Python 3.13+
- [NeteaseCloudMusicApi](https://github.com/Binaryify/NeteaseCloudMusicApi) Docker（本地 `localhost:3000`）
- DeepSeek API Key（AI 伴侣，可选）
- Node.js 20+（仅 Web 远程控制台需要）

### 安装

```bash
cd F:/projects/music-player

# 主应用（原生 tkinter）
pip install -r backend/requirements.txt

# Web 远程控制台（可选）
cd desktop && npm install && npm run build && cd ..
```

### 配置

1. 设置环境变量 `DEEPSEEK_API_KEY`（可选，无 key 时 AI 降级为模板回复）
2. 启动网易云 API Docker:
   ```bash
   docker run -d -p 3000:3000 binaryify/netease_cloud_music_api
   ```

### 启动

```bash
# 主力桌面应用（推荐）
python app.py

# Web 远程控制台（可选，另开终端）
python backend/server.py
# 浏览器打开 http://localhost:8765（或手机访问 http://<局域网IP>:8765）
```

### 快捷启动

双击桌面 `Claude Music.lnk`（调用 `launcher.vbs`）：
- 自动检测服务器是否已运行
- 未运行则启动后端 → 等待就绪 → 打开浏览器
- 已在运行则直接打开浏览器

---

## 📁 数据文件

| 文件 | 说明 |
|------|------|
| `data/today.json` | RAP 模式候选池缓存 |
| `data/today_focus.json` | Focus 模式候选池缓存 |
| `data/candidates/` | 日期快照候选池（`rap.json`、`mixed.json`、`focus.json`） |
| `data/history.json` | 评分历史 + 单曲追踪 + 聊天信号 + recommended_ids |
| `data/taste.json` | 口味画像 v2（按模式分区：rap/mixed/focus） |
| `data/session.json` | 会话状态（模式/当前播放/epsilon/Mood Radio/队列预览） |
| `data/covers/` | 专辑封面缓存 |
| `data/ncm_cookie.json` | 网易云登录态 |
| `data/artist_id_cache.json` | 艺人 ID 缓存 |

---

## 🔌 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/status` | 服务状态 |
| GET | `/api/now-playing` | 当前播放（从 session bridge 读取） |
| GET | `/api/queue` | 歌曲队列 + 模式 + epsilon |
| GET | `/api/play/{id}` | 解析歌曲播放 URL |
| GET | `/api/stream/{id}` | 音频流代理 |
| GET | `/api/lyrics/{id}` | LRC 歌词解析 |
| POST | `/api/next` | 下一首 |
| POST | `/api/prev` | 上一首 |
| POST | `/api/like/{id}` | 喜欢 |
| POST | `/api/skip/{id}` | 跳过 |
| POST | `/api/toggle` | 播放/暂停 |
| POST | `/api/mode` | 切换模式（rap/mixed/focus） |
| POST | `/api/rebuild` | 重建候选池 |
| POST | `/api/smart-insert` | 行为触发智能插歌 |
| POST | `/api/chat/message` | AI 聊天 |
| POST | `/api/playlist/add/{id}` | 加入网易云歌单 |
| POST | `/api/sleep/{min}` | 睡眠定时器 |
| WS | `/ws` | 实时进度同步 |

---

## 📝 命令参考

在聊天框输入:

| 命令 | 效果 |
|------|------|
| `/报告` `/月度` `/统计` | 生成月度听歌报告 |
| "我要听五首王菲的歌" | 搜索并队列 5 首，上调王菲权重 |
| "我失恋了" / "好开心" / "想睡觉" | 触发对应 Mood Radio |
| "不想听" / "切了吧" | AI 可回复 `[切歌]` 自动跳过 |

---

## 🧠 技术亮点

- **推荐可解释**: 每首歌的 8 维评分实时展示，为什么推这首歌一目了然
- **自适应探索**: ε-greedy bandit，喜欢探索歌曲 → ε↓，跳过推荐歌曲 → ε↑
- **模式隔离**: RAP/Mixed/Focus 完全独立（候选池、歌单 blocklist、口味画像）
- **聊天驱动推荐**: "喜欢这首歌" → 艺人权重 ↑，"太吵了" → 降低该艺人
- **Smart Insert + Smart DJ 推送**: 喜欢自动插相似歌曲，DJ 主动搜索推荐风格歌曲
- **线程安全**: StateManager + RLock + 防重入守卫，桌面歌词获取快照避免数据竞态
- **Mode Switch 强制重建**: 模式切换跳过缓存，每次完全重建候选池

---

*Built with Claude Code · 2026*
