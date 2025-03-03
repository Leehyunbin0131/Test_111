import logging
import time
from typing import Optional, Callable

from RealtimeSTT import AudioToTextRecorder

from ai_vtuber.config import Config
from ai_vtuber.exceptions import STTError

logger = logging.getLogger(__name__)

class SpeechRecognizer:
    """음성 인식을 위한 클래스"""
    
    def __init__(self, config: Config, on_text_recognized: Optional[Callable[[str], None]] = None):
        """
        음성 인식기 초기화
        
        Args:
            config: 설정 객체
            on_text_recognized: 텍스트 인식 시 호출할 콜백 함수
        """
        self.config = config
        self.on_text_recognized = on_text_recognized
        self.recorder = None
        self._setup_recorder()
        
    def _setup_recorder(self) -> None:
        """STT 레코더 설정"""
        try:
            self.recorder = AudioToTextRecorder(
                model=self.config.stt_model,
                language=self.config.stt_language,
                device=self.config.stt_device,
                gpu_device_index=self.config.stt_gpu_device_index,
                beam_size=5,
                input_device_index=0,
                handle_buffer_overflow=True,
                ensure_sentence_starting_uppercase=True,
                ensure_sentence_ends_with_period=True,
                webrtc_sensitivity=1,
                post_speech_silence_duration=1.0,
                silero_sensitivity=0.5,
                silero_deactivity_detection=True,
                min_length_of_recording=1.0,
                min_gap_between_recordings=1.0,
                level=logging.INFO,
                debug_mode=False,
                print_transcription_time=True,
                enable_realtime_transcription=True,
                use_main_model_for_realtime=True,
                realtime_model_type=self.config.stt_model,
                realtime_processing_pause=0.2,
            )
            logger.info("STT 레코더 초기화 완료")
        except Exception as e:
            logger.error(f"STT 레코더 초기화 실패: {e}")
            raise RuntimeError(f"STT 레코더 초기화 실패: {e}")
            
    def start_listening(self, stop_event) -> None:
        """
        지속적인 음성 인식 시작
        
        Args:
            stop_event: 인식 중단을 위한 이벤트
        """
        logger.info("[STT] 지속형 스트리밍 시작")
        
        with self.recorder:
            while not stop_event.is_set():
                try:
                    text = self.recorder.text()
                    if text and text.strip():
                        recognized_text = text.strip()
                        logger.info(f"[STT] 인식됨: {recognized_text}")
                        print(f"[입력 인식됨] {recognized_text}")
                        
                        if self.on_text_recognized:
                            self.on_text_recognized(recognized_text)
                    else:
                        time.sleep(0.1)
                except Exception as e:
                    logger.error("[STT] 음성 인식 오류: %s", e)
                    time.sleep(0.5)

        logger.info("[STT] 지속형 스트리밍 종료")
        
    def recognize_once(self) -> str:
        """
        단일 문장 인식
        
        Returns:
            str: 인식된 텍스트
        """
        if not self.recorder:
            raise STTError("레코더가 초기화되지 않았습니다.")
            
        with self.recorder:
            text = self.recorder.text()
            return text.strip() if text else ""