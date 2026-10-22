from __future__ import annotations

import argparse
import json
import random
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader

from stock_model.data import SequenceDataset, load_schema, make_splits
from stock_model.metrics import classification_metrics, regression_metrics, strategy_metrics
from stock_model.model import GatedHybridCNNTransformer, MultiScaleCNNTransformer


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train the multi-task stock model")
    p.add_argument("--data", default="datasets/processed/stock_daily_processed.csv")
    p.add_argument("--schema", default="datasets/processed/feature_schema.json")
    p.add_argument("--run-dir", default=None)
    p.add_argument("--sequence-length", type=int, default=60)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--patience", type=int, default=6)
    p.add_argument("--learning-rate", type=float, default=2e-4)
    p.add_argument("--weight-decay", type=float, default=1e-4)
    p.add_argument("--return-weight", type=float, default=1.0)
    p.add_argument("--direction-weight", type=float, default=1.0)
    p.add_argument("--volatility-weight", type=float, default=0.5)
    p.add_argument("--d-model", type=int, default=96)
    p.add_argument("--nhead", type=int, default=4)
    p.add_argument("--layers", type=int, default=2)
    p.add_argument("--dropout", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    p.add_argument("--model-variant", default="hybrid", choices=["baseline", "hybrid"])
    p.add_argument("--cnn-channels", type=int, default=24)
    p.add_argument("--return-scale", type=float, default=20.0, help="Scale return regression in the loss only")
    p.add_argument("--volatility-scale", type=float, default=50.0, help="Scale volatility regression in the loss only")
    return p.parse_args()


def set_seed(seed: int) -> None:
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)


def device_for(name: str) -> torch.device:
    if name == "cuda" and not torch.cuda.is_available(): raise RuntimeError("CUDA requested but unavailable")
    return torch.device("cuda" if name == "auto" and torch.cuda.is_available() else name if name != "auto" else "cpu")


def compute_loss(outputs, y, weights, return_scale=1.0, volatility_scale=1.0):
    return (weights[0] * nn.functional.smooth_l1_loss(outputs["return"] * return_scale, y[:, 0] * return_scale)
            + weights[1] * nn.functional.binary_cross_entropy_with_logits(outputs["direction"], y[:, 1])
            + weights[2] * nn.functional.smooth_l1_loss(outputs["volatility"] * volatility_scale, y[:, 2] * volatility_scale))


@torch.no_grad()
def predict_loader(model, loader, device):
    model.eval(); ys=[]; rows=[]
    for batch in loader:
        out = model(batch["x"].to(device))
        y = batch["y"].numpy()
        prob = torch.sigmoid(out["direction"]).cpu().numpy()
        pred = np.column_stack([out["return"].cpu().numpy(), prob, out["volatility"].cpu().numpy()])
        ys.append(y); rows.append(pred)
    return np.concatenate(ys), np.concatenate(rows)


def evaluate_arrays(y, pred):
    result = {}
    result.update(regression_metrics(y[:, 0], pred[:, 0], "return"))
    result.update(classification_metrics(y[:, 1], pred[:, 1], "direction"))
    result.update(regression_metrics(y[:, 2], pred[:, 2], "volatility"))
    result.update(strategy_metrics(y[:, 0], pred[:, 1]))
    return result


