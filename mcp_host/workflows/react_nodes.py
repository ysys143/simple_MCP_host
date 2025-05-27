"""ReAct 패턴 워크플로우 노드

ReAct (Reasoning and Acting) 패턴을 구현하는 LangGraph 노드들입니다.
Think-Act-Observe 사이클을 통해 복잡한 문제를 단계적으로 해결합니다.

SOLID 원칙을 준수하여 각 노드는 단일 책임을 가집니다.
"""

import logging
import re
from typing import Dict, Any, Optional, List
from datetime import datetime
import time
import asyncio
import json
from pathlib import Path

from ..models import ChatState, ChatMessage, MessageRole, MCPToolCall
from ..streaming.message_types import (
    create_thinking_message, create_acting_message, 
    create_observing_message, create_final_response_message,
    create_partial_response_message
)
from ..streaming.sse_manager import get_sse_manager
from .llm_utils import get_llm


logger = logging.getLogger(__name__)


def _build_llm_context_with_history(state: ChatState, system_prompt: str) -> Dict[str, Any]:
    """ReAct용 LLM 컨텍스트를 구성합니다"""
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
    
    messages = [SystemMessage(content=system_prompt)]
    
    # 세션 히스토리에서 메시지 추가
    chat_messages = state.get("messages", [])
    for msg in chat_messages:
        if msg.role == MessageRole.USER:
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == MessageRole.ASSISTANT:
            messages.append(AIMessage(content=msg.content))
    
    return {"messages": messages}


async def react_think_node(state: ChatState) -> ChatState:
    """ReAct Think 단계: 현재 상황을 분석하고 다음 행동을 계획합니다
    
    Args:
        state: 현재 채팅 상태
        
    Returns:
        업데이트된 채팅 상태
    """
    logger.info(f"ReAct Think 단계 시작 - 반복 {state.get('react_iteration', 0)}")
    
    session_id = state.get("session_id")
    iteration = state.get("react_iteration", 0)
    
    # 첫 번째 반복에서만 시작 메시지 전송
    if session_id and iteration == 0:
        sse_manager = get_sse_manager()
        thinking_msg = create_thinking_message(
            f"요청을 분석하고 있습니다...",
            session_id,
            iteration=iteration + 1
        )
        await sse_manager.send_to_session(session_id, thinking_msg)
    
    # 현재 상황 분석을 위한 프롬프트 구성
    think_prompt = await _build_think_prompt(state)
    
    try:
        # LLM을 통한 사고 과정 생성
        llm = get_llm()
        
        # LLM 컨텍스트 구성
        context = _build_llm_context_with_history(state, think_prompt)
        
        # LLM 호출
        response = await llm.ainvoke(context["messages"])
        
        thought_content = response.content.strip()
        
        # 생각 내용 파싱
        parsed_thought = _parse_thought_response(thought_content)
        
        # 의미있는 사고 과정만 SSE로 전송 (너무 짧거나 반복적인 내용 제외)
        if session_id and parsed_thought.get("thought"):
            thought_content = parsed_thought['thought']
            # 의미있는 사고 과정만 전송 (10글자 이상, 반복적인 표현 제외)
            if (len(thought_content) > 10 and 
                not any(skip_word in thought_content for skip_word in ['생각하는 중', '분석 중', '처리 중'])):
                sse_manager = get_sse_manager()
                thinking_detail_msg = create_thinking_message(
                    f"분석: {thought_content}",
                    session_id,
                    iteration=iteration + 1
                )
                await sse_manager.send_to_session(session_id, thinking_detail_msg)
        
        # 상태 업데이트
        state["react_thought"] = thought_content
        state["react_current_step"] = "think"
        state["react_iteration"] = iteration + 1
        
        # 미완료 작업 확인 (최우선)
        remaining_tasks = await _check_remaining_tasks(state)
        logger.info(f"미완료 작업 확인 결과: {remaining_tasks}")
        
        # 미완료 작업이 실제로 있는지 확인 (빈 리스트이거나 ['없음']이면 완료된 것으로 간주)
        has_remaining_tasks = (
            remaining_tasks and 
            remaining_tasks != ['없음'] and 
            not all(task.strip() in ['없음', '', '(추가 작업 필요 없음)', '수집된 정보를 바탕으로'] or 
                   '추가 작업 필요 없음' in task.strip() or
                   '이미' in task.strip() and '완료' in task.strip() or
                   '수집 완료' in task.strip() or
                   '도구가 아닌 직접 수행' in task.strip()
                   for task in remaining_tasks)
        )
        
        # 종료 조건 체크
        if has_remaining_tasks:
            # 미완료 작업이 있으면 무조건 계속 진행
            logger.info(f"미완료 작업이 있어 계속 진행: {remaining_tasks}")
            if parsed_thought.get("action"):
                state["react_action"] = parsed_thought["action"]
            else:
                # 행동이 명시되지 않았지만 미완료 작업이 있으면 첫 번째 작업을 행동으로 설정
                state["react_action"] = remaining_tasks[0] if remaining_tasks else "continue"
            state["react_should_continue"] = True
            state["next_step"] = "react_act"
        elif parsed_thought.get("final_answer"):
            # 미완료 작업이 없고 최종 답변이 있으면 종료
            logger.info("미완료 작업이 없고 최종 답변이 있어 종료")
            state["react_final_answer"] = parsed_thought["final_answer"]
            state["react_should_continue"] = False
            state["next_step"] = "react_finalize"
        elif parsed_thought.get("action"):
            # 미완료 작업이 없지만 행동이 있으면 실행
            state["react_action"] = parsed_thought["action"]
            state["react_should_continue"] = True
            state["next_step"] = "react_act"
        else:
            # 미완료 작업도 없고 행동도 명시되지 않았으면 종료
            logger.info("미완료 작업과 행동이 모두 없어 종료")
            state["react_should_continue"] = False
            state["next_step"] = "react_finalize"
        
        logger.info(f"Think 단계 완료 - 다음 단계: {state.get('next_step')}")
        
    except Exception as e:
        logger.error(f"Think 단계 오류: {e}")
        state["error"] = f"사고 과정 생성 중 오류: {str(e)}"
        state["react_should_continue"] = False
        state["next_step"] = "error_handler"
    
    return state


