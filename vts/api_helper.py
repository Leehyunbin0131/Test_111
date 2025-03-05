# ai_vtuber/vts/api_helper.py

"""VTube Studio API 통신 모듈"""

import json
import uuid
import time
from typing import Dict, Any, Optional, List, Union
from websocket import create_connection, WebSocketException

from ..utils.logging import get_logger
from ..utils.errors import VTSError

logger = get_logger(__name__)

class VTubeStudioAPI:
    """VTube Studio API 클라이언트 클래스"""
    
    def __init__(
        self, 
        plugin_name: str, 
        plugin_developer: str, 
        host: str = "localhost", 
        port: int = 8001,
        auto_reconnect: bool = True,
        reconnect_interval: float = 5.0
    ):
        """
        VTube Studio API 클라이언트 초기화
        
        Args:
            plugin_name: 플러그인 이름
            plugin_developer: 개발자 이름
            host: VTube Studio 호스트
            port: VTube Studio WebSocket 포트
            auto_reconnect: 연결 끊김 시 자동 재연결 여부
            reconnect_interval: 재연결 시도 간격 (초)
        """
        self.plugin_name = plugin_name
        self.plugin_developer = plugin_developer
        self.url = f"ws://{host}:{port}"
        self.ws = None
        self.authenticated = False
        self.token = None
        self.auto_reconnect = auto_reconnect
        self.reconnect_interval = reconnect_interval
        self.last_connection_attempt = 0
        
        # 연결 시도
        self._connect()
            
    def _connect(self) -> bool:
        """
        VTube Studio WebSocket 연결 시도
        
        Returns:
            연결 성공 여부
        """
        # 연결 간격 제한 (과도한 시도 방지)
        now = time.time()
        if now - self.last_connection_attempt < self.reconnect_interval:
            logger.debug("연결 시도 간격 제한으로 대기")
            return False
            
        self.last_connection_attempt = now
        
        try:
            self.ws = create_connection(self.url, timeout=5)
            logger.info("VTube Studio WebSocket 연결됨")
            
            # 인증 시도
            if not self.authenticated or not self.token:
                self._authenticate()
                
            return self.authenticated
            
        except Exception as e:
            logger.error(f"VTube Studio 연결 실패: {e}")
            self.ws = None
            self.authenticated = False
            return False
        
    def close(self):
        """WebSocket 연결 종료"""
        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                logger.debug(f"WebSocket 종료 중 오류: {e}")
            finally:
                self.ws = None
                logger.info("VTube Studio 연결 종료됨")
    
    def _send_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        VTube Studio API 메시지 전송
        
        Args:
            message: 전송할 메시지 딕셔너리
            
        Returns:
            응답 메시지 딕셔너리
            
        Raises:
            VTSError: API 통신 실패 시
        """
        # 필수 API 필드 추가
        message["apiName"] = "VTubeStudioPublicAPI"
        message["apiVersion"] = "1.0"
        message["requestID"] = str(uuid.uuid4())[:8]
        
        # 연결 상태 확인
        if not self.ws:
            if not self.auto_reconnect or not self._connect():
                raise VTSError("VTube Studio에 연결되어 있지 않습니다")
        
        try:
            # 메시지 전송 및 응답 수신
            self.ws.send(json.dumps(message))
            response = json.loads(self.ws.recv())
            
            # 오류 확인
            if "messageType" in response and response["messageType"] == "APIError":
                error_code = response.get("data", {}).get("errorID", -1)
                error_msg = response.get("data", {}).get("message", "알 수 없는 오류")
                logger.warning(f"VTS API 오류 {error_code}: {error_msg}")
                
            return response
            
        except (WebSocketException, ConnectionError) as e:
            logger.error(f"VTS 통신 오류: {e}")
            self.ws = None
            self.authenticated = False
            
            # 재연결 시도
            if self.auto_reconnect and self._connect():
                logger.info("VTS 재연결 성공, 메시지 재전송")
                return self._send_message(message)
                
            raise VTSError(f"VTube Studio 통신 실패: {e}")
    
    def _authenticate(self) -> bool:
        """
        VTube Studio API 인증
        
        Returns:
            인증 성공 여부
        """
        try:
            # 이미 인증된 경우
            if self.authenticated and self.token:
                auth_response = self._send_message({
                    "messageType": "AuthenticationRequest",
                    "data": {
                        "pluginName": self.plugin_name,
                        "pluginDeveloper": self.plugin_developer,
                        "authenticationToken": self.token
                    }
                })
                
                if auth_response.get("data", {}).get("authenticated", False):
                    self.authenticated = True
                    logger.info("기존 토큰으로 VTS 인증 성공")
                    return True
            
            # 토큰 요청
            response = self._send_message({
                "messageType": "AuthenticationTokenRequest",
                "data": {
                    "pluginName": self.plugin_name,
                    "pluginDeveloper": self.plugin_developer
                }
            })
            
            if "data" in response and "authenticationToken" in response["data"]:
                token = response["data"]["authenticationToken"]
                
                # 토큰으로 인증
                auth_response = self._send_message({
                    "messageType": "AuthenticationRequest",
                    "data": {
                        "pluginName": self.plugin_name,
                        "pluginDeveloper": self.plugin_developer,
                        "authenticationToken": token
                    }
                })
                
                if auth_response.get("data", {}).get("authenticated", False):
                    self.authenticated = True
                    self.token = token
                    logger.info("새 토큰으로 VTS 인증 성공")
                    return True
            
            logger.error("VTS 인증 실패")
            return False
            
        except Exception as e:
            logger.error(f"VTS 인증 중 오류: {e}")
            return False
    
    def inject_parameter(
        self, 
        param_id: str, 
        value: float, 
        weight: float = 1.0,
        face_found: bool = True
    ) -> bool:
        """
        Live2D 모델 파라미터 값 설정
        
        Args:
            param_id: 파라미터 ID
            value: 설정할 값
            weight: 가중치 (0.0 ~ 1.0)
            face_found: 얼굴 인식 상태
            
        Returns:
            설정 성공 여부
        """
        if not self.authenticated:
            if not self._authenticate():
                return False
        
        try:
            param_item = {"id": param_id, "value": value}
            if weight != 1.0:
                param_item["weight"] = max(0.0, min(1.0, weight))
                
            response = self._send_message({
                "messageType": "InjectParameterDataRequest",
                "data": {
                    "faceFound": face_found,
                    "mode": "set",
                    "parameterValues": [param_item]
                }
            })
            
            return "data" in response
        except Exception as e:
            logger.error(f"파라미터 설정 오류 ({param_id}): {e}")
            return False
    
    def inject_parameters(
        self, 
        parameters: List[Dict[str, Any]], 
        face_found: bool = True
    ) -> bool:
        """
        여러 Live2D 모델 파라미터 값 설정
        
        Args:
            parameters: 파라미터 목록 [{"id": "ParamID", "value": 0.5, "weight": 1.0}, ...]
            face_found: 얼굴 인식 상태
            
        Returns:
            설정 성공 여부
        """
        if not self.authenticated:
            if not self._authenticate():
                return False
                
        if not parameters:
            return True
            
        try:
            response = self._send_message({
                "messageType": "InjectParameterDataRequest",
                "data": {
                    "faceFound": face_found,
                    "mode": "set",
                    "parameterValues": parameters
                }
            })
            
            return "data" in response
        except Exception as e:
            logger.error(f"다중 파라미터 설정 오류: {e}")
            return False
    
    def inject_mouth_value(self, value: float, face_found: bool = True) -> bool:
        """
        입 열림 파라미터 설정
        
        Args:
            value: 입 열림 값 (0.0 ~ 1.0)
            face_found: 얼굴 인식 상태
            
        Returns:
            설정 성공 여부
        """
        return self.inject_parameter(
            "MouthOpen", 
            max(0.0, min(1.0, value)), 
            face_found=face_found
        )
    
    def inject_eye_blink(self, left: float, right: float, face_found: bool = True) -> bool:
        """
        눈 깜빡임 파라미터 설정
        
        Args:
            left: 왼쪽 눈 열림 값 (0.0 ~ 1.0, 0이 완전히 감은 상태)
            right: 오른쪽 눈 열림 값 (0.0 ~ 1.0, 0이 완전히 감은 상태)
            face_found: 얼굴 인식 상태
            
        Returns:
            설정 성공 여부
        """
        left, right = max(0.0, min(1.0, left)), max(0.0, min(1.0, right))
        
        return self.inject_parameters([
            {"id": "EyeOpenLeft", "value": 1.0 - left},   # 반전: 1이 눈 뜬 상태
            {"id": "EyeOpenRight", "value": 1.0 - right}  # 반전: 1이 눈 뜬 상태
        ], face_found=face_found)