def plot_history(history: pd.DataFrame, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    axes[0].plot(history.epoch, history.train_loss, label="train")
    axes[0].plot(history.epoch, history.val_loss, label="validation")
    axes[0].set_title("Multi-task loss"); axes[0].set_xlabel("epoch"); axes[0].legend(); axes[0].grid(alpha=.25)
    for col in ["return_mae", "direction_accuracy", "volatility_mae"]:
        axes[1].plot(history.epoch, history[f"val_{col}"], label=col)
    axes[1].set_title("Validation metrics"); axes[1].set_xlabel("epoch"); axes[1].legend(); axes[1].grid(alpha=.25)
    fig.tight_layout(); fig.savefig(path, dpi=160); plt.close(fig)


def main() -> None:
    cfg = args(); set_seed(cfg.seed); device = device_for(cfg.device)
    df = pd.read_csv(cfg.data, encoding="utf-8-sig")
    schema = load_schema(cfg.schema)
    features = schema["model_feature_columns"]; targets = schema["target_columns"]
    splits = make_splits(df)
    datasets = {name: SequenceDataset(df, features, targets, cfg.sequence_length, indices)
                for name, indices in [("train", splits.train), ("val", splits.val), ("test", splits.test)]}
    loaders = {name: DataLoader(ds, batch_size=cfg.batch_size, shuffle=name == "train", num_workers=0)
               for name, ds in datasets.items()}
    model_class = MultiScaleCNNTransformer if cfg.model_variant == "baseline" else GatedHybridCNNTransformer
    model_kwargs = dict(d_model=cfg.d_model, nhead=cfg.nhead, num_layers=cfg.layers,
                        dropout=cfg.dropout, max_sequence_length=cfg.sequence_length)
    if cfg.model_variant == "hybrid": model_kwargs["cnn_channels"] = cfg.cnn_channels
    model = model_class(len(features), **model_kwargs).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg.learning_rate, weight_decay=cfg.weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=.5, patience=2)
    weights = (cfg.return_weight, cfg.direction_weight, cfg.volatility_weight)
    run_dir = Path(cfg.run_dir or f"runs/{datetime.now().strftime('%Y%m%d_%H%M%S')}"); (run_dir / "plots").mkdir(parents=True, exist_ok=True)
    config = vars(cfg) | {"device": str(device), "feature_columns": features, "target_columns": targets,
                           "train_samples": len(datasets["train"]), "val_samples": len(datasets["val"]), "test_samples": len(datasets["test"]),
                           "parameter_count": sum(p.numel() for p in model.parameters())}
    (run_dir / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    best_loss = float("inf"); bad_epochs=0; records=[]
    for epoch in range(1, cfg.epochs + 1):
        model.train(); losses=[]
        for batch in loaders["train"]:
            optimizer.zero_grad(set_to_none=True); out=model(batch["x"].to(device)); loss=compute_loss(out,batch["y"].to(device),weights,cfg.return_scale,cfg.volatility_scale); loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); optimizer.step(); losses.append(loss.item())
        model.eval(); val_losses=[]
        with torch.no_grad():
            for batch in loaders["val"]:
                val_losses.append(compute_loss(model(batch["x"].to(device)), batch["y"].to(device), weights,cfg.return_scale,cfg.volatility_scale).item())
        val_y, val_pred = predict_loader(model, loaders["val"], device); val_metrics=evaluate_arrays(val_y,val_pred)
        val_loss=float(np.mean(val_losses)); scheduler.step(val_loss)
        record={"epoch":epoch,"train_loss":float(np.mean(losses)),"val_loss":val_loss,"lr":optimizer.param_groups[0]["lr"]}
        record.update({f"val_{k}":v for k,v in val_metrics.items()}); records.append(record)
        print(f"epoch {epoch:03d} train={record['train_loss']:.5f} val={val_loss:.5f} return_mae={val_metrics['return_mae']:.5f} direction_acc={val_metrics['direction_accuracy']:.3f}")
        if val_loss < best_loss:
            best_loss=val_loss; bad_epochs=0; torch.save({"model":model.state_dict(),"config":config,"best_val_loss":best_loss},run_dir/"best.pt")
        else: bad_epochs += 1
        if bad_epochs >= cfg.patience: print("early stopping"); break
    history=pd.DataFrame(records); history.to_csv(run_dir/"history.csv",index=False); plot_history(history,run_dir/"plots"/"training_curves.png")
    checkpoint=torch.load(run_dir/"best.pt",map_location=device); model.load_state_dict(checkpoint["model"])
    test_y,test_pred=predict_loader(model,loaders["test"],device); metrics=evaluate_arrays(test_y,test_pred)
    pd.DataFrame(test_pred,columns=["pred_return_5d","pred_up_probability","pred_volatility_5d"]).to_csv(run_dir/"test_predictions.csv",index=False)
    (run_dir/"metrics.json").write_text(json.dumps(metrics,indent=2),encoding="utf-8")
    print(json.dumps({"run_dir":str(run_dir),"device":str(device),"best_val_loss":best_loss,"test_metrics":metrics},indent=2))


if __name__ == "__main__": main()
