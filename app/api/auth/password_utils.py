"""
Password hashing and verification utilities using bcrypt.
Uses the bcrypt library directly to avoid passlib maintenance issues.
"""

import bcrypt


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
        password: Plain text password to hash
        
    Returns:
        Hashed password string (includes salt)
    """
    # bcrypt requires bytes, so we encode the password
    pwd_bytes = password.encode('utf-8')
    # Generate salt and hash
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    # Return as string for storage
    return hashed.decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.
    
    Args:
        plain_password: Plain text password to verify
        hashed_password: Bcrypt hash to verify against
        
    Returns:
        True if password matches, False otherwise
    """
    # Convert strings to bytes for bcrypt
    pwd_bytes = plain_password.encode('utf-8')
    hashed_bytes = hashed_password.encode('utf-8')
    
    try:
        return bcrypt.checkpw(pwd_bytes, hashed_bytes)
    except ValueError:
        # Handle invalid hash formats
        return False
