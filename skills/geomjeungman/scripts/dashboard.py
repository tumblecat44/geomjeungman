#!/usr/bin/env python3
import argparse
from base64 import b64encode
from datetime import date
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import quote
import webbrowser

from preview import destination, screenshot_size, shot_issues


def read_report(path):
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return report if isinstance(report, dict) else {}


def dimensions(value):
    if isinstance(value, list) and len(value) == 2 and all(type(n) is int and n > 0 for n in value):
        return value
    return None


def collect_run(root, day, folder):
    report_file = folder / "report.json"
    findings_file = folder / "findings.md"
    files = {p.name: p for p in folder.iterdir() if p.is_file() and p.resolve().is_relative_to(root)}
    images = sorted(p for p in files.values() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})
    if not images and report_file.name not in files and findings_file.name not in files:
        return None

    def link(path):
        return quote(path.relative_to(root).as_posix())

    report = read_report(report_file) if report_file.name in files else {}
    context = report.get("context")
    context = (context.strip() if isinstance(context, str) else "") or folder.name
    target = report.get("target", "viewport")
    if target not in ("window", "viewport"):
        target = "viewport"
    entries = report.get("captures")
    entries = entries if isinstance(entries, list) else []
    by_name = {
        Path(entry["screenshot"]).name: entry for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("screenshot"), str)
    }
    shots = []
    for image in images:
        measured = by_name.get(image.name, {})
        marked = image.with_name(f"{image.stem}-marked.svg")
        pixels = dimensions(screenshot_size(image))
        issues = shot_issues(measured.get("issues"), pixels)
        generated = destination(image, context, issues) if issues else None
        preview = None
        if generated and generated.is_file() and generated.resolve().is_relative_to(root):
            preview = {"src": link(generated), "pixels": screenshot_size(generated)}
        shots.append({
            "name": image.name,
            "src": link(image),
            "marked": link(marked) if marked.name in files else None,
            "pixels": pixels,
            "requested": dimensions(measured.get("requested")),
            "actual": dimensions(measured.get(target)),
            "mismatch": measured.get("status") == "size_mismatch",
            "issues": issues,
            "context": context,
            "preview": preview,
        })
    return {
        "id": folder.relative_to(root).as_posix(),
        "day": day,
        "title": folder.name,
        "updated": max(path.stat().st_mtime_ns for path in files.values()),
        "shots": shots,
        "report": link(report_file) if report_file.name in files else None,
        "findingsPath": link(findings_file) if findings_file.name in files else None,
        "findings": findings_file.read_text(encoding="utf-8", errors="replace") if findings_file.name in files else "",
        "error": report.get("error") if isinstance(report.get("error"), str) else None,
    }


def collect(root):
    runs = []
    for day in sorted(root.iterdir(), reverse=True):
        if not day.is_dir() or not day.resolve().is_relative_to(root):
            continue
        try:
            if date.fromisoformat(day.name).isoformat() != day.name:
                continue
        except ValueError:
            continue
        for folder in day.iterdir():
            if folder.is_dir() and folder.resolve().is_relative_to(root):
                run = collect_run(root, day.name, folder)
                if run is not None:
                    runs.append(run)
    return sorted(runs, key=lambda run: (run["day"], run["updated"], run["title"]), reverse=True)


def main():
    parser = argparse.ArgumentParser(description=".geomjeung의 검사 기록을 모아 index.html을 만듭니다.")
    parser.add_argument("--run", type=Path, help="처음에 열 검사 폴더의 경로")
    parser.add_argument("--open", action="store_true", help="완성된 HTML을 기본 브라우저에서 엽니다.")
    parser.add_argument("--serve", action="store_true", help="로컬에서 Codex 미리보기 버튼을 활성화합니다.")
    parser.add_argument("--session-fd", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    project = Path.cwd()
    root = (project / ".geomjeung").resolve()
    try:
        root.mkdir(exist_ok=True)
        runs = collect(root)
        selected = args.run.resolve().relative_to(root.resolve()).as_posix() if args.run else None
        if selected and not any(run["id"] == selected for run in runs):
            raise ValueError("지정한 검사 폴더에서 스크린샷이나 기록을 찾을 수 없습니다.")
        data = {"project": project.name, "selected": selected, "runs": runs}
        template = Path(__file__).resolve().parents[1] / "assets" / "dashboard.html"
        cursor = b64encode(template.with_name("sengi-cursor.svg").read_bytes()).decode("ascii")
        document = template.read_text(encoding="utf-8")
        document = document.replace("__GEOMJEUNG_CURSOR__", cursor, 1)

        def render(payload):
            encoded = json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")
            return document.replace("__GEOMJEUNG_DATA__", encoded, 1)

        output = root / "index.html"

        def write_index(payload):
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=root, delete=False) as temp:
                temp.write(render({**payload, "previewEnabled": False}))
            Path(temp.name).replace(output)

        write_index(data)
        print(output)
        if args.serve:
            from dashboard_server import serve
            serve(root, data, render, write_index, args.open, args.session_fd)
        elif args.open and not webbrowser.open(output.as_uri()):
            raise OSError("브라우저를 열지 못했습니다. 위 HTML 파일을 직접 여세요.")
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
