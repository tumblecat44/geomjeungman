---
name: geomjeungman-dashboard
description: 검증 관제탑 로컬 웹 서버를 켜거나 끈다. 사용자가 검증 관제탑을 켜 달라고 하거나 종료해 달라고 할 때 사용한다.
---

# 검증 관제탑

검증 결과를 보는 관제탑 웹 서버를 켜거나 끈다. 필수 입력은 동작(`start` 또는 `stop`)과 검사 결과가 있는 프로젝트 루트 경로다. 별도 경로가 주어지지 않으면 현재 작업 프로젝트의 루트를 사용한다. 시작에는 Python 3와 `geomjeungman` 스킬의 `scripts/dashboard.py`가 필요하다. 같은 위치에 설치한 두 스킬은 자동으로 연결되며, 별도 위치에 설치했다면 시작 명령에 `--dashboard-script`로 실제 파일 경로를 지정한다. 스크립트는 macOS와 Linux에서 실행한다.

1. 요청에서 동작과 프로젝트 루트를 확인한다. `PROJECT_DIR`에 프로젝트 루트 경로를, `SKILL_DIR`에 이 `SKILL.md`가 있는 폴더 경로를 둔다.
2. 켜려면 `python3 "$SKILL_DIR/scripts/dashboard_control.py" start --project "$PROJECT_DIR"`를 실행한다. 서버는 백그라운드에서 실행되며 이미 켜져 있으면 기존 접속 주소를 반환한다. 출력된 주소를 사용자에게 전달한다.
3. 끄려면 `python3 "$SKILL_DIR/scripts/dashboard_control.py" stop --project "$PROJECT_DIR"`를 실행한다. 이 스킬로 해당 프로젝트에서 켠 서버의 종료 결과를 전달한다.
