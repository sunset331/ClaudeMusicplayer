# Architecture

## 模块关系
```
                    ┌─────────────┐
                    │  NetEase    │
                    │  Cloud API  │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
    ┌─────────────┐ ┌──────────┐ ┌──────────┐
    │  engine.py  │ │  app.py  │ │ mascot.py│
    │  (推荐引擎)  │ │  (播放器) │ │ (桌宠)   │
    └──────┬──────┘ └────┬─────┘ └────┬─────┘
           │              │            │
           ▼              ▼            ▼
    ┌──────────────────────────────────────┐
    │              data/                   │
    │  today.json  taste.json  history.json│
    │  today_focus.json  ncm_cookie.json   │
    └──────────────────────────────────────┘
```

## 数据流
```
[每天首次启动]
app.py _init_data()
  → 检查today.json日期 ≠ 今天
  → 异步调用 engine.py --mode both
    → engine.py:
        加载taste.json(438首歌/338艺人)
        调用NetEase API搜索:
          - 20位top艺人 × 25首
          - 12位生态艺人 × 15首
          - 20个genre关键词 × 25首
          - 3个排行榜 × 30首
        → 评分(artist权重/genre匹配/新颖性/历史反馈)
        → 去重 → 选50首
        → 拉取top20播放URL
        → 写入 today.json
  → app.py _load() 读取JSON → 填充列表

[播放流程]
双击歌曲 → _play_current()
  → stop旧ffplay进程
  → 线程调 GET /song/url/v1?id=xxx
  → ffplay -nodisp -autoexit <url>
  → _watch_playback每2秒检查进程
  → 进程退出 → 自动_next()

[评分流程]
点Like → _update_hist(song, "like")
  → history.json: liked_artists[歌手名]++
  → 下次engine跑时 score_rap() 读history加分

[歌单流程]
点Login(QR) → 弹窗显示QR → 扫码
  → cookie存ncm_cookie.json + Session
  → 点"+ Add to Playlist"
  → GET /playlist/tracks?op=add&pid=xxx&tracks=歌曲ID
```

## 后续扩展
- **播放**: 可替换ffplay为pygame/vlc, 但ffplay目前最稳定
- **推荐**: engine可独立部署为定时任务(cron), 解耦播放器
- **多用户**: taste.json和历史按用户拆分
- **Web版**: tkinter → Flask + HTML5 Audio, 手机也能用
