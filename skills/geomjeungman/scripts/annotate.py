#!/usr/bin/env python3
import argparse
from base64 import b64encode
from pathlib import Path
from struct import unpack


def box(value):
    try:
        x, y, width, height = (int(part) for part in value.split(","))
    except ValueError as error:
        raise argparse.ArgumentTypeError("좌표를 x,y,너비,높이 순서로 입력하세요.") from error
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("좌표는 0 이상, 너비와 높이는 1 이상이어야 합니다.")
    return x, y, width, height


def annotate(source, boxes):
    png = source.read_bytes()
    if len(png) < 33 or png[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR":
        raise ValueError("PNG 스크린샷을 입력하세요.")
    width, height = unpack(">II", png[16:24])

    marks = []
    for x, y, box_width, box_height in boxes:
        if x + box_width > width or y + box_height > height:
            raise ValueError(f"박스를 이미지 크기 {width}×{height} 안에 지정하세요.")
        shape = f'x="{x}" y="{y}" width="{box_width}" height="{box_height}"'
        marks.append(f'<rect {shape} stroke="#171717" stroke-width="7"/>')
        marks.append(f'<rect {shape} stroke="#ffea00" stroke-width="3"/>')

    original = b64encode(png).decode("ascii")
    overlay = "\n".join(marks)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<title>검증맨 검사 표시</title>
<image width="{width}" height="{height}" href="data:image/png;base64,{original}"/>
<g fill="none">
{overlay}
</g>
</svg>
'''
    output = source.with_name(f"{source.stem}-marked.svg")
    output.write_text(svg, encoding="utf-8")
    return output


def main():
    parser = argparse.ArgumentParser(description="PNG 스크린샷 위에 박스를 표시한 SVG를 저장합니다.")
    parser.add_argument("screenshot", type=Path)
    parser.add_argument("--box", type=box, action="append", required=True, metavar="X,Y,WIDTH,HEIGHT")
    args = parser.parse_args()
    try:
        print(annotate(args.screenshot, args.box))
    except (OSError, ValueError) as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()
