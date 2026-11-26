import os
from pathlib import Path
import shutil
import subprocess
import sys


VERSION = "0.44.0"


def cache_directory():
    return Path(os.environ.get("GEOMJEUNG_CACHE_DIR") or Path.home() / ".cache" / "geomjeungman")


def executable():
    if installed := shutil.which("agent-browser"):
        return installed
    target = cache_directory() / f"agent-browser-{VERSION}"
    bin_directory = target / "node_modules" / ".bin"
    if cached := shutil.which("agent-browser", path=str(bin_directory)):
        return cached
    npm = shutil.which("npm")
    if npm is None:
        raise RuntimeError("Agent Browser를 설치하려면 npm이 필요합니다.")
    target.mkdir(parents=True, exist_ok=True)
    run_checked(
        [npm, "install", "--prefix", str(target), "--no-audit", "--no-fund", f"agent-browser@{VERSION}"],
        timeout=180,
    )
    if cached := shutil.which("agent-browser", path=str(bin_directory)):
        return cached
    raise RuntimeError("설치 후 Agent Browser 실행 파일을 찾을 수 없습니다.")


def run_checked(command, *, timeout):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"{Path(command[0]).name} 실행 실패 · {error}") from error
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"실행 코드 {result.returncode}")
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(subprocess.call([executable(), *sys.argv[1:]]))
    except (OSError, RuntimeError) as error:
        sys.exit(str(error))