async def react_act_node(state: ChatState) -> ChatState:
    """ReAct Act 단계: 계획된 행동을 실행합니다
    
    Args:
        state: 현재 채팅 상태
        
    Returns:
        업데이트된 채팅 상태
    """
    logger.info("ReAct Act 단계 시작")
    
    session_id = state.get("session_id")
    action = state.get("react_action", "") # 예: "get_forecast: 서울, 3"
    iteration = state.get("react_iteration", 0)
    
    # 연속 실패 카운터 확인
    consecutive_failures = state.get("react_consecutive_failures", 0)
    max_consecutive_failures = 3  # 연속 3회 실패 시 종료
    
    # tool_call_result를 먼저 실행하고 결과를 얻습니다.
    tool_call_result: Optional[MCPToolCall] = None
    try:
        tool_call_result = await _execute_action(state, action)
        logger.info(f"[react_act_node] _execute_action 결과: tool_call_result = {tool_call_result!r}") # 로깅 수정: 상세 내용을 위해 !r 사용
        
        # 도구 호출이 성공한 경우 실패 카운터 리셋
        if tool_call_result and tool_call_result.is_successful():
            state["react_consecutive_failures"] = 0
        elif tool_call_result is None:
            # 도구 호출 패턴을 찾지 못한 경우
            consecutive_failures += 1
            state["react_consecutive_failures"] = consecutive_failures
            logger.warning(f"도구 호출 패턴을 찾지 못함. 연속 실패 횟수: {consecutive_failures}")
            
            if consecutive_failures >= max_consecutive_failures:
                logger.error(f"연속 {max_consecutive_failures}회 도구 호출 실패로 ReAct 종료")
                state["react_observation"] = f"연속 {max_consecutive_failures}회 도구 호출에 실패하여 작업을 중단합니다."
                state["react_should_continue"] = False
                state["next_step"] = "react_finalize"
                return state
        else:
            # 도구 호출은 했지만 실패한 경우
            consecutive_failures += 1
            state["react_consecutive_failures"] = consecutive_failures
            logger.warning(f"도구 호출 실패. 연속 실패 횟수: {consecutive_failures}")
            
    except Exception as e:
        consecutive_failures += 1
        state["react_consecutive_failures"] = consecutive_failures
        logger.error(f"Act 단계에서 _execute_action 중 오류: {e}. 연속 실패 횟수: {consecutive_failures}")
        
        if consecutive_failures >= max_consecutive_failures:
            logger.error(f"연속 {max_consecutive_failures}회 오류로 ReAct 종료")
            state["error"] = f"연속 {max_consecutive_failures}회 오류로 작업을 중단합니다: {str(e)}"
            state["react_observation"] = f"연속 오류로 인해 작업을 중단합니다: {str(e)}"
            state["react_should_continue"] = False
            state["next_step"] = "react_finalize"
            return state
        
        state["error"] = f"행동 실행 중 오류: {str(e)}"
        state["react_observation"] = f"행동 실행 실패: {str(e)}"
        state["next_step"] = "react_observe"  # 실패해도 관찰 단계로 진행
        return state

    # SSE 메시지 전송
    if session_id:
        sse_manager = get_sse_manager()
        acting_msg = create_acting_message(
            f"행동 실행 중: {action}",
            session_id,
            action_details={"iteration": iteration}
        )
        await sse_manager.send_to_session(session_id, acting_msg)
    
    try:
        # tool_call_result는 위에서 이미 실행되었으므로 여기서 다시 실행하지 않음
        if tool_call_result:
            # 도구 호출 결과를 상태에 추가
            state["tool_calls"].append(tool_call_result)
            state["react_observation"] = _format_tool_result(tool_call_result)
        else:
            # 도구 호출이 아닌 경우 (정보 수집, 분석 등) 또는 _execute_action이 None을 반환한 경우
            state["react_observation"] = f"요청된 행동 '{action}'에 대해 실행할 특정 도구를 찾지 못했거나, 도구 호출이 필요하지 않은 작업입니다."
        
        state["react_current_step"] = "act"
        state["next_step"] = "react_observe"
        
        logger.info("Act 단계 완료")
        
    except Exception as e:
        consecutive_failures += 1
        state["react_consecutive_failures"] = consecutive_failures
        logger.error(f"Act 단계 후 처리 오류: {e}. 연속 실패 횟수: {consecutive_failures}") # _execute_action 이후의 로직에서 발생한 오류
        
        if consecutive_failures >= max_consecutive_failures:
            logger.error(f"연속 {max_consecutive_failures}회 후처리 오류로 ReAct 종료")
            state["error"] = f"연속 {max_consecutive_failures}회 후처리 오류로 작업을 중단합니다: {str(e)}"
            state["react_observation"] = f"후처리 오류로 인해 작업을 중단합니다: {str(e)}"
            state["react_should_continue"] = False
            state["next_step"] = "react_finalize"
        else:
            state["error"] = f"행동 결과 처리 중 오류: {str(e)}"
            state["react_observation"] = f"행동 결과 처리 실패: {str(e)}"
            state["next_step"] = "react_observe"  # 실패해도 관찰 단계로 진행
    
    return state


async def react_observe_node(state: ChatState) -> ChatState:
    """ReAct Observe 단계: 행동 결과를 관찰하고 다음 단계를 결정합니다
    
    Args:
        state: 현재 채팅 상태
        
    Returns:
        업데이트된 채팅 상태
    """
    logger.info("ReAct Observe 단계 시작")
    
    session_id = state.get("session_id")
    observation = state.get("react_observation", "")
    iteration = state.get("react_iteration", 0)
    max_iterations = state.get("react_max_iterations", 10)
    
    # 가장 최근의 tool_call에서 실제 JSON-RPC 데이터 가져오기
    actual_request_json = None
    actual_response_json = None
    tool_calls = state.get("tool_calls", [])
    if tool_calls:
        last_tool_call = tool_calls[-1]
        actual_request_json = last_tool_call.mcp_request_json
        actual_response_json = last_tool_call.mcp_response_json

    # SSE 메시지 전송
    if session_id:
        sse_manager = get_sse_manager()
        sse_observation_data = {
            "observation": observation, 
            "iteration": iteration,
            "actual_mcp_request_json": actual_request_json,
            "actual_mcp_response_json": actual_response_json
        }
        observing_msg = create_observing_message(
            f"결과 관찰: {observation}",
            session_id,
            observation_data=sse_observation_data
        )
        await sse_manager.send_to_session(session_id, observing_msg)
    
    try:
        # 관찰 결과를 메시지로 추가
        observation_message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=f"관찰: {observation}",
            timestamp=datetime.now(),
            metadata={"react_step": "observe", "iteration": iteration}
        )
        state["messages"].append(observation_message)
        
        # 다음 단계 결정
        state["react_current_step"] = "observe"
        
        # 종료 조건 체크
        if iteration >= max_iterations:
            logger.info(f"최대 반복 횟수 도달: {iteration}/{max_iterations}")
            state["react_should_continue"] = False
            state["react_final_answer"] = _generate_summary_answer(state)
            state["next_step"] = "react_finalize"
        elif _should_continue_react(state):
            state["react_should_continue"] = True
            state["next_step"] = "react_think"
        else:
            state["react_should_continue"] = False
            state["react_final_answer"] = _generate_summary_answer(state)
            state["next_step"] = "react_finalize"
        
        logger.info(f"Observe 단계 완료 - 계속 진행: {state.get('react_should_continue')}")
        
    except Exception as e:
        logger.error(f"Observe 단계 오류: {e}")
        state["error"] = f"관찰 단계 중 오류: {str(e)}"
        state["react_should_continue"] = False
        state["next_step"] = "react_finalize"
    
    return state


