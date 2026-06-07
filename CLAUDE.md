# Claude Music Player

## 项目目标
桌面音乐推荐播放器。每日自动生成个性化歌单（Rap + Focus/Chill 双模式），应用内播放、评分反馈优化、一键加入网易云歌单。

## 技术栈
- **语言**: Python 3.14
- **GUI**: tkinter (dark theme, ttk)
- **播放**: ffplay (ffmpeg, `-nodisp -autoexit`)
- **音源**: 网易云音乐 via [NeteaseCloudMusicApiEnhanced](https://github.com/NeteaseCloudMusicApiEnhanced/api-enhanced) (Docker, `localhost:3000`)
- **推荐引擎**: 自研评分算法 (artist权重 + genre关键词 + 新颖性 + 历史反馈)
- **平台**: Windows 11, MSYS2 bash

## 目录结构
```
music_player/
├── app.py              # GUI播放器 (699行)
├── engine.py           # 推荐引擎 (619行)
├── mascot.py           # 桌面桌宠 (559行)
├── launcher.bat        # 启动脚本
├── data/
│   ├── today.json      # Rap模式今日推荐
│   ├── today_focus.json# Focus模式今日推荐
│   ├── taste.json      # 用户口味画像(438首/338艺人)
│   ├── history.json    # 评分历史(like/skip)
│   ├── ncm_cookie.json # 网易云登录cookie
│   ├── icon.ico        # 桌面图标
│   └── covers/         # 专辑封面缓存
└── Docker              # ncm-api容器(需开机运行)
```

## 开发规范
- 路径统一用 `os.path.join(HOME, ...)` 或正斜杠
- GUI回调中异常用 `after(0, lambda e=err: ...)` 避免闭包bug
- API调用走 `ncm()` 封装函数，带session cookie
- ffplay启动必须带 `creationflags=0x08000000` 隐藏控制台
- 文件名一律小写下划线，类名驼峰
