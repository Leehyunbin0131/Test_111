import logging
from typing import Optional

from ai_vtuber.config import Config
from ai_vtuber.exceptions import VTSError

# 외부 라이브러리 가져오기
from DEMO_vts_api_helper import VTubeStudioAPI

logger = logging.getLogger(__name__)

class VTSManager:
    """VTubeStudio API 연동을 관리하는 클래스"""
    
    def __init__(self, config: Config):
        self.config = config
        self._api = None
        self._connect()
        
    def _connect(self) -> None:
        """VTS API 연결 시도"""
        try:
            self._api = VTubeStudioAPI(
                plugin_name=self.config.vts_plugin_name,
                plugin_developer=self.config.vts_plugin_developer,
                stored_token=None,
                host=self.config.vts_host,
                port=self.config.vts_port
            )
            logger.info("VTubeStudio API 연결/인증 완료.")
        except Exception as e:
            logger.error(f"VTS 플러그인 연결 실패: {e}")
            self._api = None
            
    @property
    def api(self) -> Optional[VTubeStudioAPI]:
        """VTS API 객체 반환 (연결 확인 후)"""
        if self._api and getattr(self._api, 'authenticated', False):
            return self._api
        return None
    
    def inject_eye_blink(self, left_value: float = 1.0, right_value: float = 1.0) -> bool:
        """
        눈 깜빡임 값을 VTS에 주입
        
        Args:
            left_value: 왼쪽 눈 값 (0.0=열림, 1.0=감김)
            right_value: 오른쪽 눈 값 (0.0=열림, 1.0=감김)
            
        Returns:
            bool: 성공 여부
        """
        if not self.api:
            return False
            
        try:
            self.api.inject_eye_blink(left_value, right_value)
            return True
        except Exception as e:
            logger.error(f"눈 깜빡임 주입 실패: {e}")
            return False
    
    def inject_mouth_value(self, value: float) -> bool:
        """
        입 움직임 값을 VTS에 주입
        
        Args:
            value: 입 벌림 값 (0.0=닫힘, 1.0=최대 벌림)
            
        Returns:
            bool: 성공 여부
        """
        if not self.api:
            return False
            
        try:
            self.api.inject_mouth_value(value, face_found=True, param_id="MouthOpen")
            return True
        except Exception as e:
            logger.error(f"입 움직임 주입 실패: {e}")
            return False
    
    def close(self) -> None:
        """VTS 연결 종료"""
        if self._api:
            try:
                self._api.close()
                logger.info("VTS 연결 종료됨")
            except:
                pass
            self._api = None