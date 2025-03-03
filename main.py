import logging

from ai_vtuber.config import Config
from ai_vtuber.pipeline import AIVTubePipeline

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(module)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("ai_vtuber.log", mode="a")
    ]
)
logger = logging.getLogger(__name__)

def main() -> None:
    """
    AIVTubePipeline 인스턴스를 생성해 start() 호출.
    Ctrl+C로 KeyboardInterrupt가 발생하면 stop()으로 종료.
    """
    # 기본 설정 로드
    config = Config()

    # 설정 오버라이드 (필요시 환경변수나 설정 파일에서 로드)

    # 파이프라인 시작
    pipeline = AIVTubePipeline(config)
    try:
        pipeline.start()
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt -> 프로그램 종료 요청")
    except Exception as e:
        logger.error(f"파이프라인 실행 중 예외 발생: {e}")
    finally:
        pipeline.stop()

if __name__ == "__main__":
    main()