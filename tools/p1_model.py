from __future__ import annotations
import numpy as np

def predict_dfm(intake_sum: np.ndarray,
                workout_sum: np.ndarray,
                m: float,
                c: float,
                alpha: float,
                days: np.ndarray | int) -> np.ndarray:
    """
    Predict Δfat_mass (kg) over a window.

    intake_sum, workout_sum: kcal over the window
    m: kcal/day (maintenance)
    c: fraction of workout kcal compensated (eaten back)
    alpha: kcal per kg fat
    days: window length (int or array aligned with inputs)
    """
    days_arr = np.asarray(days, dtype=float)
    net = intake_sum - (1.0 - c) * workout_sum - m * days_arr   # kcal
    return net / float(alpha)                                   # kg

def residuals(y_true_dfm: np.ndarray, y_pred_dfm: np.ndarray) -> np.ndarray:
    return y_pred_dfm - y_true_dfm  # sign convention: positive = overprediction

def mae(x: np.ndarray) -> float:
    return float(np.mean(np.abs(x)))

def rmse(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x))))
