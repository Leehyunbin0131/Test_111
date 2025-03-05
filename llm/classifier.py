# ai_vtuber/llm/classifier.py

"""사용자 발화 분류 모듈"""

import re
import time
import hashlib
from typing import Dict, List, Set, Optional, Tuple
from collections import OrderedDict

from ollama import chat

from ..utils.logging import get_logger

logger = get_logger(__name__)

class SpeechClassifier:
    """사용자 발화 분류 클래스"""
    
    # 감지 결과 상수
    IS_DIRECTED = True
    IS_BACKGROUND = False
    
    def __init__(
        self, 
        model_name: str,
        direct_keywords: Optional[List[str]] = None,
        cache_size: int = 100,
        cache_ttl: int = 3600  # 캐시 유효시간 (초)
    ):
        """
        음성 분류기 초기화
        
        Args:
            model_name: 분류에 사용할 LLM 모델명
            direct_keywords: AI에게 직접 말하는 것으로 간주할 키워드 리스트
            cache_size: 최대 캐시 크기
            cache_ttl: 캐시 항목 유효시간 (초)
        """
        self.model_name = model_name
        self.direct_keywords = direct_keywords or [
            "너", "야", "AI", "인공지능", "알아?", "해줘", "알려줘"
        ]
        
        # 캐시 설정
        self.cache_size = cache_size
        self.cache_ttl = cache_ttl
        
        # LRU 캐시 (OrderedDict 사용)
        self.cache: OrderedDict[str, Tuple[bool, float]] = OrderedDict()
        
        # 키워드 매칭 최적화를 위한 정규 표현식
        self._compile_keyword_patterns()
        
        logger.info(f"음성 분류기 초기화 완료 (모델: {model_name})")
    
    def _compile_keyword_patterns(self):
        """키워드 매칭을 위한 정규 표현식 컴파일"""
        # 정규식 특수문자 이스케이프
        escaped_keywords = [re.escape(kw) for kw in self.direct_keywords]
        
        # 단일 정규식으로 컴파일 (성능 향상)
        pattern = r'|'.join(f'({kw})' for kw in escaped_keywords)
        self.keyword_pattern = re.compile(pattern, re.IGNORECASE)
    
    def _get_text_hash(self, text: str) -> str:
        """
        텍스트의 정규화된 해시값 생성
        
        Args:
            text: 원본 텍스트
            
        Returns:
            해시값
        """
        normalized = text.strip().lower()
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()
    
    def _check_cache(self, text_hash: str) -> Optional[bool]:
        """
        캐시에서 분류 결과 조회
        
        Args:
            text_hash: 텍스트 해시값
            
        Returns:
            캐시된 분류 결과 (없으면 None)
        """
        if text_hash in self.cache:
            result, timestamp = self.cache[text_hash]
            
            # 캐시 항목 이동 (LRU 유지)
            self.cache.move_to_end(text_hash)
            
            # TTL 확인
            if time.time() - timestamp <= self.cache_ttl:
                return result
            
            # TTL 만료된 항목 제거
            del self.cache[text_hash]
        
        return None
    
    def _update_cache(self, text_hash: str, result: bool):
        """
        캐시 업데이트
        
        Args:
            text_hash: 텍스트 해시값
            result: 분류 결과
        """
        # 캐시 크기 제한
        if len(self.cache) >= self.cache_size:
            # 가장 오래된 항목 제거 (FIFO)
            self.cache.popitem(last=False)
        
        # 새 결과 캐싱
        self.cache[text_hash] = (result, time.time())
    
    def is_directed_to_ai(self, text: str) -> bool:
        """
        해당 발화가 AI에게 직접 말한 것인지 판단
        
        Args:
            text: 분류할 텍스트
            
        Returns:
            AI에게 직접 말한 것이면 True, 아니면 False
        """
        if not text or not text.strip():
            return self.IS_BACKGROUND
        
        # 텍스트 해시 계산
        text_hash = self._get_text_hash(text)
        
        # 캐시 확인
        cached_result = self._check_cache(text_hash)
        if cached_result is not None:
            return cached_result
        
        # 1단계: 키워드 기반 빠른 필터링
        if self.keyword_pattern.search(text):
            logger.debug(f"키워드 매칭으로 분류됨: {text[:30]}...")
            self._update_cache(text_hash, self.IS_DIRECTED)
            return self.IS_DIRECTED
        
        # 2단계: 패턴 기반 휴리스틱 분류
        # 질문 형태 검사
        if re.search(r'\?$|뭐지\?|뭐야\?|왜\?|언제\?|어디\?|누구\?', text):
            if len(text) < 15:  # 짧은 질문은 AI에게 직접적일 가능성 높음
                logger.debug(f"질문 패턴으로 분류됨: {text[:30]}...")
                self._update_cache(text_hash, self.IS_DIRECTED)
                return self.IS_DIRECTED
        
        # 3단계: LLM 기반 분류 (가장 비용이 높은 방법)
        try:
            classification_prompt = [
                {
                    "role": "system",
                    "content": (
                        "너는 발화 분류기야.\n"
                        "다음 문장이 AI(너)에게 질문이나 명령을 하는지, "
                        "그냥 사람들끼리 잡담하는 건지 구분해.\n"
                        "AI에게 직접 물어보거나 요구하는 거라면 'YES'만 출력.\n"
                        "그게 아니라면 'NO'만 출력.\n"
                    )
                },
                {"role": "user", "content": text}
            ]
            
            # 간단한 형태로 요청 (스트리밍 없이)
            response = chat(model=self.model_name, messages=classification_prompt)
            content = response.get("message", {}).get("content", "").strip().upper()
            
            # 응답 분석
            result = "YES" in content
            
            # 캐시 업데이트
            self._update_cache(text_hash, result)
            
            logger.debug(f"LLM 분류 결과 ({result}): {text[:30]}...")
            return result
            
        except Exception as e:
            logger.error(f"분류 오류: {e}")
            # 오류 발생 시 기본값 반환
            return self.IS_BACKGROUND