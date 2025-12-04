from functools import wraps
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from ..router import router



# Counters
vote_verifications_total = Counter(
    "vote_verifications_total", "Total number of vote verification attempts", ["status"]
)
vote_solves_total = Counter(
    "vote_solves_total", "Total number of vote solve attempts", ["status"]
)
vote_submissions_total = Counter(
    "vote_submissions_total", "Total number of vote submissions", ["status"]
)

# Histogram for request durations
vote_request_latency = Histogram(
    "vote_request_latency_seconds",
    "Time spent processing vote requests",
    ["endpoint"]
)

def track_metrics(counter, endpoint_name):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            with vote_request_latency.labels(endpoint=endpoint_name).time():
                response = await func(*args, **kwargs)
            # track success/failure based on status code
            status = "success" if response.status_code < 400 else "failure"
            counter.labels(status=status).inc()
            return response
        return wrapper
    return decorator
