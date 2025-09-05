import pandas as pd
from ml.solver import estimate_m_from_windows

def test_estimate_m_from_windows_smoke():
    df = pd.DataFrame({
        "net_kcal_sum":[-1400, -2100, -700],  # example weekly-ish deficits
        "workout_kcal_sum":[1200, 800, 600],
        "delta_fm_kg":[0.10, 0.20, 0.00],
        "days":[7,7,7]
    })
    est = estimate_m_from_windows(df, comp_c=0.25)
    assert 1200 <= est.m_kcal_per_day <= 2400

