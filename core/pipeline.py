# ai_vtuber/core/pipeline.py

"""AI VTuber 시스템 메인 파이프라인"""

import queue
import time
import threading
import re
from typing import Optional, Dict, Any, List, Callable

from ..utils.logging import get_logger
from ..config.settings import Settings
from ..vts.api_helper import VTubeStudioAPI
from ..vts.animation import AnimationController
from ..llm.chat import OllamaChat
from ..llm.classifier import SpeechClassifier
from ..tts.synthesizer import TTSManager
from ..stt.recorder import SpeechRecognizer

logger = get_logger(__name__)

class AIVTubePipeline:
    """AI VTuber 통합 파이프라인 클래스"""
    
    def __init__(self, settings: Settings):
        """
        AI VTuber 파이프라인 초기화
        
        Args:
            settings: 시스템 설정
        """
        self.settings = settings
        
        # 큐 및 이벤트
        self.recognized_queue = queue.Queue()
        self.tts_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.threads = []
        self.is_speaking = threading.Event()  # 현재 말하는 중인지
        
        # 초기화 플래그
        self._initialized = False
        self._components_initialized = False
        
        logger.info("AI VTuber 파이프라인 생성됨")
    
    def initialize(self):
        """
        파이프라인 초기화
        
        모든 구성 요소를 초기화하고 준비합니다.
        """
        if self._initialized:
            return
            
        try:
            logger.info("파이프라인 초기화 중...")
            
            # VTube Studio API 초기화
            self.vts_api = VTubeStudioAPI(
                self.settings.vts_plugin_name,
                self.settings.vts_plugin_developer,
                self.settings.vts_host,
                self.settings.vts_port
            )
            
            # 애니메이션 컨트롤러 초기화
            self.animation_controller = AnimationController(
                self.vts_api,
                self.settings.blink_min_interval,
                self.settings.blink_max_interval,
                self.settings.mouth_update_interval
            )
            
            # Ollama 챗봇 초기화
            self.ollama_session = OllamaChat(
                self.settings.ollama_model,
                self.settings.ollama_system_message,
                self.settings.ollama_max_history
            )
            
            # TTS 관리자 초기화
            self.tts_manager = TTSManager(
                self.settings.tts_server_url,
                self.settings.default_ref_audio,
                self.settings.default_prompt_text,
                self.settings.default_prompt_lang
            )
            
            # 음성 분류기 초기화
            self.speech_classifier = SpeechClassifier(
                self.settings.ollama_model
            )
            
            # STT 인식기 초기화
            self.speech_recognizer = SpeechRecognizer(
                model=self.settings.stt_model,
                language=self.settings.stt_language,
                device=self.settings.stt_device,
                gpu_device_index=self.settings.stt_gpu_device_index
            )
            
            self._components_initialized = True
            self._initialized = True
            logger.info("파이프라인 초기화 완료")
            
        except Exception as e:
            logger.error(f"파이프라인 초기화 실패: {e}")
            self.stop_event.set()
            raise
    
    def stt_thread_func(self):
        """음성 인식 스레드 함수"""
        logger.info("[STT] 인식 시작")
        
        # 인식 이벤트 콜백
        def on_recognition_result(text):
            if text and text.strip():
                logger.info(f"[입력 인식] {text}")
                self.recognized_queue.put(text.strip())
        
        try:
            # 인식 시작
            self.speech_recognizer.start(
                on_recognition_result=on_recognition_result,
                on_error=lambda e: logger.error(f"[STT] 오류: {e}")
            )
            
            # 종료 이벤트 대기
            while not self.stop_event.is_set():
                time.sleep(0.5)
                
        except Exception as e:
            logger.error(f"STT 스레드 오류: {e}")
        finally:
            self.speech_recognizer.stop()
            logger.info("[STT] 인식 종료")
    
    def tts_thread_func(self):
        """TTS 처리 스레드 함수"""
        logger.info("[TTS] 스레드 시작")
        
        try:
            while not self.stop_event.is_set():
                try:
                    # 큐에서 텍스트 가져오기
                    text = self.tts_queue.get(timeout=1)
                    if not text:
                        continue
                        
                    # 전처리 (개행, 공백, 특수문자 정규화)
                    text = re.sub(r'\n+', ' ', text)
                    text = re.sub(r'\s+', ' ', text)
                    text = text.replace('...', '… ')
                    
                    # 합성 중 플래그 설정
                    self.is_speaking.set()
                    
                    # TTS 합성 및 재생
                    self.tts_manager.synthesize_and_play(
                        text.strip(), 
                        self.vts_api,
                        on_complete=lambda: self.is_speaking.clear()
                    )
                    
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.error(f"[TTS] 오류: {e}")
                    self.is_speaking.clear()
                finally:
                    self.tts_queue.task_done()
                    
        except Exception as e:
            logger.error(f"TTS 스레드 오류: {e}")
        finally:
            logger.info("[TTS] 스레드 종료")
    
    def split_text_into_chunks(self, text: str, max_size: int = 40) -> List[str]:
        """
        긴 텍스트를 TTS용 적절한 크기로 분할
        
        Args:
            text: 분할할 텍스트
            max_size: 최대 청크 크기
            
        Returns:
            분할된 텍스트 리스트
        """
        # 이미 짧은 텍스트는 바로 반환
        if len(text) <= max_size:
            return [text]
            
        # 문장 단위로 분할
        sentences = re.split(r'([.!?。]+\s*)', text)
        chunks = []
        current_chunk = ""
        
        # 문장 단위로 합치기
        for i in range(0, len(sentences), 2):
            sentence = sentences[i]
            ending = sentences[i+1] if i+1 < len(sentences) else ""
            
            # 현재 청크에 문장 추가 가능한지 확인
            if len(current_chunk) + len(sentence) + len(ending) <= max_size:
                current_chunk += sentence + ending
            else:
                # 현재 청크가 있으면 저장
                if current_chunk:
                    chunks.append(current_chunk)
                
                # 새 문장이 최대 크기보다 크면 강제 분할
                if len(sentence) + len(ending) > max_size:
                    # 단어 단위로 분할
                    words = re.split(r'(\s+)', sentence + ending)
                    sub_chunk = ""
                    
                    for word in words:
                        if len(sub_chunk) + len(word) <= max_size:
                            sub_chunk += word
                        else:
                            if sub_chunk:
                                chunks.append(sub_chunk)
                            sub_chunk = word
                    
                    if sub_chunk:
                        current_chunk = sub_chunk
                    else:
                        current_chunk = ""
                else:
                    current_chunk = sentence + ending
        
        # 마지막 청크 추가
        if current_chunk:
            chunks.append(current_chunk)
            
        return chunks
    
    def process_llm_response(self, text: str):
        """
        LLM 응답 처리 및 TTS 전송
        
        Args:
            text: 처리할 텍스트
        """
        if not text or not text.strip():
            return
            
        # 청크로 분할
        chunks = self.split_text_into_chunks(text, self.settings.tts_chunk_size)
        
        # TTS 큐에 전송
        for chunk in chunks:
            if chunk.strip():
                self.tts_queue.put(chunk.strip())
                logger.info(f"[TTS 전송] {chunk.strip()}")
    
    def main_loop(self):
        """메인 처리 루프"""
        logger.info("AI VTuber 파이프라인 시작")
        
        try:
            while not self.stop_event.is_set():
                # 사용자 입력 대기
                try:
                    text = self.recognized_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                # 현재 말하는 중인지 확인
                is_busy = self.is_speaking.is_set()

                # 발화 분류 (AI에게 직접 말한 것인지)
                if self.speech_classifier.is_directed_to_ai(text):
                    logger.info(f"[사용자→AI] {text}")
                    
                    # AI가 말하는 중이면 잠시 대기
                    if is_busy:
                        logger.info("현재 말하는 중. 응답 준비...")
                        while self.is_speaking.is_set() and not self.stop_event.is_set():
                            time.sleep(0.1)
                            
                        # 짧은 딜레이로 자연스러운 대화 흐름
                        time.sleep(0.2)
                    
                    # 사용자 메시지 추가
                    self.ollama_session.add_user_message(text)

                    # 응답 생성 및 처리
                    full_response = ""
                    token_buffer = ""

                    try:
                        for token in self.ollama_session.stream_response():
                            if self.stop_event.is_set():
                                break
                                
                            full_response += token
                            token_buffer += token

                            # 적절한 구두점이나 길이에서 분할
                            if (len(token_buffer) > self.settings.tts_chunk_size or 
                                token and token[-1] in '.!?。'):
                                if token_buffer.strip():
                                    self.process_llm_response(token_buffer.strip())
                                    token_buffer = ""

                        # 남은 토큰 처리
                        if token_buffer.strip():
                            self.process_llm_response(token_buffer.strip())
                            
                        # 응답 기록
                        self.ollama_session.add_assistant_message(full_response)
                        logger.info(f"[AI 응답] {full_response}")
                        
                    except Exception as e:
                        logger.error(f"[LLM] 오류: {e}")
                        self.tts_queue.put("죄송합니다, 응답 생성 중 오류가 발생했습니다.")
                else:
                    # 기타 대화 처리
                    logger.info(f"[기타 대화] {text}")
                    self.ollama_session.add_background_message(text)

        except KeyboardInterrupt:
            logger.info("Ctrl+C로 종료 요청")
        except Exception as e:
            logger.error(f"메인 루프 오류: {e}")
        finally:
            self.stop_event.set()
    
    def start(self):
        """모든 스레드 시작 및 메인 루프 실행"""
        # 초기화 확인
        if not self._initialized:
            self.initialize()
            
        # 애니메이션 시작
        self.animation_controller.start_blink_animation()
        
        # STT 스레드
        stt_thread = threading.Thread(
            target=self.stt_thread_func, 
            daemon=True,
            name="STT-Thread"
        )
        stt_thread.start()
        self.threads.append(stt_thread)

        # TTS 스레드
        tts_thread = threading.Thread(
            target=self.tts_thread_func, 
            daemon=True,
            name="TTS-Thread"
        )
        tts_thread.start()
        self.threads.append(tts_thread)

        # 메인 루프 (현재 스레드에서)
        self.main_loop()
    
    def stop(self):
        """모든 리소스 정리"""
        self.stop_event.set()
        logger.info("종료 중...")
        
        # 스레드 종료 대기
        for thread in self.threads:
            thread.join(timeout=self.settings.thread_timeout)
        
        # 구성 요소 정리
        if self._components_initialized:
            # 애니메이션 중지
            if hasattr(self, 'animation_controller'):
                self.animation_controller.stop_animations()
                
            # VTS 연결 종료
            if hasattr(self, 'vts_api'):
                self.vts_api.close()
                
            # TTS 리소스 정리
            if hasattr(self, 'tts_manager'):
                self.tts_manager.close()
                
            # STT 리소스 정리
            if hasattr(self, 'speech_recognizer'):
                self.speech_recognizer.release()
        
        # 큐 정리
        while not self.recognized_queue.empty():
            try:
                self.recognized_queue.get_nowait()
            except:
                pass
                
        while not self.tts_queue.empty():
            try:
                self.tts_queue.get_nowait()
            except:
                pass
        
        logger.info("프로그램 종료됨")
    
    def __enter__(self):
        """컨텍스트 매니저 진입"""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        self.stop()