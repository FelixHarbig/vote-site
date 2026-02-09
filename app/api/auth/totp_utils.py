"""
TOTP (Time-based One-Time Password) utilities for 2FA.
"""

import pyotp


def generate_totp_secret() -> str:
    """
    Generate a new random TOTP secret.
    
    Returns:
        Base32-encoded secret string
    """
    return pyotp.random_base32()


def get_totp_uri(username: str, secret: str, issuer: str = "Voting System") -> str:
    """
    Generate an otpauth:// URI for QR code generation.
    
    This URI can be converted to a QR code that users can scan
    with TOTP apps.
    
    Args:
        username: Username for the admin account
        secret: Base32-encoded TOTP secret
        issuer: Name of the application (appears in authenticator app)
        
    Returns:
        otpauth:// URI string
    """
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=issuer)


def verify_totp(secret: str, token: str, valid_window: int = 1) -> bool:
    """
    Verify a TOTP token against a secret.
    
    Args:
        secret: Base32-encoded TOTP secret
        token: 6-digit TOTP code from authenticator app
        valid_window: Number of time steps to check before/after current (default 1)
                     This allows for slight time drift between server and client
        
    Returns:
        True if token is valid, False otherwise
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(token, valid_window=valid_window)
