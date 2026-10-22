from __future__ import annotations

import argparse, json
from pathlib import Path
import numpy as np, pandas as pd
from stock_model.metrics import classification_metrics, regression_metrics, strategy_metrics


def main():
    p=argparse.ArgumentParser(description="Create a Markdown evaluation report from test predictions")
    p.add_argument("--run-dir",required=True); p.add_argument("--data",default="datasets/processed/stock_daily_processed.csv"); p.add_argument("--output",default=None); a=p.parse_args(); run=Path(a.run_dir)
    pred=pd.read_csv(run/"test_predictions.csv"); df=pd.read_csv(a.data,encoding="utf-8-sig"); y=df.loc[df.split.eq("future"),["target_return_5d","target_up_5d","target_volatility_5d"]].reset_index(drop=True).iloc[:len(pred)].to_numpy()
    pr=pred.to_numpy(); metrics={}; metrics.update(regression_metrics(y[:,0],pr[:,0],"return")); metrics.update(classification_metrics(y[:,1],pr[:,1],"direction")); metrics.update(regression_metrics(y[:,2],pr[:,2],"volatility")); metrics.update(strategy_metrics(y[:,0],pr[:,1]));
    (run/"metrics.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8"); lines=["# Stock model evaluation report","",f"Test samples: {len(pred)}","", "| Metric | Value |","|---|---:|"]+[f"| `{k}` | {v:.6f} |" for k,v in metrics.items()]; dest=Path(a.output or run/"evaluation_report.md"); dest.write_text("\n".join(lines),encoding="utf-8"); print(dest)

if __name__ == "__main__": main()
