# ai_vtuber/tts/synthesizer.py

"""음성 합성 및 재생 모듈"""

import struct
import requests
import pyaudio
import numpy as np
import time
import math
import threading
from typing import Generator, Tuple, Dict, Any, Optional, Callable

from ..utils.logging import get_logger
from ..utils.errors import TTSError
from ..vts.api_helper import VTubeStudioAPI

logger = get_logger(__name__)

class TTSManager:
    """TTS 합성 및 재생 관리 클래스"""
    
    def __init__(
        self,
        server_url: str,
        ref_audio_path: str,
        prompt_text: str = "",
        prompt_lang: str = "ko",
        text_lang: str = "ko",
        batch_size: int = 1,
        mouth_update_interval: float = 0.05
    ):
        """
        TTS 관리자 초기화
        
        Args:
            server_url: TTS 서버 URL
            ref_audio_path: 참조 오디오 경로
            prompt_text: 프롬프트 텍스트
            prompt_lang: 프롬프트 언어
            text_lang: 합성할 텍스트 언어
            batch_size: 배치 크기
            mouth_update_interval: 입 움직임 업데이트 간격 (초)
        """
        self.server_url = server_url
        self.ref_audio_path = ref_audio_path
        self.prompt_text = prompt_text
        self.prompt_lang = prompt_lang
        self.text_lang = text_lang
        self.batch_size = batch_size
        self.mouth_update_interval = mouth_update_interval
        
        # PyAudio 인스턴스 (공유)
        self._pyaudio_instance = None
        self._lock = threading.RLock()
        
        logger.info("TTS 관리자 초기화 완료")
    
    @property
    def pyaudio_instance(self):
        """PyAudio 인스턴스 (지연 초기화)"""
        if self._pyaudio_instance is None:
            with self._lock:
                if self._pyaudio_instance is None:
                    self._pyaudio_instance = pyaudio.PyAudio()
        return self._pyaudio_instance
    
    def __del__(self):
        """리소스 정리"""
        self.close()
    
    def close(self):
        """리소스 명시적 정리"""
        if self._pyaudio_instance:
            with self._lock:
                if self._pyaudio_instance:
                    try:
                        self._pyaudio_instance.terminate()
                    except Exception as e:
                        logger.debug(f"PyAudio 종료 중 오류: {e}")
                    finally:
                        self._pyaudio_instance = None
    
    def synthesize_audio(self, text: str) -> Tuple[Generator[bytes, None, None], int, int, int]:
        """
        텍스트를 오디오로 합성
        
        Args:
            text: 합성할 텍스트
            
        Returns:
            (오디오 청크 제너레이터, 샘플 레이트, 채널 수, 비트 깊이)
            
        Raises:
            TTSError: TTS 합성 실패 시
        """
        # TTS 요청 파라미터
        params = {
            "text": text,
            "text_lang": self.text_lang,
            "ref_audio_path": self.ref_audio_path,
            "prompt_text": self.prompt_text,
            "prompt_lang": self.prompt_lang,
            "text_split_method": "cut5",
            "batch_size": self.batch_size,
            "media_type": "wav",
            "streaming_mode": "true"
        }
        
        logger.info(f"[TTS] 요청: {text}")

        try:
            # 서버에 스트리밍 요청
            response = requests.get(
                self.server_url, 
                params=params, 
                stream=True,
                timeout=10.0
            )
            response.raise_for_status()

            # WAV 헤더 파싱
            header = b""
            while len(header) < 44:  # WAV 헤더는 44바이트
                chunk = response.raw.read(44 - len(header))
                if not chunk:
                    break
                header += chunk
                
            if len(header) < 44:
                raise TTSError("WAV 헤더를 충분히 읽지 못했습니다")

            # 헤더 분석
            riff, size, wave = struct.unpack('<4sI4s', header[:12])
            if riff != b'RIFF' or wave != b'WAVE':
                raise TTSError("유효한 WAV 형식이 아닙니다")

            # 포맷 청크 분석
            fmt_chunk_pos = header.find(b'fmt ')
            if fmt_chunk_pos < 0:
                raise TTSError("fmt 청크가 없습니다")
                
            fmt_chunk_data = header[fmt_chunk_pos+8:fmt_chunk_pos+24]
            audio_format, channels, sample_rate, byte_rate, block_align, bits_per_sample = \
                struct.unpack('<HHIIHH', fmt_chunk_data)
                
            # 데이터 청크 위치 찾기
            data_chunk_pos = header.find(b'data')
            if data_chunk_pos < 0:
                raise TTSError("data 청크가 없습니다")

            # 오디오 데이터 스트리밍을 위한 제너레이터
            def audio_chunk_generator():
                chunk_size = 1024 * 4  # 버퍼 크기 최적화
                while True:
                    chunk = response.raw.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk

            return audio_chunk_generator(), sample_rate, channels, bits_per_sample
            
        except requests.RequestException as e:
            raise TTSError(f"TTS 서버 요청 실패: {e}")
        except Exception as e:
            raise TTSError(f"TTS 합성 오류: {e}")

    def play_audio(
        self, 
        audio_chunks: Generator[bytes, None, None], 
        sample_rate: int, 
        channels: int, 
        bits_per_sample: int,
        vts_api: Optional[VTubeStudioAPI] = None
    ):
        """
        오디오 재생
        
        Args:
            audio_chunks: 오디오 데이터 청크 제너레이터
            sample_rate: 샘플 레이트
            channels: 채널 수
            bits_per_sample: 비트 깊이
            vts_api: VTube Studio API 인스턴스 (입 움직임 연동용)
            
        Raises:
            TTSError: 오디오 재생 오류
        """
        # 샘플 폭에 따른 설정
        format_map = {
            8: (pyaudio.paInt8, np.int8),
            16: (pyaudio.paInt16, np.int16),
            24: (pyaudio.paInt24, np.int32),
            32: (pyaudio.paInt32, np.int32)
        }
        
        if bits_per_sample not in format_map:
            raise TTSError(f"지원되지 않는 샘플 폭: {bits_per_sample}")
            
        pa_format, dtype = format_map[bits_per_sample]
        
        try:
            # 오디오 스트림 열기
            stream = self.pyaudio_instance.open(
                format=pa_format, 
                channels=channels, 
                rate=sample_rate, 
                output=True,
                frames_per_buffer=1024  # 버퍼 크기 최적화
            )

            last_inject_time = time.time()
            inject_interval = self.mouth_update_interval
            
            # 볼륨 히스토리 (평활화용)
            volume_history = [0.0] * 3

            # 오디오 재생 & 입 모션 처리
            for chunk in audio_chunks:
                if not chunk:
                    continue
                    
                stream.write(chunk)

                # VTS 입 모션 제어
                if vts_api and getattr(vts_api, 'authenticated', False):
                    now = time.time()
                    if now - last_inject_time >= inject_interval:
                        # 오디오 분석 및 입 움직임 계산
                        data = np.frombuffer(chunk, dtype=dtype)
                        if channels > 1:
                            data = data.reshape(-1, channels).mean(axis=1)
                        
                        # 음성 강도에 따른 입 움직임 값
                        rms = math.sqrt(np.mean(data.astype(np.float32) ** 2))
                        mouth_value = min(0.4 * math.log(1 + rms / 5000.0), 1.0)
                        
                        # 볼륨 평활화 (팝핑 방지)
                        volume_history.append(mouth_value)
                        volume_history.pop(0)
                        smoothed_value = sum(volume_history) / len(volume_history)
                        
                        vts_api.inject_mouth_value(smoothed_value)
                        last_inject_time = now

            # 재생 종료
            stream.stop_stream()
            stream.close()

            # 입 닫기
            if vts_api and getattr(vts_api, 'authenticated', False):
                vts_api.inject_mouth_value(0.0)
                
            logger.debug("오디오 재생 완료")
                
        except Exception as e:
            raise TTSError(f"오디오 재생 오류: {e}")

    def synthesize_and_play(
        self, 
        text: str, 
        vts_api: Optional[VTubeStudioAPI] = None,
        on_complete: Optional[Callable] = None
    ):
        """
        TTS 합성 및 재생 통합 함수
        
        Args:
            text: 합성할 텍스트
            vts_api: VTube Studio API 인스턴스 (입 움직임 연동용)
            on_complete: 재생 완료 후 호출할 콜백 함수
            
        Raises:
            TTSError: TTS 처리 오류
        """
        # 텍스트 전처리
        if not text or not text.strip():
            if on_complete:
                on_complete()
            return
            
        try:
            # TTS 합성
            audio_gen, sr, ch, bps = self.synthesize_audio(text.strip())
            
            # 오디오 재생
            self.play_audio(audio_gen, sr, ch, bps, vts_api)
            logger.info(f"[TTS] 재생 완료: {text}")
            
            # 완료 콜백 호출
            if on_complete:
                on_complete()
                
        except TTSError as e:
            logger.error(f"TTS 처리 오류: {e}")
            if on_complete:
                on_complete()
            raise
    
    def synthesize_and_play_async(
        self, 
        text: str, 
        vts_api: Optional[VTubeStudioAPI] = None,
        on_complete: Optional[Callable] = None
    ) -> threading.Thread:
        """
        TTS 합성 및 재생 비동기 처리
        
        Args:
            text: 합성할 텍스트
            vts_api: VTube Studio API 인스턴스
            on_complete: 재생 완료 후 호출할 콜백 함수
            
        Returns:
            재생 스레드
        """
        thread = threading.Thread(
            target=self._synthesize_and_play_thread,
            args=(text, vts_api, on_complete),
            daemon=True,
            name="TTS-Thread"
        )
        thread.start()
        return thread
    
    def _synthesize_and_play_thread(
        self, 
        text: str, 
        vts_api: Optional[VTubeStudioAPI] = None,
        on_complete: Optional[Callable] = None
    ):
        """
        TTS 합성 및 재생 스레드 함수
        
        Args:
            text: 합성할 텍스트
            vts_api: VTube Studio API 인스턴스
            on_complete: 재생 완료 후 호출할 콜백 함수
        """
        try:
            self.synthesize_and_play(text, vts_api)
        except Exception as e:
            logger.error(f"TTS 스레드 오류: {e}")
        finally:
            if on_complete:
                on_complete()