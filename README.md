# AI VTuber

![AI VTuber](https://via.placeholder.com/800x200?text=AI+VTuber)

AI VTuber는 VTube Studio, Ollama LLM, GPT-SoVITS를 통합하여 자동화된 AI 기반 가상 유튜버(VTuber) 시스템을 구현한 파이썬 패키지입니다. 음성 인식, 자연어 처리, 음성 합성, 캐릭터 애니메이션을 결합하여 실시간 방송 및 대화형 콘텐츠 제작이 가능합니다.

## 🌟 주요 기능

- **실시간 음성 인식**: 마이크 입력을 텍스트로 변환
- **자연어 이해와 대화**: Ollama LLM 기반 대화 시스템
- **고품질 음성 합성**: GPT-SoVITS를 활용한 자연스러운 음성 출력
- **캐릭터 애니메이션**: VTube Studio 연동으로 캐릭터 자동 애니메이션
- **대화 맥락 관리**: 대화 맥락 유지 및 질문 의도 파악
- **모듈식 설계**: 확장 가능한 모듈식 아키텍처

## 🛠️ 시스템 아키텍처
```
ai_vtuber/
├── main.py                 # 메인 진입점
├── config/                 # 설정 관리
├── core/                   # 메인 파이프라인
├── stt/                    # 음성 인식
├── tts/                    # 음성 합성 및 재생
├── llm/                    # LLM 대화 관리
├── vts/                    # VTube Studio 연동
└── utils/                  # 유틸리티 기능
```

## 📋 요구사항

### 소프트웨어 의존성
- Python 3.9 이상
- [VTube Studio](https://denchisoft.com/)
- [Ollama](https://ollama.ai/)
- [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS)

### 하드웨어 요구사항
- NVIDIA GPU (8GB VRAM 이상 권장)
- 마이크
- 스피커/헤드폰

## 🔧 설치 방법

### 1. 저장소 클론
```bash

```

### 2. 가상환경 생성 및 활성화
```bash
# Conda 사용
conda create -n ai-vtuber python=3.9
conda activate ai-vtuber

# venv 사용
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

### 3. 의존성 설치
```bash

```

### 4. 외부 서비스 설정
#### VTube Studio
- VTube Studio 설치 및 실행
- API 액세스 허용 설정 켜기
  - 설정 → 플러그인 & API → VTube Studio API 활성화

#### Ollama 설정
```bash
ollama pull benedict/linkbricks-llama3.1-korean:8b
```

#### GPT-SoVITS 설정
```bash
python GPT_SoVITS/api_v2.py -a 127.0.0.1 -p 9880 -c GPT_SoVITS/configs/tts_infer.yaml
```

## 🚀 사용 방법

### 기본 실행
```bash
python -m ai_vtuber.main
```

### 설정 파일 지정
```bash
python -m ai_vtuber.main --config my_config.json
```

### 디버그 모드 실행
```bash
python -m ai_vtuber.main --debug
```

### 다른 LLM 모델 사용
```bash
python -m ai_vtuber.main --model llama3:8b
```

## ⚙️ 설정 파일 예시
```json
{
  "tts_server_url": "http://127.0.0.1:9880/tts",
  "default_ref_audio": "models/voice_ref.wav",
  "stt_model": "large-v2",
  "stt_language": "ko",
  "ollama_model": "benedict/linkbricks-llama3.1-korean:8b",
  "vts_host": "localhost",
  "vts_port": 8001,
  "blink_min_interval": 3.0,
  "blink_max_interval": 6.0
}
```

## 🔍 주요 모듈 설명

### STT (Speech-to-Text)
- RealtimeSTT 라이브러리를 사용하여 실시간 음성 인식을 담당합니다.

### LLM (Language Model)
- Ollama API를 통해 대화 처리 및 사용자 발화 분석을 수행합니다.

### TTS (Text-to-Speech)
- GPT-SoVITS API를 연동하여 자연스러운 음성 합성을 담당합니다.

### VTS (VTube Studio)
- WebSocket API를 통해 캐릭터 애니메이션을 제어합니다.

## 🧩 확장하기

### 새로운 TTS 엔진 추가
```python
class AzureTTSManager(TTSManager):
    def __init__(self, api_key, region, ...):
        super().__init__(...)
        self.api_key = api_key
        # 추가 초기화 코드
```

### 다른 LLM 연동
```python
class OpenAIChat(OllamaChat):
    def __init__(self, api_key, model="gpt-4", ...):
        self.api_key = api_key
        self.model = model
        # 초기화 코드
```

### 🎮 게임 연동 기능 추가하기
1. `game/` 디렉토리 생성
2. 화면 캡처 모듈 구현 (`game/capture.py`)
3. 키보드/마우스 제어 모듈 구현 (`game/controller.py`)
4. 게임 상황 인식 모듈 구현 (`game/analyzer.py`)
5. `core/pipeline.py`에 게임 연동 로직 추가

## 🐞 문제 해결

### 모델 로딩 오류
- GPU 메모리 부족: 더 작은 모델 사용
- 모델 경로 오류: 모델 다운로드 확인

### VTube Studio 연결 실패
- API 활성화 확인
- 포트 설정 확인
- 방화벽 설정 확인

### 음성 인식 오류
- 마이크 설정 확인
- STT 모델 로딩 확인
- CUDA 설치 확인 (GPU 이용 시)

## 📜 라이선스
MIT 라이선스로 배포됩니다. 자세한 내용은 LICENSE 파일을 참조하세요.

## 🤝 기여하기
기여는 언제나 환영합니다! 다음과 같은 방법으로 참여할 수 있습니다:
- **이슈 등록**: 버그 신고 또는 기능 제안
- **풀 리퀘스트**: 코드 개선 또는 새 기능 추가
- **문서화**: README 또는 주석 개선

## 📚 관련 자료
- [VTube Studio API 문서](https://denchisoft.com/)
- [Ollama 문서](https://ollama.ai/)
- [GPT-SoVITS 문서](https://github.com/RVC-Boss/GPT-SoVITS)
- [RealtimeSTT 문서](https://github.com/RealtimeSTT)

## 📞 연락처
문의사항은 [이메일 주소] 또는 이슈 트래커를 통해 연락해주세요.

**Made with ❤️ by [당신의 이름/팀명]**
