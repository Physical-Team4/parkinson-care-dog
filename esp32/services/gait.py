# MechDog 보행 제어 (담당: C). Hiwonder 펌웨어 보행 API를 감싼다.
# TODO(C): 위키 Python 강의의 MechDog 보행 함수 이름 확인 후 구현.


class Gait:
    def walk(self, speed):
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError
