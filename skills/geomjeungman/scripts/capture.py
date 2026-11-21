#!/usr/bin/env python3
import argparse
from datetime import date
import json
from pathlib import Path
import re
import subprocess


def size(value):
    match = re.fullmatch(r"([1-9][0-9]{0,4})x([1-9][0-9]{0,4})", value)
    if not match:
        raise argparse.ArgumentTypeError("Use WIDTHxHEIGHT, for example 640x600.")
    return [int(part) for part in match.groups()]


def run_name(value):
    if not re.fullmatch(r"[^\W_]+(?:-[^\W_]+)*", value) or len(value.encode("utf-8")) > 120:
        raise argparse.ArgumentTypeError("Use a short name joined by hyphens, such as settings-language-menu.")
    return value


def output_directory(name):
    day = Path.cwd() / ".geomjeung" / date.today().isoformat()
    day.mkdir(parents=True, exist_ok=True)
    index = 1
    while True:
        directory = day / (name if index == 1 else f"{name}-{index}")
        try:
            directory.mkdir()
            return directory
        except FileExistsError:
            index += 1


def browser(session, *command):
    try:
        result = subprocess.run(
            ["agent-browser", "--session", session, "--json", *command],
            capture_output=True, text=True, timeout=20,
        )
    except FileNotFoundError as error:
        raise RuntimeError("agent-browser was not found on PATH.") from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"agent-browser {command[0]} timed out.") from error

    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(result.stderr.strip() or "Invalid agent-browser response.") from error
    if result.returncode or not response.get("success"):
        raise RuntimeError(response.get("error") or result.stderr.strip() or "Browser command failed.")
    return response["data"]


def measure(session, selector):
    return browser(session, "eval", f"""(() => {{
      const selector = {json.dumps(selector)};
      const element = selector ? document.querySelector(selector) : null;
      return {{
        url: location.href,
        viewport: [innerWidth, innerHeight],
        window: [outerWidth, outerHeight],
        ready: !selector || Boolean(element && element.checkVisibility({{
          visibilityProperty: true, opacityProperty: true
        }}))
      }};
    }})()""")["result"]


def resize(session, dimensions, electron):
    width, height = dimensions
    if electron:
        browser(session, "eval", f"window.resizeTo({width}, {height})")
    else:
        browser(session, "set", "viewport", str(width), str(height))
    browser(session, "wait", "300")


def verify_page(current, original):
    if current["url"] in ("about:blank", "about:srcdoc") or current["url"].startswith("chrome-error:"):
        raise RuntimeError("Open the target page before running the capture.")
    if current["url"] != original["url"]:
        raise RuntimeError("The active page changed during capture.")


def require_screen(current):
    if not current["ready"]:
        raise RuntimeError("The requested screen is no longer visible.")


def capture(args, directory):
    target = "window" if args.electron else "viewport"
    report = {"target": target, "captures": []}
    try:
        sessions = browser(args.session, "session", "list")["sessions"]
        if args.session not in sessions:
            raise RuntimeError(f"Open the target in agent-browser session {args.session!r} first.")
        original = measure(args.session, args.require)
        verify_page(original, original)
        require_screen(original)
        report["url"] = original["url"]
    except (OSError, RuntimeError) as error:
        report["error"] = str(error)
        return report, 2

    exit_code = 0
    try:
        for index, requested in enumerate(args.sizes, start=1):
            entry = {"requested": requested, "issues": []}
            report["captures"].append(entry)
            try:
                verify_page(measure(args.session, None), original)
                resize(args.session, requested, args.electron)
                actual = measure(args.session, args.require)
                entry.update(window=actual["window"], viewport=actual["viewport"])
                verify_page(actual, original)
                if not actual["ready"] and args.reopen:
                    browser(args.session, "click", args.reopen)
                    browser(args.session, "wait", args.require)
                    browser(args.session, "wait", "300")
                    actual = measure(args.session, args.require)
                    verify_page(actual, original)
                    require_screen(actual)
                    entry.update(window=actual["window"], viewport=actual["viewport"], reopened=True)
                require_screen(actual)
                width, height = requested
                screenshot = directory / f"{index:02}-{width}x{height}.png"
                browser(args.session, "--screenshot-format", "png", "screenshot", str(screenshot))
                with screenshot.open("rb") as image:
                    if image.read(8) != b"\x89PNG\r\n\x1a\n":
                        raise RuntimeError("The browser did not save a PNG screenshot.")
                entry["screenshot"] = str(screenshot)
                matches = actual[target] == requested
                entry["status"] = "captured" if matches else "size_mismatch"
                if not matches:
                    exit_code = max(exit_code, 1)
            except (OSError, RuntimeError) as error:
                entry.update(status="unverified", error=str(error))
                exit_code = 2
    finally:
        try:
            current = measure(args.session, None)
            if current["url"] != original["url"]:
                raise RuntimeError("The active page changed during capture.")
            if current[target] != original[target]:
                resize(args.session, original[target], args.electron)
                if measure(args.session, None)[target] != original[target]:
                    raise RuntimeError("The browser did not restore the starting size.")
        except (OSError, RuntimeError) as error:
            report["restore_error"] = str(error)
            exit_code = 2
    return report, exit_code


def main():
    parser = argparse.ArgumentParser(description="Capture the current screen at several sizes.")
    parser.add_argument("--session", required=True, help="Open agent-browser session name")
    parser.add_argument("--name", required=True, type=run_name, help="Run name under .geomjeung/YYYY-MM-DD")
    parser.add_argument("--require", help="CSS selector that must stay visible")
    parser.add_argument("--reopen", help="Click this CSS selector if resizing closes the required menu")
    parser.add_argument("--electron", action="store_true", help="Resize the native Electron window")
    parser.add_argument("sizes", nargs="+", type=size, metavar="WIDTHxHEIGHT")
    args = parser.parse_args()
    if args.reopen and not args.require:
        parser.error("--reopen requires --require.")
    try:
        directory = output_directory(args.name)
        report, exit_code = capture(args, directory)
        report["report"] = str(directory / "report.json")
        output = json.dumps(report, ensure_ascii=False, indent=2)
        (directory / "report.json").write_text(output + "\n", encoding="utf-8")
    except OSError as error:
        parser.exit(2, f"{error}\n")
    print(output)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
