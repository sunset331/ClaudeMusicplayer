# Claude Music Player

原生 tkinter 赛博朋克 + FastAPI Web 远程控制台 + 网易云音乐 + DeepSeek AI 伴侣 + 推荐引擎。端口 8765。

## 速查

```bash
启动(主力):  F:/miniconda3/python.exe app.py              # 原生 tkinter 赛博朋克
启动(WEB):  F:/miniconda3/python.exe backend/server.py    # Web 远程控制台(可选)
构建:       cd desktop && npx tsc -b && npx vite build     # 改前端必须重构建
提交:       git add -A && git commit && git push            # dist/ 已入 git
```

## 目录

```
app.py                  主力桌面应用 (~2700行, tkinter + ffplay)
engine.py               推荐引擎 (不改算法)
chat.py                 AI 聊天
smart_dj.py             Smart DJ + Mood Radio
mascot.py               桌面吉祥物 Mochi
mini_player.py          Mini 播放器 + 桌面歌词
tray.py                 系统托盘 + Toast
hotkeys.py              全局热键
api/ncm_client.py       网易云 API（cookie 必须是 URL query param）
models/song.py          Song dataclass
config.py               路径常量（全局引用）
data/                   候选池/历史/封面/cookie
backend/
├── server.py           FastAPI 入口
├── state.py            StateManager (RLock 线程安全)
├── helpers.py          共享函数
├── desktop_lyrics.py   tkinter 桌面歌词
├── routes/             playback / queue / chat / lyrics / playlist
└── services/           tray / hotkeys / taskbar / lyrics_overlay
desktop/
├── src/                React 源码 (Web 远程控制台)
└── dist/               Vite 构建产物（已入 git，后端 serve）
```

## 规则

1. 每次输出必须完整，截断则报错重试
2. 改前端源码 → 重构建 dist → commit + push
3. Python 路径 = `F:/miniconda3/python.exe`
4. ncm cookie 拼 URL query param，不放 HTTP header
5. 不改推荐引擎评分逻辑
6. **主力启动**: `python app.py` (原生 tkinter 赛博朋克)
7. Web 远程控制台: `python backend/server.py` (可选，手机/平板遥控)
8. 桌面快捷方式指向 `launcher.vbs`（wscript启动 `app.py`，免终端黑窗）

## 已知坑

- `preview_start` 工具缓存了旧 Python 路径 `C:/ProgramData/miniconda3`（ENOENT），用 Bash 手动启动
- 桌面歌词 key 是 `_current_lyrics`（不是 `lyrics_cache._current`）
- `/api/prev` / `/api/toggle` 已在重构时修复
