# Claude Music Player

React 19 + FastAPI + 网易云音乐 + DeepSeek AI 伴侣 + 推荐引擎。端口 8765。

## 速查

```bash
启动: F:/miniconda3/python.exe backend/server.py    # Python 路径别写错
构建: cd desktop && npx tsc -b && npx vite build     # 改前端必须重构建
提交: git add -A && git commit && git push            # dist/ 已入 git
```

## 目录

```
backend/
├── server.py           FastAPI 入口
├── state.py            StateManager (RLock 线程安全)
├── helpers.py          共享函数
├── desktop_lyrics.py   tkinter 桌面歌词
├── routes/             playback / queue / chat / lyrics / playlist
└── services/           tray / hotkeys / taskbar / lyrics_overlay
desktop/
├── src/                React 源码 (components/hooks/store/lib)
└── dist/               Vite 构建产物（已入 git，后端 serve）
engine.py               推荐引擎（不改算法）
chat.py                 AI 聊天
api/ncm_client.py       网易云 API（cookie 必须是 URL query param）
models/song.py          Song dataclass
config.py               路径常量（全局引用）
data/                   候选池/历史/封面/cookie
```

## 规则

1. 每次输出必须完整，截断则报错重试
2. 改前端源码 → 重构建 dist → commit + push
3. Python 路径 = `F:/miniconda3/python.exe`
4. ncm cookie 拼 URL query param，不放 HTTP header
5. 不改推荐引擎评分逻辑

## 已知坑

- `preview_start` 工具缓存了旧 Python 路径 `C:/ProgramData/miniconda3`（ENOENT），用 Bash 手动启动
- 桌面歌词 key 是 `_current_lyrics`（不是 `lyrics_cache._current`）
- `/api/prev` / `/api/toggle` 已在重构时修复
