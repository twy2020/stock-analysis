from __future__ import annotations

import argparse
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def main():
    p=argparse.ArgumentParser(description="Create stock data and feature visualizations")
    p.add_argument("--raw",default="datasets/data_test/stock_daily.csv"); p.add_argument("--processed",default="datasets/processed/stock_daily_processed.csv"); p.add_argument("--output-dir",default="artifacts/data_visuals")
    a=p.parse_args(); out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True)
    raw=pd.read_csv(a.raw,encoding="utf-8-sig"); raw["trade_date"]=pd.to_datetime(raw.trade_date,dayfirst=True); raw=raw.sort_values("trade_date")
    df=pd.read_csv(a.processed,encoding="utf-8-sig"); df["trade_date"]=pd.to_datetime(df.trade_date)
    fig,axes=plt.subplots(3,1,figsize=(14,11),sharex=True); axes[0].plot(raw.trade_date,raw.close,label="close"); axes[0].set_title("Close price"); axes[1].bar(raw.trade_date,raw.vol,width=1.5); axes[1].set_title("Volume"); axes[2].plot(raw.trade_date,raw.pct_chg,label="pct_chg"); axes[2].axhline(0,color="k",lw=.6); axes[2].set_title("Daily percent change"); [ax.grid(alpha=.2) for ax in axes]; fig.tight_layout(); fig.savefig(out/"price_volume_returns.png",dpi=160); plt.close(fig)
    cols=["feat_return_1d","feat_volatility_20d","feat_momentum_20d","feat_rsi14","feat_kalman_trend"]
    fig,axes=plt.subplots(len(cols),1,figsize=(14,12),sharex=True)
    for ax,col in zip(axes,cols): ax.plot(df.trade_date,df[col]); ax.set_title(col); ax.grid(alpha=.2)
    fig.tight_layout(); fig.savefig(out/"derived_features.png",dpi=160); plt.close(fig)
    fig,axes=plt.subplots(2,1,figsize=(14,7),sharex=True); axes[0].plot(df.trade_date,df.target_return_5d); axes[0].axhline(0,color="k",lw=.6); axes[0].set_title("Future 5-day return target"); axes[1].plot(df.trade_date,df.target_volatility_5d); axes[1].set_title("Future 5-day volatility target"); [ax.grid(alpha=.2) for ax in axes]; fig.tight_layout(); fig.savefig(out/"targets.png",dpi=160); plt.close(fig)
    print(f"Wrote visualizations to {out}")

if __name__ == "__main__": main()