async def react_finalize_node(state: ChatState) -> ChatState:
    """ReAct 최종화 단계: ReAct 사이클을 종료하고 최종 답변을 생성합니다
    
    Args:
        state: 현재 채팅 상태
        
    Returns:
        업데이트된 채팅 상태
    """
    logger.info("ReAct 최종화 단계 시작")
    
    session_id = state.get("session_id")
    
    # 수집된 정보를 바탕으로 최종 답변 생성 프롬프트 구성
    final_prompt = _build_final_answer_prompt(state)
    
    try:
        # LLM을 통한 최종 답변 스트리밍 생성
        llm = get_llm()
        context = _build_llm_context_with_history(state, final_prompt)
        
        # 토큰 단위 스트리밍 응답 생성
        final_answer = ""
        word_buffer = ""  # 단어 버퍼로 변경
        token_count = 0
        
        if session_id:
            sse_manager = get_sse_manager()
            
            logger.info("ReAct 최종 답변 단어 단위 스트리밍 시작")
            
            try:
                # LLM 스트리밍 호출
                async for chunk in llm.astream(context["messages"]):
                    if hasattr(chunk, 'content') and chunk.content:
                        token = chunk.content
                        final_answer += token
                        word_buffer += token
                        token_count += 1
                        
                        # 완전 동적 버퍼링 전략
                        base_length = 8
                        adaptive_length = base_length + (len(token) if token else 0) // 3
                        adaptive_batch = max(10, 10 + (token_count // 20))
                        
                        # 동적 구분자 감지
                        is_separator = (
                            token.isspace() or  # 모든 공백 문자
                            not token.isalnum() or  # 알파벳/숫자가 아닌 문자
                            len(word_buffer) >= adaptive_length or  # 적응적 길이 제한
                            token_count % adaptive_batch == 0  # 적응적 배치
                        )
                        
                        should_send = is_separator
                        
                        if should_send and word_buffer.strip():  # 공백만 있는 버퍼는 전송하지 않음
                            # 완전한 단어 전송
                            chunk_msg = create_partial_response_message(word_buffer, session_id)
                            chunk_msg.metadata = {
                                "streaming": True, 
                                "react_final": True,
                                "word_streaming": True,
                                "cumulative": False
                            }
                            await sse_manager.send_to_session(session_id, chunk_msg)
                            logger.debug(f"ReAct 단어 전송: '{word_buffer.strip()}' ({len(word_buffer)}글자)")
                            
                            # 버퍼 초기화
                            word_buffer = ""
                            
                            # 완전 동적 지연 계산
                            base_delay = 0.02
                            buffer_length = len(word_buffer.strip())
                            
                            # 버퍼 길이와 토큰 특성에 따른 적응적 지연
                            if not token.isalnum():  # 구두점이나 특수문자
                                delay = base_delay * (2 + buffer_length / 10)
                            else:  # 일반 문자
                                delay = base_delay * (1 + buffer_length / 20)
                            
                            await asyncio.sleep(min(delay, 0.15))  # 최대 지연 제한
                
                # 마지막 남은 단어 전송
                if word_buffer.strip():
                    chunk_msg = create_partial_response_message(word_buffer, session_id)
                    chunk_msg.metadata = {
                        "streaming": True, 
                        "react_final": True,
                        "word_streaming": True,
                        "cumulative": False,
                        "final_word": True
                    }
                    await sse_manager.send_to_session(session_id, chunk_msg)
                    logger.debug(f"ReAct 마지막 단어 전송: '{word_buffer.strip()}'")
                
            except Exception as e:
                logger.error(f"ReAct 스트리밍 중 오류: {e}")
                # 오류 시 전체 응답을 한 번에 생성
                response = await llm.ainvoke(context["messages"])
                final_answer = response.content
            
            logger.info(f"ReAct 단어 단위 스트리밍 완료 - 총 길이: {len(final_answer)}글자, 토큰 수: {token_count}")
            
            # 스트리밍 완료 알림
            final_msg = create_final_response_message(final_answer, session_id)
            final_msg.metadata = {"react_final": True}
            await sse_manager.send_to_session(session_id, final_msg)
        else:
            # 세션 ID가 없으면 일반 방식으로 생성
            response = await llm.ainvoke(context["messages"])
            final_answer = response.content
        
        # 상태 업데이트
        state["react_final_answer"] = final_answer
        state["response"] = final_answer
        state["success"] = True
        
        # 세션에 최종 답변 저장
        from .state import add_assistant_message
        add_assistant_message(state, final_answer)
        
        logger.info("ReAct 최종화 완료")
        return state
        
    except Exception as e:
        logger.error(f"ReAct 최종화 오류: {e}")
        import traceback
        logger.error(f"스택 트레이스: {traceback.format_exc()}")
        
        # 오류 시 간단한 요약 답변 생성
        summary_answer = _generate_summary_answer(state)
        state["react_final_answer"] = summary_answer
        state["response"] = summary_answer
        state["success"] = True
        
        add_assistant_message(state, summary_answer)
        
        return state


async def _build_think_prompt(state: ChatState) -> str:
    """Think 단계를 위한 프롬프트를 구성합니다"""
    iteration = state.get("react_iteration", 0)
    user_message = state.get("current_message")
    tool_calls = state.get("tool_calls", [])
    
    # 동적으로 사용 가능한 도구 목록 수집
    available_tools_info = ""
    mcp_client = state.get("mcp_client")
    if mcp_client:
        try:
            tools = mcp_client.get_tools()
            server_names = mcp_client.get_server_names()
            
            tool_descriptions = []
            for tool in tools:
                tool_name = getattr(tool, 'name', '이름없음')
                tool_desc = getattr(tool, 'description', '설명없음')
                
                # 도구가 속한 서버 추정
                server = "unknown"
                for server_name in server_names:
                    if server_name in tool_name.lower() or server_name.replace('-', '_') in tool_name.lower():
                        server = server_name
                        break
                
                tool_descriptions.append(f"- {tool_name}: {tool_desc}")
            
            if tool_descriptions:
                available_tools_info = "사용 가능한 도구들:\n" + "\n".join(tool_descriptions)
            else:
                available_tools_info = "현재 사용 가능한 도구가 없습니다."
                
        except Exception as e:
            logger.warning(f"도구 정보 수집 실패: {e}")
            available_tools_info = "도구 정보를 가져올 수 없습니다."
    else:
        available_tools_info = "MCP 클라이언트가 초기화되지 않았습니다."
    
    # 사용자 요청에서 다중 항목 분석
    user_request = user_message.content if user_message else ""
    required_tasks = await _analyze_required_tasks(user_request, tool_calls, mcp_client)
    
    if iteration == 0:
        # 첫 번째 반복
        prompt = f"""당신은 ReAct (Reasoning and Acting) 패턴을 사용하여 문제를 해결하는 AI입니다.

사용자 질문: {user_request}

{available_tools_info}

{required_tasks}

다음 형식으로 응답해주세요:

생각: [현재 상황을 분석하고 다음에 무엇을 해야 할지 생각해보세요. 위에 나열된 필요한 작업들 중 아직 완료되지 않은 것이 있는지 확인하세요.]

행동: [구체적인 행동을 자연스럽게 설명하세요. 도구를 사용해야 한다면 어떤 도구로 무엇을 할지 명확히 기술하세요.]

또는

최종 답변: [모든 필요한 정보를 수집했다면 최종 답변을 제공하세요]

행동 작성 가이드:
- 자연스러운 문장으로 작성하세요 (예: "서울의 날씨 정보를 수집합니다", "get_weather 도구로 부산 날씨 조회")
- 어떤 도구를 사용할지와 필요한 정보를 명확히 포함하세요
- 형식에 얽매이지 말고 의도를 명확하게 전달하세요

중요: 
- 위에 나열된 모든 작업을 완료해야 합니다. 하나라도 빠뜨리지 마세요.
- 한 번에 하나의 작업만 수행하세요."""
    else:
        # 이후 반복
        recent_observation = state.get("react_observation", "")
        
        # 지금까지 수집된 정보 요약
        collected_info = ""
        if tool_calls:
            collected_info = "\n지금까지 수집된 정보:\n"
            for i, tc in enumerate(tool_calls, 1):
                if tc.is_successful():
                    collected_info += f"{i}. {tc.tool_name}: {tc.result}\n"
        
        prompt = f"""이전 관찰 결과: {recent_observation}
{collected_info}

{available_tools_info}

{required_tasks}

위 결과를 바탕으로 다음 단계를 결정해주세요:

생각: [현재까지의 진행 상황을 분석하고 다음에 무엇을 해야 할지 생각해보세요. 위에 나열된 필요한 작업들 중 아직 완료되지 않은 것이 있는지 반드시 확인하세요.]

행동: [추가로 필요한 행동이 있다면 자연스럽게 설명하세요. 어떤 도구로 무엇을 할지 명확히 기술하세요.]

또는

최종 답변: [모든 필요한 정보를 수집했다면 종합적인 최종 답변을 제공하세요]

행동 작성 가이드:
- 자연스러운 문장으로 작성하세요 (예: "청주의 날씨 예보를 확인합니다", "get_forecast로 청주 3일 예보 조회")
- 어떤 도구를 사용할지와 필요한 정보를 명확히 포함하세요
- 형식에 얽매이지 말고 의도를 명확하게 전달하세요

중요: 
- 위에 나열된 모든 작업이 완료되었는지 반드시 확인하세요. 하나라도 빠뜨리면 안 됩니다.
- 아직 완료되지 않은 작업이 있다면 계속 진행하세요."""
    
    return prompt


async def _analyze_required_tasks(user_request: str, completed_tool_calls: List, mcp_client) -> str:
    """LLM을 사용하여 사용자 요청을 분석하고 필요한 작업들을 동적으로 파악합니다"""
    
    # 완료된 작업 추적
    completed_tasks = []
    for tc in completed_tool_calls:
        if tc.is_successful():
            task_desc = f"{tc.tool_name}"
            if tc.arguments:
                # 주요 인수 추출
                for key, value in tc.arguments.items():
                    if value and str(value).strip():
                        task_desc += f"({str(value).strip()})"
                        break
            completed_tasks.append(task_desc)
    
    # 사용 가능한 도구 정보 수집
    available_tools = []
    if mcp_client:
        try:
            tools = mcp_client.get_tools()
            for tool in tools:
                tool_name = getattr(tool, 'name', '이름없음')
                tool_desc = getattr(tool, 'description', '설명없음')
                available_tools.append(f"- {tool_name}: {tool_desc}")
        except Exception as e:
            logger.warning(f"도구 정보 수집 실패: {e}")
    
    # LLM을 사용한 작업 분석 프롬프트
    analysis_prompt = f"""사용자 요청을 분석하여 필요한 모든 작업을 파악해주세요.

사용자 요청: "{user_request}"

사용 가능한 도구들:
{chr(10).join(available_tools) if available_tools else "도구 정보 없음"}

이미 완료된 작업들:
{chr(10).join([f"- {task}" for task in completed_tasks]) if completed_tasks else "완료된 작업 없음"}

다음 지침에 따라 필요한 작업들을 나열해주세요:

1. 사용자 요청을 자세히 분석하세요
2. 여러 항목(도시, 기술, 파일 등)이 언급되었다면 각각에 대해 별도 작업이 필요합니다
3. 비교나 분석이 요청되었다면 모든 개별 정보를 먼저 수집해야 합니다
4. 이미 완료된 작업은 제외하세요
5. 사용 가능한 도구를 고려하여 실행 가능한 작업만 나열하세요

응답 형식:
필요한 작업들:
- [구체적인 작업 1]
- [구체적인 작업 2]
- [구체적인 작업 3]
...

⚠️ 중요: 사용자가 요청한 모든 항목을 빠뜨리지 마세요!

필요한 작업들:"""

    try:
        llm = get_llm()
        
        # LLM 호출
        from langchain_core.messages import SystemMessage
        response = await llm.ainvoke([SystemMessage(content=analysis_prompt)])
        
        # 응답에서 작업 목록 추출
        analysis_result = response.content.strip()
        
        # "필요한 작업들:" 이후의 내용만 추출
        if "필요한 작업들:" in analysis_result:
            tasks_section = analysis_result.split("필요한 작업들:")[-1].strip()
            return f"필요한 작업들:\n{tasks_section}\n\n⚠️ 중요: 위의 모든 작업을 완료해야 합니다. 하나라도 빠뜨리지 마세요!"
        else:
            return f"필요한 작업들:\n{analysis_result}\n\n⚠️ 중요: 위의 모든 작업을 완료해야 합니다. 하나라도 빠뜨리지 마세요!"
            
    except Exception as e:
        logger.error(f"LLM 기반 작업 분석 실패: {e}")
        # 폴백: 기본 메시지
        return "필요한 작업: 사용자 요청에 대한 정보 수집 및 응답 제공"


def _parse_thought_response(response: str) -> Dict[str, str]:
    """Think 단계 응답을 파싱합니다"""
    result = {}
    
    # 최종 답변 패턴 매칭
    final_answer_patterns = [
        r"최종\s*답변\s*:\s*(.+)",
        r"Final\s*Answer\s*:\s*(.+)",
        r"답변\s*:\s*(.+)"
    ]
    
    for pattern in final_answer_patterns:
        match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)
        if match:
            result["final_answer"] = match.group(1).strip()
            return result
    
    # 행동 패턴 매칭
    action_patterns = [
        r"행동\s*:\s*(.+)",
        r"Action\s*:\s*(.+)"
    ]
    
    for pattern in action_patterns:
        match = re.search(pattern, response, re.IGNORECASE)
        if match:
            result["action"] = match.group(1).strip()
            break
    
    # 생각 패턴 매칭
    thought_patterns = [
        r"생각\s*:\s*(.+?)(?=행동|Action|최종|Final|$)",
        r"Thought\s*:\s*(.+?)(?=행동|Action|최종|Final|$)"
    ]
    
    for pattern in thought_patterns:
        match = re.search(pattern, response, re.IGNORECASE | re.DOTALL)
        if match:
            result["thought"] = match.group(1).strip()
            break
    
    return result


async def _execute_action(state: ChatState, action: str) -> Optional[MCPToolCall]:
    """LLM을 사용하여 행동을 분석하고 실행합니다"""
    logger.info(f"LLM 기반 행동 실행 시도: '{action}'")
    
    # MCP 클라이언트에서 사용 가능한 도구 목록 가져오기
    available_tools = []
    mcp_client = state.get("mcp_client")
    if mcp_client:
        try:
            tools = mcp_client.get_tools()
            for tool in tools:
                tool_name = getattr(tool, 'name', '')
                tool_desc = getattr(tool, 'description', '')
                available_tools.append(f"- {tool_name}: {tool_desc}")
            logger.info(f"사용 가능한 도구 목록: {[getattr(tool, 'name', '') for tool in tools]}")
        except Exception as e:
            logger.warning(f"도구 목록 수집 실패: {e}")
    
    if not available_tools:
        logger.warning("사용 가능한 도구가 없습니다")
        return None
    
    # LLM을 사용한 행동 분석 프롬프트
    analysis_prompt = f"""다음 행동 설명을 분석하여 실행할 도구와 인수를 추출해주세요.

행동 설명: "{action}"

사용 가능한 도구들:
{chr(10).join(available_tools)}

지침:
1. 행동 설명에서 실행하려는 도구를 식별하세요
2. 도구명은 위의 사용 가능한 도구 목록에서만 선택하세요
3. 필요한 인수들을 추출하세요
4. 도구 호출이 아닌 일반적인 설명이라면 "NO_TOOL"로 응답하세요

응답 형식 (JSON):
{{
    "tool_name": "도구명 또는 NO_TOOL",
    "arguments": "인수 문자열",
    "reasoning": "선택 이유"
}}

예시:
- "get_weather: 서울" → {{"tool_name": "get_weather", "arguments": "서울", "reasoning": "서울의 날씨 정보 조회"}}
- "서울의 날씨 정보 수집" → {{"tool_name": "get_weather", "arguments": "서울", "reasoning": "서울의 날씨 정보가 필요함"}}
- "분석 결과 정리" → {{"tool_name": "NO_TOOL", "arguments": "", "reasoning": "도구 호출이 아닌 일반 작업"}}

응답:"""

    try:
        llm = get_llm()
        
        # LLM 호출
        from langchain_core.messages import SystemMessage
        response = await llm.ainvoke([SystemMessage(content=analysis_prompt)])
        
        # JSON 응답 파싱
        response_text = response.content.strip()
        logger.info(f"LLM 행동 분석 응답: {response_text}")
        
        # JSON 추출 (```json 블록이 있을 수 있음)
        import json
        import re
        
        # JSON 블록 추출
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # JSON 블록이 없으면 전체에서 JSON 찾기
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                logger.warning(f"LLM 응답에서 JSON을 찾을 수 없음: {response_text}")
                return None
        
        try:
            parsed_response = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 실패: {e}, 원본: {json_str}")
            return None
        
        tool_name = parsed_response.get("tool_name", "").strip()
        arguments_str = parsed_response.get("arguments", "").strip()
        reasoning = parsed_response.get("reasoning", "")
        
        logger.info(f"LLM 분석 결과 - 도구: '{tool_name}', 인수: '{arguments_str}', 이유: '{reasoning}'")
        
        # NO_TOOL인 경우 None 반환
        if tool_name == "NO_TOOL" or not tool_name:
            logger.info("도구 호출이 아닌 일반 작업으로 판단됨")
            return None
        
        # 도구명 검증: 실제 존재하는 도구인지 확인
        available_tool_names = {getattr(tool, 'name', '') for tool in mcp_client.get_tools()}
        if tool_name not in available_tool_names:
            logger.warning(f"존재하지 않는 도구: '{tool_name}'. 사용 가능한 도구: {available_tool_names}")
            return None
        
        # 도구 호출 실행
        return await _call_mcp_tool(state, tool_name, arguments_str)
        
    except Exception as e:
        logger.error(f"LLM 기반 행동 분석 중 오류: {e}")
        return None


async def _call_mcp_tool(state: ChatState, tool_name: str, arguments_str: str) -> MCPToolCall:
    """MCP 도구를 호출합니다 (완전 동적 방식)"""
    from ..models import MCPToolCall
    from datetime import datetime
    import time
    import json
    from pathlib import Path
    import asyncio

    # 세션 ID 가져오기
    session_id = state.get("session_id", "UNKNOWN_REACT_SESSION")

    # MCP 클라이언트에서 도구 정보 동적 수집
    mcp_client = state.get("mcp_client")
    if not mcp_client:
        raise ValueError("MCP 클라이언트가 없습니다")

    # 사용 가능한 도구에서 해당 도구 찾기
    server_name = None
    tool_found = False
    tool_schema_obj = None

    try:
        tools = mcp_client.get_tools()
        logger.info(f"[_call_mcp_tool] mcp_client.get_tools() 반환값 (총 {len(tools)}개): {tools}")
        server_names = mcp_client.get_server_names()

        # 도구 이름으로 서버 찾기
        for current_tool_obj in tools: 
            if getattr(current_tool_obj, 'name', '') == tool_name:
                tool_found = True
                tool_schema_obj = current_tool_obj # 전체 tool 객체를 schema로 사용
                
                # --- 상세 로깅 추가 --- #
                logger.info(f"[_call_mcp_tool] 찾은 도구: {tool_name}")
                logger.info(f"[_call_mcp_tool]   tool_schema_obj 타입: {type(tool_schema_obj)}")
                logger.info(f"[_call_mcp_tool]   tool_schema_obj 내용: {tool_schema_obj}")
                raw_args_schema = getattr(tool_schema_obj, 'args_schema', None)
                logger.info(f"[_call_mcp_tool]   raw_args_schema 타입: {type(raw_args_schema)}")
                logger.info(f"[_call_mcp_tool]   raw_args_schema 내용: {raw_args_schema}")
                if raw_args_schema:
                    logger.info(f"[_call_mcp_tool]   raw_args_schema 필드 (v1 __fields__): {getattr(raw_args_schema, '__fields__', '없음')}")
                    logger.info(f"[_call_mcp_tool]   raw_args_schema 필드 (v2 model_fields): {getattr(raw_args_schema, 'model_fields', '없음')}")
                # --- 상세 로깅 끝 --- #
                
                # 도구가 속한 서버 추정
                for server in server_names:
                    if server in tool_name.lower() or server.replace('-', '_') in tool_name.lower():
                        server_name = server
                        break
                
                # 서버를 찾지 못했으면 첫 번째 서버 사용
                if not server_name and server_names:
                    server_name = server_names[0]
                break
        
        if not tool_found:
            # 도구를 찾지 못한 경우, 첫 번째 서버에서 시도
            if server_names:
                server_name = server_names[0]
            else:
                logger.error(f"도구 '{tool_name}'을 찾을 수 없고 사용 가능한 서버도 없습니다") # 로그 레벨 변경
                raise ValueError(f"도구 '{tool_name}'을 찾을 수 없고 사용 가능한 서버도 없습니다")
    
    except Exception as e:
        logger.warning(f"도구 정보 수집 실패: {e}")
        # 폴백: 기본 서버 사용
        server_name = "default" # server_name이 None일 수 있으므로 기본값 할당

    # 인수 파싱: 스키마 우선, JSON 시도, 단순 폴백 순서
    arguments = {}
    try:
        # 1순위: JSON 형태 파싱 시도
        if arguments_str.strip().startswith('{') and arguments_str.strip().endswith('}'):
            arguments = json.loads(arguments_str.strip())
            logger.info(f"JSON 파싱 성공: {arguments}")
        else:
            # 2순위: 도구 스키마를 사용한 동적 파싱
            if tool_schema_obj:
                arguments = _parse_arguments_with_schema(tool_schema_obj, arguments_str.strip())
                logger.info(f"스키마 기반 파싱 사용: {arguments}")
            else:
                # 3순위: 단순 폴백 (스키마가 없는 경우)
                arguments = _parse_simple_arguments(tool_name, arguments_str.strip())
                logger.info(f"단순 폴백 파싱 사용: {arguments}")
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"JSON 파싱 실패: {e}")
        # JSON 실패 시 스키마 기반 파싱으로 폴백
        if tool_schema_obj:
            arguments = _parse_arguments_with_schema(tool_schema_obj, arguments_str.strip())
        else:
            arguments = _parse_simple_arguments(tool_name, arguments_str.strip())
    
    tool_call = MCPToolCall(
        server_name=server_name, # 여기서 server_name이 None이 아니도록 보장 필요
        tool_name=tool_name,
        arguments=arguments
    )
    
    # JSON-RPC 요청 객체 생성 (호출 전)
    request_id = f"mcp-host-react-{Path(session_id).name}-{int(asyncio.get_event_loop().time() * 1000)}"
    request_payload_for_mcp_call = {
        "jsonrpc": "2.0",
        "method": "tools/call", 
        "params": {
            "server": server_name, # MCPClient.call_tool 내부에서 사용되는 server_name과 동일해야 함
            "name": tool_name,
            "arguments": arguments 
        },
        "id": request_id
    }
    tool_call.mcp_request_json = json.dumps(request_payload_for_mcp_call, ensure_ascii=False)
    logger.info(f"[_call_mcp_tool] 생성된 MCP 요청 JSON: {tool_call.mcp_request_json}")

    try:
        start_time = time.time()
        
        logger.info(f"동적 MCP 도구 호출: {server_name}.{tool_name}")
        
        # MCP Client의 call_tool 메서드 사용
        result = await mcp_client.call_tool(server_name, tool_name, arguments, session_id=session_id)
        
        tool_call.result = result
        tool_call.execution_time_ms = int((time.time() - start_time) * 1000)
        
        # JSON-RPC 응답 객체 생성 (성공 시)
        response_payload_for_mcp_call = {
            "jsonrpc": "2.0",
            "result": result, 
            "id": request_id 
        }
        tool_call.mcp_response_json = json.dumps(response_payload_for_mcp_call, ensure_ascii=False, default=str)
        logger.info(f"[_call_mcp_tool] 생성된 MCP 응답 JSON: {tool_call.mcp_response_json}")
        
        logger.info(f"MCP 도구 호출 성공: {tool_name}")
        
    except Exception as e:
        tool_call.error = str(e)
        tool_call.execution_time_ms = int((time.time() - start_time) * 1000) # 실패 시에도 시간 기록
        
        # JSON-RPC 에러 응답 객체 생성 (실패 시)
        error_response_payload_for_mcp_call = {
            "jsonrpc": "2.0",
            "error": {
                "code": -32000, # 일반적인 서버 오류 코드
                "message": f"Tool execution failed in react_nodes._call_mcp_tool: {str(e)}",
                "data": {
                    "server": server_name,
                    "tool": tool_name,
                    "arguments": arguments # 여기서 arguments는 파싱된 dict 형태
                }
            },
            "id": request_id
        }
        tool_call.mcp_response_json = json.dumps(error_response_payload_for_mcp_call, ensure_ascii=False)
        logger.error(f"[_call_mcp_tool] 생성된 MCP 에러 응답 JSON: {tool_call.mcp_response_json}")
        logger.error(f"MCP 도구 호출 실패: {tool_name} - {e}")
    
    return tool_call


