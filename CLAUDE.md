# Claude Music Player

## 项目目标
桌面音乐推荐播放器。每日自动生成个性化歌单（Rap + Mixed 双模式），Web 前端播放、评分反馈优化、一键加入网易云歌单、AI 伴侣"沧溟"聊天交互。

## 技术栈
- **前端**: React 19 + TypeScript + Vite + Zustand + Tailwind CSS + framer-motion
- **后端**: Python 3.13+ / FastAPI / uvicorn, 端口 8765
- **音源**: 网易云音乐 via NeteaseCloudMusicApiEnhanced (Docker, `localhost:3000`)
- **AI**: DeepSeek API (deepseek-v4-flash)
- **平台**: Windows 11, MSYS2 bash

## 目录结构（实际）

```
music-player/
├── backend/
│   ├── server.py              # FastAPI app 入口 (~110行)
│   ├── state.py               # StateManager 线程安全状态管理
│   ├── helpers.py             # 共享辅助函数
│   ├── desktop_lyrics.py      # tkinter 桌面歌词悬浮窗
│   ├── routes/                # API 路由 (playback/queue/chat/lyrics/playlist)
│   └── services/              # 后台服务 (tray/hotkeys/taskbar/lyrics_overlay)
├── desktop/
│   ├── src/
│   │   ├── components/        # Background/Controls/Lyrics/Chat/Queue/Score/Visualizer
│   │   ├── hooks/             # useBackend / usePlayback / useKeyboard
│   │   ├── store/playerStore.ts  # Zustand 全局状态
│   │   └── lib/               # audioEngine / constants / utils
│   ├── dist/                  # Vite 构建产物（已入 git，后端直接 serve）
│   └── vite.config.ts         # Vite 配置，proxy /api → :8765
├── engine.py                  # 推荐引擎 (~1210行)
├── chat.py                    # AI 聊天 (~480行)
├── smart_dj.py                # Smart DJ + Mood Radio
├── report.py                  # 月度听歌报告
├── config.py                  # 集中配置 + 路径常量
├── api/ncm_client.py           # 网易云 API 客户端（cookie 作为 URL query param）
├── models/song.py             # Song 数据模型（dataclass + dict 向后兼容）
├── launcher.vbs               # Windows 快捷方式启动脚本
├── launcher.bat               # 命令行启动脚本
└── data/
    ├── candidates/            # 候选池快照 (rap.json / mixed.json / 日期快照)
    ├── covers/                # 专辑封面缓存
    ├── taste.json             # 口味画像（按模式分区）
    ├── history.json           # 评分历史
    ├── session.json           # 会话状态
    └── ncm_cookie.json        # 网易云登录态
```

## 硬性规则

1. **每次输出必须完整，不得截断或空白** — 检测到输出被截断时报错加重试，不输出空响应
2. **改完前端源码后必须重新构建 dist/** — `cd desktop && npx tsc -b && npx vite build`
3. **dist/ 已入 git** — 每次构建后必须 commit + push dist/，确保桌面快捷方式能拉到最新前端
4. **Python 路径** = `F:/miniconda3/python.exe`（不是 `C:/ProgramData/miniconda3`）
5. **启动命令** = `F:/miniconda3/python.exe backend/server.py`
6. **Cookie 传参** — ncm_client 必须把 cookie 拼为 URL query param（`?cookie=...`），不能放 HTTP header
7. **不改推荐算法** — engine.py 评分逻辑、数据格式保持稳定

## 关键已知问题

- `preview_start` 工具缓存了旧 Python 路径 `C:/ProgramData/miniconda3/python.exe`（ENOENT），暂用手动 `Bash` 启动后端代替
- 桌面歌词 key 已修复为 `_current_lyrics`（之前写错成 `lyrics_cache._current`）
- `/api/prev` 路由已在重构时新增（之前 tray/hotkey 调它 404）
- `/api/toggle` 已修复为实际切换 `playing` 状态（之前是空操作）
