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
    mcp_client: Optional[Any] = None,
    react_mode: bool = False
) -> ChatState:
    """초기 채팅 상태를 생성합니다 (세션 히스토리 포함)
    
    Args:
        user_message: 사용자 메시지
        session_id: 세션 ID (선택적)
        user_id: 사용자 ID (선택적)
        mcp_client: Enhanced MCP Client 인스턴스 (선택적)
        react_mode: ReAct 모드 활성화 여부 (선택적)
    
    Returns:
        초기화된 ChatState (기존 대화 히스토리 포함)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # 새로운 사용자 메시지 생성
    new_user_message = ChatMessage(
        role=MessageRole.USER,
        content=user_message,
        timestamp=datetime.now()
    )
    
    # 기존 대화 히스토리 불러오기
    existing_messages = []
    if session_id:
        try:
            # 순환 import 방지를 위해 함수 내에서 import
            from ..sessions import get_session_manager
            session_manager = get_session_manager()
            
            logger.info(f"세션 히스토리 로딩 시도 - 세션 ID: {session_id}")
            
            # 세션에 새 사용자 메시지 추가 (히스토리에 저장)
            session_manager.add_user_message(session_id, user_message)
            logger.info(f"사용자 메시지 세션에 추가 완료: {len(user_message)} 글자")
            
            # 기존 메시지들을 ChatMessage 객체로 변환
            history = session_manager.get_conversation_history(session_id, limit=50)
            logger.info(f"세션에서 불러온 히스토리: {len(history)}개 메시지")
            
            for i, msg_dict in enumerate(history[:-1]):  # 마지막 메시지는 방금 추가한 것이므로 제외
                logger.debug(f"히스토리 메시지 {i}: {msg_dict}")
                role_map = {
                    "user": MessageRole.USER,
                    "assistant": MessageRole.ASSISTANT, 
                    "tool": MessageRole.TOOL
                }
                if msg_dict["role"] in role_map:
                    existing_messages.append(ChatMessage(
                        role=role_map[msg_dict["role"]],
                        content=msg_dict["content"],
                        timestamp=datetime.fromisoformat(msg_dict["timestamp"])
                    ))
            
            logger.info(f"변환된 기존 메시지 수: {len(existing_messages)}개")
            
        except Exception as e:
            # 세션 관리 오류가 있어도 기본 동작은 유지
            logger.warning(f"세션 히스토리 로드 실패: {e}")
            logger.exception("세션 히스토리 로드 오류 상세:")
    
    # 전체 메시지 리스트 구성 (기존 히스토리 + 새 메시지)
    all_messages = existing_messages + [new_user_message]
    logger.info(f"최종 메시지 리스트 크기: {len(all_messages)}개 (기존: {len(existing_messages)}개, 새 메시지: 1개)")
    
    state: ChatState = {
        "messages": all_messages,
        "current_message": new_user_message,  # 현재 처리할 메시지는 새 메시지
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
        "mcp_client": mcp_client,
        
        # ReAct 패턴 관련 필드 초기화
        "react_mode": react_mode,
        "react_iteration": 0,
        "react_max_iterations": 10,
        "react_current_step": None,
        "react_thought": None,
        "react_action": None,
        "react_observation": None,
        "react_final_answer": None,
        "react_should_continue": True
    }
    
    # ReAct 모드인 경우 첫 번째 단계 설정
    if react_mode:
        state["next_step"] = "react_think"
        logger.info("ReAct 모드로 초기화됨")
    
    return state


def add_assistant_message(state: ChatState, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
    """어시스턴트 메시지를 상태에 추가합니다
    
    Args:
        state: 현재 채팅 상태
        content: 메시지 내용
        metadata: 메시지 메타데이터 (선택적)
    """
    import logging
    logger = logging.getLogger(__name__)
    
    assistant_message = ChatMessage(
        role=MessageRole.ASSISTANT,
        content=content,
        timestamp=datetime.now(),
        metadata=metadata
    )
    
    state["messages"].append(assistant_message)
    state["response"] = content
    
    logger.info(f"상태에 어시스턴트 메시지 추가: {len(content)} 글자, 총 메시지: {len(state['messages'])}개")
    
    # 세션에도 저장
    session_id = state.get("session_id")
    if session_id:
        try:
            from ..sessions import get_session_manager
            session_manager = get_session_manager()
            logger.info(f"세션에 어시스턴트 메시지 저장 시도 - 세션 ID: {session_id}")
            session_manager.add_assistant_message(session_id, content, metadata)
            logger.info(f"세션에 어시스턴트 메시지 저장 완료")
        except Exception as e:
            logger.warning(f"세션에 어시스턴트 메시지 저장 실패: {e}")
            logger.exception("어시스턴트 메시지 저장 오류 상세:")
    else:
        logger.warning("session_id가 없어 세션에 메시지를 저장할 수 없습니다")


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