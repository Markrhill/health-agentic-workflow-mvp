#!/usr/bin/env python3
"""
Test suite for the 4-Parameter Energy Balance Model.

Tests core functionality including data loading, preprocessing, window building,
model fitting, parameter interpretation, and validation.
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import tempfile

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.energy_balance_model import EnergyBalanceModel

class TestEnergyBalanceModel(unittest.TestCase):
    """Test the EnergyBalanceModel class."""
    
    def setUp(self):
        """Set up test environment."""
        self.config = {
            'start_date': '2021-01-01',
            'end_date': '2021-12-31',
            'window_days': 14,
            'robust_window': 7,
            'robust_k': 3.0,
            'min_valid_days': 10,
            'huber_epsilon': 1.35,
            'huber_alpha': 1e-3
        }
        
        # Mock database engine
        self.mock_engine = Mock()
        
        # Create sample data
        self.sample_data = self._create_sample_data()
        
    def _create_sample_data(self) -> pd.DataFrame:
        """Create sample daily facts data for testing."""
        dates = pd.date_range('2021-01-01', '2021-12-31', freq='D')
        
        # Create realistic data with some noise
        np.random.seed(42)
        n_days = len(dates)
        
        # Base values
        base_fat_mass = 20.0
        base_lbm = 70.0
        base_intake = 2000
        base_workout = 300
        
        # Add some trends and noise
        fat_mass_trend = np.linspace(0, -2, n_days)  # Slight downward trend
        lbm_trend = np.linspace(0, 1, n_days)       # Slight upward trend
        
        fat_mass = base_fat_mass + fat_mass_trend + np.random.normal(0, 0.5, n_days)
        lbm = base_lbm + lbm_trend + np.random.normal(0, 1.0, n_days)
        intake = base_intake + np.random.normal(0, 200, n_days)
        workout = base_workout + np.random.normal(0, 100, n_days)
        
        # Ensure positive values
        intake = np.maximum(intake, 1000)
        workout = np.maximum(workout, 0)
        
        return pd.DataFrame({
            'fact_date': dates,
            'fat_mass_kg': fat_mass,
            'fat_free_mass_kg': lbm,
            'intake_kcal': intake,
            'workout_kcal': workout,
            'weight_kg': fat_mass + lbm
        })
    
    def test_robust_outlier_detection(self):
        """Test robust outlier detection."""
        model = EnergyBalanceModel(self.config)
        
        # Create series with outliers
        series = pd.Series([1, 2, 3, 4, 5, 100, 6, 7, 8, 9, 10])  # 100 is outlier
        cleaned = model.robust_outlier_detection(series, window=3, k=2.0)
        
        # Check that outlier was removed
        self.assertTrue(pd.isna(cleaned.iloc[5]))  # Outlier should be NaN
        self.assertFalse(pd.isna(cleaned.iloc[0]))  # Other values should remain
    
    def test_build_windows(self):
        """Test window building functionality."""
        model = EnergyBalanceModel(self.config)
        
        # Test with sample data
        windows = model.build_windows(self.sample_data)
        
        # Check that windows were created
        self.assertGreater(len(windows), 0)
        
        # Check required columns
        required_cols = ['start_date', 'end_date', 'delta_fm_kg', 'intake_sum', 
                        'workout_sum', 'mean_lbm', 'days']
        for col in required_cols:
            self.assertIn(col, windows.columns)
        
        # Check that all windows have correct length
        self.assertTrue((windows['days'] == self.config['window_days']).all())
        
        # Check that delta_fm_kg is calculated correctly
        for _, window in windows.iterrows():
            start_idx = self.sample_data[self.sample_data['fact_date'] == window['start_date']].index[0]
            end_idx = self.sample_data[self.sample_data['fact_date'] == window['end_date']].index[0]
            expected_delta = (self.sample_data.iloc[end_idx]['fat_mass_kg'] - 
                            self.sample_data.iloc[start_idx]['fat_mass_kg'])
            self.assertAlmostEqual(window['delta_fm_kg'], expected_delta, places=5)
    
    def test_fit_model(self):
        """Test model fitting."""
        model = EnergyBalanceModel(self.config)
        
        # Create sample windows
        windows = model.build_windows(self.sample_data)
        
        # Fit model
        fitted_model, scaler = model.fit_model(windows)
        
        # Check that model was fitted
        self.assertIsNotNone(fitted_model)
        self.assertIsNotNone(scaler)
        
        # Check that coefficients exist
        self.assertEqual(len(fitted_model.coef_), 4)  # 4 features
    
    def test_interpret_parameters(self):
        """Test parameter interpretation."""
        model = EnergyBalanceModel(self.config)
        
        # Create mock model and scaler
        mock_model = Mock()
        mock_model.coef_ = np.array([0.001, 0.002, -0.003, 0.004])
        
        mock_scaler = Mock()
        mock_scaler.scale_ = np.array([1.0, 1.0, 1.0, 1.0])
        
        # Test parameter interpretation
        params = model.interpret_parameters(mock_model, mock_scaler)
        
        # Check that all parameters are present
        required_params = ['alpha', 'c', 'bmr0', 'k_lbm']
        for param in required_params:
            self.assertIn(param, params)
        
        # Check that alpha is calculated correctly
        expected_alpha = 1.0 / 0.004  # 1 / beta_intake
        self.assertAlmostEqual(params['alpha'], expected_alpha, places=5)
    
    def test_validate_parameters(self):
        """Test parameter validation."""
        model = EnergyBalanceModel(self.config)
        
        # Test with plausible parameters
        plausible_params = {
            'alpha': 9000,
            'c': 0.2,
            'bmr0': 500,
            'k_lbm': 15
        }
        
        all_plausible, warnings = model.validate_parameters(plausible_params)
        self.assertTrue(all_plausible)
        self.assertEqual(len(warnings), 0)
        
        # Test with implausible parameters
        implausible_params = {
            'alpha': 5000,  # Too low
            'c': 0.8,       # Too high
            'bmr0': 50,     # Too low
            'k_lbm': 50     # Too high
        }
        
        all_plausible, warnings = model.validate_parameters(implausible_params)
        self.assertFalse(all_plausible)
        self.assertGreater(len(warnings), 0)
    
    def test_calculate_fit_metrics(self):
        """Test fit metrics calculation."""
        model = EnergyBalanceModel(self.config)
        
        # Create sample windows
        windows = model.build_windows(self.sample_data)
        
        # Fit model
        fitted_model, scaler = model.fit_model(windows)
        
        # Calculate fit metrics
        metrics = model.calculate_fit_metrics(fitted_model, scaler, windows)
        
        # Check that metrics are present
        required_metrics = ['r2', 'mae', 'rmse', 'n_windows']
        for metric in required_metrics:
            self.assertIn(metric, metrics)
        
        # Check that metrics are reasonable
        self.assertGreaterEqual(metrics['r2'], 0)  # R² should be non-negative
        self.assertGreaterEqual(metrics['mae'], 0)  # MAE should be non-negative
        self.assertGreaterEqual(metrics['rmse'], 0)  # RMSE should be non-negative
        self.assertEqual(metrics['n_windows'], len(windows))
    
    @patch('tools.energy_balance_model.create_engine')
    def test_database_connection(self, mock_create_engine):
        """Test database connection."""
        # Mock successful connection
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        model = EnergyBalanceModel(self.config)
        
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://test'}):
            result = model.connect_database()
            self.assertTrue(result)
    
    @patch('tools.energy_balance_model.create_engine')
    def test_database_connection_failure(self, mock_create_engine):
        """Test database connection failure."""
        # Mock connection failure
        mock_create_engine.side_effect = Exception("Connection failed")
        
        model = EnergyBalanceModel(self.config)
        
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://test'}):
            result = model.connect_database()
            self.assertFalse(result)
    
    def test_insufficient_data_error(self):
        """Test error handling for insufficient data."""
        model = EnergyBalanceModel(self.config)
        
        # Create minimal data (less than 20 windows)
        minimal_data = self.sample_data.iloc[:50]  # Only 50 days
        model.data = minimal_data
        model.windows = model.build_windows(minimal_data)
        
        # This should raise an error
        with self.assertRaises(ValueError):
            model.run_analysis('2021-01-01', '2021-02-28')
    
    def test_data_preprocessing(self):
        """Test data preprocessing."""
        model = EnergyBalanceModel(self.config)
        
        # Test with sample data
        processed_data = model.preprocess_data(self.sample_data)
        
        # Check that data was processed
        self.assertEqual(len(processed_data), len(self.sample_data))
        
        # Check that required columns exist
        required_cols = ['fat_mass_kg', 'fat_free_mass_kg', 'intake_kcal', 'workout_kcal']
        for col in required_cols:
            self.assertIn(col, processed_data.columns)

class TestIntegration(unittest.TestCase):
    """Integration tests for the complete energy balance model."""
    
    def setUp(self):
        """Set up test environment."""
        self.config = {
            'start_date': '2021-01-01',
            'end_date': '2021-12-31',
            'window_days': 14,
            'robust_window': 7,
            'robust_k': 3.0,
            'min_valid_days': 10,
            'huber_epsilon': 1.35,
            'huber_alpha': 1e-3
        }
    
    @patch('tools.energy_balance_model.create_engine')
    def test_end_to_end_analysis(self, mock_create_engine):
        """Test complete end-to-end analysis."""
        # Mock database engine
        mock_engine = Mock()
        mock_create_engine.return_value = mock_engine
        
        # Create sample data
        dates = pd.date_range('2021-01-01', '2021-12-31', freq='D')
        np.random.seed(42)
        
        sample_data = pd.DataFrame({
            'fact_date': dates,
            'fat_mass_kg': 20 + np.random.normal(0, 0.5, len(dates)),
            'fat_free_mass_kg': 70 + np.random.normal(0, 1.0, len(dates)),
            'intake_kcal': 2000 + np.random.normal(0, 200, len(dates)),
            'workout_kcal': 300 + np.random.normal(0, 100, len(dates)),
            'weight_kg': 90 + np.random.normal(0, 1.0, len(dates))
        })
        
        # Mock database query
        with mock_engine.connect() as mock_conn:
            mock_conn.read_sql.return_value = sample_data
        
        # Initialize model
        model = EnergyBalanceModel(self.config)
        
        with patch.dict(os.environ, {'DATABASE_URL': 'postgresql://test'}):
            # Run analysis
            results = model.run_analysis('2021-01-01', '2021-12-31')
            
            # Check that results were generated
            self.assertIn('parameters', results)
            self.assertIn('fit_metrics', results)
            self.assertIn('validation', results)
            self.assertIn('data_summary', results)
            
            # Check that parameters are present
            params = results['parameters']
            required_params = ['alpha', 'c', 'bmr0', 'k_lbm']
            for param in required_params:
                self.assertIn(param, params)
            
            # Check that fit metrics are present
            fit_metrics = results['fit_metrics']
            required_metrics = ['r2', 'mae', 'rmse', 'n_windows']
            for metric in required_metrics:
                self.assertIn(metric, fit_metrics)

def run_tests():
    """Run all tests."""
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test cases
    test_classes = [
        TestEnergyBalanceModel,
        TestIntegration
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    return result.wasSuccessful()

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
