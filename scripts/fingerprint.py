# fingerprint.py
import base64
import hashlib
import platform
import pathlib
import subprocess
import shutil

def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().strip()
    except Exception:
        return ""

def _try_cpp_fingerprint(extra_salt: str | None = None) -> str | None:
    """
    Try to compute the fingerprint using the compiled C++ helper if available.
    Looks for an executable named 'oksi_fingerprint' (installed via CMake)
    either in PATH or next to this file.
    Returns the fingerprint string on success, or None if unavailable/failed.
    """
    exe_name = "oksi_fingerprint"
    here = pathlib.Path(__file__).parent
    candidates = [shutil.which(exe_name), here / exe_name]
    for cand in candidates:
        if not cand:
            continue
        p = pathlib.Path(str(cand))
        if p.exists() and p.is_file():
            try:
                cmd = [str(p)]
                if extra_salt:
                    cmd += ["--salt", str(extra_salt)]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                if res.returncode == 0:
                    out = (res.stdout or "").strip()
                    if out:
                        return out
            except Exception:
                pass
    return None


def generate_fingerprint(extra_salt: str | None = None) -> str:
    """
    Create a reasonably stable, non-PII-heavy fingerprint using:
    - /etc/machine-id (Linux), if present
    - MAC address (uuid.getnode())
    - CPU brand + architecture
    - OS release

    Output: URL-safe base64 of SHA-256 digest.
    """
    # Prefer the C++ implementation if present
    cpp = _try_cpp_fingerprint(extra_salt)
    if cpp:
        return cpp

    import uuid

    components: list[str] = []

    # Linux machine-id is stable across reboots but resets on OS reinstall.
    machine_id = _read_text("/etc/machine-id")
    if machine_id:
        components.append(f"mid:{machine_id}")

    # # MAC (best-effort); if randomized or virtualized it may change.
    # mac = uuid.getnode()
    # components.append(f"mac:{mac:012x}")

    # # CPU/OS signals
    # components.append(f"cpu:{platform.processor() or platform.machine()}")
    # components.append(f"arch:{platform.machine()}")
    # components.append(f"os:{platform.system()}-{platform.release()}")

    if extra_salt:
        components.append(f"salt:{extra_salt}")

    raw = "|".join(components).encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

if __name__ == "__main__":
    print("Fingerprint:", generate_fingerprint())
