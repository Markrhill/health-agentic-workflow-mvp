#!/usr/bin/env python3
"""
Withings Raw Data Extraction - Pulls weight measurements from Withings API.

This script extracts raw weight measurements from Withings API and stores them
in the withings_raw_measurements table with standardized timestamps.

Features:
- Automated token management
- Incremental sync (only new data)
- Proper unit conversion
- Standardized timestamps
- Error handling and retry logic
- Comprehensive logging
"""

import os
import sys
import requests
import json
import logging
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
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

class WithingsDataExtractor:
    """Extracts raw weight data from Withings API."""
    
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
        
    def extract_weight_measurements(self, limit: int = 100, lastupdate: Optional[int] = None) -> List[Dict]:
        """
        Extract weight measurements from Withings API.
        
        Args:
            limit: Maximum number of measurements to fetch
            lastupdate: Unix timestamp for incremental sync
            
        Returns:
            List[Dict]: Raw measurement data from API
        """
        access_token = self.token_manager.get_valid_token()
        
        headers = {"Authorization": f"Bearer {access_token}"}
        
        data = {
            "action": "getmeas",
            "meastype": "1",  # Weight only
            "category": "1",  # Real measurements only
            "limit": str(limit)
        }
        
        if lastupdate:
            data["lastupdate"] = str(lastupdate)
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Fetching weight measurements (attempt {attempt + 1}/{self.max_retries})")
                
                response = requests.post(
                    self.measure_endpoint,
                    headers=headers,
                    data=data,
                    timeout=self.request_timeout
                )
                
                response.raise_for_status()
                result = response.json()
                
                if result.get("status") != 0:
                    error_msg = result.get("error", "Unknown error")
                    logger.error(f"API error: {error_msg}")
                    
                    # Handle specific error cases
                    if "invalid_token" in error_msg.lower():
                        logger.info("Token invalid, refreshing...")
                        self.token_manager.get_valid_token()  # This will refresh
                        continue
                    
                    raise ValueError(f"Withings API error: {error_msg}")
                
                body = result.get("body", {})
                measuregrps = body.get("measuregrps", [])
                
                logger.info(f"✅ Fetched {len(measuregrps)} measurement groups")
                return measuregrps
                
            except requests.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))  # Exponential backoff
                    continue
                else:
                    raise
        
        raise Exception("Max retries exceeded")
    
    def convert_weight_measurement(self, measurement_group: Dict) -> Optional[Dict]:
        """
        Convert a Withings measurement group to standardized format.
        
        Args:
            measurement_group: Raw measurement group from API
            
        Returns:
            Dict: Standardized measurement data, or None if invalid
        """
        try:
            # Extract weight measurement (type 1)
            weight_measure = None
            for measure in measurement_group.get("measures", []):
                if measure.get("type") == 1:  # Weight
                    weight_measure = measure
                    break
            
            if not weight_measure:
                logger.warning("No weight measurement found in group")
                return None
            
            # Extract data
            raw_value = weight_measure.get("value", 0)
            raw_unit = weight_measure.get("unit", 0)
            raw_date = measurement_group.get("date", 0)
            measurement_id = str(measurement_group.get("grpid", ""))
            
            # Convert units based on Withings API documentation
            if raw_unit == -3:  # Value is in grams
                weight_kg = float(raw_value / 1000)
            elif raw_unit == -2:  # Value is in 0.01 kg units
                weight_kg = float(raw_value / 100)
            else:  # Assume already in kg for unknown units
                weight_kg = float(raw_value)
            
            # Validate weight range (reasonable bounds)
            if weight_kg < 30 or weight_kg > 300:
                logger.warning(f"Weight {weight_kg} kg outside reasonable range (30-300 kg)")
                return None
            
            # Standardize timestamp
            timestamp_info = self.timestamp_standardizer.standardize_withings_timestamp(raw_date)
            
            return {
                "measurement_id": measurement_id,
                "weight_kg": weight_kg,
                "timestamp_utc": timestamp_info["utc_datetime"],
                "timestamp_user": timestamp_info["user_datetime"],
                "original_timezone": timestamp_info["original_timezone"],
                "user_timezone": timestamp_info["user_timezone"],
                "source_format": "withings_api",
                "raw_value": raw_value,
                "raw_unit": raw_unit
            }
            
        except Exception as e:
            logger.error(f"Failed to convert measurement: {e}")
            return None
    
    def sync_measurements(self, limit: int = 100, incremental: bool = True) -> Dict[str, int]:
        """
        Sync measurements from Withings API to database.
        
        Args:
            limit: Maximum number of measurements to fetch
            incremental: Whether to use incremental sync
            
        Returns:
            Dict: Sync statistics
        """
        logger.info("🔄 Starting Withings measurement sync")
        
        # Get latest timestamp for incremental sync
        lastupdate = None
        if incremental:
            lastupdate = self.db.get_latest_measurement_timestamp()
            if lastupdate:
                # Convert to Unix timestamp for API
                lastupdate = int(lastupdate.timestamp())
                logger.info(f"Incremental sync from {datetime.fromtimestamp(lastupdate)}")
            else:
                logger.info("No previous data found, doing full sync")
        
        # Extract measurements
        raw_measurements = self.extract_weight_measurements(limit=limit, lastupdate=lastupdate)
        
        # Convert and store measurements
        stats = {
            "total_fetched": len(raw_measurements),
            "successfully_converted": 0,
            "successfully_stored": 0,
            "errors": 0
        }
        
        for measurement_group in raw_measurements:
            try:
                # Convert measurement
                converted = self.convert_weight_measurement(measurement_group)
                if not converted:
                    stats["errors"] += 1
                    continue
                
                stats["successfully_converted"] += 1
                
                # Store in database
                if self.db.upsert_measurement(converted):
                    stats["successfully_stored"] += 1
                else:
                    stats["errors"] += 1
                    
            except Exception as e:
                logger.error(f"Error processing measurement: {e}")
                stats["errors"] += 1
        
        logger.info(f"✅ Sync complete: {stats}")
        return stats
    
    def get_sync_status(self) -> Dict:
        """
        Get current sync status and statistics.
        
        Returns:
            Dict: Sync status information
        """
        try:
            count = self.db.get_measurement_count()
            latest_timestamp = self.db.get_latest_measurement_timestamp()
            recent_measurements = self.db.get_recent_measurements(5)
            
            return {
                "total_measurements": count,
                "latest_measurement": latest_timestamp.isoformat() if latest_timestamp else None,
                "recent_measurements": recent_measurements,
                "token_status": self.token_manager.get_token_info(),
                "timezone_info": self.timestamp_standardizer.get_timezone_info()
            }
            
        except Exception as e:
            logger.error(f"Failed to get sync status: {e}")
            return {"error": str(e)}

