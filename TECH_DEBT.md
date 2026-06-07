# Tech Debt (updated 2026-06-08)

| 优先级 | 问题 | 影响 | 位置 |
|--------|------|------|------|
| P0 | QQ种子数据待导入 | 推荐无基线 | import_qq.py |
| P1 | engine rebuild slow (API rate limit ~0.3s/call) | 模式切换30-60秒 | engine.py build_candidates |
| P1 | ffplay进程管理粗糙, 异常退出未清理 | 稳定性 | app.py |
| P2 | Candidate pool in-memory only, lost on restart | 重复构建 | app.py |
| P2 | Docker容器无自动重启 | 可用性 | Docker |
| P2 | Chat uses templates when no DEEPSEEK_API_KEY | 体验降级 | chat.py |
| P2 | mascot.py仍引用QQ音乐代码残留 | 维护性 | mascot.py |
| P3 | 评分算法权重纯主观, 未经数据验证 | 推荐质量 | engine.py |
| P3 | 没有测试用例 | 质量保证 | 全局 |
| P3 | 新用户冷启动(无taste.json) | 首次体验 | engine.py |
| P3 | engine.py genre关键词硬编码 | 可扩展性 | engine.py |

## 预计解决顺序
1. **本周**: P0 QQ种子导入
2. **下周**: P1 engine build速度优化, P1 ffplay进程管理
3. **后续**: P2 Docker自启, P2 candidate持久化, P3 测试
