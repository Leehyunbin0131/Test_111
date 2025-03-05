# ai_vtuber/llm/chat.py

"""Ollama LLM 대화 관리 모듈"""

import hashlib
import time
from typing import Dict, List, Any, Generator, Optional, Union
from collections import deque

from ollama import chat

from ..utils.logging import get_logger
from ..utils.errors import LLMError

logger = get_logger(__name__)

class OllamaChat:
    """Ollama LLM 대화 관리 클래스"""
    
    def __init__(
        self, 
        model: str,
        system_message: str,
        max_history: int = 12,
        temperature: float = 0.7,
        request_timeout: float = 30.0
    ):
        """
        Ollama 챗봇 초기화
        
        Args:
            model: Ollama 모델명
            system_message: 시스템 메시지
            max_history: 최대 대화 히스토리 길이
            temperature: 응답 다양성 (0.0 ~ 1.0)
            request_timeout: 요청 타임아웃 (초)
        """
        self.model = model
        self.system_message = {'role': 'system', 'content': system_message}
        self.max_history = max_history
        self.temperature = temperature
        self.request_timeout = request_timeout
        
        # 대화 히스토리 (deque 사용으로 최적화)
        self.conversation_history = deque(maxlen=max_history)
        
        # 중복 메시지 필터링을 위한 해시 캐시
        self._msg_cache = {}
        self._msg_cache_maxlen = 10
        
        logger.info(f"Ollama 챗봇 초기화 완료 (모델: {model})")
    
    def stream_response(
        self, 
        history: Optional[List[Dict[str, str]]] = None
    ) -> Generator[str, None, None]:
        """
        Ollama 응답 스트리밍
        
        Args:
            history: 대화 히스토리 (없으면 현재 히스토리 사용)
            
        Returns:
            응답 토큰 제너레이터
            
        Raises:
            LLMError: LLM 요청/응답 오류
        """
        try:
            # 전체 대화 히스토리 구성
            full_history = [self.system_message] + list(history or self.conversation_history)
            
            start_time = time.time()
            logger.debug(f"Ollama 요청 시작 (토큰 수: {len(full_history)})")
            
            # 요청 옵션 설정
            options = {
                "temperature": self.temperature,
                "num_predict": 512  # 최대 토큰 수 제한
            }
            
            # 스트리밍 응답 처리
            for token in chat(
                model=self.model, 
                messages=full_history, 
                stream=True,
                options=options
            ):
                yield token.get('message', {}).get('content', '')
                
            logger.debug(f"Ollama 응답 완료 (소요시간: {time.time() - start_time:.2f}초)")
            
        except Exception as e:
            logger.error(f"Ollama 응답 오류: {e}")
            raise LLMError(f"응답 생성 실패: {e}")
    
    def add_user_message(self, message: str) -> bool:
        """
        사용자 메시지 추가 (중복 필터링)
        
        Args:
            message: 사용자 메시지
            
        Returns:
            추가 성공 여부 (중복 시 False)
        """
        if not message or not message.strip():
            return False
            
        # 메시지 정규화 및 해시
        norm_msg = message.strip().lower()
        msg_hash = hashlib.md5(norm_msg.encode()).hexdigest()
        
        # 중복 확인
        if msg_hash in self._msg_cache:
            logger.debug(f"중복 메시지 필터링됨: {message[:30]}...")
            return False
            
        # 메시지 추가
        self.conversation_history.append({'role': 'user', 'content': message})
        
        # 캐시 업데이트
        self._msg_cache[msg_hash] = time.time()
        self._trim_msg_cache()
        
        return True
    
    def add_assistant_message(self, message: str):
        """
        어시스턴트 응답 추가
        
        Args:
            message: 어시스턴트 응답
        """
        if message and message.strip():
            self.conversation_history.append({'role': 'assistant', 'content': message})
    
    def add_background_message(self, message: str):
        """
        배경 대화 메시지 추가 (AI 학습용)
        
        Args:
            message: 배경 대화 메시지
        """
        if message and message.strip():
            self.conversation_history.append({
                'role': 'user', 
                'content': f"(기타대화) {message}"
            })
    
    def _trim_msg_cache(self):
        """메시지 캐시 크기 관리"""
        if len(self._msg_cache) > self._msg_cache_maxlen:
            # 오래된 항목부터 제거
            oldest_keys = sorted(
                self._msg_cache.keys(), 
                key=lambda k: self._msg_cache[k]
            )[:len(self._msg_cache) - self._msg_cache_maxlen]
            
            for key in oldest_keys:
                del self._msg_cache[key]
    
    def clear_history(self):
        """대화 히스토리 초기화"""
        self.conversation_history.clear()
        self._msg_cache.clear()
    
    def get_history_as_list(self) -> List[Dict[str, str]]:
        """
        대화 히스토리를 리스트로 반환
        
        Returns:
            대화 히스토리 리스트
        """
        return list(self.conversation_history)