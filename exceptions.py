class TTSError(Exception):
    """TTS 처리 중 발생한 오류"""
    pass

class STTError(Exception):
    """STT 처리 중 발생한 오류"""
    pass

class VTSError(Exception):
    """VTubeStudio 연결/통신 중 발생한 오류"""
    pass

class LLMError(Exception):
    """LLM 요청/응답 중 발생한 오류"""
    pass