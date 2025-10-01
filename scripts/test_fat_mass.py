#!/usr/bin/env python3
"""
Test specifically for Withings fat mass data (measure type 8).
This is the CRITICAL data needed for your health model.
"""

import requests
import json
import os
from datetime import datetime

def test_fat_mass_data():
    """Test for fat mass measurements (type 8)."""
    
    access_token = os.getenv("WITHINGS_ACCESS_TOKEN")
    if not access_token:
        print("❌ WITHINGS_ACCESS_TOKEN not found in environment")
        return False
    
    url = "https://wbsapi.withings.net/measure"
    
    # Test different measurement types
    test_cases = [
        {"name": "Fat Mass Only", "meastype": "8"},
        {"name": "All Body Composition", "meastype": "8,9,76,77,88"},  # Fat, muscle, bone, water, etc
        {"name": "Weight + Fat Mass", "meastype": "1,8"},
        {"name": "All Available", "meastype": "1,8,9,76,77,88,11,12"}
    ]
    
    for test_case in test_cases:
        print(f"\n🧪 Testing: {test_case['name']}")
        print(f"Measure types: {test_case['meastype']}")
        
        data = {
            "action": "getmeas",
            "meastype": test_case['meastype'],
            "category": "1",  # Real measurements only
            "limit": "10"
        }
        
        headers = {"Authorization": f"Bearer {access_token}"}
        
        try:
            response = requests.post(url, data=data, headers=headers)
            result = response.json()
            
            if result.get("status") == 0:
                body = result.get("body", {})
                measuregrps = body.get("measuregrps", [])
                
                print(f"✅ Found {len(measuregrps)} measurement groups")
                
                # Analyze what measure types we actually have
                found_types = {}
                for grp in measuregrps:
                    for measure in grp.get("measures", []):
                        mtype = measure.get("type")
                        if mtype not in found_types:
                            found_types[mtype] = 0
                        found_types[mtype] += 1
                
                if found_types:
                    print("📊 Measure types found:")
                    type_names = {
                        1: "Weight", 8: "Fat Mass", 9: "Muscle Mass", 
                        76: "Bone Mass", 77: "Water %", 88: "Fat %",
                        11: "Pulse", 12: "CO2"
                    }
                    
                    for mtype, count in sorted(found_types.items()):
                        name = type_names.get(mtype, f"Unknown ({mtype})")
                        print(f"   Type {mtype} ({name}): {count} measurements")
                        
                        # Show sample values for fat mass
                        if mtype == 8:  # Fat mass
                            print("   🎯 FAT MASS SAMPLES:")
                            sample_count = 0
                            for grp in measuregrps:
                                if sample_count >= 3:
                                    break
                                for measure in grp.get("measures", []):
                                    if measure.get("type") == 8:
                                        value = measure.get("value", 0)
                                        unit = measure.get("unit", 0)
                                        # Withings unit conversion: -2 means kg, -3 means grams
                                        if unit == -2:  # kg
                                            kg_value = value / 100  # Convert from 0.01 kg to kg
                                        elif unit == -3:  # grams
                                            kg_value = value / 1000  # Convert grams to kg
                                        else:
                                            kg_value = value  # Assume already in kg
                                        date = datetime.fromtimestamp(grp.get("date", 0))
                                        print(f"      {date.strftime('%Y-%m-%d')}: {kg_value:.1f} kg")
                                        sample_count += 1
                                        if sample_count >= 3:
                                            break
                else:
                    print("❌ No measurements found")
                    
            else:
                print(f"❌ API Error: {result}")
                
        except Exception as e:
            print(f"❌ Request failed: {e}")
    
    return True

def check_scale_type():
    """Check what type of Withings scale the user has."""
    print("\n🔍 WITHINGS SCALE COMPATIBILITY CHECK")
    print("=" * 50)
    print("Your scale must support body composition for fat mass data.")
    print()
    print("Withings scales with body composition:")
    print("✅ Body+ (WBS05)")
    print("✅ Body Comp (WBS10) ")
    print("✅ Body Scan (WBS11)")
    print()
    print("Scales WITHOUT body composition:")
    print("❌ Body (WBS01) - weight only")
    print("❌ Go (WHA06) - weight only")
    print()
    print("If you only see weight measurements (type 1), you may have")
    print("a weight-only scale that cannot measure fat mass.")

def main():
    print("🎯 WITHINGS FAT MASS DATA TEST")
    print("=" * 40)
    print("Testing for measure type 8 (fat mass) - CRITICAL for health model")
    print()
    
    if not test_fat_mass_data():
        return
    
    check_scale_type()
    
    print("\n" + "=" * 50)
    print("🎯 KEY QUESTION: Did you see 'Type 8 (Fat Mass)' measurements?")
    print()
    print("✅ YES → Proceed with ETL integration") 
    print("❌ NO  → Need body composition scale or different data source")

if __name__ == "__main__":
    main()
