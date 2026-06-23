# Claude Music Player — Technical Debt & Enhancement Roadmap

> 最后更新: 2026-06-23

---

## ✅ Phase 1-3 已完成 | 📋 Phase 4 技术债

---

## 2026-06-23 重构记录

### Bug 修复
- [x] 桌面歌词 key 错误 → `_current_lyrics` 替代 `lyrics_cache._current`
- [x] 歌词线程数据竞态 → StateManager.get_snapshot() 线程安全快照
- [x] `/api/prev` 路由缺失 → 新增路由（tray/hotkey 调用从 404 修复）
- [x] `/api/toggle` 空操作 → 实际切换 `playing` 状态
- [x] `report.py` 缺 `import re` → NameError 修复
- [x] `audioEngine.onEvent` 回调泄漏 → `useRef` 追踪 cleanup
- [x] keyboard handlers 每帧重建 → `useMemo` 稳定引用

### 消除重复
- [x] 删除 `_ncm_song_to_internal()` → 统一用 `Song.from_ncm_song()`
- [x] `_load_candidates_into_state()` 提取（3 处重复 → 1 个函数）
- [x] `_refresh_mode()` + `_daily_refresh()` / `rebuild()` 合并
- [x] 前端 smart-insert 三处合并 → `useBackend.smartInsert()`
- [x] 路径常量化 → 全部从 `config.py` import

### 架构拆分
- [x] `server.py`(996行) → `state.py` + `helpers.py` + `routes/*` + `services/*`
- [x] `FluidBackground.tsx`(242行) → `PigmentBackground` + `RippleBackground` + wrapper
- [x] 启动器修复 (`launcher.vbs` / `launcher.bat` Python 路径)

---

## Phase 1: 系统托盘 + Toast 通知 + 全局媒体键 ✅

### 系统托盘 (`backend/services/tray.py`)
- **库**: pystray + PIL
- 最小化到托盘, 右键菜单: 播放/暂停/下一首/上一首/显示/退出
- 关闭按钮 → 隐藏窗口; 实际退出 → 托盘菜单

### Toast 通知 (`backend/services/tray.py`)
- **库**: winotify (降级: PowerShell toast)
- 切歌时弹 toast: 歌名 + 艺人

### 全局媒体键 (`backend/services/hotkeys.py`)
- **库**: pynput
- 媒体键: Play/Pause, Next, Previous
- Ctrl+Alt+Right/Left/Space/L/S → 控制播放

### 任务栏集成 (`backend/services/taskbar.py`)
- **库**: pywin32 (ITaskbarList3)
- 任务栏进度条 (绿色播放) + 暂停状态 (黄色)

---

## Phase 2: 桌面歌词 ✅

### 桌面歌词 (`backend/desktop_lyrics.py`)
- 透明无边框 tkinter 悬浮窗
- 卡拉OK渐变色 (左→右按进度紫→粉)
- 可拖拽, 滚轮调字号 (14-48pt)
- 双行显示：当前行 + 下一行
- 独立 daemon 线程运行

### 启动 (`backend/services/lyrics_overlay.py`)
- StateManager.get_snapshot() 线程安全快照

---

## Phase 3: AI 深度能力 ✅

### Smart DJ (`smart_dj.py`)
- 每 5 首后 AI 决定下一首方向
- 基于时间/最近反馈/聊天情绪/播放趋势
- temperature=1.2 高创意调用

### Mood Radio (`smart_dj.py`)
- 聊天触发情绪电台: "我失恋了" → 疗愈电台
- 6 种模式: 疗愈/庆祝/专注/助眠/运动/华语经典
- 10首后自然切换回普通模式

### 听歌报告 (`report.py`)
- 月度统计: 总时长/Top艺人/曲风分布/时段热力图
- 聊天命令: `/报告` `/月度` `/统计`

---

## Phase 4: 硬核体验 (技术债)

### 交叉淡入淡出 (Crossfade)
- **难度**: 中 | **工时**: ~4h
- 方案: 两个 ffplay 重叠 3s → A 音量 1.0→0, B 音量 0→1.0

### 均衡器 (EQ)
- **难度**: 中 | **工时**: ~3h
- ffmpeg equalizer/anequalizer filter
- 10段滑块: 32,64,125,250,500,1k,2k,4k,8k,16k Hz
- 预设: Bass Boost / Vocal / Treble / Custom

### 睡眠定时器 UI
- **难度**: 低 | **工时**: ~1.5h
- 后端 API 已就绪 (`POST /api/sleep/{minutes}`)
- 需前端 UI：定时器选择器 + 倒计时显示

### 主题市场
- **难度**: 中 | **工时**: ~4h
- 8套预设配色 (Cyberpunk/Midnight/Forest/Ocean/Sunset/Mono/Sakura/Matrix)
- 每套 = CSS 自定义属性层
- 热切换: 导出到 data/themes/*.json
