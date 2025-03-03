import logging
import math
import struct
import time
from typing import Generator, Optional, Tuple

import numpy as np
import pyaudio
import requests

from ai_vtuber.config import Config
from ai_vtuber.exceptions import TTSError
from ai_vtuber.vts.manager import VTSManager

logger = logging.getLogger(__name__)

class TTSManager:
    """TTS 합성 및 재생을 관리하는 클래스"""
    
    def __init__(self, config: Config):
        self.config = config
        self.pyaudio_instance = pyaudio.PyAudio()  # 한 번만 초기화
        
    def __del__(self):
        """리소스 정리"""
        try:
            self.pyaudio_instance.terminate()
        except:
            pass
    
    def synthesize_audio(self, text: str) -> Tuple[Generator[bytes, None, None], int, int, int]:
        """
        TTS 서버에 요청해 WAV를 스트리밍으로 받아온다.
        (헤더만 먼저 파싱 후, 나머지는 chunk 단위로 yield)
        
        Returns:
            Tuple[Generator, sample_rate, channels, bits_per_sample]
        
        Raises:
            TTSError: TTS 처리 실패 시
        """
        params = {
            "text": text,
            "text_lang": "ko",
            "ref_audio_path": self.config.default_ref_audio,
            "prompt_text": self.config.default_prompt_text,
            "prompt_lang": self.config.default_prompt_lang,
            "text_split_method": "cut5",
            "batch_size": 1,
            "media_type": "wav",
            "streaming_mode": "true"
        }
        logger.info("[TTS 합성] 요청 텍스트: %s", text)

        try:
            # 서버에 스트리밍 GET 요청
            response = requests.get(self.config.tts_server_url, params=params, stream=True)
            response.raise_for_status()

            # 1) WAV 헤더(44바이트)만 먼저 수신
            header = b""
            while len(header) < 44:
                chunk = response.raw.read(44 - len(header))
                if not chunk:
                    break
                header += chunk
                
            if len(header) < 44:
                raise TTSError("WAV 헤더를 충분히 읽지 못했습니다.")

            # 2) 헤더 검사
            riff, size, wave_, fmt = struct.unpack('<4sI4s4s', header[:16])
            if riff != b'RIFF' or wave_ != b'WAVE':
                raise TTSError("유효한 WAV 파일이 아닙니다.(RIFF/WAVE 오류)")

            audio_format, num_channels, sample_rate, byte_rate, block_align, bits_per_sample = struct.unpack('<HHIIHH', header[20:36])
            data_chunk_id = header[36:40]
            
            if data_chunk_id != b'data':
                raise TTSError("data 청크가 없습니다.")
                
            data_size = struct.unpack('<I', header[40:44])[0]

            logger.info("[TTS 합성] sample_rate=%d, channels=%d, bits=%d, data_size=%d",
                        sample_rate, num_channels, bits_per_sample, data_size)

            # 3) 나머지 오디오 데이터를 조금씩 읽어내기 (chunk)
            chunk_size = 1024
            def audio_generator():
                while True:
                    chunk_data = response.raw.read(chunk_size)
                    if not chunk_data:
                        break
                    yield chunk_data

            return audio_generator(), sample_rate, num_channels, bits_per_sample
            
        except requests.RequestException as e:
            raise TTSError(f"TTS 서버 요청 실패: {e}") from e
        except struct.error as e:
            raise TTSError(f"WAV 헤더 파싱 실패: {e}") from e
        except Exception as e:
            raise TTSError(f"TTS 합성 중 오류: {e}") from e

    def play_audio(self, audio_chunks: Generator[bytes, None, None], 
                 sample_rate: int, channels: int, bits_per_sample: int,
                 vts_api: Optional[VTSManager] = None) -> None:
        """
        chunk generator로부터 오디오 데이터를 받자마자 PyAudio로 재생.
        재생 중 RMS를 구해 VTS에 mouth param을 주입하여 입 모션 동기화.
        
        Raises:
            TTSError: 오디오 재생 실패 시
        """
        # 샘플 폭(bits_per_sample)에 따른 pyaudio 포맷 & numpy dtype 결정
        format_map = {
            8: (pyaudio.paInt8, np.int8, 1),
            16: (pyaudio.paInt16, np.int16, 2),
            24: (pyaudio.paInt24, np.int32, 3),  # 24비트 -> int32 사용
            32: (pyaudio.paInt32, np.int32, 4)
        }
        
        if bits_per_sample not in format_map:
            raise TTSError(f"지원되지 않는 샘플 폭: {bits_per_sample}")
            
        pa_format, dtype, sample_width = format_map[bits_per_sample]
        
        try:
            stream_out = self.pyaudio_instance.open(
                format=pa_format, 
                channels=channels, 
                rate=sample_rate, 
                output=True
            )

            last_inject_time = time.time()
            inject_interval = self.config.mouth_update_interval

            # chunk generator에서 데이터가 들어올 때마다 재생
            for chunk in audio_chunks:
                stream_out.write(chunk)

                # VTS에 mouth 모션 전송
                if vts_api and vts_api.api:
                    now = time.time()
                    if now - last_inject_time >= inject_interval:
                        # 오디오 데이터 분석 및 입 움직임 계산
                        data_array = np.frombuffer(chunk, dtype=dtype)
                        if channels > 1:
                            # stereo/multi 채널이면 평균
                            data_array = data_array.reshape(-1, channels).mean(axis=1)
                        
                        # 음성 강도에 따른 입 움직임 값 (0.0~1.0)
                        # 더 정교한 알고리즘 적용
                        rms = math.sqrt(np.mean(data_array.astype(np.float32) ** 2))
                        # 로그 스케일 적용으로 작은 소리도 반응하게
                        mouth_value = min(0.3 * math.log(1 + rms / 5000.0), 1.0)
                        
                        vts_api.inject_mouth_value(mouth_value)
                        last_inject_time = now

            # 재생 종료 처리
            stream_out.stop_stream()
            stream_out.close()

            # 입 모션 초기화(0으로)
            if vts_api and vts_api.api:
                vts_api.inject_mouth_value(0.0)
                
        except Exception as e:
            raise TTSError(f"오디오 재생 중 오류: {e}") from e

    def synthesize_and_play(self, text: str, vts_manager: Optional[VTSManager] = None) -> None:
        """TTS 합성 및 재생을 한번에 처리하는 편의 함수"""
        try:
            audio_gen, sr, ch, bps = self.synthesize_audio(text)
            self.play_audio(audio_gen, sr, ch, bps, vts_manager)
            logger.info("[TTS 재생 완료] 텍스트: %s", text)
        except TTSError as e:
            logger.error("TTS 처리 오류: %s", e)
            raise
            
    def normalize_text_for_tts(self, text: str) -> str:
        """TTS를 위한 텍스트 정규화"""
        import re
        # 여러 줄바꿈 제거
        text = re.sub(r'\n+', ' ', text)
        # 여러 공백 제거
        text = re.sub(r'\s+', ' ', text)
        # 특수 문자 처리
        text = text.replace('...', '… ')
        return text.strip()