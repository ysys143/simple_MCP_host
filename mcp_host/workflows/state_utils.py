"""워크플로우 상태 유틸리티

ChatState를 조작하기 위한 유틸리티 함수들을 제공합니다.
단일 책임 원칙을 준수하여 각 함수는 특정한 상태 변경만을 담당합니다.
"""

from typing import Dict, Any, Optional
from ..models import ChatState, MCPToolCall, ChatMessage, MessageRole
from datetime import datetime


def update_workflow_step(state: ChatState, step: str) -> None:
    """워크플로우 단계를 업데이트합니다
    
    Args:
        state: 현재 채팅 상태
        step: 새로운 워크플로우 단계
    """
    state["next_step"] = step
    if "step_count" not in state:
        state["step_count"] = 0
    state["step_count"] += 1


def set_error(state: ChatState, error_message: str) -> None:
    """오류 메시지를 상태에 설정합니다
    
    Args:
        state: 현재 채팅 상태
        error_message: 오류 메시지
    """
    state["error"] = error_message
    state["success"] = False


def add_tool_call(state: ChatState, tool_call: MCPToolCall) -> None:
    """MCP 도구 호출을 상태에 추가합니다
    
    Args:
        state: 현재 채팅 상태
        tool_call: MCP 도구 호출 정보
    """
    if "tool_calls" not in state:
        state["tool_calls"] = []
    state["tool_calls"].append(tool_call)


def add_tool_result(state: ChatState, result: Dict[str, Any]) -> None:
    """도구 실행 결과를 상태에 추가합니다
    
    Args:
        state: 현재 채팅 상태
        result: 도구 실행 결과
    """
    if "tool_results" not in state:
        state["tool_results"] = []
    state["tool_results"].append(result)


def set_success(state: ChatState, response: str) -> None:
    """성공 상태로 설정하고 응답을 저장합니다
    
    Args:
        state: 현재 채팅 상태
        response: 생성된 응답
    """
    state["success"] = True
    state["response"] = response
    state["error"] = None


def add_message(state: ChatState, role: MessageRole, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    """새 메시지를 상태에 추가합니다
    
    Args:
        state: 현재 채팅 상태
        role: 메시지 역할
        content: 메시지 내용
        metadata: 추가 메타데이터
    """
    if "messages" not in state:
        state["messages"] = []
    
    message = ChatMessage(
        role=role,
        content=content,
        timestamp=datetime.now(),
        metadata=metadata
    )
    state["messages"].append(message)


def get_last_message(state: ChatState) -> Optional[ChatMessage]:
    """마지막 메시지를 반환합니다
    
    Args:
        state: 현재 채팅 상태
        
    Returns:
        마지막 메시지 또는 None
    """
    messages = state.get("messages", [])
    return messages[-1] if messages else None


def is_workflow_complete(state: ChatState) -> bool:
    """워크플로우가 완료되었는지 확인합니다
    
    Args:
        state: 현재 채팅 상태
    
    Returns:
        워크플로우 완료 여부
    """
    return (
        state.get("success", False) or
        state.get("error") is not None or
        state.get("response", "") != ""
    ) 