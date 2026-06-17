# Claude Music Player — Technical Debt & Enhancement Roadmap

> 最后更新: 2026-06-16

## ✅ Phase 1-3 实施中 | 📋 Phase 4 技术债

---

## Phase 1: 系统托盘 + Toast 通知 + 全局媒体键

### 系统托盘 (`tray.py`)
- **库**: pystray + PIL
- 最小化到托盘, 右键菜单: 播放/暂停/下一首/上一首/显示/退出
- 关闭按钮 → 隐藏窗口; 实际退出 → 托盘菜单

### Toast 通知 (`tray.py`)
- **库**: winotify (降级: PowerShell toast)
- 切歌时弹 toast: 歌名 + 艺人

### 全局媒体键 (`hotkeys.py`)
- **库**: pynput
- 媒体键: Play/Pause, Next, Previous
- Ctrl+Alt+Right/Left/Space/L/S → 控制播放

### 任务栏集成 (`tray.py`)
- **库**: pywin32 (ITaskbarList3)
- 任务栏进度条 (绿色) + 缩略图按钮 (▶⏸ ⏭ ⏮)

---

## Phase 2: Mini Player + 桌面歌词

### Mini Player (`mini_player.py`)
- 300×80 悬浮条, 置顶, 封面+歌名+3按钮
- 可拖拽, 右键菜单切换回完整模式
- 半透明 (alpha 0.92), overrideredirect

### 桌面歌词 (`mini_player.py` — DesktopLyrics)
- 透明无边框, 单行/双行歌词悬浮
- 卡拉OK渐变色 (左→右按进度)
- 可拖拽, 右键切换大小/关闭

### 全局热键增强 (`hotkeys.py`)
- Ctrl+Alt+Up/Down: 音量 ±5%
- Ctrl+Alt+M: 静音
- Ctrl+Alt+T: 切换 Mini Player
- Ctrl+Alt+D: 切换桌面歌词

---

## Phase 3: AI 深度能力

### Smart DJ (`smart_dj.py`)
- 每 5 首后 AI 决定下一首方向
- 基于时间/最近反馈/聊天情绪/播放趋势
- temperature=1.2 高创意调用

### Mood Radio (`smart_dj.py`)
- 聊天触发情绪电台: "我失恋了" → 疗愈电台
- 30分钟/10首后自然切换
- UI 显示: "📻 疗愈电台 · 剩余 6 首"

### 每周发现 (`engine.py`)
- 每周一生成 "Claude Weekly Discovery" (20首)
- ε=0.8 高探索, 过滤近期播过的艺人

### 听歌报告 (`report.py`)
- 月度统计: 总时长/Top艺人/曲风分布/时段热力图
- 聊天命令: `/报告` `/月度` `/统计`

---

## Phase 4: 硬核体验 (技术债)

### 交叉淡入淡出 (Crossfade)
- **难度**: 中 | **工时**: ~4h
- 方案: 两个 ffplay 重叠 3s → A 音量 1.0→0, B 音量 0→1.0
- 或用 ffmpeg filter_complex concat + afade

### 频谱可视化 (Spectrum)
- **难度**: 高 | **工时**: ~8h
- ffmpeg PCM → numpy FFT → Canvas 60fps 柱状图
- 需额外 ffmpeg 进程输出 PCM

### 均衡器 (EQ)
- **难度**: 中 | **工时**: ~3h
- ffmpeg equalizer/anequalizer filter
- 10段滑块: 32,64,125,250,500,1k,2k,4k,8k,16k Hz
- 预设: Bass Boost / Vocal / Treble / Custom

### 睡眠定时器
- **难度**: 低 | **工时**: ~1.5h
- 聊天命令 "30分钟后停止"
- 最后30s 渐变音量→0
- 预设: 15/30/45/60 min

### 主题市场
- **难度**: 中 | **工时**: ~4h
- 8套预设配色 (Cyberpunk/Midnight/Forest/Ocean/Sunset/Mono/Sakura/Matrix)
- 每套 = _P + C + Cp token 层
- 热切换: 导出到 data/themes/*.json
