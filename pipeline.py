import copy
import logging
import queue
import random
import threading
import time
from typing import List, Optional

from ai_vtuber.config import Config
from ai_vtuber.exceptions import LLMError, TTSError
from ai_vtuber.llm.classifier import SpeechClassifier
from ai_vtuber.llm.ollama_chat import OllamaChat
from ai_vtuber.stt.recorder import SpeechRecognizer
from ai_vtuber.tts.manager import TTSManager
from ai_vtuber.vts.manager import VTSManager

logger = logging.getLogger(__name__)

class AIVTubePipeline:
    def __init__(self, config: Optional[Config] = None):
        """
        AI VTuber 파이프라인 초기화
        
        Args:
            config: 설정 객체 (None이면 기본값 사용)
        """
        self.config = config or Config()
        
        # 큐 초기화
        self.recognized_queue = queue.Queue()
        self.tts_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.last_activity_time = time.time()
        self.threads = []

        # 구성 요소 초기화
        self.vts_manager = VTSManager(self.config)
        self.ollama_session = OllamaChat(self.config)
        self.tts_manager = TTSManager(self.config)
        self.speech_classifier = SpeechClassifier(self.config.ollama_model)
        
        # STT 초기화 (레코더)
        self.speech_recognizer = SpeechRecognizer(
            self.config, 
            on_text_recognized=lambda text: self.recognized_queue.put(text)
        )
        
    ###########################################################################
    # (1) STT 스레드
    ###########################################################################
    def stt_thread_func(self) -> None:
        """
        마이크 음성을 RealtimeSTT로 계속 인식.
        인식된 텍스트를 recognized_queue에 넣는다.
        """
        self.speech_recognizer.start_listening(self.stop_event)

    ###########################################################################
    # (2) 눈 깜빡임 스레드
    ###########################################################################
    def blink_thread_func(self) -> None:
        """
        일정 간격(3~6초)으로 VTS에 눈 깜빡임 파라미터를 넣어
        캐릭터가 주기적으로 눈을 감았다 뜨게 한다.
        """
        logger.info("[VTS] 눈 깜빡임 스레드 시작")
        
        while not self.stop_event.is_set():
            wait_time = random.uniform(
                self.config.blink_min_interval, 
                self.config.blink_max_interval
            )
            time.sleep(wait_time)
            
            if self.stop_event.is_set():
                break
                
            # 눈 감기
            self.vts_manager.inject_eye_blink(1.0, 1.0)
            time.sleep(0.15)  # 눈 감은 상태 유지
            
            # 눈 뜨기
            self.vts_manager.inject_eye_blink(0.0, 0.0)
            
        logger.info("[VTS] 눈 깜빡임 스레드 종료")

    ###########################################################################
    # (3) TTS 스레드 (합성 & 재생)
    ###########################################################################
    def tts_streaming_worker(self) -> None:
        """
        tts_queue에서 텍스트 chunk를 꺼내어 스트리밍 TTS → 오디오 재생.
        """
        logger.info("[TTS] 스트리밍 작업자 스레드 시작")
        
        while not self.stop_event.is_set():
            try:
                text_chunk = self.tts_queue.get(timeout=1)
            except queue.Empty:
                continue

            try:
                # 텍스트 정규화 (TTS 품질 향상을 위한 전처리)
                text_chunk = self.tts_manager.normalize_text_for_tts(text_chunk)
                
                # TTS 합성 및 재생 (통합 함수 사용)
                self.tts_manager.synthesize_and_play(
                    text_chunk, 
                    self.vts_manager
                )
                logger.info("[TTS 재생 완료] 텍스트: %s", text_chunk)
                
            except TTSError as e:
                logger.error("TTS 합성/재생 오류: %s", e)
            except Exception as e:
                logger.error("TTS 처리 중 예상치 못한 오류: %s", e)
            finally:
                self.tts_queue.task_done()
                
        logger.info("[TTS] 스트리밍 작업자 스레드 종료")

    ###########################################################################
    # (4) 메인 루프: 사용자가 말한 텍스트 처리
    ###########################################################################
    def main_loop(self) -> None:
        """
        1) recognized_queue에서 사용자 텍스트 받기
        2) 분류(YES/NO) → YES면 챗봇 응답, NO면 '기타 대화'로 기록
        3) 챗봇 응답(스트리밍) 중간중간 TTS 큐에 넣어 실시간 재생
        """
        logger.info("파이프라인 시작. (Ctrl+C로 종료)\n")
        
        try:
            while not self.stop_event.is_set():
                # 1) 사용자 입력 대기
                try:
                    recognized_text = self.recognized_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                # 공백 입력은 무시
                if not recognized_text.strip():
                    continue

                # 2) AI 호출 분류
                is_directed_to_ai = self.speech_classifier.is_directed_to_ai(recognized_text)

                if is_directed_to_ai:
                    self._process_direct_query(recognized_text)
                else:
                    self._process_background_chat(recognized_text)

        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt -> 프로그램 종료 요청")
        except Exception as e:
            logger.error(f"메인 루프 중 오류 발생: {e}")
        finally:
            self.stop_event.set()
            
    def _process_direct_query(self, text: str) -> None:
        """AI에게 직접 질의한 경우 처리"""
        # AI에게 직접 말한 문장
        print(f"\n[사용자 → AI] {text}\n")
        # 대화 히스토리에 user 추가
        self.ollama_session.add_user_message(text)

        # Ollama 스트리밍 응답
        history_snapshot = copy.deepcopy(self.ollama_session.conversation_history)
        full_response = ""
        token_buffer = ""

        try:
            for token in self.ollama_session.stream_response(history_snapshot):
                full_response += token
                token_buffer += token

                # 길이나 구두점 단위로 chunk를 잘라 TTS 큐에 넣음
                if (len(token_buffer) > self.config.tts_chunk_size or 
                    token.endswith(('.', '!', '?', ':', ';'))):
                    if token_buffer.strip():
                        self.tts_queue.put(token_buffer)
                        print(f"[TTS 큐 추가] {token_buffer}")
                        token_buffer = ""
                        time.sleep(0.05)

            # 남은 token_buffer가 있으면 마지막 chunk로 처리
            if token_buffer.strip():
                self.tts_queue.put(token_buffer)
                print(f"[TTS 큐 추가(마무리)] {token_buffer}")

            # 최종 응답 기록
            self.ollama_session.add_assistant_message(full_response)
            print(f"[Ollama 응답] {full_response}\n")
            
        except LLMError as e:
            logger.error(f"LLM 응답 처리 중 오류: {e}")
            # 오류 메시지를 사용자에게 알림
            error_msg = "죄송합니다, 응답을 생성하는 중에 문제가 발생했습니다."
            self.tts_queue.put(error_msg)
            
    def _process_background_chat(self, text: str) -> None:
        """기타 대화 처리"""
        # NO -> 기타 대화
        print(f"[기타 대화] {text}")
        # '기타대화' 태그를 달아 히스토리에 기록만
        self.ollama_session.add_background_message(text)
        # AI는 응답 X

    ###########################################################################
    # 실행 / 종료
    ###########################################################################
    def start(self) -> None:
        """
        모든 스레드를 시작하고 main_loop()를 돌려 파이프라인을 구동한다.
        """
        # STT 스레드
        stt_thread = threading.Thread(
            target=self.stt_thread_func, 
            daemon=True,
            name="STT-Thread"
        )
        stt_thread.start()
        self.threads.append(stt_thread)

        # Blink(눈깜빡임) 스레드
        blink_thread = threading.Thread(
            target=self.blink_thread_func, 
            daemon=True,
            name="Blink-Thread"
        )
        blink_thread.start()
        self.threads.append(blink_thread)

        # TTS 합성 & 재생 스레드
        tts_thread = threading.Thread(
            target=self.tts_streaming_worker, 
            daemon=True,
            name="TTS-Thread"
        )
        tts_thread.start()
        self.threads.append(tts_thread)

        # 메인 루프 (현재 스레드에서)
        self.main_loop()

    def stop(self) -> None:
        """
        stop_event를 통해 모든 스레드 종료 신호를 보낸 뒤 join,
        VTS 연결도 정리.
        """
        self.stop_event.set()
        logger.info("종료 요청됨, 스레드 정리 중...")
        
        # 각 스레드 정리
        for t in self.threads:
            try:
                t.join(timeout=self.config.thread_timeout)
            except Exception as e:
                logger.warning(f"스레드 '{t.name}' 종료 중 오류: {e}")
        
        # 리소스 정리
        try:
            if hasattr(self, 'vts_manager'):
                self.vts_manager.close()
                
        except Exception as e:
            logger.error(f"리소스 정리 중 오류: {e}")
            
        logger.info("프로그램 정상 종료.")