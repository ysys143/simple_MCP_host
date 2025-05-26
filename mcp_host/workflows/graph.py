"""LangGraph StateGraph 워크플로우 구성

노드들을 연결하여 완전한 대화형 워크플로우를 구성합니다.
단일 책임 원칙: 워크플로우 구성과 실행만 담당합니다.
"""

import logging
from typing import Optional, Dict, Any

from langgraph.graph import StateGraph, END
from langgraph.graph.graph import CompiledGraph

from .state import ChatState, create_initial_state
from .nodes import parse_message, call_mcp_tool, generate_response
from .react_nodes import (
    react_think_node, react_act_node, react_observe_node, react_finalize_node
)


def should_call_mcp_tool(state: ChatState) -> str:
    """MCP 도구 호출 여부를 결정하는 조건부 엣지
    
    Args:
        state: 현재 워크플로우 상태
        
    Returns:
        다음 노드 이름
    """
    # ReAct 모드인 경우 ReAct 워크플로우로 라우팅
    if state.get("react_mode", False):
        return "react_think"
    
    parsed_intent = state.get("parsed_intent")
    
    if parsed_intent and parsed_intent.is_mcp_action():
        return "call_mcp_tool"
    else:
        return "generate_response"


def should_continue_react(state: ChatState) -> str:
    """ReAct 워크플로우 계속 여부를 결정하는 조건부 엣지
    
    Args:
        state: 현재 워크플로우 상태
        
    Returns:
        다음 노드 이름
    """
    next_step = state.get("next_step")
    
    if next_step == "react_think":
        return "react_think"
    elif next_step == "react_act":
        return "react_act"
    elif next_step == "react_observe":
        return "react_observe"
    elif next_step == "react_finalize":
        return "react_finalize"
    elif next_step == "error_handler":
        return "generate_response"  # 에러 시 일반 응답으로
    else:
        return END


def should_continue(state: ChatState) -> str:
    """워크플로우 계속 여부를 결정하는 조건부 엣지
    
    Args:
        state: 현재 워크플로우 상태
        
    Returns:
        다음 노드 이름 또는 END
    """
    should_continue = state.get("should_continue", True)
    error_message = state.get("error_message")
    
    if error_message or not should_continue:
        return END
    else:
        return "generate_response"


def create_workflow() -> CompiledGraph:
    """MCP 호스트 워크플로우를 생성합니다
    
    워크플로우 구조:
    START → parse_message → [조건부] → call_mcp_tool → generate_response → END
                          ↘ → generate_response → END
                          ↘ → react_think → react_act → react_observe → [조건부] → react_finalize → END
                                                                      ↘ → react_think (반복)
    
    Returns:
        컴파일된 LangGraph 워크플로우
    """
    logger = logging.getLogger(__name__)
    
    # StateGraph 생성
    workflow = StateGraph(ChatState)
    
    # 기존 노드 추가
    workflow.add_node("parse_message", parse_message)
    workflow.add_node("call_mcp_tool", call_mcp_tool)
    workflow.add_node("generate_response", generate_response)
    
    # ReAct 노드 추가
    workflow.add_node("react_think", react_think_node)
    workflow.add_node("react_act", react_act_node)
    workflow.add_node("react_observe", react_observe_node)
    workflow.add_node("react_finalize", react_finalize_node)
    
    # 시작점 설정
    workflow.set_entry_point("parse_message")
    
    # 엣지 연결
    # parse_message → 조건부 분기 (일반 워크플로우 vs ReAct 워크플로우)
    workflow.add_conditional_edges(
        "parse_message",
        should_call_mcp_tool,
        {
            "call_mcp_tool": "call_mcp_tool",
            "generate_response": "generate_response",
            "react_think": "react_think"
        }
    )
    
    # 기존 워크플로우 엣지
    workflow.add_edge("call_mcp_tool", "generate_response")
    workflow.add_edge("generate_response", END)
    
    # ReAct 워크플로우 엣지
    workflow.add_conditional_edges(
        "react_think",
        should_continue_react,
        {
            "react_act": "react_act",
            "react_finalize": "react_finalize",
            "generate_response": "generate_response",
            END: END
        }
    )
    
    workflow.add_conditional_edges(
        "react_act",
        should_continue_react,
        {
            "react_observe": "react_observe",
            "react_finalize": "react_finalize",
            END: END
        }
    )
    
    workflow.add_conditional_edges(
        "react_observe",
        should_continue_react,
        {
            "react_think": "react_think",
            "react_finalize": "react_finalize",
            END: END
        }
    )
    
    workflow.add_edge("react_finalize", END)
    
    # 워크플로우 컴파일
    compiled_workflow = workflow.compile()
    
    logger.info("LangGraph 워크플로우 생성 완료 (ReAct 지원)")
    return compiled_workflow


