from __future__ import annotations

import torch
from torch import nn


class MultiScaleCNNTransformer(nn.Module):
    """Parallel multi-scale temporal CNN + Transformer with three prediction heads."""

    def __init__(self, input_dim: int, d_model: int = 96, nhead: int = 4,
                 num_layers: int = 2, dim_feedforward: int = 192,
                 dropout: float = 0.15, cnn_channels: int = 32,
                 max_sequence_length: int = 512):
        super().__init__()
        if d_model % nhead:
            raise ValueError("d_model must be divisible by nhead")
        self.input_dim = input_dim
        self.d_model = d_model
        self.branches = nn.ModuleList([
            nn.Sequential(nn.Conv1d(input_dim, cnn_channels, 3, padding=1), nn.GELU(), nn.BatchNorm1d(cnn_channels)),
            nn.Sequential(nn.Conv1d(input_dim, cnn_channels, 5, padding=2), nn.GELU(), nn.BatchNorm1d(cnn_channels)),
            nn.Sequential(nn.Conv1d(input_dim, cnn_channels, 9, padding=4), nn.GELU(), nn.BatchNorm1d(cnn_channels)),
        ])
        self.projection = nn.Sequential(
            nn.Linear(cnn_channels * 3, d_model), nn.LayerNorm(d_model), nn.GELU(), nn.Dropout(dropout)
        )
        self.position = nn.Parameter(torch.zeros(1, max_sequence_length, d_model))
        nn.init.normal_(self.position, std=0.02)
        layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=dim_feedforward,
            dropout=dropout, activation="gelu", batch_first=True, norm_first=True
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=num_layers)
        self.norm = nn.LayerNorm(d_model)
        self.return_head = nn.Sequential(nn.Linear(d_model, d_model // 2), nn.GELU(), nn.Linear(d_model // 2, 1))
        self.direction_head = nn.Sequential(nn.Linear(d_model, d_model // 2), nn.GELU(), nn.Linear(d_model // 2, 1))
        self.volatility_head = nn.Sequential(nn.Linear(d_model, d_model // 2), nn.GELU(), nn.Linear(d_model // 2, 1))

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        if x.ndim != 3:
            raise ValueError("Expected x with shape [batch, sequence, features]")
        if x.shape[-1] != self.input_dim:
            raise ValueError(f"Expected {self.input_dim} features, received {x.shape[-1]}")
        z = torch.cat([branch(x.transpose(1, 2)).transpose(1, 2) for branch in self.branches], dim=-1)
        z = self.projection(z)
        z = z + self.position[:, :z.shape[1]]
        z = self.norm(self.encoder(z))
        pooled = z[:, -1]
        return {
            "return": self.return_head(pooled).squeeze(-1),
            "direction": self.direction_head(pooled).squeeze(-1),
            "volatility": self.volatility_head(pooled).squeeze(-1),
        }


class GatedHybridCNNTransformer(nn.Module):
    """Parallel raw-sequence Transformer + local multi-scale CNN with gated fusion.

    The gate lets the model reduce reliance on noisy local patterns. GroupNorm is
    used instead of BatchNorm because financial windows are small and highly
    correlated across batches.
    """

    def __init__(self, input_dim: int, d_model: int = 64, nhead: int = 4,
                 num_layers: int = 1, dim_feedforward: int = 128,
                 dropout: float = 0.20, cnn_channels: int = 24,
                 max_sequence_length: int = 512):
        super().__init__()
        if d_model % nhead:
            raise ValueError("d_model must be divisible by nhead")
        self.input_dim = input_dim
        self.d_model = d_model
        self.feature_gate = nn.Parameter(torch.zeros(input_dim))
        self.raw_projection = nn.Sequential(nn.Linear(input_dim, d_model), nn.LayerNorm(d_model), nn.GELU())
        self.local_branches = nn.ModuleList([
            nn.Sequential(nn.Conv1d(input_dim, cnn_channels, k, padding=k // 2), nn.GELU(), nn.GroupNorm(1, cnn_channels))
            for k in (3, 5, 9)
        ])
        self.local_projection = nn.Sequential(
            nn.Linear(cnn_channels * 3, d_model), nn.LayerNorm(d_model), nn.GELU(), nn.Dropout(dropout)
        )
        self.position = nn.Parameter(torch.zeros(1, max_sequence_length, d_model))
        nn.init.normal_(self.position, std=0.02)
        layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=dim_feedforward,
            dropout=dropout, activation="gelu", batch_first=True, norm_first=True
        )
        self.global_encoder = nn.TransformerEncoder(layer, num_layers=num_layers)
        self.fusion_gate = nn.Sequential(nn.Linear(2 * d_model, d_model), nn.Sigmoid())
        self.fusion_norm = nn.LayerNorm(d_model)
        self.dropout = nn.Dropout(dropout)
        self.return_head = nn.Sequential(nn.Linear(d_model, d_model // 2), nn.GELU(), nn.Dropout(dropout), nn.Linear(d_model // 2, 1))
        self.direction_head = nn.Sequential(nn.Linear(d_model, d_model // 2), nn.GELU(), nn.Dropout(dropout), nn.Linear(d_model // 2, 1))
        self.volatility_head = nn.Sequential(nn.Linear(d_model, d_model // 2), nn.GELU(), nn.Dropout(dropout), nn.Linear(d_model // 2, 1))

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        if x.ndim != 3 or x.shape[-1] != self.input_dim:
            raise ValueError(f"Expected [batch, sequence, {self.input_dim}]")
        # Start with an identity-like gate (0.5 + sigmoid(0) = 1.0),
        # rather than feeding an all-zero sequence during early updates.
        x_gated = x * (0.5 + torch.sigmoid(self.feature_gate))
        raw = self.raw_projection(x_gated)
        local = torch.cat([branch(x_gated.transpose(1, 2)).transpose(1, 2) for branch in self.local_branches], dim=-1)
        local = self.local_projection(local)
        global_features = self.global_encoder(raw + self.position[:, :x.shape[1]])
        gate = self.fusion_gate(torch.cat([local, global_features], dim=-1))
        fused = self.fusion_norm(self.dropout(gate * local + (1.0 - gate) * global_features))
        pooled = fused[:, -1]
        return {
            "return": self.return_head(pooled).squeeze(-1),
            "direction": self.direction_head(pooled).squeeze(-1),
            "volatility": self.volatility_head(pooled).squeeze(-1),
        }
