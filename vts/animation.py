# ai_vtuber/vts/animation.py

"""VTube Studio 캐릭터 애니메이션 제어 모듈"""

import random
import time
import threading
import math
import numpy as np
from typing import Optional, Callable

from ..utils.logging import get_logger
from .api_helper import VTubeStudioAPI

logger = get_logger(__name__)

class AnimationController:
    """VTube Studio 캐릭터 애니메이션 제어 클래스"""
    
    def __init__(
        self, 
        vts_api: VTubeStudioAPI,
        blink_min_interval: float = 3.0,
        blink_max_interval: float = 6.0,
        mouth_update_interval: float = 0.05
    ):
        """
        애니메이션 컨트롤러 초기화
        
        Args:
            vts_api: VTube Studio API 인스턴스
            blink_min_interval: 최소 눈 깜빡임 간격 (초)
            blink_max_interval: 최대 눈 깜빡임 간격 (초)
            mouth_update_interval: 입 움직임 업데이트 간격 (초)
        """
        self.vts_api = vts_api
        self.blink_min_interval = blink_min_interval
        self.blink_max_interval = blink_max_interval
        self.mouth_update_interval = mouth_update_interval
        
        # 스레드 제어
        self.stop_event = threading.Event()
        self.blink_thread = None
        
        # 입 움직임 상태
        self.current_mouth_value = 0.0
        self.target_mouth_value = 0.0
        self.last_mouth_update = 0
        
    def start_blink_animation(self) -> bool:
        """
        자동 눈 깜빡임 스레드 시작
        
        Returns:
            시작 성공 여부
        """
        if self.blink_thread and self.blink_thread.is_alive():
            logger.info("눈 깜빡임 스레드가 이미 실행 중입니다")
            return False
            
        self.stop_event.clear()
        self.blink_thread = threading.Thread(
            target=self._blink_thread_func,
            daemon=True,
            name="VTS-Blink-Thread"
        )
        self.blink_thread.start()
        logger.info("눈 깜빡임 애니메이션 시작됨")
        return True
    
    def stop_animations(self):
        """모든 애니메이션 스레드 중지"""
        self.stop_event.set()
        
        if self.blink_thread and self.blink_thread.is_alive():
            self.blink_thread.join(timeout=2.0)
            logger.info("눈 깜빡임 애니메이션 중지됨")
    
    def _blink_thread_func(self):
        """눈 깜빡임 스레드 함수"""
        logger.info("눈 깜빡임 스레드 시작")
        
        try:
            while not self.stop_event.is_set():
                # 다음 깜빡임까지 대기
                wait_time = random.uniform(
                    self.blink_min_interval, 
                    self.blink_max_interval
                )
                
                if self.stop_event.wait(wait_time):
                    break
                
                # 눈 깜빡임 시퀀스
                self._blink_sequence()
                
        except Exception as e:
            logger.error(f"눈 깜빡임 스레드 오류: {e}")
    
    def _blink_sequence(self):
        """눈 깜빡임 애니메이션 시퀀스"""
        try:
            # 눈 감기
            self.vts_api.inject_eye_blink(0.0, 0.0)
            time.sleep(0.1)
            
            # 살짝 뜨기
            self.vts_api.inject_eye_blink(0.3, 0.3)
            time.sleep(0.05)
            
            # 완전히 뜨기
            self.vts_api.inject_eye_blink(1.0, 1.0)
            
        except Exception as e:
            logger.debug(f"눈 깜빡임 시퀀스 오류: {e}")
    
    def update_mouth_for_audio(self, audio_chunk: bytes, dtype: np.dtype, channels: int = 1):
        """
        오디오 데이터 기반 입 움직임 업데이트
        
        Args:
            audio_chunk: 오디오 데이터 바이트
            dtype: 오디오 데이터 넘파이 타입 (np.int16 등)
            channels: 오디오 채널 수
        """
        now = time.time()
        if now - self.last_mouth_update < self.mouth_update_interval:
            return
            
        try:
            # 오디오 데이터 분석
            data = np.frombuffer(audio_chunk, dtype=dtype)
            if channels > 1:
                data = data.reshape(-1, channels).mean(axis=1)
            
            # 음성 강도에 따른 입 움직임 값 계산
            rms = math.sqrt(np.mean(data.astype(np.float32) ** 2))
            
            # 볼륨에 따른 적절한 입 움직임 매핑 (로그 스케일 사용)
            mouth_value = min(0.3 * math.log(1 + rms / 5000.0), 1.0)
            
            # 입 움직임 변화 부드럽게 처리
            self.target_mouth_value = mouth_value
            self.current_mouth_value = self.current_mouth_value * 0.5 + self.target_mouth_value * 0.5
            
            # VTS에 입 움직임 값 전송
            self.vts_api.inject_mouth_value(self.current_mouth_value)
            self.last_mouth_update = now
            
        except Exception as e:
            logger.debug(f"입 움직임 업데이트 오류: {e}")
    
    def reset_mouth(self):
        """입 움직임 초기화 (닫기)"""
        try:
            self.vts_api.inject_mouth_value(0.0)
            self.current_mouth_value = 0.0
            self.target_mouth_value = 0.0
        except Exception as e:
            logger.debug(f"입 움직임 초기화 오류: {e}")