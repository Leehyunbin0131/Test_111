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

ai_vtuber/
├── main.py                 # 메인 진입점
├── config/                 # 설정 관리
├── core/                   # 메인 파이프라인
├── stt/                    # 음성 인식
├── tts/                    # 음성 합성 및 재생
├── llm/                    # LLM 대화 관리
├── vts/                    # VTube Studio 연동
└── utils/                  # 유틸리티 기능