def _parse_arguments_with_schema(tool_schema_obj, arguments_str: str) -> Dict[str, Any]:
    """도구 스키마를 사용하여 인수를 파싱합니다 (JSON Schema dict 처리 강화)"""
    if not tool_schema_obj or not arguments_str:
        logger.debug(f"_parse_arguments_with_schema: 입력값 부족 (tool_schema_obj: {bool(tool_schema_obj)}, arguments_str: {bool(arguments_str)})")
        return {'input': arguments_str} if arguments_str else {}

    clean_value = arguments_str.strip()
    if clean_value.startswith('"') and clean_value.endswith('"'):
        clean_value = clean_value[1:-1]
    if clean_value.startswith('\"') and clean_value.endswith('\"'): # 이미 존재하는 조건
        clean_value = clean_value[2:-2]
    elif clean_value.startswith('\\\"') and clean_value.endswith('\\\"'): # 추가된 조건: 삼중 백슬래시 + 따옴표
        clean_value = clean_value[3:-3]


    parsed_args = {}
    tool_name = getattr(tool_schema_obj, 'name', 'unknown_tool')
    logger.info(f"_parse_arguments_with_schema 시작 ({tool_name}): arguments_str='{arguments_str}', clean_value='{clean_value}'")

    try:
        input_schema = getattr(tool_schema_obj, 'args_schema', None)
        if not input_schema:
            logger.warning(f"[{tool_name}] args_schema가 없습니다. 폴백합니다.")
            return {'input': clean_value}

        field_details = {} # 필드명: {'type': type, 'default': value, 'required': bool}
        field_order = []   # 스키마에 정의된 필드 순서
        logger.debug(f"[{tool_name}] 초기 field_order: {field_order}, field_details: {field_details}")

        # 스키마 타입에 따른 정보 추출
        if hasattr(input_schema, '__fields__'): # Pydantic v1
            logger.debug(f"[{tool_name}] Pydantic v1 스키마 감지")
            pydantic_fields = input_schema.__fields__
            field_order = list(pydantic_fields.keys())
            for fname, finfo in pydantic_fields.items():
                field_details[fname] = {
                    'type': getattr(finfo, 'outer_type_', str),
                    'default': getattr(finfo, 'default', None),
                    'required': getattr(finfo, 'required', False)
                }
        elif hasattr(input_schema, 'model_fields'): # Pydantic v2
            logger.debug(f"[{tool_name}] Pydantic v2 스키마 감지")
            pydantic_fields = input_schema.model_fields
            field_order = list(pydantic_fields.keys())
            for fname, finfo in pydantic_fields.items():
                field_details[fname] = {
                    'type': getattr(finfo, 'annotation', str),
                    'default': getattr(finfo, 'default', None),
                    'required': getattr(finfo, 'is_required', lambda: False)() # is_required() 호출
                }
        elif isinstance(input_schema, dict) and 'properties' in input_schema: # JSON Schema (dict)
            logger.debug(f"[{tool_name}] JSON Schema (dict) 감지: {input_schema}")
            schema_properties = input_schema.get('properties', {})
            # JSON Schema의 경우, 일반적으로 'properties' 딕셔너리의 키 순서를 따름
            field_order = list(schema_properties.keys()) # 이 부분에서 순서가 보장되는지 확인 필요
            required_fields = input_schema.get('required', [])
            logger.debug(f"[{tool_name}] JSON Schema properties keys (순서대로): {field_order}, required: {required_fields}")

            for fname, f_schema in schema_properties.items(): # dict.items()는 Python 3.7+부터 삽입 순서 보장
                raw_type = f_schema.get('type', 'string')
                field_type = str
                if raw_type == 'integer': field_type = int
                elif raw_type == 'number': field_type = float
                elif raw_type == 'boolean': field_type = bool
                
                default_value = f_schema.get('default') 
                is_required = fname in required_fields
                
                field_details[fname] = {
                    'type': field_type,
                    'default': default_value,
                    'required': is_required
                }
                logger.debug(f"[{tool_name}] JSON Schema 필드 구성: {fname} -> {field_details[fname]}")
        else:
            logger.warning(f"[{tool_name}] 알 수 없는 스키마 타입 또는 필드 정보 부족. 폴백. input_schema 타입: {type(input_schema)}")
            return {'input': clean_value}
        
        logger.info(f"[{tool_name}] 스키마 분석 후 field_order: {field_order}")
        logger.info(f"[{tool_name}] 스키마 분석 후 field_details: {field_details}")

        if not field_order:
            logger.warning(f"[{tool_name}] 스키마에서 필드 순서/목록을 결정할 수 없음. 폴백.")
            return {'input': clean_value}

        split_values = [val.strip() for val in clean_value.split(',')]
        logger.info(f"[{tool_name}] 최종 필드 순서: {field_order}, 분리된 값: {split_values} (분리 전: '{clean_value}')")

        for i, field_name in enumerate(field_order):
            logger.debug(f"[{tool_name}] 루프 시작: i={i}, field_name='{field_name}'")
            details = field_details.get(field_name)
            if not details:
                logger.error(f"[{tool_name}] 필드 '{field_name}'에 대한 상세 스키마 정보를 찾지 못했습니다! 건너뜁니다.")
                continue

            expected_type = details['type']
            default_value = details['default']
            is_required = details['required']
            current_value_str = None
            logger.debug(f"[{tool_name}]   field_name='{field_name}', expected_type={expected_type}, default={default_value}, required={is_required}")

            if i < len(split_values):
                current_value_str = split_values[i]
                logger.debug(f"[{tool_name}]   '{field_name}' 처리 중. 값 후보: '{current_value_str}'")
                try:
                    parsed_val = None
                    if expected_type == int:
                        # "3일" -> 3, "3" -> 3
                        val_to_parse = re.sub(r'[^0-9\-]', '', current_value_str)
                        if not val_to_parse: # 숫자 아닌 문자만 있어서 비었을 경우
                            raise ValueError(f"정수 변환을 위한 유효한 숫자가 없음: '{current_value_str}'")
                        parsed_val = int(val_to_parse)
                        logger.debug(f"[{tool_name}]     INT 변환 시도: '{current_value_str}' -> re:'{val_to_parse}' -> {parsed_val}")
                    elif expected_type == float:
                        val_to_parse = re.sub(r'[^0-9\.\-]', '', current_value_str)
                        if not val_to_parse:
                             raise ValueError(f"실수 변환을 위한 유효한 숫자가 없음: '{current_value_str}'")
                        parsed_val = float(val_to_parse)
                        logger.debug(f"[{tool_name}]     FLOAT 변환 시도: '{current_value_str}' -> re:'{val_to_parse}' -> {parsed_val}")
                    elif expected_type == bool:
                        parsed_val = current_value_str.lower() in ['true', 'yes', '1', 't']
                        logger.debug(f"[{tool_name}]     BOOL 변환 시도: '{current_value_str}' -> {parsed_val}")
                    else: # str 또는 기타 정의되지 않은 타입
                        parsed_val = current_value_str 
                        logger.debug(f"[{tool_name}]     STR 처리: '{current_value_str}' -> {parsed_val}")
                    
                    parsed_args[field_name] = parsed_val
                    logger.info(f"[{tool_name}]   성공적으로 매핑/변환: {field_name} = {parsed_val} (타입: {type(parsed_val)})")
                except ValueError as e:
                    logger.warning(f"[{tool_name}]   타입 변환 실패: 필드='{field_name}', 값='{current_value_str}', 예상타입={expected_type}. 오류: {e}")
                    if default_value is not None:
                        parsed_args[field_name] = default_value
                        logger.info(f"[{tool_name}]     타입 변환 실패로 기본값 사용: {field_name} = {default_value}")
                    elif is_required:
                         logger.error(f"[{tool_name}]     필수 필드 '{field_name}' 값 변환 실패 및 기본값 없음. 원본 값 '{current_value_str}' 유지.")
                         parsed_args[field_name] = current_value_str # Pydantic 검증에서 걸릴 것임.
                    else:
                        logger.info(f"[{tool_name}]     선택적 필드 '{field_name}' 값 변환 실패 및 기본값 없음. 필드 생략.")
                        
            elif default_value is not None:
                parsed_args[field_name] = default_value
                logger.info(f"[{tool_name}]   입력값이 없어 기본값 사용: {field_name} = {default_value}")
            elif is_required:
                logger.warning(f"[{tool_name}]   필수 매개변수 '{field_name}'에 대한 입력값이 없고 기본값도 없습니다. 누락됨.")
            else:
                logger.info(f"[{tool_name}]   선택적 매개변수 '{field_name}'에 대한 입력값이 없고 기본값도 없어 생략합니다.")
            logger.debug(f"[{tool_name}] 루프 종료 후 parsed_args 현재 상태: {parsed_args}")


        if not parsed_args and clean_value:
             logger.warning(f"[{tool_name}] 스키마 기반으로 인수를 전혀 매핑하지 못했습니다. 입력값을 'input'으로 폴백: {clean_value}")
             return {'input': clean_value}
        elif not parsed_args and not clean_value:
             logger.info(f"[{tool_name}] 파싱할 입력 문자열이 없어 빈 인수로 처리.")
             return {}


        logger.info(f"[{tool_name}] 최종 파싱된 인수: {parsed_args}")
        return parsed_args

    except Exception as e:
        logger.error(f"[{tool_name}] _parse_arguments_with_schema 함수 실행 중 심각한 오류: {e}")
        import traceback
        logger.error(traceback.format_exc())

    logger.warning(f"[{tool_name}] 알 수 없는 오류로 스키마 파싱 실패. 최종 폴백: input='{clean_value}'")
    return {'input': clean_value}


