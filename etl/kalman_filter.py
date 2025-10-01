#!/usr/bin/env python3
"""
Kalman Filter Implementation for BIA Fat Mass Smoothing

Purpose: Apply physiologically-constrained Kalman filtering to reduce noise in BIA measurements
while preserving true physiological changes in fat mass over time.

Mathematical Implementation:
State: x̂_t = estimated true fat mass at day t
Covariance: P_t = uncertainty in estimate at day t
Measurement: z_t = BIA reading at day t (may be NULL)
Parameters: Q = 0.0196 kg², R = 2.89 kg²

For each day t:
  1. Predict step:
     x̂_t|t-1 = x̂_t-1|t-1  (state doesn't change without measurement)
     P_t|t-1 = P_t-1|t-1 + (days_since_last_measurement × Q)
  
  2. Update step (only if z_t is not NULL):
     K_t = P_t|t-1 / (P_t|t-1 + R)  (Kalman gain)
     x̂_t|t = x̂_t|t-1 + K_t × (z_t - x̂_t|t-1)  (state update)
     P_t|t = (1 - K_t) × P_t|t-1  (covariance update)
  
  3. No update (if z_t is NULL):
     x̂_t|t = x̂_t|t-1  (forward-fill state)
     P_t|t = P_t|t-1  (uncertainty stays at predicted level)

Initialization:
- x̂_0 = first non-NULL fat_mass_kg value
- P_0 = R (start with high uncertainty = measurement noise)
"""

import argparse
import psycopg2
import numpy as np
import sys
import os
from datetime import datetime, date
from typing import List, Tuple, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class KalmanFilter:
    """True Kalman filter implementation for fat mass smoothing"""
    
    def __init__(self, Q: float = 0.0196, R: float = 2.89):
        """
        Initialize Kalman filter with physiological parameters
        
        Args:
            Q: Process noise variance (kg²) - maximum physiological daily change
            R: Measurement noise variance (kg²) - BIA sensor error
        """
        self.Q = Q  # Process noise
        self.R = R  # Measurement noise
        
        # State variables
        self.state_estimate = None  # x̂_t|t
        self.covariance_estimate = None  # P_t|t
        self.initialized = False
        
        # Tracking for validation
        self.kalman_gains = []
        self.covariances = []
        self.state_estimates = []
        
    def initialize(self, first_measurement: float):
        """
        Initialize Kalman filter with first measurement
        
        Args:
            first_measurement: First non-NULL fat_mass_kg value
        """
        self.state_estimate = first_measurement
        self.covariance_estimate = self.R  # Start with measurement uncertainty
        self.initialized = True
        
        # Track for validation
        self.kalman_gains.append(0.0)  # No gain on initialization
        self.covariances.append(self.covariance_estimate)
        self.state_estimates.append(self.state_estimate)
        
    def predict_step(self, days_since_last_measurement: int) -> Tuple[float, float]:
        """
        Predict step: x̂_t|t-1 and P_t|t-1
        
        Args:
            days_since_last_measurement: Number of days since last measurement
            
        Returns:
            Tuple of (predicted_state, predicted_covariance)
        """
        # State prediction: x̂_t|t-1 = x̂_t-1|t-1
        predicted_state = self.state_estimate
        
        # Covariance prediction: P_t|t-1 = P_t-1|t-1 + (days × Q)
        predicted_covariance = self.covariance_estimate + (days_since_last_measurement * self.Q)
        
        return predicted_state, predicted_covariance
    
    def update_step(self, measurement: float, predicted_state: float, predicted_covariance: float) -> Tuple[float, float]:
        """
        Update step: K_t, x̂_t|t, P_t|t
        
        Args:
            measurement: Current measurement z_t
            predicted_state: x̂_t|t-1 from predict step
            predicted_covariance: P_t|t-1 from predict step
            
        Returns:
            Tuple of (kalman_gain, updated_state, updated_covariance)
        """
        # Kalman gain: K_t = P_t|t-1 / (P_t|t-1 + R)
        kalman_gain = predicted_covariance / (predicted_covariance + self.R)
        
        # State update: x̂_t|t = x̂_t|t-1 + K_t × (z_t - x̂_t|t-1)
        innovation = measurement - predicted_state
        updated_state = predicted_state + kalman_gain * innovation
        
        # Covariance update: P_t|t = (1 - K_t) × P_t|t-1
        updated_covariance = (1 - kalman_gain) * predicted_covariance
        
        # Update internal state
        self.state_estimate = updated_state
        self.covariance_estimate = updated_covariance
        
        # Track for validation
        self.kalman_gains.append(kalman_gain)
        self.covariances.append(updated_covariance)
        self.state_estimates.append(updated_state)
        
        return kalman_gain, updated_state, updated_covariance
    
    def process_measurement(self, measurement: Optional[float], days_since_last: int) -> Tuple[float, float, float]:
        """
        Process a single measurement through predict and update steps
        
        Args:
            measurement: Current measurement (None if missing)
            days_since_last: Days since last measurement
            
        Returns:
            Tuple of (kalman_gain, state_estimate, covariance_estimate)
        """
        # Predict step
        predicted_state, predicted_covariance = self.predict_step(days_since_last)
        
        if measurement is not None:
            # Update step with measurement
            kalman_gain, updated_state, updated_covariance = self.update_step(
                measurement, predicted_state, predicted_covariance
            )
        else:
            # No measurement update - just propagate state
            kalman_gain = 0.0
            updated_state = predicted_state
            updated_covariance = predicted_covariance
            
            # Update internal state
            self.state_estimate = updated_state
            self.covariance_estimate = updated_covariance
            
            # Track for validation
            self.kalman_gains.append(kalman_gain)
            self.covariances.append(updated_covariance)
            self.state_estimates.append(updated_state)
        
        return kalman_gain, updated_state, updated_covariance