def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(description="Extract Withings weight measurements")
    parser.add_argument("--limit", type=int, default=100, help="Maximum measurements to fetch")
    parser.add_argument("--full-sync", action="store_true", help="Force full sync (ignore incremental)")
    parser.add_argument("--status", action="store_true", help="Show sync status only")
    parser.add_argument("--test", action="store_true", help="Test mode (fetch 5 measurements)")
    
    args = parser.parse_args()
    
    try:
        extractor = WithingsDataExtractor()
        
        if args.status:
            # Show status only
            status = extractor.get_sync_status()
            print("📊 Withings Sync Status")
            print("=" * 30)
            print(f"Total measurements: {status.get('total_measurements', 'N/A')}")
            print(f"Latest measurement: {status.get('latest_measurement', 'N/A')}")
            print(f"User timezone: {status.get('timezone_info', {}).get('user_timezone', 'N/A')}")
            
            if status.get('recent_measurements'):
                print("\nRecent measurements:")
                for m in status['recent_measurements'][:3]:
                    print(f"  {m['weight_kg']} kg at {m['timestamp_user']}")
            
            return
        
        # Perform sync
        limit = 5 if args.test else args.limit
        incremental = not args.full_sync
        
        print("🔄 Withings Data Extraction")
        print("=" * 40)
        
        stats = extractor.sync_measurements(limit=limit, incremental=incremental)
        
        print(f"\n📊 Sync Results:")
        print(f"  Total fetched: {stats['total_fetched']}")
        print(f"  Successfully converted: {stats['successfully_converted']}")
        print(f"  Successfully stored: {stats['successfully_stored']}")
        print(f"  Errors: {stats['errors']}")
        
        if stats['errors'] > 0:
            print(f"\n⚠️  {stats['errors']} errors occurred during sync")
            sys.exit(1)
        else:
            print("\n✅ Sync completed successfully")
            
    except Exception as e:
        logger.error(f"❌ Extraction failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
