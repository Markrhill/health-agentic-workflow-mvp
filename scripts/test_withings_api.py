#!/usr/bin/env python3
"""
Test Withings API connectivity and fetch recent body composition data.

Usage:
  python scripts/test_withings_api.py

Environment variables required:
  WITHINGS_ACCESS_TOKEN
  WITHINGS_REFRESH_TOKEN
  WITHINGS_CLIENT_ID
  WITHINGS_CLIENT_SECRET
  WITHINGS_USER_ID
"""

import os
import requests
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Withings API endpoints
WITHINGS_BASE_URL = "https://wbsapi.withings.net"
MEASUREMENTS_ENDPOINT = f"{WITHINGS_BASE_URL}/measure"
REFRESH_TOKEN_ENDPOINT = f"{WITHINGS_BASE_URL}/oauth2"
USER_ENDPOINT = f"{WITHINGS_BASE_URL}/user"

def get_env_var(name: str) -> str:
    """Get environment variable or raise error."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Environment variable {name} not set")
    return value

def refresh_access_token() -> Optional[str]:
    """Refresh the access token using the refresh token."""
    print("🔄 Attempting to refresh access token...")
    
    refresh_token = get_env_var("WITHINGS_REFRESH_TOKEN")
    client_id = get_env_var("WITHINGS_CLIENT_ID")
    client_secret = get_env_var("WITHINGS_CLIENT_SECRET")
    
    data = {
        "action": "requesttoken",
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret
    }
    
    try:
        response = requests.post(REFRESH_TOKEN_ENDPOINT, data=data)
        response.raise_for_status()
        
        result = response.json()
        if result.get("status") == 0:
            new_access_token = result["body"]["access_token"]
            print(f"✅ Access token refreshed successfully")
            return new_access_token
        else:
            print(f"❌ Token refresh failed: {result}")
            return None
            
    except Exception as e:
        print(f"❌ Token refresh error: {e}")
        return None

def test_api_connection(access_token: str) -> bool:
    """Test basic API connectivity."""
    print("🔗 Testing API connection...")
    
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    # Test with measurements endpoint (POST request with action parameter)
    data = {
        "action": "getmeas",
        "startdate": int((datetime.now() - timedelta(days=1)).timestamp()),
        "enddate": int(datetime.now().timestamp())
    }
    
    try:
        response = requests.post(MEASUREMENTS_ENDPOINT, headers=headers, data=data)
        response.raise_for_status()
        
        result = response.json()
        if result.get("status") == 0:
            print("✅ API connection successful")
            return True
        else:
            print(f"❌ API error: {result}")
            return False
            
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

def fetch_recent_measurements(access_token: str, days_back: int = 7) -> Optional[List[Dict]]:
    """Fetch recent body composition measurements."""
    print(f"📊 Fetching measurements from last {days_back} days...")
    
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    
    # Calculate date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    params = {
        "action": "getmeas",
        "startdate": int(start_date.timestamp()),
        "enddate": int(end_date.timestamp()),
        "meastype": "1,5,6,8,76,77,88"  # All body composition measurements
    }
    
    try:
        response = requests.get(MEASUREMENTS_ENDPOINT, headers=headers, params=params)
        response.raise_for_status()
        
        result = response.json()
        if result.get("status") == 0:
            measurements = result.get("body", {}).get("measuregrps", [])
            print(f"✅ Retrieved {len(measurements)} measurement groups")
            return measurements
        else:
            print(f"❌ Measurements fetch failed: {result}")
            return None
            
    except Exception as e:
        print(f"❌ Measurements fetch error: {e}")
        return None

def parse_measurement(measurement: Dict) -> Dict:
    """Parse a Withings measurement into our format."""
    measured_at = datetime.fromtimestamp(measurement["date"])
    
    # Parse individual measurements
    parsed = {
        "measured_at": measured_at,
        "weight_kg": None,
        "fat_mass_kg": None,
        "fat_free_mass_kg": None,
        "muscle_mass_kg": None,
        "bone_mass_kg": None,
        "body_water_kg": None,
        "fat_ratio_pct": None
    }
    
    for measure in measurement.get("measures", []):
        # Withings stores values in different units based on the unit field
        # unit: -3 means kg, 0 means kg, 1 means lb, etc.
        if measure["unit"] == -3:  # kg
            value_kg = measure["value"] / 1000  # Convert from grams to kg
        elif measure["unit"] == 0:  # kg
            value_kg = measure["value"]
        elif measure["unit"] == 1:  # lb
            value_kg = measure["value"] * 0.453592  # Convert lb to kg
        else:
            value_kg = measure["value"]  # Assume kg for unknown units
        
        if measure["type"] == 1:  # Weight
            parsed["weight_kg"] = value_kg
        elif measure["type"] == 5:  # Fat-free mass
            parsed["fat_free_mass_kg"] = value_kg
        elif measure["type"] == 6:  # Fat ratio (percentage)
            parsed["fat_ratio_pct"] = value_kg
        elif measure["type"] == 8:  # Fat mass
            parsed["fat_mass_kg"] = value_kg
        elif measure["type"] == 76:  # Muscle mass
            parsed["muscle_mass_kg"] = value_kg
        elif measure["type"] == 77:  # Body water
            parsed["body_water_kg"] = value_kg
        elif measure["type"] == 88:  # Bone mass
            parsed["bone_mass_kg"] = value_kg
    
    return parsed

def main():
    print("🧪 Testing Withings API Integration")
    print("=" * 50)
    
    try:
        # Get current access token
        access_token = get_env_var("WITHINGS_ACCESS_TOKEN")
        print(f"📋 Using access token: {access_token[:10]}...")
        
        # Test connection
        if not test_api_connection(access_token):
            print("🔄 Connection failed, trying to refresh token...")
            new_token = refresh_access_token()
            if new_token:
                access_token = new_token
                if not test_api_connection(access_token):
                    print("❌ Still can't connect after token refresh")
                    return
            else:
                print("❌ Token refresh failed")
                return
        
        # Fetch recent measurements
        measurements = fetch_recent_measurements(access_token, days_back=7)
        if not measurements:
            print("❌ No measurements retrieved")
            return
        
        # Parse and display measurements
        print("\n📈 Recent Body Composition Data:")
        print("-" * 50)
        
        for i, measurement in enumerate(measurements[:5]):  # Show last 5
            parsed = parse_measurement(measurement)
            print(f"\nMeasurement {i+1}:")
            print(f"  Date: {parsed['measured_at'].strftime('%Y-%m-%d %H:%M')}")
            if parsed['weight_kg']:
                print(f"  Weight: {parsed['weight_kg']:.1f} kg ({parsed['weight_kg']*2.20462:.1f} lbs)")
            if parsed['fat_mass_kg']:
                print(f"  Fat Mass: {parsed['fat_mass_kg']:.1f} kg ({parsed['fat_mass_kg']*2.20462:.1f} lbs)")
            if parsed['muscle_mass_kg']:
                print(f"  Muscle Mass: {parsed['muscle_mass_kg']:.1f} kg ({parsed['muscle_mass_kg']*2.20462:.1f} lbs)")
        
        print(f"\n✅ Withings API test completed successfully!")
        print(f"📊 Total measurements available: {len(measurements)}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    main()
