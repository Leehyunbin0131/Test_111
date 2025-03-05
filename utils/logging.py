# ai_vtuber/utils/logging.py

"""AI VTuber 시스템의 로깅 설정 모듈"""

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

# 기본 로그 디렉토리 설정
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# 기본 로그 파일 경로
DEFAULT_LOG_FILE = os.path.join(LOG_DIR, "ai_vtuber.log")

# 로거 인스턴스 캐시
_loggers = {}

def setup_logger(
    name: str,
    log_file: str = DEFAULT_LOG_FILE,
    level: int = logging.INFO,
    max_size_mb: int = 10,
    backup_count: int = 3
) -> logging.Logger:
    """
    모듈별 로거 설정 및 반환
    
    Args:
        name: 로거 이름 (일반적으로 __name__)
        log_file: 로그 파일 경로
        level: 로깅 레벨
        max_size_mb: 로그 파일 최대 크기 (MB 단위)
        backup_count: 백업 로그 파일 수
        
    Returns:
        설정된 로거 인스턴스
    """
    # 캐시된 로거 반환
    if name in _loggers:
        return _loggers[name]
    
    # 신규 로거 생성
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 이미 핸들러가 있으면 추가하지 않음
    if logger.handlers:
        return logger
    
    # 포맷 설정
    log_format = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s"
    )
    
    # 파일 핸들러 설정
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_size_mb * 1024 * 1024,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setFormatter(log_format)
    logger.addHandler(file_handler)
    
    # 콘솔 핸들러 설정
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_format)
    logger.addHandler(console_handler)
    
    # 캐시에 저장
    _loggers[name] = logger
    return logger

def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    모듈의 로거를 반환 (없으면 생성)
    
    Args:
        name: 로거 이름 (기본값: 'ai_vtuber')
        
    Returns:
        로거 인스턴스
    """
    module_name = name or 'ai_vtuber'
    if module_name in _loggers:
        return _loggers[module_name]
    return setup_logger(module_name)