def _parse_simple_arguments(tool_name: str, arguments_str: str) -> Dict[str, Any]:
    """단순 문자열 인수를 파싱합니다 (완전 동적 폴백)"""
    if not arguments_str:
        return {}
    
    # 값 정리 (이중 인코딩 제거)
    clean_value = arguments_str.strip()
    if clean_value.startswith('"') and clean_value.endswith('"'):
        clean_value = clean_value[1:-1]
    if clean_value.startswith('\\"') and clean_value.endswith('\\"'):
        clean_value = clean_value[2:-2]
    
    # 하드코딩 제거: 모든 도구에 대해 동일한 폴백 전략 사용
    # 가장 일반적인 매개변수 이름으로 폴백
    logger.info(f"단순 인수 파싱 폴백: {tool_name} -> input = {clean_value}")
    return {'input': clean_value}


def _format_tool_result(tool_call: MCPToolCall) -> str:
    """도구 호출 결과를 포맷팅합니다"""
    if tool_call.is_successful():
        return f"도구 '{tool_call.tool_name}' 실행 성공: {tool_call.result}"
    else:
        return f"도구 '{tool_call.tool_name}' 실행 실패: {tool_call.error}"


async def _check_remaining_tasks(state: ChatState) -> List[str]:
    """아직 완료되지 않은 작업들을 확인합니다"""
    user_message = state.get("current_message")
    completed_tool_calls = state.get("tool_calls", [])
    mcp_client = state.get("mcp_client")
    
    if not user_message:
        return []
    
    try:
        # 필요한 작업들을 다시 분석
        required_tasks_text = await _analyze_required_tasks(
            user_message.content, 
            completed_tool_calls, 
            mcp_client
        )
        
        # "필요한 작업들:" 섹션에서 작업 목록 추출
        if "필요한 작업들:" in required_tasks_text:
            tasks_section = required_tasks_text.split("필요한 작업들:")[-1].strip()
            
            # 각 라인에서 작업 추출 (- 로 시작하는 라인들)
            remaining_tasks = []
            for line in tasks_section.split('\n'):
                line = line.strip()
                if line.startswith('-') and len(line) > 2:
                    task = line[1:].strip()  # - 제거
                    if task and not task.startswith('⚠️'):  # 경고 메시지 제외
                        remaining_tasks.append(task)
            
            logger.info(f"미완료 작업 확인 결과: {remaining_tasks}")
            return remaining_tasks
        
        return []
        
    except Exception as e:
        logger.error(f"미완료 작업 확인 중 오류: {e}")
        return []