class MCPWorkflowExecutor:
    """MCP 워크플로우 실행기
    
    단일 책임 원칙: 워크플로우 실행과 결과 처리만 담당
    """
    
    def __init__(self, workflow: Optional[CompiledGraph] = None):
        """워크플로우 실행기 초기화
        
        Args:
            workflow: 컴파일된 워크플로우 (None이면 기본 워크플로우 생성)
        """
        self._workflow = workflow or create_workflow()
        self._logger = logging.getLogger(__name__)
    
    async def execute_message(self, 
                            user_message: str,
                            session_id: Optional[str] = None,
                            user_id: Optional[str] = None,
                            context: Optional[Dict[str, Any]] = None,
                            mcp_client: Optional[Any] = None) -> Dict[str, Any]:
        """사용자 메시지를 처리하고 응답을 생성합니다
        
        Args:
            user_message: 사용자 메시지
            session_id: 세션 ID (선택적)
            user_id: 사용자 ID (선택적)
            context: 추가 컨텍스트 정보 (선택적)
            mcp_client: Enhanced MCP Client 인스턴스 (선택적)
            
        Returns:
            처리 결과 딕셔너리
        """
        try:
            self._logger.info(f"워크플로우 실행 시작: {user_message}")
            
            # 초기 상태 생성 (MCP 클라이언트 포함)
            initial_state = create_initial_state(
                user_message=user_message,
                session_id=session_id,
                user_id=user_id,
                mcp_client=mcp_client
            )
            
            # 컨텍스트 정보 추가
            if context:
                # 서버 및 도구 정보 추가
                if "available_servers" in context:
                    initial_state["available_servers"] = context["available_servers"]
                if "available_tools" in context:
                    initial_state["available_tools"] = context["available_tools"]
            
            # 워크플로우 실행
            final_state = await self._workflow.ainvoke(initial_state)
            
            # 결과 추출
            result = self._extract_result(final_state)
            
            self._logger.info("워크플로우 실행 완료")
            return result
            
        except Exception as e:
            self._logger.error(f"워크플로우 실행 오류: {e}")
            return {
                "success": False,
                "error": str(e),
                "response": "죄송합니다. 요청을 처리하는 중 오류가 발생했습니다."
            }
    
    def _extract_result(self, final_state: ChatState) -> Dict[str, Any]:
        """최종 상태에서 결과를 추출합니다
        
        Args:
            final_state: 워크플로우 최종 상태
            
        Returns:
            결과 딕셔너리
        """
        # 기본 결과 구조
        result = {
            "success": True,
            "response": "",
            "intent_type": None,
            "tool_calls": [],
            "conversation_history": []
        }
        
        # 에러 확인
        error_message = final_state.get("error_message")
        if error_message:
            result["success"] = False
            result["error"] = error_message
            result["response"] = f"오류: {error_message}"
            return result
        
        # 응답 추출
        response_content = final_state.get("response_content")
        if response_content:
            result["response"] = response_content
        
        # 의도 타입 추출
        parsed_intent = final_state.get("parsed_intent")
        if parsed_intent:
            result["intent_type"] = parsed_intent.intent_type.value
        
        # 도구 호출 내역 추출
        mcp_calls = final_state.get("mcp_calls", [])
        result["tool_calls"] = [
            {
                "server": call.server_name,
                "tool": call.tool_name,
                "arguments": call.arguments,
                "result": call.result,
                "success": call.is_successful(),
                "execution_time_ms": call.execution_time_ms
            }
            for call in mcp_calls
        ]
        
        # 대화 기록 추출
        messages = final_state.get("messages", [])
        result["conversation_history"] = [msg.to_dict() for msg in messages]
        
        return result


def create_workflow_executor() -> MCPWorkflowExecutor:
    """워크플로우 실행기 팩토리 함수
    
    Returns:
        MCPWorkflowExecutor 인스턴스
    """
    return MCPWorkflowExecutor() 