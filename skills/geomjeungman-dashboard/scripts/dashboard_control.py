import argparse
from fcntl import LOCK_EX, LOCK_NB, flock
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep


TIMEOUT = 10
DEFAULT_DASHBOARD = Path(__file__).resolve().parents[2] / "geomjeungman" / "scripts" / "dashboard.py"


def start(project, directory, dashboard):
    session_path = directory / "session"
    with session_path.open("a+b") as session:
        try:
            flock(session, LOCK_EX | LOCK_NB)
        except BlockingIOError:
            process = None
        else:
            try:
                if not dashboard.is_file():
                    raise ValueError(f"관제탑 스크립트를 찾을 수 없습니다. --dashboard-script로 경로를 지정하세요. ({dashboard})")
                session.truncate(0)
                with (directory / "server.log").open("wb") as log:
                    # The child inherits the session lock and keeps it until exit.
                    process = subprocess.Popen(
                        [sys.executable, str(dashboard), "--serve", "--session-fd", str(session.fileno())],
                        cwd=project, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                        start_new_session=True, pass_fds=(session.fileno(),),
                    )
            except (OSError, ValueError):
                session_path.unlink()
                raise

        deadline = monotonic() + TIMEOUT
        while monotonic() < deadline:
            if process is not None and process.poll() is not None:
                break
            session.seek(0)
            url = session.readline()
            if url.endswith(b"\n"):
                return url.decode("ascii").strip()
            sleep(0.05)

        if process is not None:
            session_path.unlink()
            if process.poll() is None:
                process.terminate()
        raise ValueError(f"관제탑을 시작하지 못했습니다. 실행 로그를 확인하세요. ({directory / 'server.log'})")


def stop(directory):
    session_path = directory / "session"
    if not session_path.exists():
        return "검증 관제탑이 이미 꺼져 있습니다."

    with session_path.open("rb") as session:
        # The server holds this lock through socket closure. Unlinking signals only this instance.
        session_path.unlink()
        deadline = monotonic() + TIMEOUT
        while monotonic() < deadline:
            try:
                flock(session, LOCK_EX | LOCK_NB)
            except BlockingIOError:
                sleep(0.05)
            else:
                return "검증 관제탑을 껐습니다."
    raise ValueError("관제탑에 종료를 요청했지만 서버 종료를 확인하지 못했습니다.")


def main():
    parser = argparse.ArgumentParser(description="프로젝트의 검증 관제탑을 켜거나 끕니다.")
    parser.add_argument("action", choices=("start", "stop"))
    parser.add_argument("--project", type=Path, required=True, help="검사 대상 프로젝트 루트")
    parser.add_argument("--dashboard-script", type=Path, default=DEFAULT_DASHBOARD, help="검증맨의 dashboard.py 경로")
    args = parser.parse_args()

    project = args.project.resolve()
    directory = project / ".geomjeung" / ".dashboard"
    try:
        if not project.is_dir():
            raise ValueError(f"프로젝트 폴더를 찾을 수 없습니다. ({project})")
        if args.action == "stop" and not directory.exists():
            print("검증 관제탑이 이미 꺼져 있습니다.")
            return
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (directory / "control.lock").open("a") as lock:
            flock(lock, LOCK_EX)
            result = start(project, directory, args.dashboard_script.resolve()) if args.action == "start" else stop(directory)
        print(result)
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
