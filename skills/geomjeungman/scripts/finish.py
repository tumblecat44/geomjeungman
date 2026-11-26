#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from urllib.parse import quote

from capture import save_report
from preview import screenshot_size, shot_issues


def size_label(dimensions):
    return "×".join(map(str, dimensions)) if dimensions else "측정값 없음"


def verdict(entry, pixels, requested, actual):
    if entry.get("status") != "captured" or requested != actual:
        return 2, entry.get("error") or "요청한 화면을 요청한 크기에서 찍지 못했습니다."
    if not pixels:
        return 2, "원본 스크린샷을 찾거나 읽을 수 없습니다."
    if (ratio := entry.get("pixel_ratio")) is not None:
        expected_pixels = [round(value * ratio) for value in entry["viewport"]]
        if any(abs(real - expected) > 1 for real, expected in zip(pixels, expected_pixels)):
            return 2, "스크린샷과 촬영 당시 실측값의 크기가 다릅니다."
    if "page_overflow_px" not in (entry.get("layout") or {}):
        return 2, "가로 넘침 측정값이 없습니다."

    review = entry.get("review") or {}
    summary = review.get("summary", "").strip()
    status = review.get("status")
    if status not in ("clear", "issue") or not summary:
        return 2, summary or "사진 판정을 마치지 않았습니다."
    issues = entry.get("issues")
    if not isinstance(issues, list) or len(shot_issues(issues, pixels)) != len(issues):
        return 2, "문제 설명 또는 사진 위 문제 위치를 확인할 수 없습니다."
    if (status == "issue") != bool(issues):
        return 2, "사진 판정과 문제 목록이 서로 맞지 않습니다."
    layout = entry["layout"]
    signals = layout["page_overflow_px"] > 0 or any(
        item["status"] != "measured" or item["overflow_px"] > 0 for item in layout["text"]
    )
    if status == "clear" and signals and not review.get("measurement_note", "").strip():
        return 2, "수치에서 확인이 필요한 이유를 설명하지 않았습니다."
    return (1 if status == "issue" else 0), summary


def finish(report, folder):
    labels = {0: "깨짐을 찾지 못함", 1: "깨짐 확인", 2: "미검증"}
    lines = ["# 검증맨 결과", "", f"화면 · {report.get('expected_url') or report.get('url') or '기록 없음'}"]
    if report.get("restore_error"):
        lines.append(f"브라우저 크기 복원 · {report['restore_error']}")
    for entry in report["captures"]:
        requested = entry.get("requested")
        actual = entry.get(report["target"])
        image = Path(entry["screenshot"]).resolve() if entry.get("screenshot") else None
        if image is None or image.parent != folder or not image.is_file():
            image = None
        pixels = screenshot_size(image) if image else None
        number, summary = verdict(entry, pixels, requested, actual)
        entry["verdict"] = number
        lines.extend([
            "", f"## {size_label(requested)}", "",
            f"- 촬영 · {'정상 촬영' if entry.get('status') == 'captured' and pixels else '미검증'}"
            f" (실제 {size_label(actual)})",
        ])
        if layout := entry.get("layout"):
            lines.append(f"- 숫자 확인 · 페이지 가로 넘침 {layout['page_overflow_px']}px")
            for item in layout["text"]:
                if item["status"] == "measured":
                    ellipsis = " · 말줄임 스타일 적용" if item["ellipsis"] else ""
                    lines.append(
                        f"  - `{item['selector']}` · 칸 {item['available_px']}px, "
                        f"내용 {item['content_px']}px{ellipsis}"
                    )
                else:
                    reason = "요소가 보이지 않음" if item["status"] == "missing" else "한 줄 폭을 잴 수 없음"
                    lines.append(f"  - `{item['selector']}` · {reason}")
        lines.append(f"- 판정 **{number}** · {labels[number]}. {summary}")
        if note := (entry.get("review") or {}).get("measurement_note"):
            lines.append(f"  - 수치 해석 · {note}")
        if number == 1:
            for issue in entry["issues"]:
                lines.append(f"  - {issue['problem']} {issue['suggestion']}")
        if pixels:
            links = [f"[{('원본' if entry.get('status') == 'captured' else '참고 사진')}]({quote(image.name)})"]
            marked = image.with_name(f"{image.stem}-marked.svg")
            if marked.is_file():
                links.append(f"[문제 표시]({quote(marked.name)})")
            lines.append("- " + " · ".join(links))
    reviewed = all(
        entry["status"] != "captured" or (entry.get("review") or {}).get("status") in ("clear", "issue", "uncertain")
        for entry in report["captures"]
    )
    if report.get("stage") != "capturing":
        report["stage"] = "finished" if reviewed else "awaiting_review"
    if report["stage"] != "finished":
        lines[2:2] = ["**미완료** · 촬영이나 사진 검토를 끝내지 못했습니다.", ""]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description="사진 검토를 반영해 요청 크기마다 판정을 저장합니다.")
    parser.add_argument("report", type=Path, help="사진 검토를 기록한 report.json 경로")
    args = parser.parse_args()
    path = args.report.resolve()
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        findings = finish(report, path.parent)
        path.with_name("findings.md").write_text(findings, encoding="utf-8")
        save_report(path, report)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        parser.exit(1, f"검사 결과를 저장할 수 없습니다. {error}\n")
    print(path.with_name("findings.md"))


if __name__ == "__main__":
    main()
