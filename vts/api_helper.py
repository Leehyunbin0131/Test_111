# ai_vtuber/vts/api_helper.py

"""VTube Studio API 통신 모듈"""

import json
import uuid
import time
import os
import threading
import enum
from typing import Dict, Any, Optional, List, Union, Callable
from websocket import create_connection, WebSocketException, WebSocketTimeoutException, WebSocketConnectionClosedException

from ..utils.logging import get_logger
from ..utils.errors import VTSError

logger = get_logger(__name__)

class ConnectionState(enum.Enum):
    """VTube Studio 연결 상태"""
    DISCONNECTED = 0    # 연결되지 않음
    CONNECTING = 1      # 연결 시도 중
    CONNECTED = 2       # 연결됨 (인증 전)
    AUTHENTICATING = 3  # 인증 시도 중
    AUTHENTICATED = 4   # 인증 완료됨

class VTubeStudioAPI:
    """VTube Studio API 클라이언트 클래스 - 향상된 버전"""
    
    # 상수 정의
    API_NAME = "VTubeStudioPublicAPI"
    API_VERSION = "1.0"
    WS_TIMEOUT = 5.0  # 웹소켓 통신 타임아웃 (초)
    HEARTBEAT_INTERVAL = 5.0  # 하트비트 간격 (초)
    RECONNECT_DELAY = 2.0  # 재연결 시도 간격 (초)
    RECONNECT_MAX_ATTEMPTS = 5  # 최대 재연결 시도 횟수
    
    def __init__(
        self, 
        plugin_name: str, 
        plugin_developer: str, 
        host: str = "localhost", 
        port: int = 8001,
        auto_reconnect: bool = True,
        token_directory: Optional[str] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ):
        """
        VTube Studio API 클라이언트 초기화
        
        Args:
            plugin_name: 플러그인 이름
            plugin_developer: 개발자 이름
            host: VTube Studio 호스트
            port: VTube Studio WebSocket 포트
            auto_reconnect: 연결 끊김 시 자동 재연결 여부
            token_directory: 토큰 저장 디렉토리 (None이면 홈 디렉토리 사용)
            event_callback: API 이벤트 수신 시 호출할 콜백 함수
        """
        self.plugin_name = plugin_name
        self.plugin_developer = plugin_developer
        self.url = f"ws://{host}:{port}"
        self.auto_reconnect = auto_reconnect
        self.event_callback = event_callback
        
        # 상태 변수
        self.ws = None
        self.state = ConnectionState.DISCONNECTED
        self.token = None
        self.reconnect_attempts = 0
        
        # 동기화 객체
        self._lock = threading.RLock()  # 스레드 안전성을 위한 재진입 락
        self._response_lock = threading.RLock()  # 응답 처리 동기화
        self._last_request_id = None  # 마지막 요청 ID
        self._response_data = {}  # 요청 ID에 따른 응답 저장
        self._response_event = threading.Event()  # 응답 대기 이벤트
        
        # 스레드 제어
        self._stop_event = threading.Event()
        self._receiver_thread = None
        self._heartbeat_thread = None
        
        # 토큰 파일 경로
        if token_directory:
            os.makedirs(token_directory, exist_ok=True)
            token_file_path = os.path.join(token_directory, f"vts_token_{self._get_token_filename()}.json")
        else:
            token_file_path = os.path.join(os.path.expanduser("~"), f".vts_token_{self._get_token_filename()}.json")
        self.token_file_path = token_file_path
        
        # 저장된 토큰 로드
        self._load_token()
        
        logger.info(f"VTube Studio API 클라이언트 초기화 완료 (플러그인: {plugin_name})")
    
    def _get_token_filename(self) -> str:
        """
        토큰 파일명 생성 (플러그인 이름과 개발자 기반)
        
        Returns:
            토큰 파일명 해시
        """
        # 플러그인 이름과 개발자를 조합하여 해시 생성
        name_hash = str(hash(f"{self.plugin_name}_{self.plugin_developer}") & 0xFFFFFFFF)
        return name_hash
    
    def connect(self) -> bool:
        """
        VTube Studio에 연결 및 인증
        
        Returns:
            연결 및 인증 성공 여부
        """
        with self._lock:
            # 이미 연결/인증된 상태인지 확인
            if self.state == ConnectionState.AUTHENTICATED:
                return True
                
            # 연결 시도
            if self.state == ConnectionState.DISCONNECTED:
                logger.info("VTube Studio 연결 시도...")
                self.state = ConnectionState.CONNECTING
                
                try:
                    # WebSocket 연결
                    self.ws = create_connection(self.url, timeout=self.WS_TIMEOUT)
                    self.state = ConnectionState.CONNECTED
                    self.reconnect_attempts = 0
                    
                    # 수신 및 하트비트 스레드 시작
                    self._start_threads()
                    logger.info("VTube Studio WebSocket 연결 성공")
                    
                except Exception as e:
                    logger.error(f"VTube Studio 연결 실패: {e}")
                    self.ws = None
                    self.state = ConnectionState.DISCONNECTED
                    return False
            
            # 인증 시도
            if self.state == ConnectionState.CONNECTED:
                return self._authenticate()
                
            return False
    
    def _authenticate(self) -> bool:
        """
        VTube Studio API 인증
        
        Returns:
            인증 성공 여부
        """
        if self.state != ConnectionState.CONNECTED:
            return False
            
        logger.info("VTube Studio API 인증 시도...")
        self.state = ConnectionState.AUTHENTICATING
        
        try:
            # 기존 토큰으로 인증 시도
            if self.token:
                auth_success = self._authenticate_with_token(self.token)
                if auth_success:
                    return True
                
                # 인증 실패 시 토큰 만료로 간주하고 새 토큰 요청
                logger.warning("저장된 토큰으로 인증 실패, 새 토큰 요청...")
                self.token = None
            
            # 새 토큰 요청
            response = self._send_request({
                "messageType": "AuthenticationTokenRequest",
                "data": {
                    "pluginName": self.plugin_name,
                    "pluginDeveloper": self.plugin_developer
                }
            })
            
            if response and "data" in response and "authenticationToken" in response["data"]:
                new_token = response["data"]["authenticationToken"]
                
                # 토큰으로 인증
                if self._authenticate_with_token(new_token):
                    self.token = new_token
                    self._save_token()
                    return True
            
            # 인증 실패 처리
            logger.error("VTube Studio API 인증 실패")
            self.state = ConnectionState.CONNECTED
            return False
            
        except Exception as e:
            logger.error(f"VTube Studio API 인증 중 오류: {e}")
            self.state = ConnectionState.CONNECTED
            return False
    
    def _authenticate_with_token(self, token: str) -> bool:
        """
        주어진 토큰으로 인증 시도
        
        Args:
            token: 인증 토큰
            
        Returns:
            인증 성공 여부
        """
        try:
            auth_response = self._send_request({
                "messageType": "AuthenticationRequest",
                "data": {
                    "pluginName": self.plugin_name,
                    "pluginDeveloper": self.plugin_developer,
                    "authenticationToken": token
                }
            })
            
            if auth_response and "data" in auth_response and auth_response["data"].get("authenticated", False):
                self.state = ConnectionState.AUTHENTICATED
                logger.info("VTube Studio API 인증 성공")
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"토큰 인증 중 오류: {e}")
            return False
    
    def _save_token(self) -> bool:
        """
        인증 토큰을 파일에 저장
        
        Returns:
            저장 성공 여부
        """
        if not self.token:
            return False
            
        try:
            token_data = {
                "plugin_name": self.plugin_name,
                "plugin_developer": self.plugin_developer,
                "token": self.token,
                "timestamp": time.time()
            }
            
            with open(self.token_file_path, 'w') as f:
                json.dump(token_data, f)
                
            logger.debug(f"VTube Studio 인증 토큰 저장됨: {self.token_file_path}")
            return True
            
        except Exception as e:
            logger.warning(f"VTube Studio 인증 토큰 저장 실패: {e}")
            return False
    
    def _load_token(self) -> bool:
        """
        파일에서 인증 토큰 로드
        
        Returns:
            로드 성공 여부
        """
        try:
            if not os.path.exists(self.token_file_path):
                return False
                
            with open(self.token_file_path, 'r') as f:
                token_data = json.load(f)
                
            # 플러그인 정보 확인
            if (token_data.get("plugin_name") == self.plugin_name and
                token_data.get("plugin_developer") == self.plugin_developer):
                
                self.token = token_data.get("token")
                logger.debug(f"VTube Studio 인증 토큰 로드됨")
                return True
                
            return False
            
        except Exception as e:
            logger.warning(f"VTube Studio 인증 토큰 로드 실패: {e}")
            return False
    
    def _start_threads(self):
        """수신 및 하트비트 스레드 시작"""
        # 이전 스레드 정리
        self._stop_threads()
        self._stop_event.clear()
        
        # 웹소켓 수신 스레드
        self._receiver_thread = threading.Thread(
            target=self._receiver_thread_func,
            daemon=True,
            name="VTS-Receiver"
        )
        self._receiver_thread.start()
        
        # 하트비트 스레드
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_thread_func,
            daemon=True,
            name="VTS-Heartbeat"
        )
        self._heartbeat_thread.start()
    
    def _stop_threads(self):
        """스레드 정지 및 정리"""
        # 정지 시그널 설정
        self._stop_event.set()
        
        # 스레드 종료 대기
        if self._receiver_thread and self._receiver_thread.is_alive():
            self._receiver_thread.join(timeout=1.0)
            
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=1.0)
            
        self._receiver_thread = None
        self._heartbeat_thread = None
    
    def _receiver_thread_func(self):
        """웹소켓 메시지 수신 스레드 함수"""
        logger.debug("VTube Studio 수신 스레드 시작")
        
        while not self._stop_event.is_set() and self.ws:
            try:
                # 웹소켓에서 메시지 수신 (타임아웃 적용)
                self.ws.settimeout(0.5)  # 짧은 타임아웃으로 설정하여 _stop_event 확인 가능하게
                message_raw = self.ws.recv()
                message = json.loads(message_raw)
                
                # 메시지 유형에 따른 처리
                message_type = message.get("messageType", "")
                
                # 일반 응답 처리
                request_id = message.get("requestID")
                if request_id:
                    with self._response_lock:
                        self._response_data[request_id] = message
                        # 마지막 요청에 대한 응답인 경우 이벤트 설정
                        if request_id == self._last_request_id:
                            self._response_event.set()
                
                # API 이벤트 처리
                if message_type == "VTubeStudioAPIEvent":
                    self._handle_event(message)
                    
            except WebSocketTimeoutException:
                # 타임아웃은 정상적인 상황 (스레드 종료 확인용)
                continue
                
            except WebSocketConnectionClosedException:
                if not self._stop_event.is_set():
                    logger.warning("VTube Studio 웹소켓 연결이 종료됨")
                    self._handle_disconnection()
                break
                
            except Exception as e:
                if not self._stop_event.is_set():
                    logger.error(f"VTube Studio 메시지 수신 오류: {e}")
                    self._handle_disconnection()
                break
                
        logger.debug("VTube Studio 수신 스레드 종료")
    
    def _heartbeat_thread_func(self):
        """연결 유지를 위한 하트비트 스레드 함수"""
        logger.debug("VTube Studio 하트비트 스레드 시작")
        
        # 연결 유지를 위한 주기적 핑 전송
        while not self._stop_event.is_set():
            # 인증된 상태에서만 하트비트 전송
            if self.state == ConnectionState.AUTHENTICATED:
                try:
                    # APIState 요청 (간단한 핑 용도)
                    self._send_request({
                        "messageType": "APIStateRequest",
                        "data": {}
                    }, wait_response=False)  # 응답 대기 안함
                except Exception:
                    # 오류는 수신 스레드에서 처리
                    pass
                    
            # 하트비트 간격 대기
            self._stop_event.wait(self.HEARTBEAT_INTERVAL)
                
        logger.debug("VTube Studio 하트비트 스레드 종료")
    
    def _handle_event(self, event: Dict[str, Any]):
        """
        VTube Studio API 이벤트 처리
        
        Args:
            event: 이벤트 데이터
        """
        try:
            event_type = event.get("data", {}).get("eventType", "Unknown")
            logger.debug(f"VTube Studio 이벤트 수신: {event_type}")
            
            # 등록된 콜백 호출
            if self.event_callback:
                self.event_callback(event)
                
        except Exception as e:
            logger.error(f"이벤트 처리 중 오류: {e}")
    
    def _handle_disconnection(self):
        """연결 끊김 처리 및 재연결 로직"""
        with self._lock:
            # 연결 상태 업데이트
            prev_state = self.state
            self.state = ConnectionState.DISCONNECTED
            self.ws = None
            
            # 재연결 시도 (auto_reconnect가 활성화된 경우)
            if self.auto_reconnect and not self._stop_event.is_set():
                self.reconnect_attempts += 1
                
                if self.reconnect_attempts <= self.RECONNECT_MAX_ATTEMPTS:
                    logger.info(f"VTube Studio 재연결 시도 ({self.reconnect_attempts}/{self.RECONNECT_MAX_ATTEMPTS})...")
                    
                    # 재연결 대기 시간 (점진적 증가)
                    delay = min(self.RECONNECT_DELAY * self.reconnect_attempts, 10.0)
                    time.sleep(delay)
                    
                    # 이전 상태에 따라 인증까지 시도
                    success = self.connect()
                    
                    if success and prev_state == ConnectionState.AUTHENTICATED:
                        # 이전에 인증된 상태였다면 인증까지 시도
                        return
                else:
                    logger.error(f"VTube Studio 최대 재연결 시도 횟수 초과")
            
            # 재연결 비활성화 또는 재연결 실패 처리
            self._clear_request_state()
    
    def _clear_request_state(self):
        """요청 상태 초기화"""
        with self._response_lock:
            self._response_data.clear()
            self._last_request_id = None
            self._response_event.set()  # 대기 중인 모든 요청 해제
    
    def _send_request(
        self, 
        message: Dict[str, Any], 
        timeout: float = 10.0,
        wait_response: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        VTube Studio API 요청 전송 및 응답 대기
        
        Args:
            message: 요청 메시지
            timeout: 응답 대기 타임아웃 (초)
            wait_response: 응답을 기다릴지 여부
            
        Returns:
            응답 메시지 또는 None (오류 또는 타임아웃)
            
        Raises:
            VTSError: 통신 오류
        """
        if not self.ws:
            raise VTSError("VTube Studio에 연결되어 있지 않습니다")
            
        # 요청 ID 생성
        request_id = str(uuid.uuid4())[:8]
        
        # 기본 필드 추가
        message["apiName"] = self.API_NAME
        message["apiVersion"] = self.API_VERSION
        message["requestID"] = request_id
        
        try:
            # 응답 준비
            if wait_response:
                with self._response_lock:
                    self._last_request_id = request_id
                    self._response_event.clear()
            
            # 메시지 전송
            self.ws.send(json.dumps(message))
            
            # 응답 대기 (필요한 경우)
            if wait_response:
                if not self._response_event.wait(timeout):
                    logger.warning(f"요청 타임아웃: {message.get('messageType')}")
                    return None
                    
                # 응답 가져오기
                with self._response_lock:
                    response = self._response_data.pop(request_id, None)
                    
                # 오류 확인
                if response and response.get("messageType") == "APIError":
                    error_id = response.get("data", {}).get("errorID", -1)
                    error_msg = response.get("data", {}).get("message", "알 수 없는 오류")
                    logger.warning(f"VTS API 오류 {error_id}: {error_msg}")
                
                return response
            
            return None  # 응답 대기 안 함
            
        except WebSocketException as e:
            logger.error(f"VTS 메시지 전송 오류: {e}")
            self._handle_disconnection()
            raise VTSError(f"VTube Studio 통신 실패: {e}")
    
    def close(self):
        """연결 종료 및 리소스 정리"""
        logger.info("VTube Studio 연결 종료 중...")
        
        # 스레드 정지
        self._stop_threads()
        
        # WebSocket 종료
        if self.ws:
            try:
                self.ws.close()
            except Exception as e:
                logger.debug(f"WebSocket 종료 중 오류: {e}")
            finally:
                self.ws = None
        
        # 상태 초기화
        self.state = ConnectionState.DISCONNECTED
        logger.info("VTube Studio 연결 종료됨")

    # ===== API 메서드 =====
    
    def ensure_connected(self) -> bool:
        """
        연결 및 인증 상태 확인/복구
        
        Returns:
            인증 성공 여부
        """
        with self._lock:
            if self.state == ConnectionState.AUTHENTICATED:
                return True
                
            if self.state == ConnectionState.DISCONNECTED:
                return self.connect()
                
            return False
    
    def get_api_state(self) -> Dict[str, Any]:
        """
        VTube Studio API 상태 조회
        
        Returns:
            API 상태 정보
        
        Raises:
            VTSError: 통신 오류
        """
        if not self.ensure_connected():
            raise VTSError("VTube Studio에 인증되지 않았습니다")
            
        response = self._send_request({
            "messageType": "APIStateRequest",
            "data": {}
        })
        
        if not response:
            raise VTSError("API 상태 요청 실패")
            
        return response.get("data", {})
    
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
            
        Raises:
            VTSError: 통신 오류
        """
        if not self.ensure_connected():
            raise VTSError("VTube Studio에 인증되지 않았습니다")
        
        try:
            param_item = {"id": param_id, "value": value}
            if weight != 1.0:
                param_item["weight"] = max(0.0, min(1.0, weight))
                
            response = self._send_request({
                "messageType": "InjectParameterDataRequest",
                "data": {
                    "faceFound": face_found,
                    "mode": "set",
                    "parameterValues": [param_item]
                }
            })
            
            return response is not None
            
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
            
        Raises:
            VTSError: 통신 오류
        """
        if not self.ensure_connected():
            raise VTSError("VTube Studio에 인증되지 않았습니다")
                
        if not parameters:
            return True
            
        try:
            response = self._send_request({
                "messageType": "InjectParameterDataRequest",
                "data": {
                    "faceFound": face_found,
                    "mode": "set",
                    "parameterValues": parameters
                }
            })
            
            return response is not None
            
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
    
    def get_current_model_info(self) -> Dict[str, Any]:
        """
        현재 로드된 모델 정보 조회
        
        Returns:
            모델 정보
            
        Raises:
            VTSError: 통신 오류
        """
        if not self.ensure_connected():
            raise VTSError("VTube Studio에 인증되지 않았습니다")
            
        response = self._send_request({
            "messageType": "CurrentModelRequest",
            "data": {}
        })
        
        if not response:
            raise VTSError("모델 정보 요청 실패")
            
        return response.get("data", {})
    
    def get_available_parameters(self) -> List[Dict[str, Any]]:
        """
        사용 가능한 모델 파라미터 목록 조회
        
        Returns:
            파라미터 목록
            
        Raises:
            VTSError: 통신 오류
        """
        if not self.ensure_connected():
            raise VTSError("VTube Studio에 인증되지 않았습니다")
            
        response = self._send_request({
            "messageType": "ParameterListRequest",
            "data": {}
        })
        
        if not response:
            raise VTSError("파라미터 목록 요청 실패")
            
        return response.get("data", {}).get("parameters", [])
    
    def trigger_hotkey(self, hotkey_id: str) -> bool:
        """
        VTube Studio 핫키 실행
        
        Args:
            hotkey_id: 핫키 ID
            
        Returns:
            실행 성공 여부
            
        Raises:
            VTSError: 통신 오류
        """
        if not self.ensure_connected():
            raise VTSError("VTube Studio에 인증되지 않았습니다")
            
        response = self._send_request({
            "messageType": "HotkeyTriggerRequest",
            "data": {
                "hotkeyID": hotkey_id
            }
        })
        
        return response is not None
    
    def __enter__(self):
        """컨텍스트 매니저 진입"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        self.close()