"""
CLI tool to create admin accounts with TOTP secrets.
Usage: python -m app.cli.create_admin --username <username> --password <password>
"""

import asyncio
import argparse
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database.models import get_session, Admins
from api.auth.password_utils import hash_password
from api.auth.totp_utils import generate_totp_secret, get_totp_uri
from sqlalchemy import select


async def create_admin(username: str, password: str):
    """
    Create a new admin account with TOTP 2FA.
    
    Args:
        username: Username for the admin account
        password: Password for the admin account
    """
    async with get_session() as session:
        # Check if admin already exists
        result = await session.execute(
            select(Admins).where(Admins.username == username)
        )
        existing_admin = result.scalars().first()
        
        if existing_admin:
            print(f"❌ Error: Admin with username '{username}' already exists!")
            return False
        
        # Generate TOTP secret
        totp_secret = generate_totp_secret()
        
        # Hash password
        password_hash = hash_password(password)
        
        # Create admin
        admin = Admins(
            username=username,
            password_hash=password_hash,
            totp_secret=totp_secret
        )
        
        session.add(admin)
        await session.commit()
        
        # Get TOTP URI for QR code
        totp_uri = get_totp_uri(username, totp_secret)
        
        print("\n" + "="*80)
        print("✅ Admin account created successfully!")
        print("="*80)
        print(f"\n👤 Username: {username}")
        print(f"🔐 Password: [set by you]")
        print(f"\n📱 TOTP Secret (for Google Authenticator):\n")
        print(f"   {totp_secret}")
        print(f"\n🔗 TOTP URI (scan this QR code with Google Authenticator):\n")
        print(f"   {totp_uri}")
        print("\n" + "="*80)
        print("\n📋 Instructions:")
        print("   1. Open Google Authenticator (or compatible TOTP app)")
        print("   2. Add a new account by scanning QR code or entering secret manually")
        print("   3. Use the 6-digit code from the app to authenticate")
        print("\n💡 To generate a QR code, you can use online tools like:")
        print("   https://www.qr-code-generator.com/")
        print("   (Enter the TOTP URI above as the data)")
        print("="*80 + "\n")
        
        return True


def main():
    """Main entry point for the CLI tool."""
    parser = argparse.ArgumentParser(
        description="Create an admin account with TOTP 2FA for the voting system"
    )
    parser.add_argument(
        "--username",
        required=True,
        help="Username for the admin account"
    )
    parser.add_argument(
        "--password",
        required=True,
        help="Password for the admin account"
    )
    
    args = parser.parse_args()
    
    # Validate inputs
    if len(args.username) < 3:
        print("❌ Error: Username must be at least 3 characters long")
        sys.exit(1)
    
    if len(args.password) < 8:
        print("❌ Error: Password must be at least 8 characters long")
        sys.exit(1)
    
    # Create admin
    success = asyncio.run(create_admin(args.username, args.password))
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
