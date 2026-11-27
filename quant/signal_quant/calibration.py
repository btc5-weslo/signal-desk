"""Probability calibration for signal confidence.

Confidence on a Signal is a *calibrated* probability in [0, 1]. In v0 the
calibration target is the trade outcome exported by the Data backtester
(outcome, R multiple, bars held) — typically P(outcome == hit_tp) or
P(R > 0) after costs. Fit isotonic or Platt (sigmoid) on walk-forward
*training* folds only; evaluate with a reliability diagram and Brier score
on embargoed OOS windows.

This module provides the fitting API only. It does not publish scores from
market data — those do not exist yet. Synthetic smoke tests may call it with
clearly labeled synthetic outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

Method = Literal["isotonic", "platt"]


@dataclass
class CalibrationFit:
    method: Method
    model: object

    def transform(self, raw: np.ndarray) -> np.ndarray:
        x = np.asarray(raw, dtype=float).reshape(-1)
        if self.method == "isotonic":
            y = self.model.predict(x)
        else:
            y = self.model.predict_proba(x.reshape(-1, 1))[:, 1]
        return np.clip(y, 0.0, 1.0)


def fit_calibrator(
    raw_scores: np.ndarray,
    outcomes: np.ndarray,
    *,
    method: Method = "isotonic",
) -> CalibrationFit:
    """Fit a calibrator. ``outcomes`` must be 0/1 labels (e.g. hit_tp vs not)."""
    x = np.asarray(raw_scores, dtype=float).reshape(-1)
    y = np.asarray(outcomes, dtype=int).reshape(-1)
    if x.shape != y.shape:
        raise ValueError("raw_scores and outcomes must have the same length")
    if method == "isotonic":
        ir = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        ir.fit(x, y)
        return CalibrationFit(method=method, model=ir)
    # Platt: logistic regression on the raw score.
    lr = LogisticRegression()
    lr.fit(x.reshape(-1, 1), y)
    return CalibrationFit(method=method, model=lr)


def reliability_diagram(
    calibrated: np.ndarray,
    outcomes: np.ndarray,
    *,
    n_bins: int = 10,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (mean predicted probability per bin, observed frequency per bin)."""
    prob_true, prob_pred = calibration_curve(
        np.asarray(outcomes), np.asarray(calibrated), n_bins=n_bins, strategy="uniform"
    )
    return prob_pred, prob_true


def brier(calibrated: np.ndarray, outcomes: np.ndarray) -> float:
    return float(brier_score_loss(np.asarray(outcomes), np.asarray(calibrated)))


# Quiet unused-import note: CalibratedClassifierCV is reserved for a later
# tree-model pipeline (LightGBM + CV). Keep the import visible for the API plan.
_ = CalibratedClassifierCV
