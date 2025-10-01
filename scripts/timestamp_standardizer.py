#!/usr/bin/env python3
"""
Timestamp Standardizer - Converts Withings timestamps to standardized formats.

This module handles timezone conversion and timestamp standardization for Withings data:
- Converts epoch seconds to UTC datetime
- Converts to user's configured timezone (handles DST automatically)
- Preserves original timezone metadata
- Returns both UTC and user local timestamps
"""

import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
import pytz
import logging

logger = logging.getLogger(__name__)

class TimestampStandardizer:
    """Standardizes timestamps from Withings API to user timezone."""
    
    def __init__(self):
        self.user_timezone = os.getenv("USER_TIMEZONE", "America/Los_Angeles")
        self.user_tz = pytz.timezone(self.user_timezone)
        
        logger.info(f"Initialized TimestampStandardizer with user timezone: {self.user_timezone}")
    
    def standardize_withings_timestamp(self, raw_date: int, raw_timezone: str = "UTC") -> Dict[str, str]:
        """
        Convert Withings timestamp to standardized format.
        
        Args:
            raw_date: Epoch timestamp from Withings API
            raw_timezone: Original timezone from Withings (usually UTC)
            
        Returns:
            Dict containing standardized timestamp information
        """
        try:
            # Convert epoch seconds to UTC datetime
            timestamp_utc = datetime.fromtimestamp(raw_date, tz=timezone.utc)
            
            # Convert to user's timezone (handles DST automatically)
            timestamp_user = timestamp_utc.astimezone(self.user_tz)
            
            # Format timestamps
            timestamp_utc_str = timestamp_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            timestamp_user_str = timestamp_user.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
            
            # Get measurement date in user timezone (for daily aggregation)
            measurement_date_user = timestamp_user.strftime("%Y-%m-%d")
            
            return {
                "timestamp_utc": timestamp_utc_str,
                "timestamp_user": timestamp_user_str,
                "original_timezone": raw_timezone,
                "user_timezone": self.user_timezone,
                "measurement_date_user": measurement_date_user,
                "epoch_seconds": raw_date,
                "utc_datetime": timestamp_utc,
                "user_datetime": timestamp_user
            }
            
        except Exception as e:
            logger.error(f"Timestamp standardization failed for {raw_date}: {e}")
            raise ValueError(f"Invalid timestamp: {raw_date}")
    
    def get_timezone_info(self) -> Dict[str, str]:
        """
        Get timezone information for debugging.
        
        Returns:
            Dict containing timezone information
        """
        now_utc = datetime.now(timezone.utc)
        now_user = now_utc.astimezone(self.user_tz)
        
        return {
            "user_timezone": self.user_timezone,
            "current_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "current_user": now_user.strftime("%Y-%m-%dT%H:%M:%S.%f%z"),
            "dst_active": now_user.dst() != timedelta(0),
            "timezone_offset": now_user.strftime("%z")
        }

def main():
    """Test timestamp standardizer functionality."""
    logging.basicConfig(level=logging.INFO)
    
    try:
        standardizer = TimestampStandardizer()
        
        print("🕐 Testing Timestamp Standardizer")
        print("=" * 40)
        
        # Get timezone info
        tz_info = standardizer.get_timezone_info()
        print(f"User Timezone: {tz_info['user_timezone']}")
        print(f"Current UTC: {tz_info['current_utc']}")
        print(f"Current User: {tz_info['current_user']}")
        print(f"DST Active: {tz_info['dst_active']}")
        print(f"Timezone Offset: {tz_info['timezone_offset']}")
        
        # Test with sample Withings timestamp
        sample_timestamp = 1759163784  # From recent Withings data
        standardized = standardizer.standardize_withings_timestamp(sample_timestamp)
        
        print(f"\n📅 Sample Timestamp Conversion:")
        print(f"Epoch: {sample_timestamp}")
        print(f"UTC: {standardized['timestamp_utc']}")
        print(f"User: {standardized['timestamp_user']}")
        print(f"Date: {standardized['measurement_date_user']}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
