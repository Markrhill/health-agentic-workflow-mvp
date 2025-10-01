#!/usr/bin/env python3
"""
Withings Token Refresh - Automated token refresh for Withings API.

This script automatically refreshes expired Withings API tokens and updates
environment variables, eliminating the need for manual re-authentication.

Usage:
    python scripts/withings_token_refresh.py
"""

import os
import sys
import requests
import json
from typing import Dict, Optional

class WithingsTokenRefresher:
    """Automatically refreshes Withings API tokens."""
    
    def __init__(self):
        self.client_id = os.getenv("WITHINGS_CLIENT_ID")
        self.client_secret = os.getenv("WITHINGS_CLIENT_SECRET")
        self.refresh_token = os.getenv("WITHINGS_REFRESH_TOKEN")
        self.redirect_uri = os.getenv("WITHINGS_REDIRECT_URI", "https://developer.withings.com/api-explorer")
        
        if not all([self.client_id, self.client_secret, self.refresh_token]):
            raise ValueError("WITHINGS_CLIENT_ID, WITHINGS_CLIENT_SECRET, and WITHINGS_REFRESH_TOKEN must be set")
    
    def refresh_tokens(self) -> Optional[Dict]:
        """Refresh access and refresh tokens."""
        data = {
            "action": "requesttoken",
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        
        try:
            response = requests.post("https://wbsapi.withings.net/v2/oauth2", data=data)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("status") == 0:
                body = result.get("body", {})
                return {
                    "access_token": body.get("access_token"),
                    "refresh_token": body.get("refresh_token"),
                    "expires_in": body.get("expires_in"),
                    "scope": body.get("scope")
                }
            else:
                print(f"❌ Token refresh failed: {result.get('error', 'Unknown error')}")
                return None
                
        except requests.RequestException as e:
            print(f"❌ Token refresh request failed: {e}")
            return None
    
    def update_environment(self, tokens: Dict):
        """Update environment variables with new tokens."""
        os.environ["WITHINGS_ACCESS_TOKEN"] = tokens["access_token"]
        os.environ["WITHINGS_REFRESH_TOKEN"] = tokens["refresh_token"]
        
        # Also update .env file if it exists
        env_file = ".env"
        if os.path.exists(env_file):
            env_vars = {}
            with open(env_file, 'r') as f:
                for line in f:
                    if '=' in line and not line.strip().startswith('#'):
                        key, value = line.strip().split('=', 1)
                        env_vars[key] = value
            
            env_vars["WITHINGS_ACCESS_TOKEN"] = tokens["access_token"]
            env_vars["WITHINGS_REFRESH_TOKEN"] = tokens["refresh_token"]
            
            with open(env_file, 'w') as f:
                for key, value in env_vars.items():
                    f.write(f"{key}={value}\n")
            
            print(f"✅ Updated {env_file} with new tokens")
    
    def run_refresh(self):
        """Run the token refresh process."""
        print("🔄 Refreshing Withings API tokens...")
        
        tokens = self.refresh_tokens()
        
        if not tokens:
            print("❌ Token refresh failed - you may need to re-authenticate")
            print("   Run: python scripts/withings_oauth_helper.py")
            return False
        
        print("✅ Successfully refreshed tokens:")
        print(f"   Access Token: {tokens['access_token'][:20]}...")
        print(f"   Refresh Token: {tokens['refresh_token'][:20]}...")
        print(f"   Expires In: {tokens['expires_in']} seconds")
        
        self.update_environment(tokens)
        
        print("\n🎉 Token refresh completed successfully!")
        return True

def main():
    """Main CLI interface."""
    try:
        refresher = WithingsTokenRefresher()
        success = refresher.run_refresh()
        
        if success:
            print("\n🧪 Testing API connection...")
            os.system("python scripts/test_withings_api.py")
        else:
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Token refresh failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
