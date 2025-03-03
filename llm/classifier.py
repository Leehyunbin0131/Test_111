import logging
from typing import Dict

from ollama import chat

logger = logging.getLogger(__name__)

class SpeechClassifier:
    """음성 입력을 분류하는 클래스"""
    
    def __init__(self, model_name: str):
        self.model_name = model_name
        # 간단한 키워드 기반 필터링을 위한 설정
        self.direct_keywords = ["너", "야", "AI", "알아?", "해줘", "알려줘"]
        self.cache: Dict[str, str] = {}  # 캐싱으로 반복 요청 최소화
        self.cache_max_size = 100
        
    def is_directed_to_ai(self, text: str) -> bool:
        """
        해당 발화가 AI에게 말한 것인지 판단.
        1. 캐시 확인
        2. 간단한 키워드 매칭
        3. LLM 기반 분류
        """
        # 1. 캐시 확인
        text_key = text.strip().lower()
        if text_key in self.cache:
            result = self.cache[text_key]
            logger.debug(f"[분류] 캐시 결과 사용: {text} -> {result}")
            return result == "YES"
            
        # 2. 간단한 키워드 기반 필터링 (LLM 호출 최소화)
        for keyword in self.direct_keywords:
            if keyword in text:
                self._update_cache(text_key, "YES")
                return True
                
        # 3. LLM에 질의
        result = self._classify_with_llm(text)
        self._update_cache(text_key, result)
        
        return result == "YES"
    
    def _classify_with_llm(self, text: str) -> str:
        """
        Ollama 모델에 간단한 프롬프트를 보내, 
        해당 발화가 'AI에게 직접 요청/명령'인지 vs '그냥 다른 사람 대화'인지를 YES/NO로 분류.
        """
        classification_prompt = [
            {
                "role": "system",
                "content": (
                    "너는 발화 분류기야.\n"
                    "다음 문장이 AI(너)에게 질문이나 명령을 하는지, "
                    "그냥 사람들끼리 잡담하는 건지 구분해.\n"
                    "AI에게 직접 물어보거나 요구하는 거라면 'YES'만 출력.\n"
                    "그게 아니라면 'NO'만 출력.\n"
                    "그 외 어떤 말도 출력하지 마.\n"
                )
            },
            {"role": "user", "content": text}
        ]
        try:
            response = chat(model=self.model_name, messages=classification_prompt, stream=False)
            if not response or not response.get("message"):
                return "NO"
            resp_text = response["message"].get("content", "").strip().upper()
            if "YES" in resp_text:
                return "YES"
            return "NO"
        except Exception as e:
            logger.error(f"[분류 에러] {e}")
            return "NO"  # 에러 시 기본적으로 'NO' 반환
            
    def _update_cache(self, text_key: str, result: str) -> None:
        """캐시 업데이트 및 크기 관리"""
        self.cache[text_key] = result
        # 캐시 크기 제한
        if len(self.cache) > self.cache_max_size:
            # 가장 오래된 20% 항목 제거
            remove_count = int(self.cache_max_size * 0.2)
            for _ in range(remove_count):
                self.cache.pop(next(iter(self.cache)), None)