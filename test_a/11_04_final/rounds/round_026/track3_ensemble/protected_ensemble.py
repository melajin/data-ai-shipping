"""Protected Ensemble & Prior-Shift Probability Calibration Module.

Round 026 Track 3: Class-Protected Multi-Model Probability Calibration & Ensemble.
Provides reusable functions to combine probabilities from LightGBM, CatBoost,
and TabICLv2 with class-prior shift calibration and gated decision rules,
strictly protecting minority classes (Class 3 TP >= 92) and majority classes
(Class 0 TP >= 2389) while maximizing micro-F1.
"""

from __future__ import annotations

import numpy as np


# Default learned prior multipliers from INNER 3-fold Out-Of-Fold CV
# Scaled relative to reference Class 1 (alpha_1 = 1.0)
DEFAULT_ALPHA_B1 = np.array([1.027, 1.000, 1.033, 1.458], dtype=np.float64)
DEFAULT_ALPHA_B2_TRIO = np.array([1.033, 1.000, 0.983, 1.500], dtype=np.float64)

# Default weights
DEFAULT_WEIGHTS_PAIR = (0.50, 0.50) # LightGBM, TabICL
DEFAULT_WEIGHTS_TRIO = (0.45, 0.10, 0.45) # LightGBM, CatBoost, TabICL


def blend_probabilities_pair(
    p_lgb: np.ndarray,
    p_tabicl: np.ndarray,
    w_lgb: float = 0.50,
) -> np.ndarray:
    """Linear convex combination of LightGBM and TabICLv2 probabilities."""
    p_blend = w_lgb * p_lgb + (1.0 - w_lgb) * p_tabicl
    return p_blend


def blend_probabilities_trio(
    p_lgb: np.ndarray,
    p_cat: np.ndarray,
    p_tabicl: np.ndarray,
    weights: tuple[float, float, float] = DEFAULT_WEIGHTS_TRIO,
) -> np.ndarray:
    """Linear convex combination of LightGBM, CatBoost, and TabICLv2 probabilities."""
    w1, w2, w3 = weights
    p_blend = w1 * p_lgb + w2 * p_cat + w3 * p_tabicl
    return p_blend


def apply_prior_shift(
    p_blend: np.ndarray,
    alpha: np.ndarray = DEFAULT_ALPHA_B2_TRIO,
    normalize: bool = True,
) -> np.ndarray:
    """Apply Bayesian prior-shift multipliers to probability predictions.
    
    Formula: P_calibrated(c) = alpha_c * P_blend(c) / sum_k(alpha_k * P_blend(k))
    Compensates for the difference between raw empirical prior (TabICL) and
    resampled sqrt_macro prior (LightGBM).
    """
    p_scaled = p_blend * alpha
    if normalize:
        p_scaled /= p_scaled.sum(axis=1, keepdims=True)
    return p_scaled


def predict_class_protected(
    p_blend: np.ndarray,
    alpha: np.ndarray = DEFAULT_ALPHA_B2_TRIO,
) -> np.ndarray:
    """Make class-protected predictions using Bayes decision multipliers."""
    return (p_blend * alpha).argmax(axis=1)


def predict_dual_gate(
    p_blend: np.ndarray,
    p_lgb: np.ndarray,
    a0: float = 1.02,
    a2: float = 1.05,
    tau_lgb3: float = 0.25,
) -> np.ndarray:
    """Make class-protected predictions using dual threshold gate on Class 3.
    
    If LightGBM indicates high confidence on Class 3 (P_lgb(3) >= tau),
    route to Class 3 directly; otherwise argmax with prior multiplier on Class 0 and 2.
    """
    pred = (p_blend * np.array([a0, 1.0, a2, 1.0])).argmax(axis=1)
    pred[p_lgb[:, 3] >= tau_lgb3] = 3
    return pred
