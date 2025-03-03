from dataclasses import dataclass

@dataclass
class Config:
    """전역 설정을 관리하는 클래스"""
    # TTS 관련 설정
    tts_server_url: str = "http://127.0.0.1:9880/tts"
    default_ref_audio: str = r"C:\Users\unit6\Documents\Test\My_tts\My_BaseTTS_v2.wav"
    default_prompt_text: str = ""
    default_prompt_lang: str = "ko"
    
    # STT 관련 설정
    stt_model: str = "large-v2"
    stt_language: str = "ko"
    stt_device: str = "cuda"
    stt_gpu_device_index: int = 0
    
    # Ollama 관련 설정
    ollama_model: str = "benedict/linkbricks-llama3.1-korean:8b"
    ollama_system_message: str = (
        "당신은 인터넷 AI 방송 크리에이터입니다. "
        "Ollama 기반의 인공지능 AI이며, 시청자들과 소통하는 것을 즐기고 털털한 성격을 가졌습니다. "
        "존댓말을 사용하지 말고, 대화는 짧고 간결하게 하며, 정확한 정보를 전달하세요."
    )
    ollama_max_history: int = 12
    
    # VTS 관련 설정
    vts_host: str = "localhost"
    vts_port: int = 8001
    vts_plugin_name: str = "AI VTuber Plugin"
    vts_plugin_developer: str = "AI Developer"
    
    # 스레드 관련 설정
    thread_timeout: float = 5.0
    
    # 동작 관련 설정
    blink_min_interval: float = 3.0
    blink_max_interval: float = 6.0
    mouth_update_interval: float = 0.05
    tts_chunk_size: int = 40  # 이 길이만큼 모으면 TTS 요청