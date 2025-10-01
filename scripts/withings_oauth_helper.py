#!/usr/bin/env python3
"""
Withings OAuth Helper - Semi-automated OAuth flow for Withings API.

This script automates the OAuth token exchange process by:
1. Opening the authorization URL in the browser
2. Starting a local web server to catch the redirect
3. Automatically exchanging the authorization code for tokens
4. Updating environment variables

Usage:
    python scripts/withings_oauth_helper.py
"""

import os
import sys
import webbrowser
import http.server
import socketserver
import urllib.parse
import requests
import json
from typing import Dict, Optional

class WithingsOAuthHelper:
    """Handles Withings OAuth flow with minimal user interaction."""
    
    def __init__(self):
        self.client_id = os.getenv("WITHINGS_CLIENT_ID")
        self.client_secret = os.getenv("WITHINGS_CLIENT_SECRET")
        self.redirect_uri = os.getenv("WITHINGS_REDIRECT_URI", "https://developer.withings.com/api-explorer")
        
        if not all([self.client_id, self.client_secret]):
            raise ValueError("WITHINGS_CLIENT_ID and WITHINGS_CLIENT_SECRET must be set")
    
    def get_authorization_url(self) -> str:
        """Generate the Withings authorization URL."""
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": "user.metrics",
            "state": "withings_auth"
        }
        
        base_url = "https://account.withings.com/oauth2_user/authorize2"
        query_string = urllib.parse.urlencode(params)
        return f"{base_url}?{query_string}"
    
    def start_callback_server(self) -> str:
        """Start a local web server to catch the OAuth redirect."""
        class CallbackHandler(http.server.BaseHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                self.oauth_helper = kwargs.pop('oauth_helper')
                super().__init__(*args, **kwargs)
            
            def do_GET(self):
                if self.path.startswith('/callback'):
                    # Parse the callback URL
                    parsed = urllib.parse.urlparse(self.path)
                    query_params = urllib.parse.parse_qs(parsed.query)
                    
                    code = query_params.get('code', [None])[0]
                    state = query_params.get('state', [None])[0]
                    
                    if code and state == 'withings_auth':
                        # Send success response
                        self.send_response(200)
                        self.send_header('Content-type', 'text/html')
                        self.end_headers()
                        self.wfile.write(b'''
                        <html>
                        <body>
                        <h1>Authorization Successful!</h1>
                        <p>You can close this window and return to the terminal.</p>
                        <script>window.close();</script>
                        </body>
                        </html>
                        ''')
                        
                        # Store the authorization code
                        self.oauth_helper.auth_code = code
                        self.server.shutdown()
                    else:
                        # Send error response
                        self.send_response(400)
                        self.send_header('Content-type', 'text/html')
                        self.end_headers()
                        self.wfile.write(b'<html><body><h1>Authorization Failed</h1></body></html>')
                        self.server.shutdown()
            
            def log_message(self, format, *args):
                pass  # Suppress server logs
        
        # Create server with custom handler
        handler = type('Handler', (CallbackHandler,), {'oauth_helper': self})
        
        with socketserver.TCPServer(("", self.redirect_port), handler) as httpd:
            print(f"🌐 Started callback server on port {self.redirect_port}")
            print("⏳ Waiting for authorization callback...")
            httpd.timeout = 300  # 5 minute timeout
            httpd.handle_request()
        
        return getattr(self, 'auth_code', None)
    
    def exchange_code_for_tokens(self, auth_code: str) -> Optional[Dict]:
        """Exchange authorization code for access and refresh tokens."""
        data = {
            "action": "requesttoken",
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": auth_code,
            "redirect_uri": self.redirect_uri
        }
        
        try:
            response = requests.post("https://wbsapi.withings.net/oauth2", data=data)
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
                print(f"❌ Token exchange failed: {result.get('error', 'Unknown error')}")
                return None
                
        except requests.RequestException as e:
            print(f"❌ Token exchange request failed: {e}")
            return None
    
    def update_environment_file(self, tokens: Dict):
        """Update .env file with new tokens."""
        env_file = ".env"
        
        # Read existing .env file
        env_vars = {}
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                for line in f:
                    if '=' in line and not line.strip().startswith('#'):
                        key, value = line.strip().split('=', 1)
                        env_vars[key] = value
        
        # Update with new tokens
        env_vars["WITHINGS_ACCESS_TOKEN"] = tokens["access_token"]
        env_vars["WITHINGS_REFRESH_TOKEN"] = tokens["refresh_token"]
        
        # Write back to .env file
        with open(env_file, 'w') as f:
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")
        
        print(f"✅ Updated {env_file} with new tokens")
    
    def run_oauth_flow(self):
        """Run the complete OAuth flow."""
        print("🔐 Withings OAuth Helper")
        print("=" * 50)
        
        # Step 1: Open authorization URL
        auth_url = self.get_authorization_url()
        print(f"🌐 Opening authorization URL in browser...")
        print(f"   {auth_url}")
        
        webbrowser.open(auth_url)
        
        # Step 2: Get authorization code manually
        print(f"\n📋 After authorizing, you'll be redirected to your callback URL:")
        print(f"   {self.redirect_uri}")
        print("\nYour callback endpoint should display the authorization code.")
        print("Please copy the AUTHORIZATION_CODE and paste it below:")
        
        auth_code = input("Authorization code: ").strip()
        
        if not auth_code:
            print("❌ No authorization code provided")
            return False
        
        print(f"✅ Received authorization code: {auth_code[:10]}...")
        
        # Step 3: Exchange code for tokens
        print("🔄 Exchanging authorization code for tokens...")
        tokens = self.exchange_code_for_tokens(auth_code)
        
        if not tokens:
            print("❌ Token exchange failed")
            return False
        
        print("✅ Successfully obtained tokens:")
        print(f"   Access Token: {tokens['access_token'][:20]}...")
        print(f"   Refresh Token: {tokens['refresh_token'][:20]}...")
        print(f"   Expires In: {tokens['expires_in']} seconds")
        
        # Step 4: Update environment file
        self.update_environment_file(tokens)
        
        # Step 5: Update current environment
        os.environ["WITHINGS_ACCESS_TOKEN"] = tokens["access_token"]
        os.environ["WITHINGS_REFRESH_TOKEN"] = tokens["refresh_token"]
        
        print("\n🎉 OAuth flow completed successfully!")
        print("You can now run the Withings API scripts.")
        
        return True

def main():
    """Main CLI interface."""
    try:
        helper = WithingsOAuthHelper()
        success = helper.run_oauth_flow()
        
        if success:
            print("\n🧪 Testing API connection...")
            os.system("python scripts/test_withings_api.py")
        else:
            print("\n❌ OAuth flow failed")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ OAuth helper failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
