from __future__ import annotations

import argparse
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def main():
    p=argparse.ArgumentParser(description="Plot predictions and a simple test strategy curve")
    p.add_argument("--run-dir",required=True); p.add_argument("--data",default="datasets/processed/stock_daily_processed.csv"); p.add_argument("--output",default=None); a=p.parse_args()
    run=Path(a.run_dir); pred=pd.read_csv(run/"test_predictions.csv"); df=pd.read_csv(a.data,encoding="utf-8-sig"); future=df[df.split.eq("future")].reset_index(drop=True).iloc[:len(pred)].copy(); future["trade_date"]=pd.to_datetime(future.trade_date)
    pred["trade_date"]=future.trade_date.to_numpy(); pred["strategy_return"]=pred.pred_up_probability.ge(.5)*future.target_return_5d.to_numpy(); pred["strategy_curve"]=(1+pred.strategy_return).cumprod(); pred["buy_hold_curve"]=(1+future.target_return_5d.to_numpy()).cumprod()
    fig,axes=plt.subplots(3,1,figsize=(14,11),sharex=True); axes[0].plot(pred.trade_date,future.target_return_5d,label="actual"); axes[0].plot(pred.trade_date,pred.pred_return_5d,label="predicted",alpha=.8); axes[0].axhline(0,color="k",lw=.6); axes[0].set_title("5-day return: actual vs predicted"); axes[0].legend(); axes[1].plot(pred.trade_date,future.target_up_5d.rolling(20).mean(),label="actual rolling rate"); axes[1].plot(pred.trade_date,pred.pred_up_probability,label="predicted probability"); axes[1].set_ylim(-.05,1.05); axes[1].set_title("Direction probability"); axes[1].legend(); axes[2].plot(pred.trade_date,pred.strategy_curve,label="threshold strategy"); axes[2].plot(pred.trade_date,pred.buy_hold_curve,label="buy and hold"); axes[2].set_title("Illustrative cumulative curve (no costs)"); axes[2].legend(); [ax.grid(alpha=.2) for ax in axes]; fig.tight_layout(); destination=Path(a.output or run/"plots"/"test_predictions.png"); destination.parent.mkdir(parents=True,exist_ok=True); fig.savefig(destination,dpi=160); plt.close(fig); print(destination)

if __name__ == "__main__": main()
