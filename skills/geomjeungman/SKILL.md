---
name: geomjeungman
description: Navigate to the screen the user describes, then capture it at several window or viewport sizes with measured dimensions. Use for 검증맨, responsive checks, and layout checks after UI work.
---

# 검증맨

1. Resolve the app or URL, the screen to reach, and the sizes to try from the user's request and project. For a desktop app, try its normal size, minimum width at normal height, then its minimum size. For Morrow these are `1080x760`, `640x760`, and `640x600`. For a website without project sizes, use `1440x900`, `390x900`, and `390x600`.
2. Use a dedicated `agent-browser --session <name>` session. Open the website or, for Electron, attach to the app's loopback DevTools port with `agent-browser --session <name> connect <port>` and select the app tab. Use the project's development launch instructions if the app is not running. Confirm the target before interacting.
3. Use `snapshot` and non-persisting UI actions to reach the requested state. Verify that the requested heading, dialog, or menu is visible. Identify a stable CSS selector for that state and pass it to `--require` so the script can detect if resizing closes it.
4. Run `python3 <this-skill-directory>/scripts/capture.py --session <name> --require '<selector>' <width>x<height> ...`. Add `--electron` for a native Electron window, with a fresh session and no viewport or device emulation. If a resize dismisses a menu, add `--reopen '<opener-selector>'` for the known button that reopens it without saving changes. The script restores the starting size after capture.
5. Report each requested size, measured size, and screenshot path. For Electron, report the window and the rendered viewport separately. Use Chrome DevTools MCP on the same target if investigating a suspected layout issue. Base any finding on the screenshot or measured DOM. The capture script only verifies the requested screen and sizes; it does not grade the layout.

The report distinguishes a captured requested size, a size mismatch, and an unverified capture. Keep a mismatch screenshot as evidence of the size the app actually allowed. If the screen or Electron target cannot be reached, say what blocked verification. Browser setup: `agent-browser install` after installing the CLI.
