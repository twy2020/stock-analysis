from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import torch

from stock_model.model import GatedHybridCNNTransformer, MultiScaleCNNTransformer


def main():
    p=argparse.ArgumentParser(description="Run a latest-window stock prediction")
    p.add_argument("--run-dir",required=True); p.add_argument("--data",default="datasets/processed/stock_daily_processed.csv"); p.add_argument("--schema",default="datasets/processed/feature_schema.json"); p.add_argument("--sequence-length",type=int,default=None); p.add_argument("--device",default="auto",choices=["auto","cuda","cpu"]); p.add_argument("--output",default=None)
    a=p.parse_args(); run=Path(a.run_dir); ckpt=torch.load(run/"best.pt",map_location="cpu"); cfg=ckpt["config"]; seq=a.sequence_length or cfg["sequence_length"]; device=torch.device("cuda" if a.device=="auto" and torch.cuda.is_available() else "cpu" if a.device=="auto" else a.device)
    df=pd.read_csv(a.data,encoding="utf-8-sig"); features=cfg["feature_columns"]; recent=df.sort_values(["ts_code","trade_date"]).tail(seq); 
    if len(recent)<seq: raise ValueError(f"Need {seq} rows, found {len(recent)}")
    x=torch.tensor(recent[features].to_numpy(dtype=np.float32),device=device).unsqueeze(0)
    model_class = MultiScaleCNNTransformer if cfg.get("model_variant", "baseline") == "baseline" else GatedHybridCNNTransformer
    model_kwargs=dict(d_model=cfg["d_model"],nhead=cfg["nhead"],num_layers=cfg["layers"],dropout=cfg["dropout"],max_sequence_length=seq)
    if cfg.get("model_variant") == "hybrid": model_kwargs["cnn_channels"] = cfg.get("cnn_channels", 24)
    model=model_class(len(features),**model_kwargs).to(device); model.load_state_dict(ckpt["model"]); model.eval()
    with torch.no_grad(): out=model(x); result={"ts_code":str(recent.ts_code.iloc[-1]),"as_of":str(recent.trade_date.iloc[-1]),"horizon":"5 trading days","pred_return_5d":float(out["return"].item()),"pred_up_probability":float(torch.sigmoid(out["direction"]).item()),"pred_volatility_5d":float(out["volatility"].item()),"device":str(device)}
    destination=Path(a.output or run/"latest_prediction.json"); destination.write_text(json.dumps(result,indent=2),encoding="utf-8"); print(json.dumps(result,indent=2,ensure_ascii=False))

if __name__ == "__main__": main()