def _should_continue_react(state: ChatState) -> bool:
    """ReAct 사이클을 계속 진행할지 결정합니다"""
    
    # 1. 최우선: 미완료 작업 확인
    try:
        # 비동기 함수를 동기적으로 호출하기 위해 이벤트 루프 사용
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            remaining_tasks = loop.run_until_complete(_check_remaining_tasks(state))
        except RuntimeError:
            # 이미 실행 중인 이벤트 루프가 있는 경우
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, _check_remaining_tasks(state))
                remaining_tasks = future.result(timeout=10)
        
        if remaining_tasks:
            logger.info(f"미완료 작업이 있어 ReAct 계속 진행: {remaining_tasks}")
            return True
        else:
            logger.info("모든 필요한 작업이 완료되어 ReAct 종료")
            return False
            
    except Exception as e:
        logger.error(f"미완료 작업 확인 중 오류: {e}")
        # 오류 시 기존 로직으로 폴백
    
    # 2. 폴백: 최근 성공적인 도구 호출이 있었다면 보수적으로 판단
    tool_calls = state.get("tool_calls", [])
    recent_successful_calls = [tc for tc in tool_calls[-2:] if tc.is_successful()]
    
    if recent_successful_calls:
        logger.info("최근 성공적인 도구 호출이 있었지만 미완료 작업 확인 실패로 보수적 종료")
        return False
    
    # 3. 기존 유사도 기반 무한루프 방지 (실패 케이스에만 적용)
    messages = state.get("messages", [])
    recent_observations = [
        msg for msg in messages[-4:] 
        if msg.metadata and msg.metadata.get("react_step") == "observe"
    ]
    
    if len(recent_observations) >= 2:
        # 연속된 관찰에서 내용이 매우 유사하면 종료 (실패 케이스 감지)
        last_obs = recent_observations[-1].content
        prev_obs = recent_observations[-2].content
        
        # 실패 메시지가 반복되는 경우만 체크
        if ("실패" in last_obs or "오류" in last_obs) and ("실패" in prev_obs or "오류" in prev_obs):
            if len(last_obs) > 0 and len(prev_obs) > 0:
                last_words = set(last_obs.split())
                prev_words = set(prev_obs.split())
                
                if last_words and prev_words:
                    intersection = len(last_words & prev_words)
                    union = len(last_words | prev_words)
                    
                    jaccard_similarity = intersection / union if union > 0 else 0
                    
                    if jaccard_similarity > 0.8:  # 실패 케이스에만 엄격한 기준 적용
                        logger.info("연속된 실패로 인한 ReAct 종료")
                        return False
    
    # 기본적으로 계속 진행
    return True


