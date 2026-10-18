"""Local process/device observations; missing instruments remain explicit."""

import resource
import shutil
import subprocess
import sys


def memory_snapshot(*, device=True):
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result = {
        "process_peak_rss_bytes": rss if sys.platform == "darwin" else rss * 1024,
        "device_memory_mib": None,
        "device_memory_scope": "whole_device_not_job_attribution",
    }
    binary = shutil.which("nvidia-smi")
    if device and binary:
        try:
            reply = subprocess.run(
                [binary, "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=0.5,
                check=True,
            )
            result["device_memory_mib"] = [int(line) for line in reply.stdout.splitlines()]
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return result
