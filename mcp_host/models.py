"""MCP 호스트 데이터 모델

이 모듈은 MCP 호스트 시스템에서 사용하는 모든 데이터 모델을 정의합니다.
Pydantic과 TypedDict를 활용하여 타입 안전성을 보장하고,
각 모델이 단일 책임을 갖도록 SOLID 원칙을 준수합니다.
"""

from typing import TypedDict, List, Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
from langchain_core.messages import BaseMessage


class MessageRole(str, Enum):
    """메시지 역할을 나타내는 열거형"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class IntentType(str, Enum):
    """사용자 의도 유형을 나타내는 열거형"""
    WEATHER_QUERY = "WEATHER_QUERY"
    FILE_OPERATION = "FILE_OPERATION"
    API_REQUEST = "API_REQUEST"
    SERVER_STATUS = "SERVER_STATUS"
    TOOL_LIST = "TOOL_LIST"
    GENERAL_CHAT = "GENERAL_CHAT"
    HELP = "HELP"
    UNKNOWN = "UNKNOWN"


@dataclass
class ChatMessage:
    """채팅 메시지를 나타내는 데이터 클래스
    
    단일 책임 원칙: 채팅 메시지의 데이터와 메타데이터만을 담당
    """
    role: MessageRole
    content: str
    timestamp: datetime
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """메시지를 딕셔너리로 변환합니다"""
        return {
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata or {}
        }


@dataclass 
class ParsedIntent:
    """파싱된 사용자 의도를 나타내는 데이터 클래스
    
    단일 책임 원칙: 의도 분석 결과만을 담당
    """
    intent_type: IntentType
    confidence: float
    parameters: Dict[str, Any]
    target_server: Optional[str] = None
    target_tool: Optional[str] = None
    
    def is_mcp_action(self) -> bool:
        """MCP 도구 호출이 필요한 의도인지 확인합니다"""
        return self.intent_type in [
            IntentType.WEATHER_QUERY,
            IntentType.FILE_OPERATION, 
            IntentType.API_REQUEST
        ]


@dataclass
class MCPToolCall:
    """MCP 도구 호출을 나타내는 데이터 클래스
    
    단일 책임 원칙: MCP 도구 호출의 요청과 결과만을 담당
    """
    server_name: str
    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None
    
    def is_successful(self) -> bool:
        """도구 호출이 성공했는지 확인합니다"""
        return self.error is None and self.result is not None


class ChatState(TypedDict, total=False):
    """LangGraph 워크플로우에서 사용하는 채팅 상태
    
    TypedDict를 사용하여 상태 구조를 명확히 정의하고 타입 안정성을 제공합니다.
    total=False로 설정하여 모든 키가 선택적으로 사용될 수 있도록 합니다.
    """
    
    # 현재 메시지 (LangChain BaseMessage 호환)
    current_message: Optional[BaseMessage]
    
    # 세션 및 컨텍스트
    session_id: Optional[str]
    context: Dict[str, Any]
    
    # Enhanced MCP Client
    mcp_client: Optional[Any]
    
    # 메시지 히스토리
    messages: List[ChatMessage]
    
    # 의도 분석 결과
    parsed_intent: Optional[ParsedIntent]
    
    # MCP 도구 호출 관련
    tool_calls: List[MCPToolCall]
    tool_results: List[Dict[str, Any]]
    
    # 응답 생성
    response: str
    
    # 워크플로우 제어
    success: bool
    error: Optional[str]
    step_count: int
    next_step: Optional[str] 