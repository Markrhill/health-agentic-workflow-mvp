from dataclasses import dataclass

KCALS_PER_KG_FAT = 7700.0

@dataclass
class MaintenanceEstimate:
    m_kcal_per_day: float
    comp_c: float  # compensation coefficient used (0.0–0.5 typical)

def estimate_m_from_windows(df, comp_c: float = 0.25) -> MaintenanceEstimate:
    """
    df must have columns: net_kcal_sum, workout_kcal_sum, delta_fm_kg, days (7–9).
    net_kcal_sum = intake_kcal_sum - workout_kcal_sum (uncompensated)
    We apply compensation inside this function.
    """
    adj_net = df["net_kcal_sum"] + comp_c * df["workout_kcal_sum"]
    # m_hat is avg over windows of (adj_net - 7700*ΔFM)/days
    m_hat = ((adj_net - KCALS_PER_KG_FAT * df["delta_fm_kg"]) / df["days"]).mean()
    return MaintenanceEstimate(m_kcal_per_day=float(m_hat), comp_c=comp_c)

