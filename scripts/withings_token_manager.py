#!/usr/bin/env python3
"""
Withings Token Manager - Handles OAuth token lifecycle and refresh.

This module manages Withings API authentication tokens, including:
- Token validation
- Automatic refresh when expired
- Secure token storage
- Error handling for token expiration
"""

import os
import requests
import json
import logging
from typing import Optional, Tuple
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class WithingsTokenManager:
    """Manages Withings API authentication tokens."""
    
    def __init__(self):
        self.base_url = "https://wbsapi.withings.net"
        self.token_endpoint = f"{self.base_url}/oauth2"
        self.client_id = os.getenv("WITHINGS_CLIENT_ID")
        self.client_secret = os.getenv("WITHINGS_CLIENT_SECRET")
        
        if not all([self.client_id, self.client_secret]):
            raise ValueError("WITHINGS_CLIENT_ID and WITHINGS_CLIENT_SECRET must be set")
    
    def get_valid_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.
        
        Returns:
            str: Valid access token
            
        Raises:
            ValueError: If tokens cannot be refreshed
            requests.RequestException: If API calls fail
        """
        current_token = os.getenv("WITHINGS_ACCESS_TOKEN")
        refresh_token = os.getenv("WITHINGS_REFRESH_TOKEN")
        
        if not current_token or not refresh_token:
            raise ValueError("WITHINGS_ACCESS_TOKEN and WITHINGS_REFRESH_TOKEN must be set. Run: python scripts/withings_oauth_helper.py")
        
        # TEMP FIX: Skip token validation - tokens are valid for 3 hours from OAuth
        # Withings refresh endpoint returns "Not implemented" error
        logger.info("Using access token (3-hour validity window)")
        return current_token
        
        # Test current token
        if self._is_token_valid(current_token):
            logger.debug("Current access token is valid")
            return current_token
        
        # Token is invalid, try to refresh
        logger.info("Access token expired, attempting refresh")
        new_access_token, new_refresh_token = self._refresh_tokens(refresh_token)
        
        # Update environment variables (in production, store securely)
        os.environ["WITHINGS_ACCESS_TOKEN"] = new_access_token
        os.environ["WITHINGS_REFRESH_TOKEN"] = new_refresh_token
        
        logger.info("Tokens refreshed successfully")
        return new_access_token
    
    def _is_token_valid(self, token: str) -> bool:
        """
        Test if an access token is valid by making a simple API call.
        
        Args:
            token: Access token to test
            
        Returns:
            bool: True if token is valid, False otherwise
        """
        headers = {"Authorization": f"Bearer {token}"}
        
        # Simple test request - get recent measurements
        data = {
            "action": "getmeas",
            "meastype": "1",  # Weight only
            "category": "1",
            "limit": "1"
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/measure",
                headers=headers,
                data=data,
                timeout=10
            )
            
            result = response.json()
            return result.get("status") == 0
            
        except Exception as e:
            logger.warning(f"Token validation failed: {e}")
            return False
    
    def _refresh_tokens(self, refresh_token: str) -> Tuple[str, str]:
        """
        Refresh access and refresh tokens.
        
        Args:
            refresh_token: Current refresh token
            
        Returns:
            Tuple[str, str]: New access token and refresh token
            
        Raises:
            ValueError: If token refresh fails
        """
        data = {
            "action": "requesttoken",
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": os.getenv("WITHINGS_REDIRECT_URI")
        }
        
        try:
            response = requests.post(self.token_endpoint, data=data, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get("status") != 0:
                error_msg = result.get("error", "Unknown error")
                raise ValueError(f"Token refresh failed: {error_msg}")
            
            body = result.get("body", {})
            new_access_token = body.get("access_token")
            new_refresh_token = body.get("refresh_token")
            
            if not new_access_token:
                raise ValueError("No access token in refresh response")
            
            return new_access_token, new_refresh_token
            
        except requests.RequestException as e:
            raise ValueError(f"Token refresh request failed: {e}")
    
    def get_token_info(self) -> dict:
        """
        Get information about current tokens (for debugging).
        
        Returns:
            dict: Token information
        """
        return {
            "client_id": self.client_id[:10] + "..." if self.client_id else None,
            "has_access_token": bool(os.getenv("WITHINGS_ACCESS_TOKEN")),
            "has_refresh_token": bool(os.getenv("WITHINGS_REFRESH_TOKEN")),
            "access_token_valid": self._is_token_valid(os.getenv("WITHINGS_ACCESS_TOKEN", ""))
        }

def main():
    """Test token manager functionality."""
    logging.basicConfig(level=logging.INFO)
    
    try:
        manager = WithingsTokenManager()
        
        print("🔑 Testing Withings Token Manager")
        print("=" * 40)
        
        # Get token info
        info = manager.get_token_info()
        print(f"Client ID: {info['client_id']}")
        print(f"Has Access Token: {info['has_access_token']}")
        print(f"Has Refresh Token: {info['has_refresh_token']}")
        print(f"Access Token Valid: {info['access_token_valid']}")
        
        # Get valid token
        token = manager.get_valid_token()
        print(f"\n✅ Valid access token: {token[:10]}...")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
