# Current State (2026-06-08)

## 已完成
- [x] 推荐引擎: 网易云API搜歌, 多数据源(歌手/流派/排行榜), 评分算法, top20预取URL, 输出50首到today.json
- [x] GUI播放器: tkinter深色主题, 歌曲列表+专辑封面, ffplay流媒体播放, 进度条, 自动切歌
- [x] 评分系统: Like/Skip按钮 → history.json → engine下次跑时影响推荐
- [x] QR登录: 弹出二维码窗口, 扫码后cookie持久化到ncm_cookie.json
- [x] 歌单: 登录后可一键加到网易云"Claude Picks"歌单
- [x] 桌宠: 悬浮动画+气泡推荐+TTS语音
- [x] 桌面快捷方式: pythonw启动, 自定义图标
- [x] Docker ncm-api: 开机后需手动确认运行

## 开发中
- [ ] 播放稳定性: URL过期导致跳过 → 已改为每次实时拉取, 待验证
- [ ] 用户首次扫码登录(QR之前base64 bug导致失败, 已修复)

## 已知问题
1. **切歌后黑窗闪现**: 已加`creationflags=0x08000000`, 部分Windows版本仍可能弹窗
2. **首首歌有1-2秒"Fetching..."延迟**: 实时拉URL的代价, 可接受
3. **未登录时歌单功能不可用**: 预期行为, 需先扫码
4. **Focus模式候选歌少**: 流派查询返回结果不如Rap模式丰富
5. **封面加载慢**: 逐张请求网易云album API, 未做预加载

## 下一步计划
- [ ] 播放历史回溯(浏览昨天的推荐)
- [ ] 收藏歌曲本地缓存(like的歌曲汇总)
- [ ] 音量控制滑块
- [ ] 免Docker方案: 直接跑Node.js ncm-api
