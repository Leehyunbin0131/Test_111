# ai_vtuber/stt/recorder.py

"""음성 인식 모듈"""

import time
import threading
import queue
from typing import Optional, Callable, List, Dict, Any, Tuple

from RealtimeSTT import AudioToTextRecorder

from ..utils.logging import get_logger
from ..utils.errors import STTError

logger = get_logger(__name__)

class SpeechRecognizer:
    """음성 인식 관리 클래스"""
    
    def __init__(
        self,
        model: str = "large-v2",
        language: str = "ko",
        device: str = "cuda",
        gpu_device_index: int = 0,
        post_speech_silence_duration: float = 1.0,
        min_length_of_recording: float = 1.0,
        timeout: float = 15.0,
        max_retries: int = 3,
        retry_interval: float = 1.0
    ):
        """
        음성 인식기 초기화
        
        Args:
            model: 인식 모델
            language: 인식 언어
            device: 사용할 장치 ('cuda' 또는 'cpu')
            gpu_device_index: GPU 장치 인덱스
            post_speech_silence_duration: 말하기 후 침묵 감지 시간 (초)
            min_length_of_recording: 최소 녹음 길이 (초)
            timeout: 인식 타임아웃 (초)
            max_retries: 최대 재시도 횟수
            retry_interval: 재시도 간격 (초)
        """
        self.model = model
        self.language = language
        self.device = device
        self.gpu_device_index = gpu_device_index
        self.post_speech_silence_duration = post_speech_silence_duration
        self.min_length_of_recording = min_length_of_recording
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_interval = retry_interval
        
        # 상태 변수
        self.is_running = False
        self.is_recording = False
        self.text_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.recorder = None
        
        # 콜백 함수
        self.on_recognition_start = None
        self.on_recognition_result = None
        self.on_recognition_end = None
        self.on_error = None
        
        logger.info(f"음성 인식기 초기화 완료 (모델: {model}, 언어: {language}, 장치: {device})")
    
    def initialize(self):
        """음성 인식기 초기화 (지연 로딩)"""
        if self.recorder is not None:
            return
            
        try:
            logger.info("음성 인식기 로딩 중...")
            self.recorder = AudioToTextRecorder(
                model=self.model,
                language=self.language,
                device=self.device,
                gpu_device_index=self.gpu_device_index,
                post_speech_silence_duration=self.post_speech_silence_duration,
                min_length_of_recording=self.min_length_of_recording,
                handle_buffer_overflow=True,  # 버퍼 오버플로우 자동 처리
                enable_realtime_transcription=False,  # 실시간 모드는 사용하지 않음 (CPU/메모리 최적화)
                silero_sensitivity=0.7,  # 침묵 감지 감도
                silero_use_onnx=True  # ONNX 사용으로 성능 향상
            )
            logger.info("음성 인식기 로딩 완료")
            
        except Exception as e:
            logger.error(f"음성 인식기 초기화 오류: {e}")
            raise STTError(f"음성 인식기 초기화 실패: {e}")
    
    def start(
        self,
        on_recognition_start: Optional[Callable] = None,
        on_recognition_result: Optional[Callable[[str], None]] = None,
        on_recognition_end: Optional[Callable] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ):
        """
        음성 인식 시작
        
        Args:
            on_recognition_start: 인식 시작 시 호출할 콜백
            on_recognition_result: 인식 결과 받을 때 호출할 콜백
            on_recognition_end: 인식 종료 시 호출할 콜백
            on_error: 에러 발생 시 호출할 콜백
            
        Raises:
            STTError: 음성 인식 시작 실패 시
        """
        if self.is_running:
            logger.debug("이미 인식 중입니다")
            return
            
        # 콜백 설정
        self.on_recognition_start = on_recognition_start
        self.on_recognition_result = on_recognition_result
        self.on_recognition_end = on_recognition_end
        self.on_error = on_error
        
        # 초기화 확인
        self.initialize()
        
        # 인식 스레드 시작
        self.is_running = True
        self.stop_event.clear()
        
        self.recognition_thread = threading.Thread(
            target=self._recognition_thread_func,
            daemon=True,
            name="STT-Thread"
        )
        self.recognition_thread.start()
        logger.info("음성 인식 시작됨")
    
    def stop(self):
        """음성 인식 중지"""
        if not self.is_running:
            return
            
        self.stop_event.set()
        
        if self.recognition_thread and self.recognition_thread.is_alive():
            self.recognition_thread.join(timeout=2.0)
            
        self.is_running = False
        logger.info("음성 인식 중지됨")
    
    def _process_result(self, text: str):
        """
        인식 결과 처리
        
        Args:
            text: 인식된 텍스트
        """
        if not text or not text.strip():
            return
            
        # 텍스트 정규화
        text = text.strip()
        
        # 콜백 호출
        if self.on_recognition_result:
            try:
                self.on_recognition_result(text)
            except Exception as e:
                logger.error(f"인식 결과 콜백 오류: {e}")
        
        # 큐에 추가
        self.text_queue.put(text)
        logger.debug(f"인식 결과: {text}")
    
    def _recognition_thread_func(self):
        """음성 인식 스레드 함수"""
        if not self.recorder:
            logger.error("음성 인식기가 초기화되지 않았습니다")
            return
            
        try:
            # 콜백 호출
            if self.on_recognition_start:
                self.on_recognition_start()
                
            with self.recorder as recorder:
                self.is_recording = True
                
                while not self.stop_event.is_set():
                    # 음성 인식 시도
                    retry_count = 0
                    while retry_count < self.max_retries:
                        try:
                            # 타임아웃 처리
                            start_time = time.time()
                            result = recorder.text()
                            
                            # 텍스트가 있는 경우만 처리
                            if result and result.strip():
                                self._process_result(result)
                                
                            # 짧은 대기 (CPU 사용률 최적화)
                            if not self.stop_event.wait(0.1):
                                break
                                
                        except Exception as e:
                            retry_count += 1
                            logger.warning(f"음성 인식 오류 (재시도 {retry_count}/{self.max_retries}): {e}")
                            
                            # 콜백 호출
                            if self.on_error:
                                self.on_error(e)
                                
                            # 마지막 시도가 아니면 재시도
                            if retry_count < self.max_retries:
                                time.sleep(self.retry_interval)
                            else:
                                logger.error(f"최대 재시도 횟수 초과: {e}")
                        
        except Exception as e:
            logger.error(f"음성 인식 스레드 오류: {e}")
            
            # 콜백 호출
            if self.on_error:
                self.on_error(e)
                
        finally:
            self.is_recording = False
            
            # 콜백 호출
            if self.on_recognition_end:
                self.on_recognition_end()
    
    def get_next_text(self, timeout: Optional[float] = None) -> Optional[str]:
        """
        다음 인식 결과 가져오기 (블로킹)
        
        Args:
            timeout: 대기 타임아웃 (초)
            
        Returns:
            인식된 텍스트 (타임아웃 시 None)
        """
        try:
            return self.text_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def get_all_text(self) -> List[str]:
        """
        모든 인식 결과 가져오기 (논블로킹)
        
        Returns:
            인식된 텍스트 리스트
        """
        results = []
        while not self.text_queue.empty():
            try:
                results.append(self.text_queue.get_nowait())
            except queue.Empty:
                break
        return results
    
    def release(self):
        """리소스 정리"""
        self.stop()
        
        # 큐 정리
        while not self.text_queue.empty():
            try:
                self.text_queue.get_nowait()
            except:
                pass
                
        # 레코더 정리
        if self.recorder:
            try:
                self.recorder.shutdown()
            except:
                pass
                
        self.recorder = None
        logger.info("음성 인식기 리소스 정리 완료")
    
    def __enter__(self):
        """컨텍스트 매니저 진입"""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        self.release()