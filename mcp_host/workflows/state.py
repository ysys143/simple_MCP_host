"""워크플로우 상태 관리

LangGraph 워크플로우에서 사용하는 상태 관리 유틸리티들입니다.
models.py의 정의를 재사용하여 중복을 제거했습니다.

SOLID 원칙을 준수하여 상태 관리 로직만을 담당합니다.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime

# models.py에서 필요한 클래스들을 import
from ..models import (
    ChatState, ChatMessage, MessageRole, 
    MCPToolCall
)


def create_initial_state(
    user_message: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    mcp_client: Optional[Any] = None
) -> ChatState:
    """초기 채팅 상태를 생성합니다
    
    Args:
        user_message: 사용자 메시지
        session_id: 세션 ID (선택적)
        user_id: 사용자 ID (선택적)
        mcp_client: Enhanced MCP Client 인스턴스 (선택적)
    
    Returns:
        초기화된 ChatState
    """
    initial_message = ChatMessage(
        role=MessageRole.USER,
        content=user_message,
        timestamp=datetime.now()
    )
    
    state: ChatState = {
        "messages": [initial_message],
        "current_message": initial_message,
        "parsed_intent": None,
        "tool_calls": [],  # models.py의 ChatState 구조에 맞춤
        "tool_results": [],
        "response": "",
        "success": False,
        "error": None,
        "step_count": 0,
        "next_step": None,
        "session_id": session_id,
        "context": {},
        "mcp_client": mcp_client
    }
    
    return state


def add_assistant_message(state: ChatState, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    """어시스턴트 메시지를 상태에 추가합니다
    
    Args:
        state: 현재 채팅 상태
        content: 메시지 내용
        metadata: 메시지 메타데이터 (선택적)
    """
    assistant_message = ChatMessage(
        role=MessageRole.ASSISTANT,
        content=content,
        timestamp=datetime.now(),
        metadata=metadata
    )
    
    state["messages"].append(assistant_message)
    state["response"] = content


def add_tool_message(state: ChatState, tool_call: MCPToolCall) -> None:
    """도구 호출 결과를 메시지로 추가합니다
    
    Args:
        state: 현재 채팅 상태
        tool_call: MCP 도구 호출 결과
    """
    tool_content = f"도구 호출: {tool_call.server_name}.{tool_call.tool_name}"
    if tool_call.is_successful():
        tool_content += f"\n결과: {tool_call.result}"
    else:
        tool_content += f"\n오류: {tool_call.error}"
    
    tool_message = ChatMessage(
        role=MessageRole.TOOL,
        content=tool_content,
        timestamp=datetime.now(),
        metadata={
            "server_name": tool_call.server_name,
            "tool_name": tool_call.tool_name,
            "arguments": tool_call.arguments,
            "execution_time_ms": tool_call.execution_time_ms
        }
    )
    
    state["messages"].append(tool_message)


def get_conversation_history(state: ChatState, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """대화 기록을 반환합니다
    
    Args:
        state: 현재 채팅 상태
        limit: 반환할 메시지 수 제한 (선택적)
    
    Returns:
        메시지 딕셔너리 리스트
    """
    messages = state.get("messages", [])
    if limit:
        messages = messages[-limit:]
    
    return [msg.to_dict() for msg in messages]


def is_workflow_complete(state: ChatState) -> bool:
    """워크플로우가 완료되었는지 확인합니다
    
    Args:
        state: 현재 채팅 상태
    
    Returns:
        완료 여부
    """
    return state.get("success", False) or state.get("error") is not None 