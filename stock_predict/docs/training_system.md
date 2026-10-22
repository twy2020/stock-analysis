# 训练系统说明与架构可行性分析

## 已实现模块

```text
processed CSV + feature schema
          ↓
60 日滑动窗口 Dataset
          ↓
多尺度 1D CNN（kernel=3/5/9）
          ↓
Transformer Encoder（2 层，4 heads）
          ↓
多任务预测头
  ├── 未来 5 日收益率回归
  ├── 未来 5 日上涨概率分类
  └── 未来 5 日波动率回归
```

当前推荐的优化版本是 `GatedHybridCNNTransformer`：CNN 和 Transformer 并行提取局部/全局信息，再通过逐时间步门控融合。训练入口使用 `--model-variant hybrid`；`baseline` 仍保留用于对照。

训练入口为 `train.py`，模型和数据模块位于 `stock_model/`。

## 训练产物

每个 run 目录包含：

- `config.json`：训练超参数、字段、样本数和参数量；
- `best.pt`：验证集损失最优 checkpoint；
- `history.csv`：每轮训练损失、验证指标、学习率；
- `metrics.json`：测试集指标；
- `test_predictions.csv`：测试窗口逐条预测；
- `evaluation_report.md`：Markdown 评估报告；
- `plots/training_curves.png`：损失和验证指标曲线；
- `plots/test_predictions.png`：预测、概率和简单策略曲线。

## 基线结果（当前数据）

当前数据只有一只股票、975 条有效样本，训练结果只能作为管线验证：

- 方向准确率约 51.3%，接近随机水平；
- 收益方向准确率约 49.7%；
- 测试集收益率 MAE 约 0.058；
- 测试集最大回撤约 -63.7%；
- 简单阈值策略未计交易成本，不能作为投资结论。

## 可行性判断

工程上可行：当前架构约 19.6 万参数，RTX 3060 上批量 32、窗口 60 的前向计算约 4.9 ms，适合快速实验。

研究上暂不能下结论：当前样本只有单只股票，且有效样本不足 1000 条。模型很容易记住个股的局部历史形态，无法据此判断跨股票泛化能力。正式实验前应：

1. 增加多只股票、行业和市场指数数据；
2. 使用滚动 walk-forward 验证，而非单一时间切分；
3. 与收益率均值、动量、逻辑回归、纯 Transformer 和纯 CNN baseline 比较；
4. 加入手续费、滑点、涨跌停和持仓约束；
5. 对多任务 loss 权重和概率阈值做验证集调参；
6. 检查不同市场阶段、行业和股票池的稳定性。
