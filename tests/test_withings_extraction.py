#!/usr/bin/env python3
"""
Test suite for Withings data extraction system.

Tests the core functionality of:
- Token management
- Timestamp standardization
- Database operations
- Data extraction and conversion
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
import json

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.withings_token_manager import WithingsTokenManager
from scripts.timestamp_standardizer import TimestampStandardizer
from models.withings_measurements import WithingsMeasurementsDB
from scripts.extract_withings_raw import WithingsDataExtractor

class TestWithingsTokenManager(unittest.TestCase):
    """Test token management functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.manager = WithingsTokenManager()
    
    @patch.dict(os.environ, {
        'WITHINGS_CLIENT_ID': 'test_client',
        'WITHINGS_CLIENT_SECRET': 'test_secret',
        'WITHINGS_ACCESS_TOKEN': 'test_token',
        'WITHINGS_REFRESH_TOKEN': 'test_refresh'
    })
    def test_initialization(self):
        """Test token manager initialization."""
        manager = WithingsTokenManager()
        self.assertEqual(manager.client_id, 'test_client')
        self.assertEqual(manager.client_secret, 'test_secret')
    
    def test_missing_credentials(self):
        """Test error handling for missing credentials."""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                WithingsTokenManager()
    
    @patch('requests.post')
    def test_token_validation_success(self, mock_post):
        """Test successful token validation."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": 0}
        mock_post.return_value = mock_response
        
        with patch.dict(os.environ, {
            'WITHINGS_ACCESS_TOKEN': 'valid_token',
            'WITHINGS_REFRESH_TOKEN': 'valid_refresh'
        }):
            manager = WithingsTokenManager()
            result = manager._is_token_valid('valid_token')
            self.assertTrue(result)
    
    @patch('requests.post')
    def test_token_validation_failure(self, mock_post):
        """Test token validation failure."""
        mock_response = Mock()
        mock_response.json.return_value = {"status": 1, "error": "invalid_token"}
        mock_post.return_value = mock_response
        
        with patch.dict(os.environ, {
            'WITHINGS_ACCESS_TOKEN': 'invalid_token',
            'WITHINGS_REFRESH_TOKEN': 'valid_refresh'
        }):
            manager = WithingsTokenManager()
            result = manager._is_token_valid('invalid_token')
            self.assertFalse(result)

class TestTimestampStandardizer(unittest.TestCase):
    """Test timestamp standardization functionality."""
    
    def setUp(self):
        """Set up test environment."""
        with patch.dict(os.environ, {'USER_TIMEZONE': 'America/Los_Angeles'}):
            self.standardizer = TimestampStandardizer()
    
    def test_standardize_timestamp(self):
        """Test timestamp standardization."""
        # Test with a known timestamp
        test_timestamp = 1759163784  # From recent Withings data
        
        result = self.standardizer.standardize_withings_timestamp(test_timestamp)
        
        self.assertIn('timestamp_utc', result)
        self.assertIn('timestamp_user', result)
        self.assertIn('measurement_date_user', result)
        self.assertEqual(result['user_timezone'], 'America/Los_Angeles')
        self.assertEqual(result['epoch_seconds'], test_timestamp)
    
    def test_invalid_timestamp(self):
        """Test error handling for invalid timestamps."""
        with self.assertRaises(ValueError):
            self.standardizer.standardize_withings_timestamp(-1)
    
    def test_timezone_info(self):
        """Test timezone information retrieval."""
        info = self.standardizer.get_timezone_info()
        
        self.assertIn('user_timezone', info)
        self.assertIn('current_utc', info)
        self.assertIn('current_user', info)
        self.assertEqual(info['user_timezone'], 'America/Los_Angeles')

class TestWithingsMeasurementsDB(unittest.TestCase):
    """Test database operations."""
    
    def setUp(self):
        """Set up test environment."""
        with patch.dict(os.environ, {'DATABASE_URL': 'sqlite:///:memory:'}):
            self.db = WithingsMeasurementsDB()
    
    def test_initialization(self):
        """Test database initialization."""
        self.assertIsNotNone(self.db.engine)
        self.assertIsNotNone(self.db.withings_raw_measurements)
    
    def test_table_creation(self):
        """Test table creation."""
        # This will create the table in memory
        self.db.create_table()
        # If no exception is raised, table creation succeeded
        self.assertTrue(True)
    
    def test_upsert_measurement(self):
        """Test measurement upsert."""
        self.db.create_table()
        
        test_data = {
            'measurement_id': 'test_123',
            'weight_kg': 75.5,
            'timestamp_utc': datetime.now(timezone.utc),
            'timestamp_user': datetime.now(timezone.utc),
            'original_timezone': 'UTC',
            'user_timezone': 'America/Los_Angeles',
            'source_format': 'test',
            'raw_value': 75500,
            'raw_unit': -3
        }
        
        result = self.db.upsert_measurement(test_data)
        self.assertTrue(result)

class TestWithingsDataExtractor(unittest.TestCase):
    """Test data extraction functionality."""
    
    def setUp(self):
        """Set up test environment."""
        with patch.dict(os.environ, {
            'WITHINGS_CLIENT_ID': 'test_client',
            'WITHINGS_CLIENT_SECRET': 'test_secret',
            'WITHINGS_ACCESS_TOKEN': 'test_token',
            'WITHINGS_REFRESH_TOKEN': 'test_refresh',
            'DATABASE_URL': 'sqlite:///:memory:',
            'USER_TIMEZONE': 'America/Los_Angeles'
        }):
            self.extractor = WithingsDataExtractor()
    
    def test_initialization(self):
        """Test extractor initialization."""
        self.assertIsNotNone(self.extractor.token_manager)
        self.assertIsNotNone(self.extractor.timestamp_standardizer)
        self.assertIsNotNone(self.extractor.db)
    
    def test_convert_weight_measurement(self):
        """Test weight measurement conversion."""
        # Sample Withings API response
        sample_measurement = {
            "grpid": 12345,
            "date": 1759163784,
            "measures": [
                {
                    "type": 1,  # Weight
                    "value": 75500,
                    "unit": -3  # Grams
                }
            ]
        }
        
        result = self.extractor.convert_weight_measurement(sample_measurement)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['measurement_id'], '12345')
        self.assertEqual(result['weight_kg'], 75.5)  # 75500 / 1000
        self.assertEqual(result['raw_value'], 75500)
        self.assertEqual(result['raw_unit'], -3)
    
    def test_convert_invalid_measurement(self):
        """Test conversion of invalid measurement."""
        # Measurement without weight data
        invalid_measurement = {
            "grpid": 12345,
            "date": 1759163784,
            "measures": [
                {
                    "type": 8,  # Fat mass, not weight
                    "value": 20000,
                    "unit": -3
                }
            ]
        }
        
        result = self.extractor.convert_weight_measurement(invalid_measurement)
        self.assertIsNone(result)
    
    def test_convert_out_of_range_weight(self):
        """Test conversion of out-of-range weight."""
        # Extremely high weight
        invalid_measurement = {
            "grpid": 12345,
            "date": 1759163784,
            "measures": [
                {
                    "type": 1,  # Weight
                    "value": 500000,  # 500 kg
                    "unit": -3
                }
            ]
        }
        
        result = self.extractor.convert_weight_measurement(invalid_measurement)
        self.assertIsNone(result)
    
    @patch('requests.post')
    def test_extract_weight_measurements(self, mock_post):
        """Test weight measurement extraction."""
        # Mock API response
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": 0,
            "body": {
                "measuregrps": [
                    {
                        "grpid": 12345,
                        "date": 1759163784,
                        "measures": [
                            {
                                "type": 1,
                                "value": 75500,
                                "unit": -3
                            }
                        ]
                    }
                ]
            }
        }
        mock_post.return_value = mock_response
        
        # Mock token validation
        with patch.object(self.extractor.token_manager, '_is_token_valid', return_value=True):
            result = self.extractor.extract_weight_measurements(limit=10)
            
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0]['grpid'], 12345)

class TestIntegration(unittest.TestCase):
    """Integration tests for the complete system."""
    
    def setUp(self):
        """Set up test environment."""
        with patch.dict(os.environ, {
            'WITHINGS_CLIENT_ID': 'test_client',
            'WITHINGS_CLIENT_SECRET': 'test_secret',
            'WITHINGS_ACCESS_TOKEN': 'test_token',
            'WITHINGS_REFRESH_TOKEN': 'test_refresh',
            'DATABASE_URL': 'sqlite:///:memory:',
            'USER_TIMEZONE': 'America/Los_Angeles'
        }):
            self.extractor = WithingsDataExtractor()
            self.extractor.db.create_table()
    
    @patch('requests.post')
    def test_end_to_end_sync(self, mock_post):
        """Test complete end-to-end sync process."""
        # Mock API response
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": 0,
            "body": {
                "measuregrps": [
                    {
                        "grpid": 12345,
                        "date": 1759163784,
                        "measures": [
                            {
                                "type": 1,
                                "value": 75500,
                                "unit": -3
                            }
                        ]
                    }
                ]
            }
        }
        mock_post.return_value = mock_response
        
        # Mock token validation
        with patch.object(self.extractor.token_manager, '_is_token_valid', return_value=True):
            stats = self.extractor.sync_measurements(limit=10, incremental=False)
            
            self.assertEqual(stats['total_fetched'], 1)
            self.assertEqual(stats['successfully_converted'], 1)
            self.assertEqual(stats['successfully_stored'], 1)
            self.assertEqual(stats['errors'], 0)

def run_tests():
    """Run all tests."""
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test cases
    test_classes = [
        TestWithingsTokenManager,
        TestTimestampStandardizer,
        TestWithingsMeasurementsDB,
        TestWithingsDataExtractor,
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