def _build_final_answer_prompt(state: ChatState) -> str:
    """최종 답변 생성을 위한 프롬프트를 구성합니다"""
    user_message = state.get("current_message")
    tool_calls = state.get("tool_calls", [])
    
    # 성공한 도구 호출 결과 수집
    successful_calls = [tc for tc in tool_calls if tc.is_successful()]
    
    # 사용자 요청
    user_request = user_message.content if user_message else "정보 요청"
    
    # 수집된 정보 정리 (동적 방식)
    collected_info = ""
    if successful_calls:
        collected_info = "수집된 정보:\n"
        for i, tc in enumerate(successful_calls, 1):
            # 도구 이름과 인수를 기반으로 동적 설명 생성
            tool_desc = _format_tool_call_description(tc)
            collected_info += f"{i}. {tool_desc}: {tc.result}\n"
    else:
        collected_info = "수집된 정보가 없습니다."
    
    prompt = f"""사용자 요청: {user_request}

{collected_info}

위의 수집된 정보를 바탕으로 사용자의 요청에 대한 완전하고 유용한 답변을 작성해주세요.

답변 작성 지침:
1. 수집된 모든 정보를 활용하여 포괄적인 답변을 제공하세요
2. 비교가 요청되었다면, 각 항목을 비교 분석하세요
3. 마크다운 형식을 사용하여 읽기 쉽게 구성하세요
4. 구체적이고 실용적인 정보를 포함하세요
5. 사용자가 요청한 모든 항목을 다루었는지 확인하세요

답변을 시작하세요:"""
    
    return prompt


