#!/usr/bin/env python3
"""
Withings Historical Data Backfill - Extract historical body composition measurements from Jan 2021 to Feb 2024.

This script extracts historical body composition measurements (weight, fat mass, muscle mass, bone mass, 
body water, fat ratio) from Withings API using date range queries and pagination to fill the gap 
between CSV export data and current API data.

Features:
- Chunked date range processing (6-month chunks)
- Pagination handling for large datasets
- Progress tracking and resume capability
- Rate limiting and error handling
- Duplicate prevention
- Comprehensive logging
- Full body composition data extraction (all measure types)
"""

import os
import sys
import requests
import json
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import argparse

# Add project root to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.withings_token_manager import WithingsTokenManager
from scripts.timestamp_standardizer import TimestampStandardizer
from models.withings_measurements import WithingsMeasurementsDB

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WithingsHistoricalBackfill:
    """Extracts historical Withings data using date range queries."""
    
    def __init__(self):
        self.token_manager = WithingsTokenManager()
        self.timestamp_standardizer = TimestampStandardizer()
        self.db = WithingsMeasurementsDB()
        self.base_url = "https://wbsapi.withings.net"
        self.measure_endpoint = f"{self.base_url}/measure"
        
        # Configuration
        self.max_retries = 3
        self.retry_delay = 5  # seconds
        self.request_timeout = 30  # seconds
        self.rate_limit_delay = 1  # seconds between requests
        self.rate_limit_error_delay = 60  # seconds for rate limit errors
        
        # Progress tracking
        self.progress_file = "backfill_progress.json"
        self.progress_data = self._load_progress()
    
    def _load_progress(self) -> Dict:
        """Load progress tracking data."""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load progress file: {e}")
        
        return {
            "completed_chunks": [],
            "total_measurements_extracted": 0,
            "total_errors": 0,
            "last_chunk_completed": None,
            "start_time": None
        }
    
    def _save_progress(self):
        """Save progress tracking data."""
        try:
            with open(self.progress_file, 'w') as f:
                json.dump(self.progress_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save progress: {e}")
    
    def _date_to_unix_timestamp(self, date_str: str) -> int:
        """Convert date string to Unix timestamp."""
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return int(dt.timestamp())
    
    def _unix_timestamp_to_date(self, timestamp: int) -> str:
        """Convert Unix timestamp to date string."""
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%Y-%m-%d")
    
    def chunk_date_ranges(self, start_date: str, end_date: str, chunk_months: int = 6) -> List[Tuple[str, str]]:
        """
        Break large date range into smaller chunks.
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            chunk_months: Number of months per chunk
            
        Returns:
            List of (start_date, end_date) tuples
        """
        chunks = []
        current_start = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        while current_start < end_dt:
            # Calculate chunk end date
            if chunk_months == 6:
                # 6-month chunks
                if current_start.month <= 6:
                    chunk_end = current_start.replace(month=6, day=30)
                else:
                    chunk_end = current_start.replace(month=12, day=31)
            else:
                # Generic month chunks
                chunk_end = current_start + timedelta(days=chunk_months * 30)
            
            # Don't exceed the overall end date
            if chunk_end > end_dt:
                chunk_end = end_dt
            
            chunks.append((
                current_start.strftime("%Y-%m-%d"),
                chunk_end.strftime("%Y-%m-%d")
            ))
            
            # Move to next chunk
            current_start = chunk_end + timedelta(days=1)
        
        return chunks
    
    def extract_chunk_with_pagination(self, start_date: str, end_date: str) -> List[Dict]:
        """
        Extract all measurements for a date range using pagination.
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            List of measurement groups from API
        """
        access_token = self.token_manager.get_valid_token()
        headers = {"Authorization": f"Bearer {access_token}"}
        
        start_timestamp = self._date_to_unix_timestamp(start_date)
        end_timestamp = self._date_to_unix_timestamp(end_date)
        
        all_measurements = []
        offset = 0
        
        logger.info(f"Extracting chunk {start_date} to {end_date}")
        
        while True:
            params = {
                "action": "getmeas",
                "meastype": "1,5,6,8,76,77,88",  # All body composition types
                "category": "1",  # Real measurements only
                "startdate": str(start_timestamp),
                "enddate": str(end_timestamp),
                "offset": str(offset)
            }
            
            try:
                response = requests.post(
                    self.measure_endpoint,
                    headers=headers,
                    data=params,
                    timeout=self.request_timeout
                )
                
                response.raise_for_status()
                result = response.json()
                
                # Handle API errors
                error_action = self._handle_api_errors(result, f"{start_date} to {end_date}")
                if error_action == "retry":
                    time.sleep(self.rate_limit_error_delay)
                    continue
                elif error_action == "skip_chunk":
                    logger.error(f"Skipping chunk {start_date} to {end_date} due to API error")
                    break
                
                # Process successful response
                if result.get("status") != 0:
                    logger.error(f"API error: {result.get('error', 'Unknown error')}")
                    break
                
                body = result.get("body", {})
                measurements = body.get("measuregrps", [])
                all_measurements.extend(measurements)
                
                logger.info(f"  Fetched {len(measurements)} measurements (offset {offset})")
                
                # Check if more data available
                if body.get("more", 0) == 0:
                    break
                
                offset = body.get("offset", offset + len(measurements))
                
                # Rate limiting
                time.sleep(self.rate_limit_delay)
                
            except requests.RequestException as e:
                logger.error(f"Request failed for chunk {start_date} to {end_date}: {e}")
                break
        
        logger.info(f"Chunk {start_date} to {end_date}: {len(all_measurements)} total measurements")
        return all_measurements
    
    def _handle_api_errors(self, response: Dict, chunk_info: str) -> str:
        """
        Handle API errors and return action to take.
        
        Args:
            response: API response
            chunk_info: Description of current chunk
            
        Returns:
            "success", "retry", or "skip_chunk"
        """
        status = response.get("status", 0)
        
        if status == 601:  # Rate limit
            logger.warning(f"Rate limited on {chunk_info}, waiting {self.rate_limit_error_delay} seconds...")
            return "retry"
        elif status == 401:  # Invalid token
            logger.warning("Token invalid, refreshing...")
            self.token_manager.get_valid_token()  # This will refresh
            return "retry"
        elif status != 0:
            logger.error(f"API error {status} on {chunk_info}: {response.get('error', 'Unknown error')}")
            return "skip_chunk"
        
        return "success"
    
    def parse_withings_measurements(self, measure_group):
        """Extract all measure types from a Withings API response"""
        measurements = {}
        
        for measure in measure_group['measures']:
            value = measure['value'] * (10 ** measure['unit'])
            
            measure_type = measure['type']
            if measure_type == 1:
                measurements['weight_kg'] = value
            elif measure_type == 5:
                measurements['fat_free_mass_kg'] = value
            elif measure_type == 6:
                measurements['fat_ratio_pct'] = value
            elif measure_type == 8:
                measurements['fat_mass_kg'] = value
            elif measure_type == 76:
                measurements['muscle_mass_kg'] = value
            elif measure_type == 77:
                measurements['body_water_kg'] = value
            elif measure_type == 88:
                measurements['bone_mass_kg'] = value
        return measurements

    def convert_and_store_measurements(self, measurements: List[Dict], chunk_info: str) -> Tuple[int, int]:
        """
        Convert measurements to standardized format and store in database.
        
        Args:
            measurements: Raw measurement groups from API
            chunk_info: Description of current chunk
            
        Returns:
            Tuple of (successful_stored, errors)
        """
        successful_stored = 0
        errors = 0
        
        for measurement_group in measurements:
            try:
                # Filter for Body+ device only (modelid 13)
                modelid = measurement_group.get("modelid")
                if modelid != 13:  # Only Body+ device
                    continue
                
                # Parse all measurement types
                parsed_measurements = self.parse_withings_measurements(measurement_group)
                
                # Skip if no weight measurement (required field)
                if 'weight_kg' not in parsed_measurements:
                    continue
                
                # Extract metadata
                raw_date = measurement_group.get("date", 0)
                measurement_id = str(measurement_group.get("grpid", ""))
                
                # Validate weight range (reasonable bounds)
                weight_kg = parsed_measurements['weight_kg']
                if weight_kg < 30 or weight_kg > 300:
                    logger.warning(f"Weight {weight_kg} kg outside reasonable range (30-300 kg)")
                    errors += 1
                    continue
                
                # Standardize timestamp
                timestamp_info = self.timestamp_standardizer.standardize_withings_timestamp(raw_date)
                
                # Build measurement data with all available fields
                measurement_data = {
                    "measurement_id": measurement_id,
                    "weight_kg": weight_kg,
                    "timestamp_utc": timestamp_info["utc_datetime"],
                    "timestamp_user": timestamp_info["user_datetime"],
                    "original_timezone": timestamp_info["original_timezone"],
                    "user_timezone": timestamp_info["user_timezone"],
                    "source_format": "withings_api_historical",
                    "raw_value": None,  # Not applicable for multi-measure parsing
                    "raw_unit": None,   # Not applicable for multi-measure parsing
                }
                
                # Add body composition measurements (provide None for missing values)
                measurement_data['fat_mass_kg'] = parsed_measurements.get('fat_mass_kg')
                measurement_data['fat_free_mass_kg'] = parsed_measurements.get('fat_free_mass_kg')
                measurement_data['muscle_mass_kg'] = parsed_measurements.get('muscle_mass_kg')
                measurement_data['bone_mass_kg'] = parsed_measurements.get('bone_mass_kg')
                measurement_data['body_water_kg'] = parsed_measurements.get('body_water_kg')
                measurement_data['fat_ratio_pct'] = parsed_measurements.get('fat_ratio_pct')
                
                # Store in database
                if self.db.upsert_measurement(measurement_data):
                    successful_stored += 1
                else:
                    errors += 1
                    
            except Exception as e:
                logger.error(f"Error processing measurement: {e}")
                errors += 1
        
        logger.info(f"Chunk {chunk_info}: {successful_stored} stored, {errors} errors")
        return successful_stored, errors
    
    def check_existing_data(self, start_date: str, end_date: str) -> int:
        """
        Check how many measurements already exist for this date range.
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            Number of existing measurements
        """
        try:
            from sqlalchemy import text
            
            query = text("""
                SELECT COUNT(*) as count
                FROM withings_raw_measurements
                WHERE timestamp_user::date BETWEEN :start_date AND :end_date
            """)
            
            with self.db.engine.connect() as conn:
                result = conn.execute(query, {"start_date": start_date, "end_date": end_date}).fetchone()
                return result.count if result else 0
                
        except Exception as e:
            logger.error(f"Failed to check existing data: {e}")
            return 0
    
    def backfill_historical_data(self, start_date: str, end_date: str, chunk_months: int = 6) -> Dict:
        """
        Perform historical data backfill for the specified date range.
        
        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            chunk_months: Number of months per chunk
            
        Returns:
            Dictionary with backfill statistics
        """
        logger.info(f"🔄 Starting historical backfill from {start_date} to {end_date}")
        
        # Initialize progress tracking
        if not self.progress_data.get("start_time"):
            self.progress_data["start_time"] = datetime.now().isoformat()
        
        # Generate date chunks
        chunks = self.chunk_date_ranges(start_date, end_date, chunk_months)
        total_chunks = len(chunks)
        
        logger.info(f"📅 Generated {total_chunks} chunks for processing")
        
        # Process each chunk
        for i, (chunk_start, chunk_end) in enumerate(chunks, 1):
            chunk_info = f"{chunk_start} to {chunk_end}"
            
            # Skip if already completed
            if chunk_info in self.progress_data["completed_chunks"]:
                logger.info(f"⏭️  Skipping completed chunk {i}/{total_chunks}: {chunk_info}")
                continue
            
            logger.info(f"📦 Processing chunk {i}/{total_chunks}: {chunk_info}")
            
            # Check existing data
            existing_count = self.check_existing_data(chunk_start, chunk_end)
            if existing_count > 0:
                logger.info(f"📊 Found {existing_count} existing measurements for this chunk")
            
            # Extract measurements
            measurements = self.extract_chunk_with_pagination(chunk_start, chunk_end)
            
            if not measurements:
                logger.warning(f"⚠️  No measurements found for chunk {chunk_info}")
                self.progress_data["completed_chunks"].append(chunk_info)
                self.progress_data["last_chunk_completed"] = chunk_info
                self._save_progress()
                continue
            
            # Convert and store measurements
            successful_stored, errors = self.convert_and_store_measurements(measurements, chunk_info)
            
            # Update progress
            self.progress_data["completed_chunks"].append(chunk_info)
            self.progress_data["total_measurements_extracted"] += successful_stored
            self.progress_data["total_errors"] += errors
            self.progress_data["last_chunk_completed"] = chunk_info
            self._save_progress()
            
            logger.info(f"✅ Chunk {i}/{total_chunks} complete: {successful_stored} measurements extracted")
            
            # Brief pause between chunks
            time.sleep(2)
        
        # Final statistics
        total_time = datetime.now() - datetime.fromisoformat(self.progress_data["start_time"])
        
        stats = {
            "total_chunks": total_chunks,
            "completed_chunks": len(self.progress_data["completed_chunks"]),
            "total_measurements_extracted": self.progress_data["total_measurements_extracted"],
            "total_errors": self.progress_data["total_errors"],
            "total_time": str(total_time),
            "start_date": start_date,
            "end_date": end_date
        }
        
        logger.info(f"🎉 Backfill complete! {stats}")
        return stats
    
    def get_backfill_status(self) -> Dict:
        """Get current backfill status."""
        return {
            "progress_file": self.progress_file,
            "progress_data": self.progress_data,
            "database_stats": self.db.validate_data_integrity()
        }

def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(description="Withings Historical Data Backfill")
    parser.add_argument("--test-chunk", nargs=2, metavar=("START_DATE", "END_DATE"), 
                       help="Test single chunk extraction")
    parser.add_argument("--full-backfill", nargs=2, metavar=("START_DATE", "END_DATE"),
                       help="Full historical backfill")
    parser.add_argument("--status", action="store_true", help="Show backfill status")
    parser.add_argument("--chunk-months", type=int, default=6, 
                       help="Months per chunk (default: 6)")
    
    args = parser.parse_args()
    
    try:
        backfill = WithingsHistoricalBackfill()
        
        if args.status:
            # Show status
            status = backfill.get_backfill_status()
            print("📊 Withings Historical Backfill Status")
            print("=" * 50)
            print(f"Progress file: {status['progress_file']}")
            print(f"Completed chunks: {len(status['progress_data']['completed_chunks'])}")
            print(f"Total measurements extracted: {status['progress_data']['total_measurements_extracted']}")
            print(f"Total errors: {status['progress_data']['total_errors']}")
            print(f"Last chunk completed: {status['progress_data']['last_chunk_completed']}")
            
            if status['progress_data']['completed_chunks']:
                print("\nCompleted chunks:")
                for chunk in status['progress_data']['completed_chunks']:
                    print(f"  ✅ {chunk}")
            
            return
        
        if args.test_chunk:
            # Test single chunk
            start_date, end_date = args.test_chunk
            print(f"🧪 Testing chunk extraction: {start_date} to {end_date}")
            
            stats = backfill.backfill_historical_data(start_date, end_date, args.chunk_months)
            print(f"\n📊 Test Results:")
            print(f"  Measurements extracted: {stats['total_measurements_extracted']}")
            print(f"  Errors: {stats['total_errors']}")
            print(f"  Time: {stats['total_time']}")
            
        elif args.full_backfill:
            # Full backfill
            start_date, end_date = args.full_backfill
            print(f"🔄 Starting full historical backfill: {start_date} to {end_date}")
            
            stats = backfill.backfill_historical_data(start_date, end_date, args.chunk_months)
            print(f"\n🎉 Backfill Complete!")
            print(f"  Total chunks: {stats['total_chunks']}")
            print(f"  Completed chunks: {stats['completed_chunks']}")
            print(f"  Measurements extracted: {stats['total_measurements_extracted']}")
            print(f"  Errors: {stats['total_errors']}")
            print(f"  Total time: {stats['total_time']}")
            
        else:
            parser.print_help()
            
    except Exception as e:
        logger.error(f"❌ Backfill failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
