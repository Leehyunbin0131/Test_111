#!/usr/bin/env python3
# ai_vtuber/main.py

"""AI VTuber 시스템 메인 진입점"""

import os
import sys
import argparse
import signal
import logging
import traceback
from pathlib import Path

# 상위 디렉토리를 모듈 경로에 추가 (개발 환경에서 필요)
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_vtuber.utils.logging import setup_logger
from ai_vtuber.config.settings import Settings, get_settings
from ai_vtuber.core.pipeline import AIVTubePipeline
from ai_vtuber.utils.errors import BaseError

# 로거 초기화
logger = setup_logger(__name__)

def parse_arguments():
    """명령줄 인자 파싱"""
    parser = argparse.ArgumentParser(description="AI VTuber 시스템")
    
    parser.add_argument("--config", "-c", type=str, 
                      help="설정 파일 경로")
    
    parser.add_argument("--ref-audio", "-r", type=str,
                      help="참조 오디오 파일 경로")
    
    parser.add_argument("--model", "-m", type=str,
                      help="사용할 LLM 모델")
    
    parser.add_argument("--debug", "-d", action="store_true",
                      help="디버그 모드 활성화")
    
    parser.add_argument("--log-level", "-l", type=str, 
                      choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                      default="INFO",
                      help="로그 레벨 설정")
    
    return parser.parse_args()

def setup_signal_handlers(pipeline):
    """시그널 핸들러 설정"""
    def signal_handler(sig, frame):
        logger.info(f"시그널 {sig} 수신, 종료 중...")
        pipeline.stop()
        sys.exit(0)
    
    # SIGINT(Ctrl+C) 및 SIGTERM 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

def apply_settings_from_args(settings, args):
    """명령줄 인자에서 설정 적용"""
    # 참조 오디오 경로 설정
    if args.ref_audio:
        if os.path.exists(args.ref_audio):
            settings.default_ref_audio = args.ref_audio
        else:
            logger.warning(f"참조 오디오 파일을 찾을 수 없습니다: {args.ref_audio}")
    
    # LLM 모델 설정
    if args.model:
        settings.ollama_model = args.model
    
    # 디버그 모드 설정
    if args.debug:
        settings.debug = True
    
    # 로그 레벨 설정
    log_level = getattr(logging, args.log_level)
    logger.setLevel(log_level)
    
    return settings

def main():
    """메인 함수"""
    # 시작 로그
    logger.info("==== AI VTuber 시스템 시작 ====")
    
    try:
        # 명령줄 인자 파싱
        args = parse_arguments()
        
        # 설정 로드
        settings = None
        if args.config:
            try:
                settings = Settings.load_from_file(args.config)
                logger.info(f"설정 파일 로드: {args.config}")
            except Exception as e:
                logger.error(f"설정 파일 로드 실패: {e}")
                logger.info("기본 설정을 사용합니다.")
                settings = get_settings()
        else:
            settings = get_settings()
        
        # 명령줄 인자에서 설정 적용
        settings = apply_settings_from_args(settings, args)
        
        # 파이프라인 초기화
        pipeline = AIVTubePipeline(settings)
        
        # 시그널 핸들러 설정
        setup_signal_handlers(pipeline)
        
        # 파이프라인 시작
        logger.info("파이프라인 시작 중...")
        pipeline.start()
        
    except BaseError as e:
        logger.error(f"AI VTuber 오류: {e}")
        return 1
    except KeyboardInterrupt:
        logger.info("Ctrl+C로 종료 요청")
        return 0
    except Exception as e:
        logger.critical(f"예상치 못한 오류: {e}")
        logger.debug(traceback.format_exc())
        return 1
    finally:
        logger.info("==== AI VTuber 시스템 종료 ====")
    
    return 0

# 직접 실행 시
if __name__ == "__main__":
    sys.exit(main())