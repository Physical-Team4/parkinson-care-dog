# esp32/ 규칙

루트 [CLAUDE.md](../CLAUDE.md)를 먼저 따른다. 여기는 MechDog MicroPython 전용 규칙.

- **MicroPython**이다. f-string 일부·typing·dataclasses·asyncio 전체 기능 등 CPython 전용 기능 쓰지 말 것. 표준 모듈은 `ujson`/`json`, `utime`/`time`, `machine`, `select`.
- Hiwonder 펌웨어 모듈(`Hiwonder`, `Hiwonder_IIC`, MechDog 보행 API)은 펌웨어에 내장. 이름·사용법은 Hiwonder 위키 Python 강의 기준으로 확인 후 사용하고, 모르면 TODO.
- 핀 번호·주소·타이밍은 전부 `config.py`. 미확정 값은 `None` → 해당 드라이버는 비활성 + `# warn:` 출력.
- USB 시리얼 = REPL 포트. 디버그 출력은 반드시 `#`로 시작 (`log()` 사용). 메시지 형식은 [docs/serial-protocol.md](../docs/serial-protocol.md).
- 메인 루프는 블로킹 금지 (`sleep` 길게 쓰지 말 것). 각 서비스는 `tick(now_ms)`로 짧게 돌린다.
- 레이저 기본 꺼짐. 부팅·예외·정지 시 반드시 끄기.
- 금지: 배터리 3핀, 빈 4핀 커넥터, 공식 슬레이브 UART 프로토콜(포트 3).
- 계층: `controllers/`(시리얼 명령·하트비트) → `services/`(보행·F1·F2·F3) → `drivers/`(ToF·MP3·레이저·터치).
