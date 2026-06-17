# Claude Music · 赛博朋克音乐播放器

> tkinter 暗色主题 + 网易云音乐 + DeepSeek AI 伴侣 + 推荐引擎  
> "不只是播放器，是懂你品味的音乐伙伴"

---

## 🎯 核心体验

| 维度 | 描述 |
|------|------|
| 🎧 **双模式** | RAP 模式（说唱） / Mixed 模式（混合），独立候选池+评分 |
| 🧠 **推荐引擎** | ε-greedy bandit + 8维评分（艺人/流派/新颖性/历史反馈/时长/AI信号/来源/探索） |
| 🐰 **AI 伴侣沧溟** | DeepSeek 驱动，实时聊天+切歌+情绪感应+点歌 |
| 🎨 **设计系统** | 三层 token 架构（`_P`→`C`→`Cp`），4px 网格，赛博朋克紫粉蓝渐变 |
| 📊 **可解释推荐** | 实时评分明细柱状图，每首歌曲的推荐理由透明可见 |

---

## 🏗️ 架构

```
app.py          GUI 主程序 (~2450行), tkinter + ffplay
├── engine.py   推荐引擎 (~1130行), 候选池构建+8维评分
├── chat.py     AI 聊天 (~455行), DeepSeek API + 信号提取
├── tray.py     系统托盘+Toast通知+任务栏进度条 (Phase 1)
├── hotkeys.py  全局媒体键+组合热键 (Phase 1-2)
├── mini_player.py  Mini Player + 桌面歌词 (Phase 2)
├── smart_dj.py Smart DJ + Mood Radio (Phase 3)
├── report.py   月度听歌报告 (Phase 3)
├── config.py   API 配置
├── api/        网易云 API 客户端
└── models/     数据模型
```

---

## ✨ 功能清单

### Phase 0 — 核心播放
- [x] ffplay 子进程播放（`-nodisp -autoexit -loglevel quiet`）
- [x] 暂停/恢复（wall-clock 计时，非模拟 tick）
- [x] 可拖拽进度条（鼠标 seek）
- [x] 键盘 seek（←→ 前后 5%）
- [x] LRC 歌词解析 + 同步高亮
- [x] 专辑封面（PIL 加载 JPEG，暗化 25% 作为背景）
- [x] 音量滑块（0-150%，debounced 重启 ffplay）
- [x] 会话持久化（关闭恢复上次播放位置+模式）

### Phase 0 — 推荐引擎
- [x] 两种模式: RAP / Mixed（独立候选池 + 独立歌单）
- [x] 候选池: top artist → similar artist → genre → charts
- [x] 8 维评分: 历史反馈 / 标签匹配 / 艺人匹配 / AI 信号 / 探索奖励 / 来源质量 / 时长偏好 / 聊天信号
- [x] ε-greedy bandit（智能探索 vs 利用，自适应调整）
- [x] 每 10 首扩展相似歌曲
- [x] 歌单去重（已加入歌单的不再推荐）
- [x] 口味画像持久化（`taste.json`，按模式分区）
- [x] 评分明细 UI（6 条实时柱状图）

### Phase 0 — AI 伴侣沧溟
- [x] DeepSeek API（`deepseek-v4-flash`，无推理开销）
- [x] 切歌/喜欢/跳过/加入歌单 系统事件自动评论
- [x] `[切歌]` 标签 → AI 可主动跳过当前歌曲
- [x] 真实数据上下文（播放次数、上次收听、喜欢/跳过记录、艺人偏好）
- [x] 聊天信号提取（16 条规则 → 影响推荐评分）
- [x] 点歌系统（"我要听五首王菲的歌" → 队列 5 首 + 提升权重）
- [x] 艺人权重自动上调（点歌后 taste.json 权重 +0.15）
- [x] 禁止编造（system prompt 约束：不编造歌曲故事/背景）

### Phase 1 — 系统托盘 + Toast + 全局媒体键
- [x] **系统托盘**: pystray 图标，关闭→最小化到托盘不退出
- [x] **托盘菜单**: 播放/暂停、下一首、上一首、显示/隐藏、退出
- [x] **Toast 通知**: 切歌时右下角弹出歌名+艺人（winotify → PowerShell 降级）
- [x] **任务栏进度条**: 绿色播放进度 + 黄色暂停状态（ITaskbarList3）
- [x] **全局媒体键**: 键盘多媒体键（Play/Pause/Next/Previous）
- [x] **全局热键**: `Ctrl+Alt+←→Space L S ↑↓ M`

