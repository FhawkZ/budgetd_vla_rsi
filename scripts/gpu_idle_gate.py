"""Bounded resource observation. Never relax idle criteria or stop other jobs."""
import time

class GPUUnavailable(RuntimeError):
    pass

def wait_idle(read, record, timeout=6.0, interval=0.5, clock=time.monotonic, sleep=time.sleep):
    if not 0 <= timeout <= 6 or not 0 < interval <= 1:
        raise ValueError("bounded observation limits")
    deadline = clock() + timeout
    while True:
        sample = read()
        record(dict(sample))
        # Any visible process or significant memory remains an immediate refusal.
        if sample["processes"] or sample["memory_mib"] >= 128:
            raise GPUUnavailable("GPU occupied; no displacement or waiting for a job")
        if sample["utilization"] == 0:
            return sample
        remaining = deadline - clock()
        if remaining <= 0:
            raise GPUUnavailable("GPU utilization did not become idle within resource-only deadline")
        sleep(min(interval, remaining))
