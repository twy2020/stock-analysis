from __future__ import annotations

import argparse, json, time
from pathlib import Path
import torch
from stock_model.model import MultiScaleCNNTransformer


def main():
    p=argparse.ArgumentParser(description="Analyze parameter count and a forward-pass feasibility estimate")
    p.add_argument("--features",type=int,default=31); p.add_argument("--sequence-length",type=int,default=60); p.add_argument("--d-model",type=int,default=96); p.add_argument("--nhead",type=int,default=4); p.add_argument("--layers",type=int,default=2); p.add_argument("--batch-size",type=int,default=32); p.add_argument("--output",default="artifacts/architecture_analysis.json"); a=p.parse_args()
    device=torch.device("cuda" if torch.cuda.is_available() else "cpu"); model=MultiScaleCNNTransformer(a.features,a.d_model,a.nhead,a.layers,max_sequence_length=a.sequence_length).to(device); params=sum(x.numel() for x in model.parameters()); x=torch.randn(a.batch_size,a.sequence_length,a.features,device=device)
    for _ in range(3): model(x)
    if device.type=="cuda": torch.cuda.synchronize()
    t=time.perf_counter();
    for _ in range(10): model(x)
    if device.type=="cuda": torch.cuda.synchronize()
    latency=(time.perf_counter()-t)/10; result={"device":str(device),"input_shape":[a.batch_size,a.sequence_length,a.features],"parameter_count":params,"parameter_count_millions":params/1e6,"forward_latency_ms":latency*1000,"estimated_samples_per_second":a.batch_size/latency,"assessment":"feasible for this dataset and RTX 3060; collect more stocks before drawing generalization conclusions","risks":["Only one stock and 975 usable rows are currently available","Financial labels are noisy and non-stationary","A single chronological split is not enough for robust model selection","The multi-task loss weights should be tuned on a rolling validation scheme"]}; dest=Path(a.output); dest.parent.mkdir(parents=True,exist_ok=True); dest.write_text(json.dumps(result,indent=2),encoding="utf-8"); print(json.dumps(result,indent=2))

if __name__ == "__main__": main()