def _generate_summary_answer(state: ChatState) -> str:
    """ReAct 과정을 요약하여 최종 답변을 생성합니다"""
    messages = state.get("messages", [])
    tool_calls = state.get("tool_calls", [])
    user_message = state.get("current_message")
    
    # 성공한 도구 호출 결과 수집
    successful_calls = [tc for tc in tool_calls if tc.is_successful()]
    failed_calls = [tc for tc in tool_calls if not tc.is_successful()]
    
    if not successful_calls and not failed_calls:
        # 도구 호출이 없었던 경우
        if user_message:
            return f"'{user_message.content}' 요청을 분석했지만, 추가 정보 수집이 필요하지 않아 일반적인 답변을 제공합니다."
        else:
            return "요청을 처리했습니다."
    
    # 답변 구성
    answer_parts = []
    
    if user_message:
        answer_parts.append(f"## {user_message.content}\n")
    
    if successful_calls:
        answer_parts.append("### 수집된 정보:")
        for i, tc in enumerate(successful_calls, 1):
            # 동적 도구 설명 생성
            tool_desc = _format_tool_call_description(tc)
            answer_parts.append(f"\n**{i}. {tool_desc}:**")
            answer_parts.append(f"- {tc.result}")
    
    if failed_calls:
        answer_parts.append(f"\n### 처리 중 발생한 문제:")
        for i, tc in enumerate(failed_calls, 1):
            answer_parts.append(f"{i}. {tc.tool_name} 실행 실패: {tc.error}")
    
    # 다중 결과 분석 (여러 결과가 있는 경우)
    if len(successful_calls) > 1:
        answer_parts.append(f"\n### 수집된 정보 요약:")
        results = []
        for tc in successful_calls:
            tool_desc = _format_tool_call_description(tc)
            results.append(f"{tool_desc}({tc.result})")
        
        answer_parts.append(f"총 {len(successful_calls)}개 항목의 정보를 수집했습니다:")
        answer_parts.append(f"- " + ", ".join(results))
    
    return "\n".join(answer_parts)


def _format_tool_call_description(tool_call: MCPToolCall) -> str:
    """도구 호출을 사용자 친화적으로 설명합니다 (완전 동적 방식)"""
    tool_name = tool_call.tool_name
    arguments = tool_call.arguments
    
    # 주요 인수 추출 (첫 번째 값 사용)
    main_arg = None
    if arguments:
        # 가장 의미있어 보이는 값 선택
        for key, value in arguments.items():
            if value and str(value).strip():  # 빈 값이 아닌 것
                main_arg = str(value).strip()
                break
    
    # 범용적인 설명 생성
    if main_arg:
        return f"{tool_name}({main_arg})"
    else:
        return tool_name 