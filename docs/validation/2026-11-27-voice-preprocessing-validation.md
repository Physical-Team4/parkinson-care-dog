# Raspberry Pi 5 음성 전처리·잡음 제거 기술 검증

- 실험일: 2026-11-26 ~ 2026-11-27
- 실험·결과 제공: B 담당자 (음성 인식, 화자 인식, 발성 훈련, Pi 쪽 UART·통합)
- 실험 위치: Raspberry Pi 5의 독립 실험 폴더 `/home/w8zu/audio-lab` (레포 밖)
- 문서 작성 기준: `origin/main`의 `ced0165`
- 변경 범위: 검증 기록만 추가. 기능 코드, `environment.yml`, 팀 설정은 바꾸지 않았다.
  이 문서를 쓰면서 녹음·처리를 다시 실행하지 않았고, B 담당자가 제공한 조건과 수치만 옮겼다.

## 1. 요약 (Executive Summary)

- **마이크**: AB13X USB 핀마이크는 Windows와 Pi에서 인식·녹음이 되지만, 입력 게인을 최대(100%)로 해도
  입에서 2~3cm 거리의 음성이 작게 들어온다. 지속적인 고주파 "삐" 소리도 들린다.
  마이크 결함인지 제품 특성인지는 확인하지 못했다.
  - **팀 미팅 결과 (2026-11-27)**: 팀장(A)의 같은 모델 마이크는 정상 작동을 확인했다. B는 **새 마이크를 받기로** 했고,
    받기 전까지는 지금 마이크에 **임시 소프트웨어 증폭**을 적용해 개발·테스트한다. 새 마이크를 받으면 주요 기술을 다시 검증한다.
- **증폭 (Software Gain)**: 10배 증폭으로 평균 신호가 20dB 커졌다. 증폭은 잡음도 같이 키우므로 SNR은 좋아지지 않는다.
- **잡음 제거 비교** (선풍기 소음, 단일 평가자 청취 평가):
  - **AFFTDN** (FFmpeg FFT denoiser)이 배경 잡음 4점, 목소리 선명도 3점으로 가장 균형이 좋았다 → 우선 적용 후보.
  - **RNNoise**는 배경 잡음·삐 소리를 거의 없앴지만(5점) 목소리 선명도가 1점이었다 → 채택 보류.
    작은 목소리 보존이 더 중요하다는 기준(파킨슨병 환자의 발성 저하)에 맞지 않는다.
  - High/Low-pass 필터는 연산이 가벼운 보조 후보, Spectral Gating은 대안 후보.
