# ai_vtuber/utils/errors.py

"""AI VTuber 시스템에서 사용되는 예외 클래스 정의"""

class BaseError(Exception):
    """AI VTuber 시스템의 모든 예외 클래스의 기본 클래스"""
    pass

class TTSError(BaseError):
    """TTS(Text-to-Speech) 처리 중 발생하는 오류"""
    pass

class STTError(BaseError):
    """STT(Speech-to-Text) 처리 중 발생하는 오류"""
    pass

class VTSError(BaseError):
    """VTube Studio 연결/통신 중 발생하는 오류"""
    pass

class LLMError(BaseError):
    """LLM(Language Model) 요청/응답 중 발생하는 오류"""
    pass