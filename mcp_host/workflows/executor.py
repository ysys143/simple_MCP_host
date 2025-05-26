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
from .llm_nodes import llm_parse_intent, llm_call_mcp_tool, llm_generate_response, llm_generate_response_with_streaming
from .state import create_initial_state


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
            
            # 초기 상태 구성 - create_initial_state 사용
            initial_state = create_initial_state(
                user_message=user_message,
                session_id=session_id,
                mcp_client=mcp_client
            )
            
            # 컨텍스트 정보 추가
            if context:
                initial_state["context"].update(context)
            
            # 워크플로우 실행
            result = await self.workflow.ainvoke(initial_state)
            
            # 결과 정리
            parsed_intent = result.get("parsed_intent")
            intent_type_value = None
            if parsed_intent and hasattr(parsed_intent, "intent_type"):
                intent_type_value = parsed_intent.intent_type.value if hasattr(parsed_intent.intent_type, "value") else str(parsed_intent.intent_type)
            
            response_data = {
                "success": result.get("success", False),
                "response": result.get("response", "응답을 생성할 수 없습니다."),
                "intent_type": intent_type_value,
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
    
    async def execute_message_with_streaming(
        self,
        user_message: str,
        session_id: str,
        sse_manager = None,
        context: Optional[Dict[str, Any]] = None,
        mcp_client = None
    ) -> Dict[str, Any]:
        """SSE 스트리밍과 함께 사용자 메시지를 처리합니다
        
        Args:
            user_message: 사용자 입력 메시지
            session_id: 세션 식별자 
            sse_manager: SSE 매니저 인스턴스
            context: 추가 컨텍스트 정보
            mcp_client: MCP 클라이언트 인스턴스
            
        Returns:
            실행 결과를 포함한 딕셔너리
        """
        if not sse_manager:
            # SSE 매니저가 없으면 기본 실행
            return await self.execute_message(user_message, session_id, context, mcp_client)
        
        # SSE 스트리밍 import (순환 import 방지)
        from ..streaming import (
            create_thinking_message,
            create_acting_message,
            create_observing_message,
            create_tool_call_message,
            create_final_response_message,
            create_error_message
        )
        
        try:
            self._logger.info(f"스트리밍 워크플로우 실행 시작 - 세션: {session_id}")
            
            # 1단계: 의도 분석 시작
            thinking_msg = create_thinking_message(
                f"'{user_message}' 요청을 분석하고 있습니다...",
                session_id,
                iteration=1
            )
            await sse_manager.send_to_session(session_id, thinking_msg)
            
            # 초기 상태 구성 - create_initial_state 사용
            initial_state = create_initial_state(
                user_message=user_message,
                session_id=session_id,
                mcp_client=mcp_client
            )
            
            # 컨텍스트 정보 추가
            if context:
                initial_state["context"].update(context)
            
            # 의도 분석 실행
            thinking_msg = create_thinking_message(
                "요청 의도를 파악하고 적절한 도구를 선택하고 있습니다...",
                session_id,
                iteration=2
            )
            await sse_manager.send_to_session(session_id, thinking_msg)
            
            # 의도 분석 단계
            state = llm_parse_intent(initial_state)
            
            # 의도 분석 결과 스트리밍
            if state.get("parsed_intent"):
                intent = state["parsed_intent"]
                logger.info(f"의도 분석 결과: {intent.intent_type.value}")
                logger.info(f"대상 서버: {intent.target_server}")
                logger.info(f"대상 도구: {intent.target_tool}")
                logger.info(f"매개변수: {intent.parameters}")
                logger.info(f"MCP 액션 여부: {intent.is_mcp_action()}")
                
                observing_msg = create_observing_message(
                    f"의도 분석 완료: {intent.intent_type.value}",
                    session_id,
                    observation_data={"intent_type": intent.intent_type.value}
                )
                await sse_manager.send_to_session(session_id, observing_msg)
                
                # 도구 호출이 필요한 경우 - is_mcp_action() 메서드 사용
                if intent.is_mcp_action():
                    logger.info(f"🔧 MCP 도구 호출 필요 - 서버: {intent.target_server}, 도구: {intent.target_tool}")
                    
                    acting_msg = create_acting_message(
                        f"필요한 도구를 호출하고 있습니다...",
                        session_id,
                        action_details={"intent": intent.intent_type.value, "server": intent.target_server, "tool": intent.target_tool}
                    )
                    await sse_manager.send_to_session(session_id, acting_msg)
                    
                    # 도구 호출 실행
                    logger.info(f"🔧 도구 호출 함수 실행 시작")
                    state = await llm_call_mcp_tool(state)
                    logger.info(f"🔧 도구 호출 함수 실행 완료")
                    
                    # 도구 호출 결과 스트리밍
                    if state.get("tool_calls"):
                        logger.info(f"🔧 도구 호출 결과 있음: {len(state['tool_calls'])}개")
                        for tool_call in state["tool_calls"]:
                            tool_msg = create_tool_call_message(
                                tool_call.server_name,
                                tool_call.tool_name,
                                "completed" if tool_call.is_successful() else "failed",
                                session_id
                            )
                            await sse_manager.send_to_session(session_id, tool_msg)
                            
                            observing_msg = create_observing_message(
                                f"도구 실행 결과: {tool_call.result}",
                                session_id,
                                observation_data={
                                    "tool": tool_call.tool_name,
                                    "success": tool_call.is_successful()
                                }
                            )
                            await sse_manager.send_to_session(session_id, observing_msg)
                    else:
                        logger.warning(f"🔧 도구 호출 후에도 tool_calls가 비어있음")
                else:
                    logger.info(f"일반 대화 처리 - MCP 도구 호출 불필요")
            else:
                logger.warning(f"의도 분석 결과가 없음")
                observing_msg = create_observing_message(
                    "의도 분석에 실패했습니다. 일반 대화로 처리합니다.",
                    session_id,
                    observation_data={"intent_type": "failed"}
                )
                await sse_manager.send_to_session(session_id, observing_msg)
            
            # 응답 생성 단계
            thinking_msg = create_thinking_message(
                "수집된 정보를 바탕으로 최종 응답을 생성하고 있습니다...",
                session_id,
                iteration=3
            )
            await sse_manager.send_to_session(session_id, thinking_msg)
            
            # 토큰 단위 스트리밍 응답 생성
            self._logger.info("🚀 스트리밍 응답 생성 함수 호출 시작")
            try:
                result = await llm_generate_response_with_streaming(state, sse_manager, session_id)
                self._logger.info("🚀 스트리밍 응답 생성 함수 완료")
            except Exception as e:
                self._logger.error(f"🚀 스트리밍 응답 생성 함수 오류: {e}")
                import traceback
                self._logger.error(f"🚀 스택 트레이스: {traceback.format_exc()}")
                raise
            
            # 최종 응답 생성 (스트리밍에서 이미 전송되므로 final_response는 생략)
            parsed_intent = result.get("parsed_intent")
            intent_type_value = None
            if parsed_intent and hasattr(parsed_intent, "intent_type"):
                intent_type_value = parsed_intent.intent_type.value if hasattr(parsed_intent.intent_type, "value") else str(parsed_intent.intent_type)
            
            response_data = {
                "success": result.get("success", False),
                "response": result.get("response", "응답을 생성할 수 없습니다."),
                "intent_type": intent_type_value,
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
                error_msg = create_error_message(
                    response_data["error"],
                    session_id
                )
                await sse_manager.send_to_session(session_id, error_msg)
            
            # 스트리밍에서 이미 final_response가 전송되므로 여기서는 생략
            
            self._logger.info(f"스트리밍 워크플로우 실행 완료 - 성공: {response_data['success']}")
            return response_data
            
        except Exception as e:
            self._logger.error(f"스트리밍 워크플로우 실행 오류: {e}")
            
            # 오류 메시지 스트리밍
            if sse_manager:
                error_msg = create_error_message(str(e), session_id)
                await sse_manager.send_to_session(session_id, error_msg)
            
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