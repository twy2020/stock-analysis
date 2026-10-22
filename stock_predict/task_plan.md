# 股票预测训练系统

## Goal

在已有预处理数据基础上，构建可运行的多任务 CNN + Transformer 训练系统，提供训练过程可视化、股票数据可视化、预测入口、评估报告和架构可行性分析。

## Phases

### Phase 1: 现有数据和接口复核
**Status:** completed
- [x] 检查预处理输出和 feature schema
- [x] 确定序列窗口、时间切分和多任务标签接口
- [x] 设计训练/预测/评估文件布局

### Phase 2: 模型和数据管线
**Status:** completed
- [x] 实现 Dataset、时间序列窗口和 DataLoader
- [x] 实现多尺度 CNN + Transformer + 三任务 heads
- [x] 实现可复现配置、checkpoint 和早停

### Phase 3: 训练和可视化
**Status:** completed
- [x] 实现训练循环、损失记录和 PNG 图表
- [x] 实现股票价格/成交量/特征/标签可视化
- [x] 实现训练参数和预测分布可视化

### Phase 4: 预测和评估
**Status:** completed
- [x] 实现单条/最新窗口预测入口
- [x] 实现回归、分类、波动率和简单策略指标
- [x] 输出评估 JSON/CSV/Markdown 报告

### Phase 5: 架构分析和端到端验证
**Status:** completed
- [x] 完成参数量、显存、速度和数据规模分析
- [x] 用小规模配置跑通训练、预测和评估
- [x] 记录限制、风险和下一步建议

## Next Step

已完成 gated hybrid 架构优化、基线对比和端到端验证。

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| `git status` reported not a repository | 1 | Repository metadata is absent; proceeded with direct file validation |
| PowerShell cleanup command was rejected by runtime policy | 1 | Kept generated `__pycache__` artifact; no impact on preprocessing outputs |
| Transformer nested-tensor warning | 1 | Non-blocking warning from `norm_first=True`; training and inference completed |
| torch.load future warning | 1 | Non-blocking serialization warning; checkpoint loaded successfully |
| Hybrid v2 gate initialization collapsed input scale | 1 | Initialized the feature gate to identity-like scaling and reran as hybrid v3 |
