"""
Supabase client configuration for authentication and database access.
Uses NEW Supabase API keys format (sb_publishable_ and sb_secret_).

Environment variables:
- SUPABASE_URL: Your Supabase project URL
- SUPABASE_PUBLISHABLE_KEY: Publishable key (starts with sb_publishable_)
- SUPABASE_SECRET_KEY: Secret key (starts with sb_secret_)

Can be easily disabled thorugh settings (database)
"""
from supabase import create_client, Client
from dotenv import load_dotenv
import os
from common.log_handler import log

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")

SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")

log.debug(f"Supabase URL: {SUPABASE_URL[:30]}..." if SUPABASE_URL else "Supabase URL: NOT SET")
log.debug(f"Supabase Publishable Key: {'SET' if SUPABASE_PUBLISHABLE_KEY else 'NOT SET'}")
log.debug(f"Supabase Secret Key: {'SET' if SUPABASE_SECRET_KEY else 'NOT SET'}")

# Global client instances
_supabase_client: Client = None
_supabase_admin_client: Client = None


def get_supabase_client() -> Client:
    """
    Get or create the Supabase client for public operations.
    Uses publishable key (sb_publishable_...) - safe for client-side use.
    """
    global _supabase_client
    
    if _supabase_client is None:
        if not SUPABASE_URL:
            log.warning("Supabase URL not configured. Set SUPABASE_URL in .env")
            return None
        
        # Use new publishable key, fallback to legacy anon key
        api_key = SUPABASE_PUBLISHABLE_KEY
        
        if not api_key:
            log.warning("No Supabase API key configured. Set SUPABASE_PUBLISHABLE_KEY (new) or SUPABASE_ANON_KEY (legacy) in .env")
            return None
        
        try:
            _supabase_client = create_client(SUPABASE_URL, api_key)
            log.info("Supabase client initialized successfully")
        except Exception as e:
            log.error(f"Failed to initialize Supabase client: {e}")
            return None
    
    return _supabase_client


def get_supabase_admin_client() -> Client:
    """
    Get or create the Supabase admin client for privileged operations.
    Uses secret key (sb_secret_...) - NEVER expose to client.
    """
    global _supabase_admin_client
    
    if _supabase_admin_client is None:
        if not SUPABASE_URL:
            log.warning("Supabase URL not configured. Set SUPABASE_URL in .env")
            return None
        
        # Use new secret key, fallback to legacy service role key
        api_key = SUPABASE_SECRET_KEY
        
        if not api_key:
            log.warning("No Supabase secret key configured. Set SUPABASE_SECRET_KEY (new) or SUPABASE_SERVICE_ROLE_KEY (legacy) in .env")
            return None
        
        try:
            log.info(f"Creating Supabase client with URL: {SUPABASE_URL}")
            _supabase_admin_client = create_client(SUPABASE_URL, api_key)
            log.info("Supabase admin client initialized successfully")
        except Exception as e:
            log.error(f"Failed to initialize Supabase admin client: {e}")
            return None
    
    return _supabase_admin_client


def is_supabase_configured() -> bool:
    """Check if Supabase is properly configured."""
    return bool(SUPABASE_URL and (SUPABASE_PUBLISHABLE_KEY))


def is_supabase_admin_configured() -> bool:
    """Check if Supabase admin (service role) is properly configured."""
    return bool(SUPABASE_URL and (SUPABASE_SECRET_KEY))
