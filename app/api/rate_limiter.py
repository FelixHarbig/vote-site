from slowapi.util import get_remote_address
import slowapi
limiter = slowapi.Limiter(key_func=get_remote_address, default_limits=["1/minute"])