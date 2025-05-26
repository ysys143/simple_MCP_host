"""SSE 스트리밍 메시지 타입 정의

SSE(Server-Sent Events)를 통해 전송되는 다양한 메시지 타입들을 정의합니다.
각 메시지는 JSON 형태로 직렬화되어 클라이언트에게 전송됩니다.
"""

from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import json


class StreamMessageType(Enum):
    """스트림 메시지 타입 열거형"""
    SESSION_START = "session_start"      # 세션 시작
    THINKING = "thinking"                # AI 추론 과정
    ACTING = "acting"                    # AI 행동 수행
    OBSERVING = "observing"              # 결과 관찰
    TOOL_CALL = "tool_call"             # 도구 호출
    PARTIAL_RESPONSE = "partial_response" # 부분 응답
    FINAL_RESPONSE = "final_response"    # 최종 응답
    ERROR = "error"                      # 오류 발생
    SESSION_END = "session_end"          # 세션 종료


@dataclass
class StreamMessage:
    """SSE 스트림 메시지 데이터 클래스
    
    모든 SSE 메시지는 이 구조를 따릅니다.
    JSON으로 직렬화되어 data: 필드로 전송됩니다.
    """
    type: StreamMessageType
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None
    timestamp: Optional[str] = None
    
    def __post_init__(self):
        """초기화 후 타임스탬프 자동 설정"""
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        data = asdict(self)
        data["type"] = self.type.value  # Enum을 문자열로 변환
        return data
    
    def to_json(self) -> str:
        """JSON 문자열로 변환"""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    def to_sse_format(self) -> str:
        """SSE 형식으로 변환"""
        data = json.dumps({
            "type": self.type.value,  # Enum을 문자열로 변환
            "content": self.content,
            "metadata": self.metadata,
            "session_id": self.session_id,
            "timestamp": self.timestamp
        }, ensure_ascii=False)
        
        # SSE 형식으로 변환하고 즉시 flush를 위해 개행 추가
        return f"data: {data}\n\n"


def create_session_start_message(session_id: str) -> StreamMessage:
    """세션 시작 메시지 생성"""
    return StreamMessage(
        type=StreamMessageType.SESSION_START,
        content="세션이 시작되었습니다",
        session_id=session_id,
        metadata={"action": "start"}
    )


def create_thinking_message(content: str, session_id: str, iteration: int = 1) -> StreamMessage:
    """추론 과정 메시지 생성"""
    return StreamMessage(
        type=StreamMessageType.THINKING,
        content=content,
        session_id=session_id,
        metadata={"iteration": iteration}
    )


def create_acting_message(content: str, session_id: str, action_details: Optional[Dict[str, Any]] = None) -> StreamMessage:
    """행동 수행 메시지 생성"""
    return StreamMessage(
        type=StreamMessageType.ACTING,
        content=content,
        session_id=session_id,
        metadata={"action_details": action_details or {}}
    )


def create_observing_message(content: str, session_id: str, observation_data: Optional[Dict[str, Any]] = None) -> StreamMessage:
    """관찰 결과 메시지 생성"""
    return StreamMessage(
        type=StreamMessageType.OBSERVING,
        content=content,
        session_id=session_id,
        metadata={"observation_data": observation_data or {}}
    )


def create_tool_call_message(server: str, tool: str, status: str, session_id: str, arguments: Optional[Dict[str, Any]] = None) -> StreamMessage:
    """도구 호출 메시지 생성"""
    return StreamMessage(
        type=StreamMessageType.TOOL_CALL,
        content=f"{server}.{tool} 호출 중",
        session_id=session_id,
        metadata={
            "server": server,
            "tool": tool,
            "status": status,
            "arguments": arguments or {}
        }
    )


def create_final_response_message(content: str, session_id: str) -> StreamMessage:
    """최종 응답 메시지 생성"""
    return StreamMessage(
        type=StreamMessageType.FINAL_RESPONSE,
        content=content,
        session_id=session_id,
        metadata={"final": True}
    )


def create_partial_response_message(content: str, session_id: str) -> StreamMessage:
    """부분 응답 메시지 생성 (토큰 단위 스트리밍용)"""
    return StreamMessage(
        type=StreamMessageType.PARTIAL_RESPONSE,
        content=content,
        session_id=session_id,
        metadata={"partial": True}
    )


def create_error_message(error: str, session_id: str) -> StreamMessage:
    """오류 메시지 생성"""
    return StreamMessage(
        type=StreamMessageType.ERROR,
        content=f"오류가 발생했습니다: {error}",
        session_id=session_id,
        metadata={"error": error}
    )


def create_session_end_message(session_id: str) -> StreamMessage:
    """세션 종료 메시지 생성"""
    return StreamMessage(
        type=StreamMessageType.SESSION_END,
        content="세션이 종료되었습니다",
        session_id=session_id,
        metadata={"action": "end"}
    ) 