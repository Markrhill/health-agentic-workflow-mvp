#!/usr/bin/env python3
"""
Get a fresh Withings access token using the authorization code.

Usage:
  python scripts/get_withings_token.py

Environment variables required:
  WITHINGS_AUTH_CODE
  WITHINGS_CLIENT_ID
  WITHINGS_CLIENT_SECRET
  WITHINGS_REDIRECT_URI
"""

import os
import requests
import json

# Withings API endpoints
WITHINGS_BASE_URL = "https://wbsapi.withings.net"
TOKEN_ENDPOINT = f"{WITHINGS_BASE_URL}/oauth2"

# Alternative endpoints to try
WITHINGS_V2_BASE = "https://wbsapi.withings.net/v2"
TOKEN_ENDPOINT_V2 = f"{WITHINGS_V2_BASE}/oauth2"

def get_env_var(name: str) -> str:
    """Get environment variable or raise error."""
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Environment variable {name} not set")
    return value

def get_access_token():
    """Get access token using authorization code."""
    print("🔑 Getting fresh Withings access token...")
    
    auth_code = get_env_var("WITHINGS_AUTH_CODE")
    client_id = get_env_var("WITHINGS_CLIENT_ID")
    client_secret = get_env_var("WITHINGS_CLIENT_SECRET")
    redirect_uri = get_env_var("WITHINGS_REDIRECT_URI")
    
    data = {
        "action": "requesttoken",
        "grant_type": "authorization_code",
        "code": auth_code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri
    }
    
    # Try both endpoints
    endpoints = [
        ("v1", TOKEN_ENDPOINT),
        ("v2", TOKEN_ENDPOINT_V2)
    ]
    
    for version, endpoint in endpoints:
        print(f"🔄 Trying {version} endpoint: {endpoint}")
        
        try:
            response = requests.post(endpoint, data=data)
            response.raise_for_status()
            
            result = response.json()
            print(f"Response: {json.dumps(result, indent=2)}")
            
            if result.get("status") == 0:
                body = result.get("body", {})
                access_token = body.get("access_token")
                refresh_token = body.get("refresh_token")
                expires_in = body.get("expires_in")
                
                print(f"\n✅ Token exchange successful with {version}!")
                print(f"Access Token: {access_token}")
                print(f"Refresh Token: {refresh_token}")
                print(f"Expires in: {expires_in} seconds")
                
                return access_token, refresh_token
            else:
                print(f"❌ {version} failed: {result}")
                
        except Exception as e:
            print(f"❌ {version} error: {e}")
    
    print("❌ All endpoints failed")
    return None, None

def main():
    print("🔑 Withings Token Exchange")
    print("=" * 40)
    
    try:
        access_token, refresh_token = get_access_token()
        
        if access_token:
            print(f"\n📋 Update your .env file with:")
            print(f"WITHINGS_ACCESS_TOKEN={access_token}")
            if refresh_token:
                print(f"WITHINGS_REFRESH_TOKEN={refresh_token}")
        
    except Exception as e:
        print(f"❌ Failed: {e}")

if __name__ == "__main__":
    main()
