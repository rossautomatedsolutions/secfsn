import time
from contextlib import contextmanager
import logging


@contextmanager
def log_timing(label: str, logger_name: str = None):
    start = time.perf_counter()
    yield
    end = time.perf_counter()
    if logger_name:
        import logging
        logger = logging.getLogger(logger_name)
        logger.info(f"{label} took {end - start:.4f}s")

def timed(label: str, logger_name: str = None):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            out = fn(*args, **kwargs)
            end = time.perf_counter()
            if logger_name:
                import logging
                logger = logging.getLogger(logger_name)
                logger.info(f"{label} took {end - start:.4f}s")
            return out
        return wrapper
    return decorator
