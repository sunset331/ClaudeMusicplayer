# Tech Debt

| 优先级 | 问题 | 影响 | 位置 |
|--------|------|------|------|
| P0 | 播放每次实时拉URL, 切歌延迟1-2秒 | 体验 | app.py `_play_current` |
| P1 | ffplay进程管理粗糙, 异常退出未清理 | 稳定性 | app.py `_start_ffplay` |
| P1 | engine.py `_fetch_and_play` 与 app.py 各自调API, 无缓存共享 | 重复请求 | engine.py/app.py |
| P2 | GUI回调用`after(0, lambda...)`散落各处, 异常难追踪 | 维护性 | app.py 多处 |
| P2 | mascot.py仍引用QQ音乐代码残留(QQMUSIC_DIR等已被清理但逻辑混) | 维护性 | mascot.py |
| P2 | Docker容器无自动重启, 开机后需手动`docker start ncm-api` | 可用性 | Docker |
| P3 | engine.py genre关键词硬编码, 扩展需改源码 | 可扩展性 | engine.py |
| P3 | 评分算法`score_rap`/`score_focus`未经数据验证, 权重纯主观 | 推荐质量 | engine.py |
| P3 | 没有测试用例 | 质量保证 | 全局 |
| P3 | engine.py依赖`data/taste.json`由旧QQ数据构建, 新用户无初始数据 | 冷启动 | engine.py |

## 预计解决顺序
1. **本周**: P0播放延迟(预加载下一首), P1 ffplay进程管理
2. **下周**: Docker自启 + engine冷启动优化
3. **后续**: 重构engine/genre配置为外部JSON, 补充测试
