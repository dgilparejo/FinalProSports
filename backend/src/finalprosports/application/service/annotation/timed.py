import functools
import logging
import time

log = logging.getLogger("finalprosports.timing")


def timed(fn):
    """Log the wall time of a service/use-case call (ms)."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            log.info("%s took %.1f ms", fn.__qualname__, (time.perf_counter() - t0) * 1000)
    return wrapper
