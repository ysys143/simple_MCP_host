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

from ..models import ChatState, ChatMessage, MessageRole, MCPToolCall
from ..streaming.message_types import (
    create_thinking_message, create_acting_message, 
    create_observing_message, create_final_response_message,
    create_partial_response_message
)
from ..streaming.sse_manager import get_sse_manager
from .llm_nodes import get_llm


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
    
    # SSE 메시지 전송
    if session_id:
        sse_manager = get_sse_manager()
        thinking_msg = create_thinking_message(
            f"생각하는 중... (단계 {iteration + 1})",
            session_id,
            iteration=iteration + 1
        )
        await sse_manager.send_to_session(session_id, thinking_msg)
    
    # 현재 상황 분석을 위한 프롬프트 구성
    think_prompt = _build_think_prompt(state)
    
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
        
        # 사고 과정을 SSE로 전송
        if session_id and parsed_thought.get("thought"):
            sse_manager = get_sse_manager()
            thinking_detail_msg = create_thinking_message(
                f"사고: {parsed_thought['thought']}",
                session_id,
                iteration=iteration + 1
            )
            await sse_manager.send_to_session(session_id, thinking_detail_msg)
        
        # 상태 업데이트
        state["react_thought"] = thought_content
        state["react_current_step"] = "think"
        state["react_iteration"] = iteration + 1
        
        # 종료 조건 체크
        if parsed_thought.get("final_answer"):
            state["react_final_answer"] = parsed_thought["final_answer"]
            state["react_should_continue"] = False
            state["next_step"] = "react_finalize"
        elif parsed_thought.get("action"):
            state["react_action"] = parsed_thought["action"]
            state["react_should_continue"] = True
            state["next_step"] = "react_act"
        else:
            # 행동이 명시되지 않았으면 일반 응답으로 처리
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
    action = state.get("react_action", "")
    
    # SSE 메시지 전송
    if session_id:
        sse_manager = get_sse_manager()
        acting_msg = create_acting_message(
            f"행동 실행 중: {action}",
            session_id,
            action_details={"action": action}
        )
        await sse_manager.send_to_session(session_id, acting_msg)
    
    try:
        # 행동 파싱 및 실행
        tool_call_result = await _execute_action(state, action)
        
        if tool_call_result:
            # 도구 호출 결과를 상태에 추가
            state["tool_calls"].append(tool_call_result)
            state["react_observation"] = _format_tool_result(tool_call_result)
        else:
            # 도구 호출이 아닌 경우 (정보 수집, 분석 등)
            state["react_observation"] = f"행동 완료: {action}"
        
        state["react_current_step"] = "act"
        state["next_step"] = "react_observe"
        
        logger.info("Act 단계 완료")
        
    except Exception as e:
        logger.error(f"Act 단계 오류: {e}")
        state["error"] = f"행동 실행 중 오류: {str(e)}"
        state["react_observation"] = f"행동 실행 실패: {str(e)}"
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
    
    # SSE 메시지 전송
    if session_id:
        sse_manager = get_sse_manager()
        observing_msg = create_observing_message(
            f"결과 관찰: {observation}",
            session_id,
            observation_data={"observation": observation, "iteration": iteration}
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
                        
                        # 단어 단위 버퍼링 전략 (자연스러운 방식)
                        should_send = (
                            token in [' ', '\t'] or  # 공백이나 탭 (단어 구분자)
                            token in ['.', '!', '?', ',', ';', ':', '\n'] or  # 구두점이나 줄바꿈
                            token in ['。', '！', '？', '，', '；', '：'] or  # 한국어/중국어 구두점
                            len(word_buffer) >= 15 or  # 너무 긴 단어 방지 (15글자 제한)
                            token_count % 20 == 0  # 안전장치: 20토큰마다 강제 전송
                        )
                        
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
                            
                            # 자연스러운 읽기 지연
                            if token in ['.', '!', '?', '。', '！', '？']:
                                await asyncio.sleep(0.15)  # 문장 끝 지연
                            elif token in [',', ';', '，', '；']:
                                await asyncio.sleep(0.08)  # 쉼표 지연
                            elif token == '\n':
                                await asyncio.sleep(0.1)   # 줄바꿈 지연
                            else:
                                await asyncio.sleep(0.05)  # 일반 단어 지연
                
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


def _build_think_prompt(state: ChatState) -> str:
    """Think 단계를 위한 프롬프트를 구성합니다"""
    iteration = state.get("react_iteration", 0)
    user_message = state.get("current_message")
    tool_calls = state.get("tool_calls", [])
    
    if iteration == 0:
        # 첫 번째 반복
        prompt = f"""당신은 ReAct (Reasoning and Acting) 패턴을 사용하여 문제를 해결하는 AI입니다.

사용자 질문: {user_message.content if user_message else ""}

사용 가능한 도구들:
- get_weather: 특정 위치의 현재 날씨 정보를 가져옵니다 (예: get_weather: 서울)
- get_forecast: 특정 위치의 일기예보를 가져옵니다 (예: get_forecast: 부산)
- list_files: 디렉토리의 파일 목록을 가져옵니다
- read_file: 파일 내용을 읽습니다
- file_info: 파일 정보를 가져옵니다

다음 형식으로 응답해주세요:

생각: [현재 상황을 분석하고 다음에 무엇을 해야 할지 생각해보세요. 여러 도시의 날씨가 필요하다면 하나씩 순서대로 처리해야 합니다.]

행동: [구체적인 행동을 명시하세요. 도구를 사용할 때는 정확히 "도구명: 인수" 형식으로 작성하세요. 예: get_weather: 서울]

또는

최종 답변: [모든 필요한 정보를 수집했다면 최종 답변을 제공하세요]

중요: 
- 행동은 반드시 "도구명: 인수" 형식으로 작성하세요 (번호나 기호 없이)
- 여러 위치의 정보가 필요한 경우, 한 번에 하나씩 처리하세요."""
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
위 결과를 바탕으로 다음 단계를 결정해주세요:

생각: [현재까지의 진행 상황을 분석하고 다음에 무엇을 해야 할지 생각해보세요. 아직 필요한 정보가 더 있는지 확인하세요.]

행동: [추가로 필요한 행동이 있다면 정확히 "도구명: 인수" 형식으로 명시하세요. 예: get_weather: 부산]

또는

최종 답변: [모든 필요한 정보를 수집했다면 종합적인 최종 답변을 제공하세요]

중요: 
- 행동은 반드시 "도구명: 인수" 형식으로 작성하세요 (번호나 기호 없이)
- 사용자가 요청한 모든 정보를 수집했는지 확인하고, 부족한 부분이 있다면 계속 진행하세요."""
    
    return prompt


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
    """행동을 실행합니다"""
    # 도구 호출 패턴 매칭 (다양한 형식 지원)
    tool_patterns = [
        r"(\w+)\s*:\s*(.+)",           # "도구명: 인수" 형식
        r"(\w+)\((.+)\)",              # "도구명(인수)" 형식
        r"\d+\.\s*(\w+)\s*:\s*(.+)",   # "1. 도구명: 인수" 형식
        r"-\s*(\w+)\s*:\s*(.+)",       # "- 도구명: 인수" 형식
    ]
    
    for pattern in tool_patterns:
        match = re.match(pattern, action.strip())
        if match:
            tool_name = match.group(1)
            arguments_str = match.group(2)
            
            # 도구 호출 실행
            return await _call_mcp_tool(state, tool_name, arguments_str)
    
    # 도구 호출이 아닌 경우 None 반환
    return None


async def _call_mcp_tool(state: ChatState, tool_name: str, arguments_str: str) -> MCPToolCall:
    """MCP 도구를 호출합니다"""
    from ..models import MCPToolCall
    from datetime import datetime
    import time
    
    # 도구별 적절한 인수 구성
    if tool_name == "get_weather":
        arguments = {"location": arguments_str.strip()}
        server_name = "weather"
    elif tool_name == "get_forecast":
        arguments = {"location": arguments_str.strip(), "days": 3}
        server_name = "weather"
    elif tool_name == "list_files":
        arguments = {"directory": arguments_str.strip() if arguments_str.strip() else "."}
        server_name = "file-manager"
    elif tool_name == "read_file":
        arguments = {"filename": arguments_str.strip()}
        server_name = "file-manager"
    elif tool_name == "file_info":
        arguments = {"filename": arguments_str.strip()}
        server_name = "file-manager"
    else:
        # 기본값
        arguments = {"query": arguments_str.strip()}
        server_name = "default"
    
    tool_call = MCPToolCall(
        server_name=server_name,
        tool_name=tool_name,
        arguments=arguments
    )
    
    try:
        start_time = time.time()
        
        # MCP 클라이언트를 통한 실제 도구 호출
        mcp_client = state.get("mcp_client")
        if not mcp_client:
            raise ValueError("MCP 클라이언트가 없습니다")
        
        logger.info(f"실제 MCP 도구 호출: {server_name}.{tool_name}")
        
        # Enhanced MCP Client의 call_tool 메서드 사용 (server_name, tool_name, arguments 순서)
        result = await mcp_client.call_tool(server_name, tool_name, arguments)
        
        tool_call.result = result
        tool_call.execution_time_ms = int((time.time() - start_time) * 1000)
        
        logger.info(f"MCP 도구 호출 성공: {tool_name}")
        
    except Exception as e:
        tool_call.error = str(e)
        tool_call.execution_time_ms = int((time.time() - start_time) * 1000)
        logger.error(f"MCP 도구 호출 실패: {tool_name} - {e}")
    
    return tool_call


def _format_tool_result(tool_call: MCPToolCall) -> str:
    """도구 호출 결과를 포맷팅합니다"""
    if tool_call.is_successful():
        return f"도구 '{tool_call.tool_name}' 실행 성공: {tool_call.result}"
    else:
        return f"도구 '{tool_call.tool_name}' 실행 실패: {tool_call.error}"


def _should_continue_react(state: ChatState) -> bool:
    """ReAct 사이클을 계속 진행할지 결정합니다"""
    # 최근 2번의 관찰에서 진전이 없으면 종료
    messages = state.get("messages", [])
    recent_observations = [
        msg for msg in messages[-4:] 
        if msg.metadata and msg.metadata.get("react_step") == "observe"
    ]
    
    if len(recent_observations) >= 2:
        # 연속된 관찰에서 유사한 내용이면 종료
        last_obs = recent_observations[-1].content
        prev_obs = recent_observations[-2].content
        
        if len(last_obs) > 0 and len(prev_obs) > 0:
            # 간단한 유사도 체크 (실제로는 더 정교한 로직 필요)
            similarity = len(set(last_obs.split()) & set(prev_obs.split())) / max(len(last_obs.split()), len(prev_obs.split()))
            if similarity > 0.8:
                return False
    
    return True


def _build_final_answer_prompt(state: ChatState) -> str:
    """최종 답변 생성을 위한 프롬프트를 구성합니다"""
    user_message = state.get("current_message")
    tool_calls = state.get("tool_calls", [])
    
    # 성공한 도구 호출 결과 수집
    successful_calls = [tc for tc in tool_calls if tc.is_successful()]
    
    # 사용자 요청
    user_request = user_message.content if user_message else "정보 요청"
    
    # 수집된 정보 정리
    collected_info = ""
    if successful_calls:
        collected_info = "수집된 정보:\n"
        for i, tc in enumerate(successful_calls, 1):
            if tc.tool_name == "get_weather":
                location = tc.arguments.get("location", "알 수 없는 위치")
                collected_info += f"{i}. {location} 날씨: {tc.result}\n"
            elif tc.tool_name == "get_forecast":
                location = tc.arguments.get("location", "알 수 없는 위치")
                days = tc.arguments.get("days", 3)
                collected_info += f"{i}. {location} {days}일 예보: {tc.result}\n"
            else:
                collected_info += f"{i}. {tc.tool_name}: {tc.result}\n"
    else:
        collected_info = "수집된 정보가 없습니다."
    
    prompt = f"""사용자 요청: {user_request}

{collected_info}

위의 수집된 정보를 바탕으로 사용자의 요청에 대한 완전하고 유용한 답변을 작성해주세요.

답변 작성 지침:
1. 수집된 모든 정보를 활용하여 포괄적인 답변을 제공하세요
2. 날씨 비교가 요청된 경우, 각 지역의 날씨를 비교 분석하세요
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
            if tc.tool_name == "get_weather":
                location = tc.arguments.get("location", "알 수 없는 위치")
                answer_parts.append(f"\n**{i}. {location} 날씨:**")
                answer_parts.append(f"- {tc.result}")
            elif tc.tool_name == "get_forecast":
                location = tc.arguments.get("location", "알 수 없는 위치")
                days = tc.arguments.get("days", 3)
                answer_parts.append(f"\n**{i}. {location} {days}일 예보:**")
                answer_parts.append(f"- {tc.result}")
            else:
                answer_parts.append(f"\n**{i}. {tc.tool_name}:**")
                answer_parts.append(f"- {tc.result}")
    
    if failed_calls:
        answer_parts.append(f"\n### 처리 중 발생한 문제:")
        for i, tc in enumerate(failed_calls, 1):
            answer_parts.append(f"{i}. {tc.tool_name} 실행 실패: {tc.error}")
    
    # 날씨 비교 리포트 생성 (날씨 관련 요청인 경우)
    weather_calls = [tc for tc in successful_calls if tc.tool_name in ["get_weather", "get_forecast"]]
    if len(weather_calls) > 1 and user_message and "비교" in user_message.content:
        answer_parts.append(f"\n### 비교 분석:")
        locations = []
        for tc in weather_calls:
            location = tc.arguments.get("location", "알 수 없는 위치")
            locations.append(f"{location}({tc.result})")
        
        answer_parts.append(f"총 {len(weather_calls)}개 지역의 날씨 정보를 수집했습니다:")
        answer_parts.append(f"- " + ", ".join(locations))
    
    return "\n".join(answer_parts) 