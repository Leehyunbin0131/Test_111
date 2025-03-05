# ai_vtuber/config/settings.py

"""AI VTuber 시스템 설정 관리 모듈"""

import os
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional

from ..utils.logging import get_logger

logger = get_logger(__name__)

@dataclass
class Settings:
    """AI VTuber 시스템 설정 클래스"""
    
    # TTS 관련 설정
    tts_server_url: str = "http://127.0.0.1:9880/tts"
    default_ref_audio: str = "models/voice_ref.wav"
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
    
    # 실행 관련 설정
    thread_timeout: float = 5.0
    blink_min_interval: float = 3.0
    blink_max_interval: float = 6.0
    mouth_update_interval: float = 0.05
    tts_chunk_size: int = 40  # 문장 분리 기준 길이
    
    # 디버깅 설정
    debug: bool = False
    
    def __post_init__(self):
        """환경 변수에서 설정 로드"""
        self._load_from_env()
        if self.debug:
            logger.info(f"설정 로드됨: {self.to_dict()}")
    
    def _load_from_env(self):
        """환경 변수에서 설정 값 로드"""
        for field_name in self.__dataclass_fields__:
            env_name = f"AIVTUBER_{field_name.upper()}"
            env_value = os.environ.get(env_name)
            
            if env_value is not None:
                # 필드 타입에 맞게 변환
                field_type = self.__dataclass_fields__[field_name].type
                try:
                    if field_type == bool:
                        value = env_value.lower() in ('true', 'yes', '1', 'y')
                    elif field_type == int:
                        value = int(env_value)
                    elif field_type == float:
                        value = float(env_value)
                    else:
                        value = env_value
                        
                    setattr(self, field_name, value)
                    logger.debug(f"환경 변수에서 로드: {env_name}={value}")
                except ValueError:
                    logger.warning(f"환경 변수 변환 실패: {env_name}={env_value}")
    
    def to_dict(self) -> Dict[str, Any]:
        """설정을 딕셔너리로 변환"""
        return {k: v for k, v in asdict(self).items() if not k.startswith('_')}
    
    def save_to_file(self, filepath: str):
        """설정을 JSON 파일로 저장"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            logger.info(f"설정 저장됨: {filepath}")
        except Exception as e:
            logger.error(f"설정 저장 실패: {e}")
    
    @classmethod
    def load_from_file(cls, filepath: str) -> 'Settings':
        """JSON 파일에서 설정 로드"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            logger.info(f"파일에서 설정 로드됨: {filepath}")
            return cls(**data)
        except Exception as e:
            logger.warning(f"설정 파일 로드 실패, 기본값 사용: {e}")
            return cls()

# 싱글톤 인스턴스
_instance = None

def get_settings() -> Settings:
    """전역 설정 인스턴스 반환"""
    global _instance
    if _instance is None:
        # 설정 파일 로드 시도
        config_path = os.environ.get("AIVTUBER_CONFIG", "config.json")
        if os.path.exists(config_path):
            _instance = Settings.load_from_file(config_path)
        else:
            _instance = Settings()
    return _instance