def get_database_connection():
    """Get database connection using environment variables"""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL not set in .env")
    return psycopg2.connect(database_url)


def load_fat_mass_data(conn, start_date: str, end_date: str) -> List[Tuple[date, Optional[float]]]:
    """
    Load fat mass data from database
    
    Args:
        conn: Database connection
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        
    Returns:
        List of (date, fat_mass_kg) tuples, ordered by date
    """
    query = """
        SELECT fact_date, fat_mass_kg
        FROM daily_facts
        WHERE fact_date BETWEEN %s AND %s
        ORDER BY fact_date
    """
    
    with conn.cursor() as cur:
        cur.execute(query, (start_date, end_date))
        results = []
        for row in cur.fetchall():
            # Convert Decimal to float if present
            fat_mass = float(row[1]) if row[1] is not None else None
            results.append((row[0], fat_mass))
        return results


def create_filtered_table(conn):
    """Create daily_facts_filtered table if it doesn't exist"""
    query = """
        CREATE TABLE IF NOT EXISTS daily_facts_filtered (
            fact_date DATE PRIMARY KEY,
            fat_mass_kg_filtered NUMERIC(10,3),
            fat_mass_kg_variance NUMERIC(10,6),
            kalman_gain NUMERIC(8,6),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    
    with conn.cursor() as cur:
        cur.execute(query)
    conn.commit()


def save_filtered_data(conn, results: List[Tuple[date, float, float, float]]):
    """
    Save filtered results to database
    
    Args:
        conn: Database connection
        results: List of (date, state_estimate, covariance_estimate, kalman_gain) tuples
    """
    query = """
        INSERT INTO daily_facts_filtered (fact_date, fat_mass_kg_filtered, fat_mass_kg_variance, kalman_gain)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (fact_date) DO UPDATE SET
            fat_mass_kg_filtered = EXCLUDED.fat_mass_kg_filtered,
            fat_mass_kg_variance = EXCLUDED.fat_mass_kg_variance,
            kalman_gain = EXCLUDED.kalman_gain,
            created_at = CURRENT_TIMESTAMP
    """
    
    with conn.cursor() as cur:
        cur.executemany(query, results)
    conn.commit()


def run_kalman_filter(start_date: str, end_date: str, test_mode: bool = False) -> None:
    """
    Run Kalman filter on specified date range
    
    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        test_mode: If True, print detailed intermediate calculations
    """
    conn = get_database_connection()
    
    try:
        # Load data
        data = load_fat_mass_data(conn, start_date, end_date)
        
        if not data:
            print(f"No data found for range {start_date} to {end_date}")
            return
        
        # Find first measurement for initialization
        first_measurement = None
        first_date = None
        for date_val, measurement in data:
            if measurement is not None:
                first_measurement = measurement
                first_date = date_val
                break
        
        if first_measurement is None:
            print("No measurements found in date range")
            return
        
        # Initialize Kalman filter
        kf = KalmanFilter()
        kf.initialize(first_measurement)
        
        if test_mode:
            print(f"🔧 Kalman Filter Test Mode - {start_date} to {end_date}")
            print(f"Parameters: Q = {kf.Q}, R = {kf.R}")
            print(f"Initial state: x̂₀ = {first_measurement:.3f} kg, P₀ = {kf.R:.3f} kg²")
            print("=" * 80)
        
        # Process each day
        results = []
        last_measurement_date = first_date
        
        for i, (current_date, measurement) in enumerate(data):
            days_since_last = (current_date - last_measurement_date).days
            
            # Process through Kalman filter
            kalman_gain, state_estimate, covariance_estimate = kf.process_measurement(
                measurement, days_since_last
            )
            
            # Update last measurement date if we have a measurement
            if measurement is not None:
                last_measurement_date = current_date
            
            results.append((current_date, state_estimate, covariance_estimate, kalman_gain))
            
            if test_mode:
                measurement_str = f"{measurement:.3f}" if measurement is not None else "NULL"
                print(f"Day {i+1}: {current_date}")
                print(f"  Measurement: {measurement_str} kg")
                print(f"  Days since last: {days_since_last}")
                print(f"  Predicted state: {kf.state_estimates[-2] if len(kf.state_estimates) > 1 else 'N/A':.3f} kg")
                print(f"  Predicted covariance: {kf.covariances[-2] if len(kf.covariances) > 1 else 'N/A':.3f} kg²")
                print(f"  Kalman gain: K_t = {kalman_gain:.6f}")
                print(f"  Updated state: x̂_t = {state_estimate:.3f} kg")
                print(f"  Updated covariance: P_t = {covariance_estimate:.3f} kg²")
                print()
        
        # Validation checks in test mode
        if test_mode:
            print("🔍 VALIDATION CHECKS:")
            print("=" * 50)
            
            # Check 1: Kalman gain between 0 and 1
            gains = [g for g in kf.kalman_gains if g > 0]  # Exclude initialization
            if gains:
                min_gain = min(gains)
                max_gain = max(gains)
                print(f"✅ Kalman gain range: {min_gain:.6f} to {max_gain:.6f} (should be 0-1)")
                if not (0 <= min_gain <= max_gain <= 1):
                    print("❌ ERROR: Kalman gain outside [0,1] range!")
            else:
                print("⚠️  No measurements to validate Kalman gain")
            
            # Check 2: Gain decreases with consecutive measurements
            consecutive_gains = []
            for i in range(1, len(kf.kalman_gains)):
                if kf.kalman_gains[i] > 0:  # Only check actual measurements
                    consecutive_gains.append(kf.kalman_gains[i])
            
            if len(consecutive_gains) > 1:
                decreasing = all(consecutive_gains[i] >= consecutive_gains[i+1] 
                               for i in range(len(consecutive_gains)-1))
                print(f"✅ Gain decreases with consecutive measurements: {decreasing}")
                if not decreasing:
                    print("❌ ERROR: Kalman gain should decrease with more confidence!")
            
            # Check 3: Covariance decreases with consecutive measurements
            consecutive_covs = [kf.covariances[i] for i in range(1, len(kf.covariances)) 
                              if kf.kalman_gains[i] > 0]
            
            if len(consecutive_covs) > 1:
                decreasing_cov = all(consecutive_covs[i] >= consecutive_covs[i+1] 
                                   for i in range(len(consecutive_covs)-1))
                print(f"✅ Covariance decreases with consecutive measurements: {decreasing_cov}")
                if not decreasing_cov:
                    print("❌ ERROR: Covariance should decrease with more confidence!")
            
            # Calculate statistics
            measurements = [m for _, m in data if m is not None]
            if len(measurements) > 1:
                raw_std = np.std(measurements)
                filtered_std = np.std([r[1] for r in results if r[0] in [d[0] for d in data if d[1] is not None]])
                improvement = (raw_std - filtered_std) / raw_std * 100
                
                print(f"📊 STATISTICS:")
                print(f"  Raw stddev: {raw_std:.3f} kg")
                print(f"  Filtered stddev: {filtered_std:.3f} kg")
                print(f"  Improvement: {improvement:.1f}% reduction")
                print(f"  Expected: ~67% reduction (3x improvement)")
        
        # Save results
        create_filtered_table(conn)
        save_filtered_data(conn, results)
        
        print(f"✅ Kalman filter completed: {len(results)} days processed")
        print(f"   Date range: {start_date} to {end_date}")
        print(f"   Results saved to daily_facts_filtered table")
        
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='Kalman filter for BIA fat mass smoothing')
    parser.add_argument('--start-date', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--test', action='store_true', 
                       help='Run test mode on Sept 9-11 data with detailed output')
    
    args = parser.parse_args()
    
    if args.test:
        # Test mode with known data
        run_kalman_filter('2025-09-09', '2025-09-11', test_mode=True)
    elif args.start_date and args.end_date:
        # Normal mode
        run_kalman_filter(args.start_date, args.end_date, test_mode=False)
    else:
        print("Usage:")
        print("  python etl/kalman_filter.py --test")
        print("  python etl/kalman_filter.py --start-date 2021-01-01 --end-date 2025-09-28")
        sys.exit(1)


if __name__ == "__main__":
    main()
