"""워크플로우 실행기

LangGraph 기반의 MCP 워크플로우 실행을 담당합니다.
LLM(ChatGPT) 기반 의도 분석과 자연어 응답 생성을 통해
더 지능적이고 유연한 대화형 MCP 호스트 시스템을 제공합니다.

SOLID 원칙을 준수하여 실행기는 워크플로우 관리만 담당하고,
각 노드는 단일 책임을 갖도록 설계되었습니다.
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, END

from ..models import ChatState
from .llm_nodes import llm_parse_intent, llm_call_mcp_tool, llm_generate_response


# 로깅 설정
logger = logging.getLogger(__name__)


def _decide_next_step(state: ChatState) -> str:
    """현재 상태를 기반으로 다음 워크플로우 단계를 결정합니다
    
    Args:
        state: 현재 워크플로우 상태
        
    Returns:
        다음 실행할 노드 이름
    """
    next_step = state.get("next_step")
    if next_step:
        return next_step
    
    # 성공적으로 완료되었거나 응답이 생성되었으면 종료
    if state.get("success") or state.get("response"):
        return "completed"
    
    # 기본적으로는 LLM 응답 생성으로
    return "llm_generate_response"


class MCPWorkflowExecutor:
    """MCP 워크플로우 실행기
    
    단일 책임 원칙: 워크플로우 실행과 상태 관리만 담당
    개방-폐쇄 원칙: 새로운 노드 추가 시 기존 코드 수정 없이 확장 가능
    """
    
    def __init__(self, compiled_workflow):
        self.workflow = compiled_workflow
        self._logger = logging.getLogger(__name__)
        
    async def execute_message(
        self,
        user_message: str,
        session_id: str,
        context: Optional[Dict[str, Any]] = None,
        mcp_client = None
    ) -> Dict[str, Any]:
        """사용자 메시지를 처리하고 워크플로우를 실행합니다
        
        Args:
            user_message: 사용자 입력 메시지
            session_id: 세션 식별자
            context: 추가 컨텍스트 정보
            mcp_client: MCP 클라이언트 인스턴스
            
        Returns:
            실행 결과를 포함한 딕셔너리
        """
        try:
            self._logger.info(f"워크플로우 실행 시작 - 세션: {session_id}")
            
            # 초기 상태 구성 (models.py의 ChatState 구조 사용)
            initial_state: ChatState = {
                "current_message": BaseMessage(content=user_message, type="human"),
                "session_id": session_id,
                "context": context or {},
                "mcp_client": mcp_client,
                "messages": [],
                "parsed_intent": None,
                "tool_calls": [],
                "tool_results": [],
                "response": "",
                "success": False,
                "error": None,
                "step_count": 0,
                "next_step": None
            }
            
            # 워크플로우 실행
            result = await self.workflow.ainvoke(initial_state)
            
            # 결과 정리
            parsed_intent = result.get("parsed_intent")
            intent_type = parsed_intent.intent_type.value if parsed_intent else None
            
            response_data = {
                "success": result.get("success", False),
                "response": result.get("response", "응답을 생성할 수 없습니다."),
                "intent_type": intent_type,
                "tool_calls": [
                    {
                        "server": call.server_name,
                        "tool": call.tool_name,
                        "arguments": call.arguments,
                        "result": call.result,
                        "success": call.is_successful(),
                        "execution_time_ms": call.execution_time_ms
                    } for call in result.get("tool_calls", [])
                ],
                "session_id": session_id
            }
            
            if not result.get("success"):
                response_data["error"] = result.get("error", "알 수 없는 오류")
            
            self._logger.info(f"워크플로우 실행 완료 - 성공: {response_data['success']}")
            return response_data
            
        except Exception as e:
            self._logger.error(f"워크플로우 실행 오류: {e}")
            return {
                "success": False,
                "response": f"죄송합니다. 요청을 처리하는 중 오류가 발생했습니다: {e}",
                "error": str(e),
                "session_id": session_id
            }


def create_workflow_executor() -> MCPWorkflowExecutor:
    """LangGraph 기반 MCP 워크플로우 실행기를 생성합니다
    
    LLM(ChatGPT) 기반의 지능적인 의도 분석, 도구 호출, 응답 생성을 
    통해 자연스러운 대화형 MCP 호스트 시스템을 구성합니다.
    
    Returns:
        설정된 워크플로우 실행기
    """
    # StateGraph 생성
    workflow = StateGraph(ChatState)
    
    # === LLM 기반 노드들 ===
    workflow.add_node("llm_parse_intent", llm_parse_intent)
    workflow.add_node("llm_call_mcp_tool", llm_call_mcp_tool) 
    workflow.add_node("llm_generate_response", llm_generate_response)
    
    # === 진입점과 흐름 설정 ===
    workflow.set_entry_point("llm_parse_intent")  # LLM 우선 시도
    
    # LLM 기반 흐름
    workflow.add_conditional_edges(
        "llm_parse_intent",
        _decide_next_step,
        {
            "llm_call_mcp_tool": "llm_call_mcp_tool",
            "llm_generate_response": "llm_generate_response",
        }
    )
    
    workflow.add_edge("llm_call_mcp_tool", "llm_generate_response")
    
    # llm_generate_response에서 조건부 분기
    workflow.add_conditional_edges(
        "llm_generate_response",
        _decide_next_step,
        {
            "completed": END,
        }
    )
    
    # 워크플로우 컴파일
    compiled_workflow = workflow.compile()
    
    logger.info("LLM 기반 MCP 워크플로우 생성 완료")
    return MCPWorkflowExecutor(compiled_workflow) 