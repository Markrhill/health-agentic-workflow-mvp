#!/usr/bin/env python3
"""
Test suite for Withings historical data backfill functionality.

Tests the core functionality of:
- Date range chunking
- Pagination handling
- Progress tracking
- Error handling
- Data conversion and storage
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import json
import tempfile

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.withings_historical_backfill import WithingsHistoricalBackfill
from scripts.backfill_progress_tracker import BackfillProgressTracker

class TestWithingsHistoricalBackfill(unittest.TestCase):
    """Test historical backfill functionality."""
    
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
            self.backfill = WithingsHistoricalBackfill()
    
    def test_date_to_unix_timestamp(self):
        """Test date to Unix timestamp conversion."""
        # Test known date
        timestamp = self.backfill._date_to_unix_timestamp("2021-01-01")
        expected = 1609459200  # Jan 1, 2021 00:00:00 UTC
        self.assertEqual(timestamp, expected)
        
        # Test another date
        timestamp = self.backfill._date_to_unix_timestamp("2024-02-01")
        expected = 1706745600  # Feb 1, 2024 00:00:00 UTC
        self.assertEqual(timestamp, expected)
    
    def test_unix_timestamp_to_date(self):
        """Test Unix timestamp to date conversion."""
        date_str = self.backfill._unix_timestamp_to_date(1609459200)
        self.assertEqual(date_str, "2021-01-01")
        
        date_str = self.backfill._unix_timestamp_to_date(1706745600)
        self.assertEqual(date_str, "2024-02-01")
    
    def test_chunk_date_ranges(self):
        """Test date range chunking."""
        chunks = self.backfill.chunk_date_ranges("2021-01-01", "2021-12-31", 6)
        
        # Should create 2 chunks for 2021
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[0], ("2021-01-01", "2021-06-30"))
        self.assertEqual(chunks[1], ("2021-07-01", "2021-12-31"))
    
    def test_chunk_date_ranges_multiple_years(self):
        """Test chunking across multiple years."""
        chunks = self.backfill.chunk_date_ranges("2021-01-01", "2022-12-31", 6)
        
        # Should create 4 chunks for 2021-2022
        self.assertEqual(len(chunks), 4)
        self.assertEqual(chunks[0], ("2021-01-01", "2021-06-30"))
        self.assertEqual(chunks[1], ("2021-07-01", "2021-12-31"))
        self.assertEqual(chunks[2], ("2022-01-01", "2022-06-30"))
        self.assertEqual(chunks[3], ("2022-07-01", "2022-12-31"))
    
    def test_chunk_date_ranges_partial_year(self):
        """Test chunking with partial year."""
        chunks = self.backfill.chunk_date_ranges("2021-01-01", "2021-03-15", 6)
        
        # Should create 1 chunk for partial year
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], ("2021-01-01", "2021-03-15"))
    
    def test_handle_api_errors_success(self):
        """Test successful API response handling."""
        response = {"status": 0, "body": {"measuregrps": []}}
        action = self.backfill._handle_api_errors(response, "test_chunk")
        self.assertEqual(action, "success")
    
    def test_handle_api_errors_rate_limit(self):
        """Test rate limit error handling."""
        response = {"status": 601, "error": "Rate limit exceeded"}
        action = self.backfill._handle_api_errors(response, "test_chunk")
        self.assertEqual(action, "retry")
    
    def test_handle_api_errors_invalid_token(self):
        """Test invalid token error handling."""
        response = {"status": 401, "error": "Invalid token"}
        with patch.object(self.backfill.token_manager, 'get_valid_token'):
            action = self.backfill._handle_api_errors(response, "test_chunk")
            self.assertEqual(action, "retry")
    
    def test_handle_api_errors_other_error(self):
        """Test other API error handling."""
        response = {"status": 500, "error": "Internal server error"}
        action = self.backfill._handle_api_errors(response, "test_chunk")
        self.assertEqual(action, "skip_chunk")
    
    def test_convert_and_store_measurements(self):
        """Test measurement conversion and storage."""
        # Sample Withings API response
        measurements = [
            {
                "grpid": 12345,
                "date": 1609459200,  # Jan 1, 2021
                "measures": [
                    {
                        "type": 1,  # Weight
                        "value": 75000,  # 75 kg in grams
                        "unit": -3
                    }
                ]
            },
            {
                "grpid": 12346,
                "date": 1609545600,  # Jan 2, 2021
                "measures": [
                    {
                        "type": 1,  # Weight
                        "value": 75100,  # 75.1 kg in grams
                        "unit": -3
                    }
                ]
            }
        ]
        
        with patch.object(self.backfill.db, 'upsert_measurement', return_value=True):
            successful, errors = self.backfill.convert_and_store_measurements(measurements, "test_chunk")
            
            self.assertEqual(successful, 2)
            self.assertEqual(errors, 0)
    
    def test_convert_and_store_measurements_invalid_weight(self):
        """Test measurement conversion with invalid weight."""
        measurements = [
            {
                "grpid": 12345,
                "date": 1609459200,
                "measures": [
                    {
                        "type": 1,  # Weight
                        "value": 5000,  # 5 kg (too low)
                        "unit": -3
                    }
                ]
            }
        ]
        
        successful, errors = self.backfill.convert_and_store_measurements(measurements, "test_chunk")
        
        self.assertEqual(successful, 0)
        self.assertEqual(errors, 1)
    
    def test_convert_and_store_measurements_no_weight(self):
        """Test measurement conversion with no weight data."""
        measurements = [
            {
                "grpid": 12345,
                "date": 1609459200,
                "measures": [
                    {
                        "type": 8,  # Fat mass, not weight
                        "value": 20000,
                        "unit": -3
                    }
                ]
            }
        ]
        
        successful, errors = self.backfill.convert_and_store_measurements(measurements, "test_chunk")
        
        self.assertEqual(successful, 0)
        self.assertEqual(errors, 0)  # No errors, just skipped

class TestBackfillProgressTracker(unittest.TestCase):
    """Test progress tracking functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
        self.temp_file.close()
        self.tracker = BackfillProgressTracker(self.temp_file.name)
    
    def tearDown(self):
        """Clean up test files."""
        os.unlink(self.temp_file.name)
    
    def test_initial_progress(self):
        """Test initial progress state."""
        summary = self.tracker.get_progress_summary()
        self.assertEqual(summary["status"], "not_started")
    
    def test_progress_summary(self):
        """Test progress summary generation."""
        # Set up test data
        self.tracker.progress_data = {
            "completed_chunks": ["2021-01-01 to 2021-06-30", "2021-07-01 to 2021-12-31"],
            "total_measurements_extracted": 500,
            "total_errors": 10,
            "last_chunk_completed": "2021-07-01 to 2021-12-31",
            "start_time": "2023-01-01T10:00:00"
        }
        
        summary = self.tracker.get_progress_summary()
        
        self.assertEqual(summary["status"], "in_progress")
        self.assertEqual(summary["completed_chunks"], 2)
        self.assertEqual(summary["total_measurements_extracted"], 500)
        self.assertEqual(summary["total_errors"], 10)
        self.assertEqual(summary["success_rate"], 98.0)  # 500/(500+10)*100
    
    def test_chunk_analysis(self):
        """Test chunk analysis functionality."""
        # Set up test data
        self.tracker.progress_data = {
            "chunk_details": {
                "2021-01-01 to 2021-06-30": {"measurements": 250, "errors": 5},
                "2021-07-01 to 2021-12-31": {"measurements": 300, "errors": 3},
                "2022-01-01 to 2022-06-30": {"measurements": 200, "errors": 0}
            }
        }
        
        analysis = self.tracker.get_chunk_analysis()
        
        self.assertEqual(analysis["total_chunks_processed"], 3)
        self.assertEqual(analysis["avg_measurements_per_chunk"], 250.0)
        self.assertEqual(analysis["max_measurements_in_chunk"], 300)
        self.assertEqual(analysis["min_measurements_in_chunk"], 200)
        self.assertEqual(analysis["total_errors"], 8)
        self.assertEqual(analysis["chunks_with_errors"], 2)
    
    def test_remaining_chunks(self):
        """Test remaining chunks calculation."""
        all_chunks = [
            "2021-01-01 to 2021-06-30",
            "2021-07-01 to 2021-12-31",
            "2022-01-01 to 2022-06-30",
            "2022-07-01 to 2022-12-31"
        ]
        
        self.tracker.progress_data = {
            "completed_chunks": ["2021-01-01 to 2021-06-30", "2022-01-01 to 2022-06-30"]
        }
        
        remaining = self.tracker.get_remaining_chunks(all_chunks)
        
        self.assertEqual(len(remaining), 2)
        self.assertIn("2021-07-01 to 2021-12-31", remaining)
        self.assertIn("2022-07-01 to 2022-12-31", remaining)
    
    def test_estimate_completion_time(self):
        """Test completion time estimation."""
        self.tracker.progress_data = {
            "start_time": "2023-01-01T10:00:00",
            "completed_chunks": ["chunk1", "chunk2", "chunk3"]
        }
        
        remaining_chunks = ["chunk4", "chunk5"]
        
        # Mock datetime.now to return a fixed time
        with patch('scripts.backfill_progress_tracker.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2023, 1, 1, 12, 0, 0)  # 2 hours later
            mock_datetime.fromisoformat.return_value = datetime(2023, 1, 1, 10, 0, 0)
            
            estimated_time = self.tracker.estimate_completion_time(remaining_chunks)
            
            self.assertIsNotNone(estimated_time)
            self.assertIn("0:40:00", estimated_time)  # 2 hours / 3 chunks * 2 remaining = 40 minutes
    
    def test_generate_report(self):
        """Test report generation."""
        self.tracker.progress_data = {
            "completed_chunks": ["2021-01-01 to 2021-06-30"],
            "total_measurements_extracted": 250,
            "total_errors": 5,
            "last_chunk_completed": "2021-01-01 to 2021-06-30",
            "start_time": "2023-01-01T10:00:00"
        }
        
        report = self.tracker.generate_report()
        
        self.assertIn("WITHINGS HISTORICAL BACKFILL PROGRESS REPORT", report)
        self.assertIn("Status: In_progress", report)
        self.assertIn("Completed Chunks: 1", report)
        self.assertIn("Total Measurements Extracted: 250", report)
        self.assertIn("Success Rate: 98.0%", report)

class TestIntegration(unittest.TestCase):
    """Integration tests for the complete backfill system."""
    
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
            self.backfill = WithingsHistoricalBackfill()
            self.backfill.db.create_table()
    
    @patch('requests.post')
    def test_end_to_end_chunk_extraction(self, mock_post):
        """Test complete chunk extraction process."""
        # Mock API response
        mock_response = Mock()
        mock_response.json.return_value = {
            "status": 0,
            "body": {
                "measuregrps": [
                    {
                        "grpid": 12345,
                        "date": 1609459200,  # Jan 1, 2021
                        "measures": [
                            {
                                "type": 1,
                                "value": 75000,
                                "unit": -3
                            }
                        ]
                    }
                ],
                "more": 0  # No more data
            }
        }
        mock_post.return_value = mock_response
        
        # Mock token validation
        with patch.object(self.backfill.token_manager, '_is_token_valid', return_value=True):
            measurements = self.backfill.extract_chunk_with_pagination("2021-01-01", "2021-01-31")
            
            self.assertEqual(len(measurements), 1)
            self.assertEqual(measurements[0]['grpid'], 12345)
    
    def test_progress_tracking_integration(self):
        """Test progress tracking integration."""
        # Simulate chunk completion
        self.backfill.progress_data["completed_chunks"].append("2021-01-01 to 2021-06-30")
        self.backfill.progress_data["total_measurements_extracted"] = 250
        self.backfill.progress_data["total_errors"] = 5
        self.backfill._save_progress()
        
        # Verify progress was saved
        self.assertTrue(os.path.exists(self.backfill.progress_file))
        
        # Load and verify
        with open(self.backfill.progress_file, 'r') as f:
            saved_data = json.load(f)
        
        self.assertEqual(len(saved_data["completed_chunks"]), 1)
        self.assertEqual(saved_data["total_measurements_extracted"], 250)
        self.assertEqual(saved_data["total_errors"], 5)

def run_tests():
    """Run all tests."""
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test cases
    test_classes = [
        TestWithingsHistoricalBackfill,
        TestBackfillProgressTracker,
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