### Phase 2 — Mini Player + 桌面歌词
- [x] **Mini Player**: 340×72 悬浮条，置顶，半透明（α=0.93）
- [x] Mini 显示: 封面缩略图 + 歌名 + 艺人 + 4 按钮
- [x] Mini 拖拽移动（鼠标按住任意位置）
- [x] Mini 右键菜单: 返回完整模式 / 退出
- [x] **桌面歌词**: 透明无边框悬浮窗，卡拉 OK 渐变色（按进度紫→粉）
- [x] 歌词可拖拽，滚轮调字号（16-48pt）
- [x] 歌词右键菜单: 字号调节 / 关闭
- [x] 底栏 Mini/歌词 切换按钮

### Phase 3 — AI 深度能力
- [x] **Smart DJ**: 每 5 首后 AI 点评 + 推荐方向（temperature=1.2 高创意）
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
- [x] **听歌报告**: `/报告` `/月度` `/统计` 命令
  - 总播放次数/时长/首数
  - Top 10 艺人/歌曲
  - 喜欢率/跳过率
  - 曲风分布
  - 艺人权重 TOP 8
  - AI 互动信号统计

### Phase 4 — 硬核体验（技术债）
> 详见 [TECH_DEBT.md](TECH_DEBT.md)
- [ ] 交叉淡入淡出（Crossfade，3s afade）
- [ ] 频谱可视化（ffmpeg PCM → numpy FFT → Canvas 60fps）
- [ ] 10 段均衡器（Bass Boost/Vocal/Treble 预设）
- [ ] 睡眠定时器（30min 渐变音量→0）
- [ ] 主题市场（8 套配色热切换）

### 歌单管理
- [x] 网易云扫码登录
- [x] 自动创建 `Claude Rap` + `Claude Picks` 歌单
- [x] 一键加入歌单
- [x] 导入网易云歌单到播放队列
- [x] 历史回溯（按日期浏览过去的候选池）

---

## ⌨️ 快捷键

| 按键 | 功能 |
|------|------|
| `Space` | 播放/暂停 |
| `Ctrl+←` `Ctrl+→` | 上一首/下一首 |
| `←` `→` | 快退/快进 5% |
| `Ctrl+L` | 喜欢 |
| `Ctrl+S` | 跳过 |
| `Ctrl+A` | 加入歌单 |
| `Ctrl+F` | 聚焦聊天框 |
| `Ctrl+M` | 切换 Mini Player |
| `Ctrl+D` | 切换桌面歌词 |
| `+` `-` | 音量 ±5% |

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
| `Ctrl+Alt+↑` `Ctrl+Alt+↓` | 音量 ±5% |
| `Ctrl+Alt+M` | 静音 |

---

## 🚀 快速开始

### 环境要求
- Python 3.10+
- [NeteaseCloudMusicApi](https://github.com/Binaryify/NeteaseCloudMusicApi) Docker（本地 `localhost:3000`）
- ffplay（Windows: `winget install ffmpeg`）
- DeepSeek API Key（AI 伴侣，可选）

### 安装

```bash
cd F:/projects/music-player
pip install -r requirements.txt
```

### 配置

1. 设置环境变量 `DEEPSEEK_API_KEY`（可选，无 key 时 AI 降级为模板回复）
2. 启动网易云 API Docker:
   ```bash
   docker run -d -p 3000:3000 binaryify/netease_cloud_music_api
   ```
3. 运行:
   ```bash
   python app.py
   ```
4. 点击底栏「登录」扫码登录网易云

### 依赖

```
requests  pillow  pywin32  pystray  pynput  winotify
```

---

## 📁 数据文件

| 文件 | 说明 |
|------|------|
| `data/today.json` | RAP 模式候选池缓存 |
| `data/today_focus.json` | Mixed 模式候选池缓存 |
| `data/history.json` | 评分历史 + 单曲追踪 + 聊天信号 |
| `data/taste.json` | 口味画像（按模式分区） |
| `data/session.json` | 会话状态 |
| `data/covers/` | 专辑封面缓存 (.jpg) |
| `data/ncm_cookie.json` | 网易云登录态 |

---

## 🎨 设计系统

三层 token 架构，受 frontend-design + ui-ux-pro-max 技能指导：

```
_P (原语)     →  C (语义)     →  Cp (组件)
void=#06060f    BG=void         BTN_LIKE_BG=ash_border
lavender=#c084fc  AC=lavender   BTN_NAV_FG=blush
blush=#f0a8c0   AC_WARM=blush  BAR_FG=wisp
...
```

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
- **模式隔离**: RAP/Mixed 完全独立（候选池、歌单 blocklist、口味画像）
- **聊天驱动推荐**: "喜欢这首歌" → 艺人权重 ↑，"太吵了" → 降低该艺人
- **跨模式共享**: 点歌/情绪信号跨模式传递，但不会污染另一模式的候选池

---

*Built with Claude Code · 2026*