- **Notch Filter**: 조용한 녹음에서 찾은 5267.6Hz·4869.1Hz 피크를 제거해도 삐 소리는 줄지 않았다.
- 기술별 청취 평가는 [§6-3 통합 비교표](#6-3-청취-평가-통합-비교표)에 한 번에 정리했다.
- **DeepFilterNet 3**: Pi 5의 16KB 메모리 페이지와 사전 빌드 실행 파일의 jemalloc이 맞지 않아 실행되지 않았다 → 성능 검증 보류.
- **Vosk**: 한국어 small 모델이 Pi CPU에서 실행된다. 하지만 조용한 녹음에서도 원본은 인식 결과가 없었고,
  증폭 후에는 텍스트가 나오지만 실제 발화와 크게 달랐다. **명령 인식률은 아직 측정하지 않았다.**
- **최종 전처리 알고리즘은 확정하지 않았다.** 다음 단계는 팀 명령어로 Vosk 인식률 비교, Grammar 제한, Silero VAD 검증이다.

## 2. 검증 목적

1. 지금 USB 마이크의 수음 성능과 한계 파악
2. 소프트웨어 증폭 효과 확인
3. 전통적인 신호 처리 방식과 AI 기반 잡음 제거 기술 비교
4. 작은 목소리가 보존되는지 확인
5. 계속 나는 고주파 잡음을 없앨 수 있는지 확인
6. Raspberry Pi 5 CPU만으로 실행 가능한지 확인
7. 이후 VAD, STT, 화자 인식 개발에 쓸 전처리 후보 선정

**평가 기준**: 파킨슨병 환자는 발성이 약해지므로, 잡음을 얼마나 없앴는지보다 **작은 목소리가 남아 있는지**를 더 중요하게 본다.

팀 요구사항과의 관계 ([docs/features.md](../features.md)):
음성 명령은 Silero VAD + Vosk 한국어 small, F5 화자 인식은 ECAPA-TDNN, F4 발성 훈련은 RMS → dB로 정해져 있다.
전처리 방식은 팀 문서에 정해진 것이 없어 이번 실험에서 후보를 고른다.

## 3. 하드웨어 및 소프트웨어 환경

| 항목 | 환경 |
|---|---|
| SBC | Raspberry Pi 5 8GB |
| OS | Debian 13.7 Trixie |
| 아키텍처 | aarch64 |
| 커널 | 6.18.50+rpt-rpi-2712 |
| 메모리 페이지 크기 | 16384 bytes (16KB) |
| Conda 환경 | `pd-dog` |
| Python | 3.13.18 |
| FFmpeg | 7.1.5 |
| NumPy | 2.5.5 |
| SciPy | 1.18.1 |
| noisereduce | 3.0.3 |
| Vosk | 0.3.45 |
| STT 모델 | `vosk-model-small-ko-0.22` |
| 마이크 | AB13X USB 핀마이크 |
| USB ID | `001f:0b21` |
| ALSA 장치 | `hw:2,0` |
| 녹음 규격 | 48kHz, Mono, S16_LE |
| ALSA 입력 볼륨 | **100% (31.99dB)** |
| AI 가속기 | 사용 안 함 (CPU만) |

- **입력 볼륨 차이**: 팀 문서 기본값은 80%다 ([setup.md](../setup.md) 2-7). 이번 독립 실험은 **100%**로 했다.
  아래 dBFS 값은 100% 기준이므로 80% 설정의 값과 바로 비교하면 안 된다.
- **의존성 분리**: SciPy·noisereduce 관련 패키지는 팀 공용 conda 환경을 바꾸지 않도록
  `~/audio-lab/tools/spectral-deps`에 따로 설치했다. `environment.yml`에는 넣지 않았다.
- RNNoise는 공식 저장소([xiph/rnnoise](https://github.com/xiph/rnnoise))의 commit `70f1d25`를 Pi에서 빌드했다.

## 4. 마이크 기초 검증

### 4-1. 장치 인식

Windows와 Raspberry Pi 모두에서 장치 인식과 녹음에 성공했다. 관찰된 문제:

- 실제 음성 입력이 매우 작다. 입에서 2~3cm 떨어진 거리에서도 신호가 약하다.
- 하드웨어 입력 게인을 최대로 해도 수음이 충분하지 않다.
- 소프트웨어로 키우면 배경 잡음도 같이 커진다.
- 들어 보면 지속적인 고주파 삐 소리가 있다.

마이크 자체 결함인지 제품 특성인지는 확정하지 못했다.
다른 마이크 구매도 검토했지만 배송 일정과 개발 기간을 고려해 **AB13X를 계속 쓰기로** 했다.

> **업데이트 (2026-11-27 팀 미팅)**: 팀장 마이크는 정상 작동을 확인했고, B는 새 마이크를 받기로 했다.
> 새 마이크를 받기 전까지 지금 마이크에 임시 소프트웨어 증폭을 적용해 개발·테스트하고, 받은 뒤 주요 기술을 다시 검증한다.

### 4-2. 거리별 초기 측정

25초 동안 녹음하며 5초씩 조건을 바꿨다.

| 구간 | 조건 | 평균 dBFS | 최대 dBFS |
|---|---|---:|---:|
| 0~5초 | 침묵 | -45.3 | -11.1 |
| 5~10초 | 2cm 발성 | -56.3 | -28.1 |
| 10~15초 | 10cm 발성 | -53.9 | -32.1 |
| 15~20초 | 30cm 발성 | -53.9 | -36.7 |
| 20~25초 | 침묵 | -60.7 | -30.4 |

- 첫 침묵 구간이 발성 구간보다 크다(평균 -45.3, 최대 -11.1). 마이크 접촉이나 움직임일 수 있지만 원인은 확인하지 못했다.
- 이 때문에 첫 침묵 구간은 잡음 기준으로 쓰기 어렵다. 마지막 침묵(-60.7)과 발성 구간의 차이는 약 4~7dB로 작다.
- [setup.md](../setup.md) 2-7의 기존 측정(볼륨 80%, 30cm "아~" RMS -37 ~ -45 dBFS)과 차이가 크다.
  입력 볼륨, 발성 방식, 측정 방법이 달라 이 문서만으로 원인을 판단할 수 없다 → 같은 조건으로 다시 재야 한다.

## 5. 실험 방법 및 평가 기준

### 5-1. 녹음 파일

실험용 녹음은 Pi의 `~/audio-lab`에만 있고 레포에는 넣지 않았다 ([§13](#13-개인정보-및-저장소-관리)).

| 파일 | 길이 | 환경 | 용도 |
|---|---|---|---|
| `close_voice.wav` | 20초 | 조용한 환경, 근거리 발성 | 증폭·주파수 필터, Notch Filter, Vosk |
| `noisy_fan.wav` | 30초 | 선풍기 소음, 근거리 발성, 48kHz Mono 16bit PCM | 잡음 제거 기술 비교 |

`noisy_fan.wav` 설계:
- 처음 5초와 마지막 5초는 침묵 구간
- 발화는 팀 음성 명령어: "도와줘", "출발", "걷자", "멈춰", "잘게"
- 정확한 발화 시점은 따로 손으로 확인(라벨링)하지 않았다.
- 원본 평균 -42.2 dBFS, 최대 -1.6 dBFS. 순간적으로 큰 신호가 생긴 원인은 확인하지 못했다.

### 5-2. 처리 순서

같은 녹음 원본에 각 잡음 제거 기술을 적용한 뒤, 기본적으로 **10배 증폭 + 리미터**를 적용해 비교했다.
(예외: E는 증폭·리미터를 먼저 하고 잡음 제거를 나중에 했다.)

- 리미터: `alimiter=limit=0.9:level=0`
- 10배 증폭은 초기 비교 기준일 뿐, 최적 배율로 정한 것이 아니다.

### 5-3. 평가 방법

- **청취 평가**: 평가자가 같은 원본에서 만든 파일들을 직접 듣고 5점 척도로 매겼다 (1 = 매우 나쁨, 5 = 매우 좋음).
  항목: 배경 잡음 제거, 목소리 선명도, 고주파 잡음(삐 소리) 제거.
  - **평가자는 한 명이고 주관적인 평가다.** 객관적 음성 품질 지표나 명령 인식률이 아니다.
  - 파일마다 음량이 달랐고 재생 음량을 맞추지(정규화) 않았다.
- **정량 측정**: 구간별 평균 dBFS (처음 5초 / 중간 20초 / 마지막 5초).
- **처리 시간**: Pi 5 CPU에서 30초 파일 처리 시간 (측정 범위는 [§7-2](#7-2-처리-시간) 참고).

## 6. 잡음 제거 기술 비교

### 6-1. 소프트웨어 증폭 및 주파수 필터 (조용한 환경)

`close_voice.wav`(20초)로 5배·10배·20배 증폭과 주파수 필터를 비교했다.
필터 조건: High-pass 80Hz, Low-pass 7600Hz, 리미터 `alimiter=limit=0.9:level=0`.

| 처리 방식 | 평균 dBFS | 최대 dBFS |
|---|---:|---:|
| 원본 | -49.4 | -27.7 |
| 10배 증폭 | -29.4 | -7.7 |
| 주파수 필터 + 10배 증폭 | -29.8 | -8.7 |

- 10배 증폭으로 평균이 20dB 커졌다 (20·log10(10) = 20dB와 일치).
- 주파수 필터를 더하면 평균이 0.4dB만 줄었고, 들어 봐도 큰 차이는 없었다.
- **증폭은 신호 크기만 키우고 SNR은 좋아지지 않는다.**

### 6-2. 비교한 기술과 설정 (선풍기 소음 환경)

| ID | 기술 | 설정 |
|---|---|---|
| A | 증폭만 (Software Gain) | `volume=10` |
| B | High/Low-pass Filter | `highpass=f=80`, `lowpass=f=7600` |
| C | AFFTDN (FFmpeg FFT Denoiser) | `afftdn=nr=12:nf=-50:tn=1` |
| D | RNNoise | 잡음 제거 → 10배 증폭 |
| E | RNNoise | 10배 증폭 + 리미터 → 잡음 제거 |
| G | AFWTDN (FFmpeg Wavelet Denoiser) | `afwtdn=sigma=-50dB:percent=70` |
| H | ANLMDN (FFmpeg Non-Local Means Denoiser) | `anlmdn=s=0.001` |
| I | Spectral Gating (Stationary) | noisereduce, `prop_decrease=0.7`, 1~4초 구간을 잡음 프로파일로 |
| J | Spectral Gating (Non-stationary) | noisereduce, `prop_decrease=0.7` |
| K | Wiener Filter | STFT 기반 잡음 추정, 최소 gain 0.3 |
| L1~L3 | Notch Filter | [§8](#8-주파수-분석-및-notch-filter) 참고 (조용한 환경 녹음 사용) |

- **F는 결번**: AFFTDN 잡음 프로파일 방식은 명령어만 제안했고 실제 실행·평가가 확인되지 않아 결과에서 뺐다.
- **K. Wiener Filter**는 초기 실험용으로 직접 구현했다: STFT `nperseg=1024`, `noverlap=768`으로
  주파수별 잡음 에너지를 추정하고 Wiener gain을 적용 (최소 gain 0.3).

### 6-3. 청취 평가 통합 비교표

모든 기술의 청취 평가를 한 표로 모았다. 평가 기준: 1~5점 척도의 주관적 청취 평가 (1 = 매우 나쁨, 5 = 매우 좋음, 단일 평가자).

| ID | 처리 방식 | 녹음 환경 | 배경 잡음 제거 | 목소리 선명도 | 고주파 잡음 제거 |
|---|---|---|---:|---:|---:|
| — | 원본 | 선풍기 소음 | 2 | 1 | 1 |
| A | 10배 증폭 | 선풍기 소음 | 2 | 3 | 2 |
| B | High/Low-pass | 선풍기 소음 | 3 | 3 | 2 |
| **C** | **AFFTDN** | 선풍기 소음 | **4** | **3** | 2 |
| D | RNNoise | 선풍기 소음 | 5 | 1 | 5 |
| G | AFWTDN | 선풍기 소음 | 2 | 2 | 3 |
| H | ANLMDN | 선풍기 소음 | 2 | 2 | 3 |
| I | Spectral Gating (Stationary) | 선풍기 소음 | 3 | 3 | 2 |
| J | Spectral Gating (Non-stationary) | 선풍기 소음 | 3 | 3 | 2 |
| K | Wiener Filter | 선풍기 소음 | 2.5 | 3 | 2 |
| L1 | Notch Filter (5267.6Hz) | 조용한 환경 | 미평가 | 3 | 1 |
| L2 | Notch Filter (4869.1Hz) | 조용한 환경 | 미평가 | 3 | 1 |
| L3 | Notch Filter (두 주파수) | 조용한 환경 | 미평가 | 3 | 1 |
| — | DeepFilterNet 3 | — | 실행 불가 | — | — |

비고:
- **환경 차이**: Notch Filter(L1~L3)는 조용한 환경(`close_voice.wav`), 나머지는 선풍기 소음 환경(`noisy_fan.wav`)에서 평가했다.
  녹음이 달라 **두 그룹 사이의 직접적인 순위 비교에는 한계가 있다.** Notch Filter 설정은 [§8-2](#8-2-notch-filter-결과).
- **E (10배 증폭 + 리미터 → RNNoise)**: 정성적 평가만 했다. 배경 잡음은 거의 완전히 사라졌지만 D보다 목소리가 더 흐리게 들렸다. 점수는 매기지 않았다.
- **DeepFilterNet 3**: 실행 환경 문제로 평가하지 못했다 ([§9](#9-deepfilternet-호환성-문제)). 성능이 낮아서 뺀 것이 아니다.
- K의 배경 잡음 점수는 평가자의 추가 의견으로 3점에서 2.5점으로 바꿨다.
- 목소리 선명도 3점을 유지하면서 배경 잡음 점수가 가장 높은 것은 **AFFTDN(C)** → 지금 청취 평가 기준 **우선 후보**.
  단, **실제 음성 인식률(Vosk)은 검증하지 않았다.**
- 고주파 잡음을 크게 줄인 것은 RNNoise(D)뿐이지만 목소리 선명도가 1점이다.
- 이 점수는 B의 기존 AB13X 마이크로 얻은 결과다. 팀장 마이크는 정상 작동을 확인했으며, **B는 새 마이크를 받은 뒤 주요 기술을 다시 검증할 예정**이다.

## 7. 정량 측정 및 처리 시간

### 7-1. 구간별 신호 크기 (`noisy_fan.wav`, 10배 증폭 + 리미터 후)

단위: dBFS

| 처리 방식 | 처음 5초 | 중간 20초 | 마지막 5초 |
|---|---:|---:|---:|
| A. 증폭만 | -29.1 | -27.6 | -37.2 |
| B. 주파수 필터 | -29.9 | -27.7 | -40.1 |
| C. AFFTDN | -29.3 | -27.7 | -37.4 |
| D. RNNoise | -60.4 | -44.2 | -58.4 |

A 대비 신호 에너지 감소량:

| 처리 방식 | 처음 5초 | 중간 20초 | 마지막 5초 |
|---|---:|---:|---:|
| B. 주파수 필터 | 0.8dB | 0.1dB | 2.9dB |
| C. AFFTDN | 0.2dB | 0.1dB | 0.2dB |
| D. RNNoise | 31.3dB | 16.6dB | 21.2dB |

해석:
- **AFFTDN**: 들어 보면 잡음이 줄었지만 전체 에너지 감소는 작았다 (0.1~0.2dB).
  구간 평균 에너지만으로는 청취 평가의 차이가 드러나지 않는다.
- **RNNoise**: 침묵 구간 에너지가 크게 줄었지만(21~31dB) 음성이 섞인 중간 구간도 16.6dB 줄었다.
  들어 봐도 목소리 선명도가 떨어졌다.
- 중간 20초에는 음성 외에 잡음과 발화 사이 침묵도 들어 있다. **이 값을 순수 음성 감소량으로 보면 안 된다.**
- 정확한 SNR 개선량, 음성 손실률, STOI, PESQ는 측정하지 않았다.

### 7-2. 처리 시간

같은 30초 파일을 Pi 5 CPU로 처리했다.

| 기술 | 처리 시간 | 측정 범위 |
|---|---:|---|
| AFWTDN | 0.393초 | FFmpeg 실행 + 파일 처리 전체 |
| ANLMDN | 5.474초 | FFmpeg 실행 + 파일 처리 전체 |
| Spectral Gating (Stationary) | 0.830초 | 잡음 제거 함수 연산만 |
| Spectral Gating (Non-stationary) | 0.894초 | 잡음 제거 함수 연산만 |

- 측정 범위가 서로 달라 **같은 조건의 벤치마크로 보면 안 된다.**
- AFFTDN, RNNoise, Wiener Filter 처리 시간은 확인된 측정값이 없어 적지 않았다.
- CPU 사용률, 메모리 사용량, 실시간 스트리밍 지연, 비전 모델(Hailo)과 같이 돌릴 때의 성능은 검증하지 않았다.

## 8. 주파수 분석 및 Notch Filter

### 8-1. Welch PSD 분석

계속 나는 고주파 삐 소리의 주파수를 찾기 위해 SciPy Welch PSD를 계산했다.

- 대상: `close_voice.wav`, `noisy_fan.wav` 각각의 **마지막 4초**
- `nperseg=8192`, `noverlap=4096`, 피크 검출 `prominence=8`

조용한 환경 (`close_voice.wav`) 주요 피크:

| 주파수 | PSD |
|---:|---:|
| 5267.6Hz | -88.1dB/Hz |
| 4869.1Hz | -91.3dB/Hz |
| 1002.0Hz | -99.4dB/Hz |
| 750.0Hz | -102.4dB/Hz |
| 843.8Hz | -105.9dB/Hz |
| 1130.9Hz | -107.2dB/Hz |
| 5003.9Hz | -107.3dB/Hz |

선풍기 소음 환경 (`noisy_fan.wav`) 주요 피크:

| 주파수 | PSD |
|---:|---:|
| 1259.8Hz | -91.2dB/Hz |
| 1470.7Hz | -95.4dB/Hz |
| 832.0Hz | -98.2dB/Hz |
| 556.6Hz | -106.8dB/Hz |
| 3035.2Hz | -113.3dB/Hz |
| 3281.2Hz | -117.7dB/Hz |

조용한 환경에서 가장 강한 **5267.6Hz, 4869.1Hz**를 삐 소리 후보로 골랐다.

### 8-2. Notch Filter 결과

FFmpeg `bandreject` 필터로 시험했다 (대역폭 각 40Hz, `close_voice.wav` 사용).

| ID | 처리 방식 |
|---|---|
| L1 | 5267.6Hz 제거 |
| L2 | 4869.1Hz 제거 |
| L3 | 두 주파수 동시 제거 |

청취 점수는 [§6-3 통합 비교표](#6-3-청취-평가-통합-비교표)에 있다 (세 경우 모두 목소리 선명도 3, 고주파 잡음 제거 1, 배경 잡음 미평가).

- 지금 설정에서는 **삐 소리가 줄지 않았다.**
- 두 주파수가 삐 소리의 실제 원인인지는 확정하지 못했다.
- 조용한 환경 녹음으로 시험했으므로 §6-3(선풍기 소음)의 점수와 순위를 직접 비교하지 않는다.

## 9. DeepFilterNet 호환성 문제

[DeepFilterNet](https://github.com/Rikorose/DeepFilterNet) 공식 GitHub 릴리스
[v0.5.6](https://github.com/Rikorose/DeepFilterNet/releases/tag/v0.5.6)의 ARM64 Linux용 독립 실행 파일
(DeepFilterNet 3 모델 포함 `deep-filter`)을 받아 실행 권한을 주었다. 실행하면 다음 오류로 바로 종료됐다.

```
<jemalloc>: Unsupported system page size
<jemalloc>: Unsupported system page size
memory allocation of 5 bytes failed
Aborted
```

- Pi의 메모리 페이지 크기는 **16384 bytes (16KB)**로 확인했다 (Pi 5 커널 `6.18.50+rpt-rpi-2712`).
- 사전 빌드 실행 파일에 들어 있는 jemalloc이 16KB 페이지 환경과 맞지 않는 문제로 **추정**한다.
  jemalloc은 빌드할 때 allocator 페이지 크기를 정하고, 그 값이 시스템 페이지 크기 이상이어야 한다
  ([jemalloc INSTALL.md](https://github.com/jemalloc/jemalloc/blob/dev/INSTALL.md)의 `--with-lg-page`).
- 개발 환경 안정성을 위해 다음은 하지 않았다: 커널 변경(4KB 페이지 커널), 재부팅, Rust 개발 환경 구축 후 직접 빌드.
- **DeepFilterNet은 성능이 낮아서 뺀 것이 아니다.** 실행 환경 문제로 성능 검증을 보류한 것이다.

## 10. Vosk 초기 검증

[Vosk](https://github.com/alphacep/vosk-api) 0.3.45와
`vosk-model-small-ko-0.22`([모델 목록](https://alphacephei.com/vosk/models))를 설치해 Pi CPU에서 실행하는 데 성공했다.

`close_voice.wav`(조용한 환경, 20초) 결과:

| 조건 | 인식 결과 | 처리 시간 |
|---|---|---:|
| 원본 | 인식된 음성 없음 | 2.72초 |
| 필터 + 10배 | `관문 / 벌써 [5] 원 / 앨범 오 / 호엔 기각 / [5] 회 행성` | 3.91초 |
| 필터 + 20배 | `그 가 관권 / 벌써 [5] 원 / 앨범 오 / 호엔 실과 / [5] 회 행성` | 3.80초 |
| 필터 + 5배 | `원문 / 얼버무 의원 / 앨범 오 / 고엔지 학 / [5] 월 [20]` | 3.89초 |
| 10배 | `관문 / - [5] 원 / 앨범 오 / 호엔 기관 / 오해영` | 3.75초 |
| 20배 | `그 가 관권 / 벌써 소아과 의원 / 앨범 [5] 기 / 호엔 귀관 의 오해 행성 / 이 아니다` | 4.03초 |
| 5배 | `원문 / 에서 의원 / 앨범 오 / 호엔 일까 / [5] 월 [20]` | 4.11초 |

- 실제 발화: "안녕", "발성 훈련 시작", "발성 훈련 종료", "보행 시작", "보행 정지".
  **초기 기술 검증용 문장이며 팀 음성 명령어가 아니다** (팀 명령어는 [features.md](../features.md) 참고).
- 원본은 아무것도 인식되지 않았고, 증폭하면 텍스트가 나오지만 실제 발화와 크게 다르다.
  **텍스트가 나왔다고 해서 명령 인식에 성공한 것으로 보지 않는다.**
- 처리 시간에는 모델 로딩과 FFmpeg 변환 시간이 빠져 있다.
- 선풍기 소음 환경에서 잡음 제거 기술별 Vosk 인식률과 Grammar 제한 인식은 아직 검증하지 않았다.

## 11. 잠정 기술 선정

| 기술 | 잠정 판단 | 근거 |
|---|---|---|
| 소프트웨어 증폭 | **필요** | 원본은 Vosk가 아무것도 인식 못 함, 입력 신호가 작음. 배율은 미정 |
| AFFTDN | **우선 적용 후보** | 청취 평가에서 잡음 4 / 선명도 3 |
| High/Low-pass Filter | 보조 필터 후보 | 연산 부담 낮음, 잡음 3 / 선명도 3 |
| Spectral Gating | 대안 후보 | 잡음 3 / 선명도 3, 30초 처리 약 0.8~0.9초 |
| RNNoise | 채택 보류 | 배경·고주파 잡음은 5점이지만 선명도 1점 (작은 목소리 손실) |
| AFWTDN, ANLMDN | 우선순위 낮춤 | 지금 설정에서 잡음 2 / 선명도 2 |
| Wiener Filter | 추가 이점 없음 | 잡음 2.5 / 선명도 3 |
| Notch Filter | 효과 미확인 | 시험한 주파수·대역폭에서 고주파 잡음 제거 1점 |
| DeepFilterNet | 보류 | 실행 환경 호환성 문제 (§9) |
| WebRTC NS | 미검증 | — |
| 복합 필터링 | 미검증 | — |

**최종 전처리 알고리즘은 확정하지 않았다.** 위 판단은 지금 장비·설정·녹음 샘플에서 관찰한 결과이며,
각 기술의 일반적인 성능을 평가한 것이 아니다.

개발할 때 지킬 점:
- **F4 발성 훈련의 음량 측정은 증폭·자동 게인 조절(AGC)을 적용한 신호와 분리**해야 한다.
  증폭된 신호로 dB를 재면 실제 발성 크기를 반영하지 못한다.
- **dBFS와 실제 음압(dB SPL)은 같은 값이 아니다.** dB SPL로 표시하려면 소음계 보정(`calibration_offset_db`)이 필요하다
  ([todo.md](../todo.md) "F4 dB 보정 순서").
- **안전 관련 음성 명령**("도와줘", "멈춰" 등)은 오인식·미인식을 충분히 검증하기 전까지 실제 로봇 동작과 연결하지 않는다.

## 12. 한계 및 향후 개발 방향

### 12-1. 실험 한계

- 녹음 샘플이 적다 (조용한 환경 20초, 선풍기 소음 30초 등).
- 단일 평가자의 주관적 청취 평가다.
- 실제 파킨슨병 환자의 음성으로 검증하지 않았다.
- 지금 마이크의 입력 신호가 작다.
- 잡음·발화 구간을 정확히 손으로 라벨링하지 않았다.
- 초기 필터 설정만 비교했고 파라미터 최적화는 충분히 하지 않았다.
- 파일마다 음량이 다른 상태로 들었고 재생 음량을 정규화하지 않았다.
- 실제 로봇 구동 환경(MechDog 서보, Pi 냉각팬)에서 검증하지 않았다.
- 객관적 음성 품질 지표와 정확한 명령 인식률을 측정하지 않았다.
- 입력 볼륨이 팀 기본값(80%)과 다르다(100%).

### 12-2. 향후 개발 항목

1. 실제 팀 명령어로 Vosk 인식 성능 비교 (전처리 기술별)
2. Grammar 제한 인식, 명령이 아닌 발화 거부 테스트
3. Silero VAD 설치, 작은 목소리 검출 검증
4. AFFTDN 설정 최적화, 필요하면 복합 필터링
5. MechDog 냉각팬·서보모터 소음 환경 검증
6. 실시간 스트리밍 지연, CPU·메모리 사용량 검증
7. ECAPA-TDNN 화자 인식
8. 지속 발성 훈련과 음량 측정 (F4)
9. Pi 쪽 UART와 전체 기능 통합
10. 새 마이크를 받은 뒤 주요 기술(증폭, AFFTDN, High/Low-pass, Spectral Gating, RNNoise) 다시 검증

### 12-3. 팀 협의가 필요한 항목

- 실험용 음성 녹음의 보존 허용 범위 (§13)
- 입력 볼륨 기준 (팀 기본 80% vs 이번 실험 100%). F4 보정은 볼륨을 고정한 뒤에 해야 한다.
- ~~마이크 교체 여부~~ → 2026-11-27 팀 미팅: B는 새 마이크를 받기로 함. 받기 전까지 임시 소프트웨어 증폭으로 개발·테스트

## 13. 개인정보 및 저장소 관리

- 팀 규칙: **음성 원본 저장 금지** ([CLAUDE.md](../../CLAUDE.md) "안전·개인정보", [features.md](../features.md) 공통 원칙).
  화자 임베딩은 Pi 로컬에만 두고 Supabase에 올리지 않는다.
- 이번 실험의 녹음 파일(`close_voice.wav`, `noisy_fan.wav`, 처리 결과 파일)은 Pi의 `~/audio-lab`에만 있고 **레포에 넣지 않았다.**
  이 파일들은 운영 코드와 따로 관리하며, **실험용 음성을 얼마 동안·어디까지 보관해도 되는지는 팀과 협의**한다.
- 레포에 넣지 않은 것: 음성 녹음(WAV, PCM), 모델 파일(Vosk 모델 등), 실행 바이너리(RNNoise 빌드, DeepFilterNet),
  conda 환경과 설치된 패키지(`~/audio-lab/tools/spectral-deps` 포함).
- 이번 PR은 이 문서만 추가한다. 기능 코드와 `environment.yml`은 바꾸지 않았다.

## 14. 참고 자료

공식 저장소·문서만 적었다 (2026-11-27 링크 확인).

- FFmpeg Filters Documentation — [afftdn](https://ffmpeg.org/ffmpeg-filters.html#afftdn),
  [afwtdn](https://ffmpeg.org/ffmpeg-filters.html#afwtdn), [anlmdn](https://ffmpeg.org/ffmpeg-filters.html#anlmdn),
  [highpass](https://ffmpeg.org/ffmpeg-filters.html#highpass), [lowpass](https://ffmpeg.org/ffmpeg-filters.html#lowpass),
  [bandreject](https://ffmpeg.org/ffmpeg-filters.html#bandreject), [alimiter](https://ffmpeg.org/ffmpeg-filters.html#alimiter)
- RNNoise: https://github.com/xiph/rnnoise (commit `70f1d25`)
- noisereduce (Spectral Gating): https://github.com/timsainb/noisereduce
- SciPy: [scipy.signal.welch](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.welch.html),
  [scipy.signal.find_peaks](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.find_peaks.html)
- DeepFilterNet: https://github.com/Rikorose/DeepFilterNet ([v0.5.6 릴리스](https://github.com/Rikorose/DeepFilterNet/releases/tag/v0.5.6))
- jemalloc INSTALL (`--with-lg-page`): https://github.com/jemalloc/jemalloc/blob/dev/INSTALL.md
- Vosk: https://github.com/alphacep/vosk-api, 모델 목록 https://alphacephei.com/vosk/models
- Silero VAD (다음 단계): https://github.com/snakers4/silero-vad

팀 문서: [features.md](../features.md), [setup.md](../setup.md) 2-7, [todo.md](../todo.md), [team.md](../team.md)
