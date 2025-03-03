import logging
from typing import Dict, Generator, List

from ollama import chat

from ai_vtuber.config import Config
from ai_vtuber.exceptions import LLMError

logger = logging.getLogger(__name__)

class OllamaChat:
    def __init__(self, config: Config) -> None:
        """
        Ollama 기반 챗봇 세션을 관리한다.
        - system_message: AI의 기본 인격/지시사항
        - conversation_history: user/assistant 대화 기록
        """
        self.model = config.ollama_model
        self.max_history = config.ollama_max_history
        self.system_message = {
            'role': 'system',
            'content': config.ollama_system_message
        }
        self.conversation_history: List[Dict[str, str]] = []
        self._msg_cache: Dict[str, str] = {}  # 중복 메시지 필터링용 캐시
    
    def get_response(self, conversation_history: List[Dict[str, str]] = None) -> str:
        """
        Ollama에 일괄 요청(스트리밍X).
        
        Args:
            conversation_history: 선택적 대화 기록, None이면 내부 기록 사용
            
        Returns:
            str: 모델의 응답 텍스트
        
        Raises:
            LLMError: 모델 응답 실패 시
        """
        if conversation_history is None:
            conversation_history = self.conversation_history
            
        try:
            full_history = [self.system_message] + conversation_history
            response = chat(model=self.model, messages=full_history)
            return response.get('message', {}).get('content', "응답을 받지 못했습니다.")
        except Exception as e:
            logger.error("[Ollama] 모델 응답 에러: %s", e)
            raise LLMError(f"모델 응답 실패: {e}") from e

    def stream_response(self, conversation_history: List[Dict[str, str]] = None) -> Generator[str, None, None]:
        """
        Ollama에 스트리밍 모드로 요청.
        토큰(부분 결과)을 순차적으로 yield.
        
        Args:
            conversation_history: 선택적 대화 기록, None이면 내부 기록 사용
            
        Yields:
            str: 토큰 단위의 응답 부분 텍스트
            
        Raises:
            LLMError: 스트리밍 응답 실패 시
        """
        if conversation_history is None:
            conversation_history = self.conversation_history
            
        try:
            full_history = [self.system_message] + conversation_history
            stream_obj = chat(model=self.model, messages=full_history, stream=True)
            for token in stream_obj:
                yield token.get('message', {}).get('content', '')
        except Exception as e:
            logger.error("[Ollama] 스트리밍 응답 에러: %s", e)
            raise LLMError(f"스트리밍 응답 실패: {e}") from e

    def add_user_message(self, message: str) -> None:
        """
        사용자가 말한 내용을 히스토리에 추가.
        중복 메시지는 건너뜀.
        """
        # 중복 메시지 필터링 - 최근 5개 메시지 내 중복만 체크
        msg_hash = hash(message.strip().lower())
        if msg_hash in self._msg_cache:
            logger.debug("[Ollama] 중복 메시지 감지, 무시: %s", message)
            return
            
        self._msg_cache[msg_hash] = message
        # 캐시 크기 제한
        if len(self._msg_cache) > 5:
            old_keys = list(self._msg_cache.keys())[:-5]
            for k in old_keys:
                del self._msg_cache[k]
                
        self.conversation_history.append({'role': 'user', 'content': message})
        self.trim_history()

    def add_assistant_message(self, message: str) -> None:
        """
        AI(assistant) 응답을 히스토리에 추가.
        """
        self.conversation_history.append({'role': 'assistant', 'content': message})
        logger.info("[Ollama] 모델 응답: %s", message)
        self.trim_history()

    def add_background_message(self, message: str) -> None:
        """
        백그라운드 대화(AI에게 직접적으로 말한 것이 아닌)를 히스토리에 추가.
        """
        self.conversation_history.append({
            "role": "user", 
            "content": f"(기타대화) {message}"
        })
        self.trim_history()

    def trim_history(self) -> None:
        """
        system 이외의 메시지가 일정 수를 넘으면 오래된 것부터 삭제.
        """
        non_system_msgs = [msg for msg in self.conversation_history if msg['role'] != 'system']
        if len(non_system_msgs) > self.max_history:
            non_system_msgs = non_system_msgs[-self.max_history:]
            self.conversation_history = non_system_msgs