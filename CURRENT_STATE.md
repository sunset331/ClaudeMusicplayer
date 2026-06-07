# Current State (2026-06-08)

## 已完成
- [x] v2 Real-time Engine: candidate pool builder, scoring, rescoring, simi expansion
- [x] QQ playlist import tool (import_qq.py)
- [x] taste.json v2 migration (mode-partitioned: rap + mixed)
- [x] Three-column layout: song list | now playing | AI chat
- [x] Chat panel with DeepSeek API + keyword signal extraction
- [x] Mixed Mode (replaces Focus, based on user's QQ mixed playlist)
- [x] 网易云API搜歌, 多数据源(歌手/流派/排行榜/simi)
- [x] GUI播放器: tkinter深色主题, ffplay流媒体播放, 自动切歌
- [x] 评分系统: Like/Skip → history.json → 实时重排
- [x] QR登录 + 一键加歌单
- [x] 桌宠: 悬浮动画+气泡推荐+TTS语音

## 开发中
- [ ] QQ playlist data extraction (user needs to export from browser DevTools)
- [ ] Seed data ingestion: waiting for QQ JSON files → run import_qq.py

## 已知问题
1. Chat requires DEEPSEEK_API_KEY env var (falls back to templates)
2. Engine rebuild on mode switch takes 30-60 seconds (API rate limiting)
3. Candidate pool not persisted across app restarts (P2)
4. 切歌后黑窗闪现: 已加`creationflags=0x08000000`, 部分Windows版本仍可能弹窗
5. Docker容器无自动重启, 开机后需手动`docker start ncm-api`

## 下一步计划
- [ ] 导入QQ歌单种子数据 (用户需导出JSON)
- [ ] 音量控制滑块
- [ ] 播放历史回溯(浏览昨天的推荐)
- [ ] 免Docker方案: 直接跑Node.js ncm-api
