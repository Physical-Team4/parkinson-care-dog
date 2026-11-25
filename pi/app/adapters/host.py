"""Pi OS 제어 (base.HostSystem). 안전 종료만 한다.

`sudo -n`(비밀번호 묻지 않음)으로 실행 → Pi에 sudoers 규칙이 있어야 한다 (docs/setup.md 2-6).
"""
from __future__ import annotations

import logging
import subprocess

log = logging.getLogger(__name__)

POWEROFF_CMD = ["sudo", "-n", "/usr/sbin/shutdown", "-h", "now"]


class LinuxHost:
    def poweroff(self) -> None:
        log.warning("Pi 안전 종료 실행: %s", " ".join(POWEROFF_CMD))
        try:
            subprocess.run(POWEROFF_CMD, check=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as e:
            log.error("종료 명령 실패 (sudoers 규칙 확인, docs/setup.md 2-6): %s", e)
