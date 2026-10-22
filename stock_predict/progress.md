# 进度记录

## 2026-08-21

- 已阅读并启用文件规划流程。
- 已创建 `task_plan.md`、`findings.md`、`progress.md`。
- 已完成初步审计：只有 `stock_daily.csv`，1000 行、12 列、单只股票，数据按日期倒序，`industry` 存在编码显示问题。
- 下一步：确认文件编码、重复和异常值，并设计派生字段及目标。
- 已完成字段方案文档 `docs/data_fields.md`。
- 已新增并运行 `scripts/preprocess_stock_data.py`。
- 已生成 `datasets/processed/stock_daily_processed.csv` 和 `datasets/processed/feature_schema.json`。
- 验证结果：975 行、31 个模型字段、3 个目标、无缺失值、时间升序、train 780 行 / future 195 行；脚本通过 `py_compile`。
- 最终断言验证通过：模型字段无缺失，日期升序，train 最后日期为 2025-10-24，future 首日期为 2025-10-27。
- 已创建 Conda 环境 `stock_predict_train`，Python 3.11.15。
- 已安装 PyTorch 2.5.1 + CUDA 12.4、torchvision、torchaudio，以及 pandas、scipy、scikit-learn、tqdm、matplotlib、seaborn、JupyterLab、ipykernel、openpyxl。
- GPU 验证通过：RTX 3060 Laptop GPU 可用，CUDA tensor 运算成功。
- 已添加可复现环境文件 `environment.yml`。
- 已实现 `stock_model/data.py`、`stock_model/model.py`、`stock_model/metrics.py`。
- 已实现训练入口 `train.py`、预测入口 `predict.py`、评估入口 `evaluate.py`。
- 已实现 `visualize_data.py`、`visualize_run.py` 和 `analyze_architecture.py`。
- 已完成 CUDA 基线训练：7 个 epoch 后早停，最佳验证损失约 0.6868。
- 已生成 `runs/baseline_cnn_transformer` 下的 checkpoint、历史曲线、测试预测、指标、评估报告和预测图。
- 架构分析：196,291 参数，RTX 3060 前向约 4.88 ms；工程可行，但当前单股票数据不足以证明泛化能力。
- 新增 `GatedHybridCNNTransformer`：并行原始序列 Transformer、kernel=3/5/9 CNN、门控融合、GroupNorm、特征门控和更强 dropout。
- 修正多任务回归损失尺度：收益率和波动率在 loss 中分别放大 20x/50x，避免分类损失压制回归任务。
- hybrid v2：收益率 MAE 0.0413、波动率 MAE 0.00667，但方向头退化为全预测上涨。
- 修复 v2 的特征门控初始化后，hybrid v3 方向准确率提升到 53.85%，收益率 MAE 0.0481、波动率 MAE 0.01694；仍需多股票数据和滚动验证。
