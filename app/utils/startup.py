import time

# Store the application start time
_app_start_time = time.time()


def get_uptime() -> float:
    """Get application uptime in seconds."""
    return time.time() - _app_start_time


def set_start_time() -> None:
    """Reset the start time (for testing)."""
    global _app_start_time
    _app_start_time = time.time()
