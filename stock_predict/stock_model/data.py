from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset


@dataclass
class SplitIndices:
    train: list[int]
    val: list[int]
    test: list[int]


def load_schema(schema_path: str | Path) -> dict:
    import json
    return json.loads(Path(schema_path).read_text(encoding="utf-8-sig"))


def make_splits(df: pd.DataFrame, val_ratio: float = 0.2) -> SplitIndices:
    if "split" not in df:
        raise ValueError("Processed data must contain split column")
    train_rows = df.index[df["split"].eq("train")].tolist()
    test_rows = df.index[df["split"].eq("future")].tolist()
    if len(train_rows) < 10 or len(test_rows) < 1:
        raise ValueError("Need both train and future rows for a chronological split")
    cut = int(len(train_rows) * (1 - val_ratio))
    cut = max(1, min(len(train_rows) - 1, cut))
    return SplitIndices(train_rows[:cut], train_rows[cut:], test_rows)


class SequenceDataset(Dataset):
    """Sliding windows whose label is at the final timestep."""

    def __init__(self, df: pd.DataFrame, feature_columns: list[str], target_columns: list[str],
                 sequence_length: int, target_indices: list[int]):
        self.x = df[feature_columns].to_numpy(dtype=np.float32)
        self.y = df[target_columns].to_numpy(dtype=np.float32)
        self.codes = df["ts_code"].astype(str).to_numpy()
        self.dates = df["trade_date"].astype(str).to_numpy()
        self.sequence_length = sequence_length
        self.samples: list[tuple[int, int]] = []
        target_set = set(target_indices)
        for end in sorted(target_indices):
            start = end - sequence_length + 1
            if start < 0:
                continue
            if len(set(self.codes[start:end + 1])) != 1:
                continue
            if not np.isfinite(self.x[start:end + 1]).all() or not np.isfinite(self.y[end]).all():
                continue
            # Require all rows in the window to precede the target in the same stock;
            # the target split itself controls train/validation/test membership.
            if end not in target_set:
                continue
            self.samples.append((start, end))
        if not self.samples:
            raise ValueError("No valid sequence samples; reduce sequence_length or inspect data")

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor | str]:
        start, end = self.samples[index]
        return {
            "x": torch.from_numpy(self.x[start:end + 1]),
            "y": torch.from_numpy(self.y[end]),
            "date": self.dates[end],
            "ts_code": self.codes[end],
        }
