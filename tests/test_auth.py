"""
Script to test admin authentication flow.
1. Generate a valid TOTP code for the test admin
2. Authenticate via /api/auth/verify_totp to get JWT
3. Use JWT to access a protected admin endpoint
"""

import sys
import os
import asyncio
import httpx
import pyotp

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Test credentials (this will obviously not work, change it to yours. If making changed to repo, please don't override it with your credentials)
USERNAME = "admin"
PASSWORD = "Password"
# The secret from the CLI output
TOTP_SECRET = "EXAMPLE"
BASE_URL = "http://localhost:8001"

async def test_auth_flow():
    print(f"Testing authentication flow for user: {USERNAME}")
    
    # 1. Generate TOTP code
    totp = pyotp.TOTP(TOTP_SECRET)
    totp_code = totp.now()
    print(f"Generated TOTP code: {totp_code}")
    
    async with httpx.AsyncClient() as client:
        # 2. Authenticate
        print("Authenticating...")
        try:
            response = await client.post(
                f"{BASE_URL}/api/auth/verify_totp",
                json={
                    "username": USERNAME,
                    "password": PASSWORD,
                    "totp_code": totp_code
                }
            )
            
            print(f"Request URL: {response.request.url}")
            print(f"Request Method: {response.request.method}")
            print(f"Response Status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"❌ Authentication failed: {response.text}")
                return False
                
            data = response.json()
            if not data["success"]:
                print(f"❌ Authentication failed: {data['message']}")
                return False
                
            token = data["data"]["access_token"]
            print(f"✅ Authentication successful! Got token: {token[:20]}...")
            
        except Exception as e:
            print(f"❌ Error connecting to server: {e}")
            print("Is the server running?")
            return False
            
        # 3. Access protected endpoint
        print("Accessing protected admin endpoint...")
        try:
            # We use list_votecode_amount as it's a safe GET request
            response = await client.get(
                f"{BASE_URL}/api/admin/list_votecode_amount",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code == 200:
                print(f"✅ Protected endpoint access successful!")
                print(f"Response: {response.json()}")
                return True
            else:
                print(f"❌ Protected endpoint access failed: {response.status_code} {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Error accessing protected endpoint: {e}")
            return False

if __name__ == "__main__":
    asyncio.run(test_auth_flow())
