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
    TOOL_CALL = "TOOL_CALL"  # 특정 도구 호출이 필요한 경우
    GENERAL_CHAT = "GENERAL_CHAT"  # 일반 대화
    HELP = "HELP"  # 도움말 요청
    SERVER_STATUS = "SERVER_STATUS"  # 서버 상태 확인
    TOOL_LIST = "TOOL_LIST"  # 도구 목록 요청
    UNKNOWN = "UNKNOWN"  # 알 수 없는 의도


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
        return self.intent_type == IntentType.TOOL_CALL


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
    mcp_request_json: Optional[str] = None # 실제 MCP 요청 JSON 문자열
    mcp_response_json: Optional[str] = None # 실제 MCP 응답 JSON 문자열
    
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
    
    # MCP Client
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
    
    # ReAct 패턴 관련 필드
    react_mode: bool  # ReAct 모드 활성화 여부
    react_iteration: int  # 현재 ReAct 반복 횟수
    react_max_iterations: int  # 최대 ReAct 반복 횟수 (기본값: 10)
    react_current_step: Optional[str]  # 현재 ReAct 단계 (think/act/observe)
    react_thought: Optional[str]  # 현재 생각 내용
    react_action: Optional[str]  # 현재 행동 계획
    react_observation: Optional[str]  # 현재 관찰 결과
    react_final_answer: Optional[str]  # 최종 답변
    react_should_continue: bool  # 계속 진행할지 여부 