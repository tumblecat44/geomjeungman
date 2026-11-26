#!/usr/bin/env python3
import argparse
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit

from agent_browser import cache_directory, executable, run_checked
from preview import screenshot_size


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


def required_selector(value):
    generic = {"*", "html", "body", "main", "#root", "#app", ":root", "[role=main]"}
    for alternative in value.lower().split(","):
        alternative = re.sub(r"""["']""", "", alternative).strip()
        alternative = re.sub(r"\[role\s*=\s*main\]", "[role=main]", alternative)
        parts = re.split(r"\s*[>+~]\s*|\s+", alternative)
        if not alternative or all(part in generic for part in parts):
            raise argparse.ArgumentTypeError("#pricing-table처럼 검사할 화면을 알아볼 선택자를 지정하세요.")
    return value


def document_url(value):
    try:
        url = urlsplit(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("검사할 화면의 전체 주소를 지정하세요.") from error
    if not url.scheme or (url.scheme in {"http", "https"} and not url.netloc):
        raise argparse.ArgumentTypeError("검사할 화면의 전체 주소를 지정하세요.")
    return value


def browser(args, *command):
    result = run_checked([args.agent_browser, "--session", args.session, "--json", *command], timeout=30)
    try:
        response = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(result.stderr.strip() or "Invalid agent-browser response.") from error
    if result.returncode or not response.get("success"):
        raise RuntimeError(response.get("error") or result.stderr.strip() or "Browser command failed.")
    return response["data"]


def lock_session(session):
    locks = cache_directory() / "sessions"
    locks.mkdir(parents=True, exist_ok=True)
    lease = (locks / sha256(session.encode()).hexdigest()).open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            lease.seek(0)
            msvcrt.locking(lease.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        lease.close()
        raise RuntimeError("같은 Agent Browser 세션에서 다른 검증맨 검사가 진행 중입니다.") from error
    return lease


def save_report(path, report):
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
        temporary.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    Path(temporary.name).replace(path)


def measure_expression(selector, text_selectors=None):
    config = json.dumps({"selector": selector, "textSelectors": text_selectors})
    return f"""(() => {{
      const {{ selector, textSelectors }} = {config};
      const visible = node => node?.checkVisibility({{
        visibilityProperty: true, opacityProperty: true
      }});
      const screen = selector ? document.querySelector(selector) : null;
      const rect = screen?.getBoundingClientRect();
      const onScreen = rect && rect.width > 0 && rect.height > 0 &&
        rect.right > 0 && rect.bottom > 0 && rect.left < innerWidth && rect.top < innerHeight;
      const unobscured = onScreen && [0.25, 0.5, 0.75].some(fraction => {{
        const left = Math.max(0, rect.left), right = Math.min(innerWidth, rect.right);
        const top = Math.max(0, rect.top), bottom = Math.min(innerHeight, rect.bottom);
        return screen.contains(document.elementFromPoint(
          left + (right - left) * fraction, top + (bottom - top) * fraction
        ));
      }});
      const result = {{
        url: location.href,
        viewport: [innerWidth, innerHeight],
        window: [outerWidth, outerHeight],
        pixel_ratio: devicePixelRatio,
        ready: !selector || Boolean(visible(screen) && unobscured),
        busy: Boolean(screen?.closest('[aria-busy="true"]') || screen?.querySelector('[aria-busy="true"]'))
      }};
      if (!textSelectors || !result.ready) return result;

      const page = document.scrollingElement || document.documentElement;
      result.layout = {{
        page_overflow_px: Math.max(0, page.scrollWidth - page.clientWidth),
        text: textSelectors.map(selector => {{
          const node = screen.matches(selector) ? screen : screen.querySelector(selector);
          if (!visible(node)) return {{ selector, status: "missing" }};
          const style = getComputedStyle(node);
          if (!node.clientWidth || style.textWrapMode !== "nowrap") {{
            return {{ selector, status: "not_single_line" }};
          }}
          return {{
            selector,
            status: "measured",
            available_px: node.clientWidth,
            content_px: node.scrollWidth,
            overflow_px: Math.max(0, node.scrollWidth - node.clientWidth),
            ellipsis: style.textOverflow === "ellipsis"
          }};
        }})
      }};
      return result;
    }})()"""


def measure(args, selector=None, *, layout=False):
    result = browser(args, "eval", measure_expression(selector, args.text if layout else None)).get("result")
    if not isinstance(result, dict):
        raise RuntimeError("브라우저에서 화면이나 선택자를 확인할 수 없습니다.")
    return result


def resize(args, dimensions):
    width, height = dimensions
    if args.electron:
        browser(args, "eval", f"""(async () => {{
          window.resizeTo({width}, {height});
          await new Promise(resolve => setTimeout(resolve, 300));
          return [outerWidth, outerHeight];
        }})()""")
    else:
        browser(args, "set", "viewport", str(width), str(height))


def wait_for_screen(args):
    selector = json.dumps(args.require)
    ready_selector = json.dumps(args.ready)
    result = browser(args, "eval", f"""(async () => {{
      const deadline = performance.now() + 3000;
      while (performance.now() < deadline) {{
        const screen = document.querySelector({selector});
        const marker = {ready_selector};
        const ready = !marker || Boolean(document.querySelector(marker)?.checkVisibility());
        if (!screen) return !marker;
        const busy = screen.closest('[aria-busy="true"]') || screen.querySelector('[aria-busy="true"]');
        const loadingImage = [...screen.querySelectorAll('img')].some(img =>
          img.getBoundingClientRect().top < innerHeight && img.checkVisibility() && !img.complete);
        const animating = screen.getAnimations({{subtree: true}}).some(animation =>
          animation.playState === 'running' && animation.effect?.getTiming().iterations !== Infinity);
        if (ready && !busy && !loadingImage && !animating && document.fonts.status === 'loaded') return true;
        await new Promise(resolve => setTimeout(resolve, 75));
      }}
      return false;
    }})()""")["result"]
    if not result:
        raise RuntimeError("요청한 화면의 글꼴, 이미지, 움직임 또는 준비 표식이 아직 준비되지 않았습니다.")


def verify_page(current, expected_url):
    if current["url"] in ("about:blank", "about:srcdoc") or current["url"].startswith("chrome-error:"):
        raise RuntimeError("촬영 전에 검사할 화면을 열어 주세요.")
    if current["url"] != expected_url:
        raise RuntimeError(f"요청 주소는 {expected_url}입니다. 브라우저에서 열린 주소는 {current['url']}입니다.")


def require_screen(current):
    if not current["ready"]:
        raise RuntimeError("검사할 화면을 알아볼 요소가 보이지 않습니다.")


def start_report(args, path):
    target = "window" if args.electron else "viewport"
    entries = [{"requested": dimensions, "status": "pending", "issues": []} for dimensions in args.sizes]
    return {"target": target, "expected_url": args.url, "captures": entries,
            "stage": "capturing", "report": str(path)}


def capture(args, directory, report):
    target = report["target"]
    entries = report["captures"]
    report_path = directory / "report.json"
    try:
        if args.cdp:
            browser(args, "connect", args.cdp)
        sessions = browser(args, "session", "list")["sessions"]
        if args.session not in sessions:
            if args.electron:
                raise RuntimeError(f"Agent Browser 세션 {args.session!r}을 앱에 연결하세요.")
            browser(args, "open", args.url)
        original = measure(args, args.require)
        report["url"] = original["url"]
        expected_url = browser(args, "eval", f"new URL({json.dumps(args.url)}).href")["result"]
        verify_page(original, expected_url)
    except (OSError, RuntimeError) as error:
        fail_run(report, str(error))
        return

    resized = False
    try:
        for index, entry in enumerate(entries, start=1):
            requested = entry["requested"]
            try:
                verify_page(measure(args), expected_url)
                resized = True
                resize(args, requested)
                actual = measure(args, args.require)
                verify_page(actual, expected_url)
                if not actual["ready"] and args.reopen:
                    browser(args, "click", args.reopen)
                    browser(args, "wait", args.require)
                    entry["reopened"] = True
                wait_for_screen(args)
                actual = measure(args, args.require, layout=True)
                entry.update(window=actual["window"], viewport=actual["viewport"], pixel_ratio=actual["pixel_ratio"])
                verify_page(actual, expected_url)
                require_screen(actual)
                width, height = actual[target]
                screenshot = directory / f"{index:02}-{width}x{height}.png"
                browser(args, "--screenshot-format", "png", "screenshot", str(screenshot))
                try:
                    pixels = screenshot_size(screenshot)
                    expected_pixels = [round(value * actual["pixel_ratio"]) for value in actual["viewport"]]
                    if not pixels or any(abs(real - expected) > 1 for real, expected in zip(pixels, expected_pixels)):
                        raise RuntimeError("스크린샷 파일을 읽을 수 없거나 사진 크기가 실측값과 다릅니다.")
                    after = measure(args, args.require)
                    verify_page(after, expected_url)
                    require_screen(after)
                    if after["busy"] or any(after[key] != actual[key] for key in ("window", "viewport", "pixel_ratio")):
                        raise RuntimeError("촬영 중 화면이 준비 상태를 벗어났거나 크기가 바뀌었습니다.")
                except (OSError, RuntimeError):
                    screenshot.unlink(missing_ok=True)
                    raise
                entry["screenshot"] = str(screenshot)
                if actual[target] == requested:
                    entry.update(status="captured", layout=actual["layout"])
                else:
                    entry.update(status="size_mismatch", error="실제 크기가 요청한 크기와 다릅니다.")
            except (OSError, RuntimeError) as error:
                entry.update(status="unverified", error=str(error))
            save_report(report_path, report)
    finally:
        try:
            if resized:
                current = measure(args)
                verify_page(current, expected_url)
                if current[target] != original[target]:
                    resize(args, original[target])
                if measure(args)[target] != original[target]:
                    raise RuntimeError("브라우저가 시작 크기로 돌아가지 않았습니다.")
        except (OSError, RuntimeError) as error:
            report["restore_error"] = str(error)


def fail_run(report, error):
    report["error"] = error
    for entry in report["captures"]:
        if entry["status"] == "pending":
            entry.update(status="unverified", error=error)


def main():
    parser = argparse.ArgumentParser(description="Capture the current screen at several sizes.")
    parser.add_argument("--session", required=True, help="Agent Browser 세션 이름")
    parser.add_argument("--cdp", help="실행 중인 브라우저나 Electron 앱의 CDP 포트 또는 주소")
    parser.add_argument("--name", required=True, type=run_name, help="Run name under .geomjeung/YYYY-MM-DD")
    parser.add_argument("--url", required=True, type=document_url, help="Expected document address")
    parser.add_argument("--require", required=True, type=required_selector, help="Screen-specific CSS selector")
    parser.add_argument("--text", action="append", default=[], help="Single-line text selector within the screen")
    parser.add_argument("--ready", help="화면이 다 준비된 뒤 보이는 요소의 CSS 선택자")
    parser.add_argument("--reopen", help="Click this CSS selector if resizing closes the required menu")
    parser.add_argument("--electron", action="store_true", help="Resize the native Electron window")
    parser.add_argument("sizes", nargs="+", type=size, metavar="WIDTHxHEIGHT")
    args = parser.parse_args()
    try:
        directory = output_directory(args.name)
        path = directory / "report.json"
        report = start_report(args, path)
        save_report(path, report)
        try:
            with lock_session(args.session):
                args.agent_browser = executable()
                capture(args, directory, report)
        except (OSError, RuntimeError) as error:
            fail_run(report, str(error))
        report["stage"] = "awaiting_review"
        save_report(path, report)
    except OSError as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
