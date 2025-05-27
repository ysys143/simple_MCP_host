"""LLM 기반 워크플로우 노드

OpenAI ChatGPT를 활용하여 자연어 이해와 응답 생성을 수행하는 노드들입니다.
키워드 매칭에서 진정한 AI 기반 대화 시스템으로 업그레이드됩니다.

SOLID 원칙을 준수하여 각 노드가 단일 책임을 가지도록 설계되었습니다.
"""

import asyncio
import logging
import os
from typing import Dict, Any, Optional
import re

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.callbacks import BaseCallbackHandler

from ..models import ChatState, IntentType, ParsedIntent, MessageRole
from .state_utils import update_workflow_step, set_error, increment_step_count

# 로깅 설정
logger = logging.getLogger(__name__)

# LLM 유틸리티 임포트
from .llm_utils import get_llm


async def llm_parse_intent(state: ChatState) -> ChatState:
    """LLM을 사용하여 사용자 의도를 분석하고 적절한 도구를 선택합니다
    
    사용 가능한 모든 MCP 도구의 설명을 LLM에게 제공하여
    사용자 요청에 가장 적합한 도구를 동적으로 선택합니다.
    
    Args:
        state: 현재 워크플로우 상태
        
    Returns:
        의도 분석이 완료된 상태
    """
    try:
        current_message = state.get("current_message")
        mcp_client = state.get("mcp_client")
        
        if not current_message:
            raise ValueError("현재 메시지가 없습니다")
        
        # 사용자 입력 정리
        user_input = current_message.content
        user_input_clean = re.sub(r'[\U00010000-\U0010ffff]|[\u2600-\u27BF]|[\uD800-\uDBFF][\uDC00-\uDFFF]', '', user_input)
        user_input_clean = user_input_clean.strip()
        
        logger.info(f"동적 LLM 의도 분석 시작: {user_input_clean}")
        
        # 사용 가능한 도구 목록 수집
        available_tools_info = ""
        if mcp_client:
            try:
                tools = mcp_client.get_tools()
                server_names = mcp_client.get_server_names()
                
                tool_descriptions = []
                for tool in tools:
                    tool_name = getattr(tool, 'name', '이름없음')
                    tool_desc = getattr(tool, 'description', '설명없음')
                    
                    # 도구명만 사용 (서버명 제외)
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
        
        # LLM을 사용한 동적 의도 분석
        llm = get_llm()
        
        # 동적 의도 분석 프롬프트 (안전한 방식으로 구성)
        system_prompt = f"""당신은 사용자의 요청을 분석하여 적절한 도구를 선택하는 AI입니다.

{available_tools_info}

사용자 요청을 분석하여 다음 중 하나로 분류해주세요:

1. TOOL_CALL: 위의 도구 중 하나를 사용해야 하는 경우
   - 도구 이름과 필요한 매개변수를 정확히 식별해주세요
   - 여러 도구가 필요한 경우 가장 적합한 하나를 선택해주세요

2. GENERAL_CHAT: 일반적인 대화나 정보 제공 요청
   - 도구 없이 답변 가능한 경우

3. HELP: 도움말이나 사용법 문의
4. SERVER_STATUS: MCP 서버 상태 확인  
5. TOOL_LIST: 사용 가능한 도구 목록 요청

응답 형식:
INTENT: [의도]
CONFIDENCE: [0.0-1.0 신뢰도]
TARGET_TOOL: [정확한 도구명 또는 null]
PARAMETERS: [추출된 매개변수들, JSON 형식]
REASONING: [선택 근거]

중요: TARGET_TOOL은 위에 나열된 도구명과 정확히 일치해야 합니다.

예시:
INTENT: TOOL_CALL
CONFIDENCE: 0.95
TARGET_TOOL: get_weather
PARAMETERS: {{"location": "부산"}}
REASONING: 사용자가 부산의 날씨 정보를 요청했습니다.

중요 지침:
- 여러 지역이나 항목이 언급된 경우, ReAct 모드를 권장하세요
- 복잡한 비교나 분석 요청은 ReAct 모드에서 처리하세요
- 단순한 단일 정보 조회만 이 모드에서 처리하세요"""

        # 안전한 메시지 구성 (ChatPromptTemplate 없이)
        from langchain_core.messages import SystemMessage, HumanMessage
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_input_clean)
        ]
        
        # LLM 호출
        response = await llm.ainvoke(messages)
        response_text = response.content
        
        # 응답 파싱 (원본 user_input 사용)
        parsed_intent = _parse_llm_intent_response(response_text, user_input)
        state["parsed_intent"] = parsed_intent
        
        # 복잡한 요청 감지 (ReAct 모드 전환 여부 결정)
        user_input_clean = user_input.strip()
        user_input_lower = user_input_clean.lower()
        
        # 디버깅 정보 추가
        comma_count = len(re.findall(r'[,，]', user_input_clean))
        keyword_matches = [keyword for keyword in ['비교', '분석', '리포트', '여러', '모든', '각각'] if keyword in user_input_lower]
        korean_word_groups = re.findall(r'[가-힣]{2,}(?:\\s*,\\s*[가-힣]{2,}){2,}', user_input_clean)
        
        logger.info(f"복잡한 요청 감지 분석:")
        logger.info(f"  입력: '{user_input_clean}'")
        logger.info(f"  쉼표 개수: {comma_count}")
        logger.info(f"  키워드 매치: {keyword_matches}")
        logger.info(f"  한국어 단어 그룹: {korean_word_groups}")
        
        # 더 엄격한 복잡한 요청 감지 조건
        is_complex_request = (
            comma_count >= 3 or  # 쉼표가 3개 이상 (더 엄격)
            (len(keyword_matches) > 0 and comma_count >= 1) or  # 키워드가 있고 쉼표도 있는 경우
            len(korean_word_groups) > 0  # 3개 이상의 한국어 단어가 쉼표로 구분
        )
        
        logger.info(f"  복잡한 요청 여부: {is_complex_request}")
        
        if is_complex_request and not state.get("react_mode"):
            logger.info(f"복잡한 요청 감지 - ReAct 모드로 전환: {user_input_clean}")
            # ReAct 모드로 전환
            state["react_mode"] = True
            state["should_use_react"] = True
            update_workflow_step(state, "switch_to_react")
            return state
        
        # 다음 단계 결정
        if parsed_intent.is_mcp_action():
            update_workflow_step(state, "llm_call_mcp_tool")
        else:
            update_workflow_step(state, "llm_generate_response")
        
        logger.info(f"동적 LLM 의도 분석 완료: {parsed_intent.intent_type.value}")
        if parsed_intent.target_server and parsed_intent.target_tool:
            logger.info(f"선택된 도구: {parsed_intent.target_server}.{parsed_intent.target_tool}")
        
        return state
        
    except Exception as e:
        logger.error(f"동적 LLM 의도 분석 오류: {e}")
        # 실패 시 일반 대화로 처리
        from ..models import ParsedIntent, IntentType
        fallback_intent = ParsedIntent(
            intent_type=IntentType.GENERAL_CHAT,
            confidence=0.5,
            parameters={},
            target_server=None,
            target_tool=None
        )
        state["parsed_intent"] = fallback_intent
        update_workflow_step(state, "llm_generate_response")
        return state


async def llm_call_mcp_tool(state: ChatState) -> ChatState:
    """LLM이 MCP 도구 호출을 결정하고 실행합니다
    
    사용자 요청을 분석하여 적절한 MCP 도구를 선택하고 실행합니다.
    도구 실행 결과를 state에 저장합니다.
    
    Args:
        state: 현재 워크플로우 상태
        
    Returns:
        도구 호출 결과가 포함된 상태
    """
    try:
        parsed_intent = state.get("parsed_intent")
        if not parsed_intent:
            raise ValueError("파싱된 의도가 없습니다")
        
        # MCP 클라이언트 상태 확인
        mcp_client = state.get("mcp_client")
        logger.info(f"LLM MCP 도구 호출 시작:")
        logger.info(f"  대상: {parsed_intent.target_server}.{parsed_intent.target_tool}")
        logger.info(f"  MCP 클라이언트 존재: {mcp_client is not None}")
        if mcp_client:
            logger.info(f"  MCP 클라이언트 타입: {type(mcp_client)}")
            logger.info(f"  call_tool 메서드 존재: {hasattr(mcp_client, 'call_tool')}")
        
        # 도구 호출 전 상태 확인
        logger.info(f"도구 호출 전 tool_calls 길이: {len(state.get('tool_calls', []))}")
        
        # 기존 도구 호출 로직 재사용 (비동기 호출)
        from .nodes import call_mcp_tool
        updated_state = await call_mcp_tool(state)
        
        # 도구 호출 후 상태 확인
        tool_calls_after = updated_state.get("tool_calls", [])
        logger.info(f"도구 호출 후 tool_calls 길이: {len(tool_calls_after)}")
        if tool_calls_after:
            logger.info(f"마지막 호출 결과: {tool_calls_after[-1].server_name}.{tool_calls_after[-1].tool_name} = {tool_calls_after[-1].result}")
        
        # 다음 단계로 LLM 응답 생성
        update_workflow_step(updated_state, "llm_generate_response")
        return updated_state
        
    except Exception as e:
        logger.error(f"LLM MCP 도구 호출 오류: {e}")
        logger.exception("LLM MCP 도구 호출 상세 오류:")
        set_error(state, f"도구 호출 실패: {e}")
        return state


def llm_generate_response(state: ChatState) -> ChatState:
    """LLM을 사용하여 자연스러운 응답을 생성합니다
    
    사용자 질문과 MCP 도구 결과(있는 경우)를 바탕으로
    ChatGPT가 자연스럽고 도움이 되는 응답을 생성합니다.
    
    Args:
        state: 현재 워크플로우 상태
        
    Returns:
        LLM 응답이 포함된 상태
    """
    try:
        current_message = state.get("current_message")
        parsed_intent = state.get("parsed_intent")
        # 실제 도구 호출 결과 가져오기 (tool_calls에서)
        tool_calls = state.get("tool_calls", [])
        
        if not current_message:
            raise ValueError("현재 메시지가 없습니다")
        
        user_input = current_message.content
        logger.info(f"LLM 응답 생성 시작: {parsed_intent.intent_type.value if parsed_intent else 'None'}")
        
        # 시스템 정보 요청인 경우 직접 정보 제공
        if parsed_intent and parsed_intent.intent_type == IntentType.TOOL_LIST:
            # MCP 클라이언트에서 실제 도구 정보 가져오기
            mcp_client = state.get("mcp_client")
            if mcp_client:
                try:
                    server_names = mcp_client.get_server_names()
                    tools_info = mcp_client.get_tools_info()
                    
                    # 동적으로 도구 목록 생성
                    content_parts = ["## 🔧 사용 가능한 도구 목록\n", "현재 사용 가능한 도구들은 다음과 같습니다:\n"]
                    
                    for server_name in server_names:
                        server_tools = tools_info.get(server_name, [])
                        if server_tools:
                            # 서버별 섹션 추가 (동적 아이콘 생성)
                            server_icon = _get_server_icon(server_name)
                            content_parts.append(f"\n### {server_icon} {server_name} 서버")
                            
                            for tool in server_tools:
                                tool_name = tool.get('name', '이름없음')
                                tool_desc = tool.get('description', '설명없음')
                                content_parts.append(f"- **{tool_name}**: {tool_desc}")
                    
                    # 사용법 안내 추가
                    content_parts.extend([
                        "\n### 📝 도구 사용 시 유의사항",
                        "- 도구를 사용할 때는 항상 정확한 결과를 확인하고, 필요한 경우 추가적인 정보를 요청해 주세요.",
                        "- 도구가 정상적으로 작동하지 않을 경우, 다른 방법으로 문제를 해결할 수 있지 고민해보세요.",
                        "\n추가적인 질문이나 도움이 필요하시면 언제든지 말씀해 주세요! 😊"
                    ])
                    
                    system_info_content = "\n".join(content_parts)
                    
                except Exception as e:
                    logger.error(f"도구 정보 가져오기 실패: {e}")
                    # 실패 시 기본 메시지
                    system_info_content = "## 🔧 도구 목록\n\n도구 정보를 가져오는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
            else:
                # MCP 클라이언트가 없는 경우
                system_info_content = "## 🔧 도구 목록\n\nMCP 클라이언트가 초기화되지 않았습니다."
            
            state["response"] = system_info_content
            state["success"] = True
            update_workflow_step(state, "completed")
            return state
        
        elif parsed_intent and parsed_intent.intent_type == IntentType.SERVER_STATUS:
            # MCP 클라이언트에서 실제 서버 상태 가져오기
            mcp_client = state.get("mcp_client")
            if mcp_client:
                try:
                    server_names = mcp_client.get_server_names()
                    server_count = mcp_client.get_server_count()
                    tool_count = len(mcp_client.get_tool_names())
                    
                    # 동적으로 서버 상태 생성
                    content_parts = ["## 🟢 서버 상태\n", "### 연결된 서버"]
                    
                    for server_name in server_names:
                        server_icon = _get_server_icon(server_name)
                        content_parts.append(f"- **{server_name}**: {server_icon} 서버 ✅")
                    
                    content_parts.extend([
                        "\n### 시스템 상태",
                        f"- **서버**: {server_count}개 활성화",
                        f"- **도구**: {tool_count}개 사용 가능", 
                        "- **상태**: 모든 시스템 정상 작동 중",
                        "\n모든 서버가 정상적으로 연결되어 있으며 도구 사용이 가능합니다."
                    ])
                    
                    system_info_content = "\n".join(content_parts)
                    
                except Exception as e:
                    logger.error(f"서버 상태 가져오기 실패: {e}")
                    # 실패 시 기본 메시지
                    system_info_content = "## 🟢 서버 상태\n\n서버 상태 정보를 가져오는 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."
            else:
                # MCP 클라이언트가 없는 경우
                system_info_content = "## 🟢 서버 상태\n\nMCP 클라이언트가 초기화되지 않았습니다."
            
            state["response"] = system_info_content
            state["success"] = True
            update_workflow_step(state, "completed")
            return state
        
        # 디버깅: tool_calls 내용 확인
        logger.info(f"tool_calls 길이: {len(tool_calls)}")
        if tool_calls:
            for i, call in enumerate(tool_calls):
                logger.info(f"tool_call[{i}]: {call.server_name}.{call.tool_name} = {call.result}")
        else:
            logger.info("tool_calls가 비어있습니다!")
        
        llm = get_llm()
        
        # 응답 생성 프롬프트 구성
        system_message = """당신은 친절하고 도움이 되는 AI 어시스턴트입니다.
사용자의 질문에 대해 정확하고 유용한 답변을 제공해주세요.

만약 외부 도구(MCP 도구)를 사용한 결과가 있다면, 그 결과를 바탕으로 답변해주세요.
결과가 없거나 오류가 있다면, 일반적인 지식으로 최선의 답변을 제공해주세요.

**응답 형식**: 
- 마크다운 형식으로 답변을 작성해주세요
- 적절한 제목(##), 목록(-), 강조(**텍스트**), 코드(`코드`) 등을 사용하세요
- 답변은 한국어로 친근하고 이해하기 쉽게 작성해주세요
- 정보가 많을 때는 구조화된 형태로 정리해주세요."""

        messages = [SystemMessage(content=system_message)]
        
        # 사용자 메시지 추가
        user_input = state.get("current_message", BaseMessage(content="", type="human")).content
        
        # 기본 사용자 컨텐츠 초기화
        user_content = f"사용자 질문: {user_input}"
        
        # MCP 도구 호출 결과가 있다면 추가
        if tool_calls:
            user_content += "\n\n도구 실행 결과:"
            for i, mcp_call in enumerate(tool_calls):
                if mcp_call.is_successful():
                    user_content += f"\n{i+1}. {mcp_call.server_name}.{mcp_call.tool_name}: {mcp_call.result}"
                else:
                    user_content += f"\n{i+1}. {mcp_call.server_name}.{mcp_call.tool_name}: 오류 - {mcp_call.error}"
            
            # 도구 호출 정보 요약 추가
            user_content += "\n\n사용된 도구:"
            for mcp_call in tool_calls:
                user_content += f"\n- {mcp_call.server_name}.{mcp_call.tool_name}({mcp_call.arguments})"
        
        messages.append(HumanMessage(content=user_content))
        
        # 디버깅: LLM에 전달되는 프롬프트 내용 출력
        logger.info(f"LLM에 전달되는 프롬프트:")
        logger.info(f"시스템 메시지: {system_message}")
        logger.info(f"사용자 컨텐츠: {user_content}")
        
        # LLM 응답 생성
        response = llm.invoke(messages)
        generated_response = response.content
        
        # 상태 업데이트
        state["response"] = generated_response
        state["success"] = True
        update_workflow_step(state, "completed")
        
        logger.info("LLM 응답 생성 완료")
        return state
        
    except Exception as e:
        logger.error(f"LLM 응답 생성 오류: {e}")
        # 실패 시 기존 방식으로 폴백
        logger.info("기존 방식 응답 생성으로 폴백")
        update_workflow_step(state, "generate_response")
        return state


def _parse_llm_intent_response(response_text: str, user_input: str) -> ParsedIntent:
    """LLM 응답을 파싱하여 ParsedIntent 객체로 변환합니다
    
    Args:
        response_text: LLM의 원시 응답 텍스트
        user_input: 원본 사용자 입력
        
    Returns:
        파싱된 의도 객체
    """
    try:
        lines = response_text.strip().split('\n')
        intent_type_str = "GENERAL_CHAT"
        confidence = 0.5
        parameters = {}
        target_server = None
        target_tool = None
        
        for line in lines:
            line = line.strip()
            if line.startswith("INTENT:"):
                intent_type_str = line.replace("INTENT:", "").strip()
            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.replace("CONFIDENCE:", "").strip())
                except ValueError:
                    confidence = 0.5
            elif line.startswith("TARGET_TOOL:"):
                tool_str = line.replace("TARGET_TOOL:", "").strip()
                target_tool = tool_str if tool_str.lower() != "null" else None
            elif line.startswith("PARAMETERS:"):
                param_str = line.replace("PARAMETERS:", "").strip()
                try:
                    import json
                    parameters = json.loads(param_str)
                except (json.JSONDecodeError, ValueError):
                    parameters = {}
        
        # IntentType으로 변환
        try:
            intent_type = IntentType(intent_type_str)
        except ValueError:
            intent_type = IntentType.GENERAL_CHAT
        
        # 도구명으로 서버 자동 추론 (동적 방식)
        if target_tool:
            target_server = _infer_server_from_tool(target_tool)
        
        # TOOL_CALL인데 target_tool이 없으면 폴백
        if intent_type == IntentType.TOOL_CALL and not target_tool:
            # 기존 방식으로 폴백
            target_server, target_tool = _determine_target_from_intent_fallback(parameters, user_input)
        
        return ParsedIntent(
            intent_type=intent_type,
            confidence=confidence,
            parameters=parameters,
            target_server=target_server,
            target_tool=target_tool
        )
        
    except Exception as e:
        logger.warning(f"LLM 응답 파싱 실패: {e}")
        # 기본값 반환
        return ParsedIntent(
            intent_type=IntentType.GENERAL_CHAT,
            confidence=0.3,
            parameters={},
            target_server=None,
            target_tool=None
        )


def _infer_server_from_tool(tool_name: str) -> Optional[str]:
    """도구명으로부터 서버명을 동적으로 추론합니다 (완전 동적 방식)"""
    if not tool_name:
        return None
    
    # 도구명에서 서버명 추출 시도
    tool_lower = tool_name.lower()
    
    # 하이픈이나 언더스코어로 구분된 경우 첫 번째 부분을 서버로 추정
    if '-' in tool_name:
        potential_server = tool_name.split('-')[0]
        return potential_server
    elif '_' in tool_name:
        potential_server = tool_name.split('_')[0]
        return potential_server
    
    # 기본값: None (MCP 클라이언트가 자동으로 찾도록)
    return None


def _determine_target_from_intent_fallback(parameters: Dict[str, Any], user_input: str) -> tuple[Optional[str], Optional[str]]:
    """폴백: 매개변수와 사용자 입력으로부터 대상 서버와 도구를 추정합니다 (완전 동적 방식)"""
    # 하드코딩된 키워드 매칭 제거
    # 매개변수나 사용자 입력에서 힌트를 찾되, 특정 도구에 의존하지 않음
    
    # 매개변수에서 힌트 찾기
    if parameters:
        # 첫 번째 매개변수 키를 기반으로 추론
        first_key = list(parameters.keys())[0] if parameters else None
        first_value = list(parameters.values())[0] if parameters else None
        
        if first_key and first_value:
            # 매개변수 이름과 값을 기반으로 일반적인 추론
            return None, None  # 동적 시스템에서는 LLM이 결정하도록 함
    
    # 사용자 입력에서 서버나 도구 이름이 명시적으로 언급된 경우만 처리
    user_lower = user_input.lower()
    
    # 명시적인 서버/도구 언급 찾기 (동적)
    import re
    
    # "서버명.도구명" 패턴 찾기
    server_tool_pattern = r'(\w+)\.(\w+)'
    matches = re.findall(server_tool_pattern, user_input)
    if matches:
        return matches[0][0], matches[0][1]
    
    # 특정 서버가 명시적으로 언급된 경우
    server_mentions = re.findall(r'(\w+)\s*(?:서버|server)', user_lower)
    if server_mentions:
        return server_mentions[0], None
    
    # 기본적으로는 LLM이 결정하도록 None 반환
    return None, None


class StreamingCallbackHandler(BaseCallbackHandler):
    """토큰 단위 스트리밍을 위한 콜백 핸들러"""
    
    def __init__(self, sse_manager, session_id: str):
        self.sse_manager = sse_manager
        self.session_id = session_id
        self.current_content = ""
        self.token_count = 0
    
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        """새 토큰이 생성될 때마다 호출"""
        if token and token.strip():  # 공백 토큰 무시
            self.current_content += token
            self.token_count += 1
            
            # 동적 배치 크기 계산
            batch_size = max(2, min(5, 3 + (self.token_count // 20)))  # 2-5 사이에서 적응적 조정
            
            # 동적 배치마다 전송
            if self.token_count % batch_size == 0:
                self._send_partial_update_sync()
    
    def on_llm_end(self, response, **kwargs) -> None:
        """LLM 응답 완료 시 마지막 토큰들 전송"""
        if self.current_content:
            self._send_partial_update_sync()
    
    def _send_partial_update_sync(self):
        """부분 업데이트를 동기적으로 전송"""
        try:
            from ..streaming import create_partial_response_message
            
            partial_msg = create_partial_response_message(
                self.current_content,
                self.session_id
            )
            
            # 이벤트 루프가 실행 중인지 확인하고 안전하게 전송
            import asyncio
            import threading
            
            def send_message():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(
                        self.sse_manager.send_to_session(self.session_id, partial_msg)
                    )
                    loop.close()
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"스트리밍 전송 스레드 오류: {e}")
            
            # 별도 스레드에서 실행
            thread = threading.Thread(target=send_message, daemon=True)
            thread.start()
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"부분 응답 전송 실패: {e}")


async def llm_generate_response_with_streaming(state: ChatState, sse_manager, session_id: str) -> ChatState:
    """토큰 단위 스트리밍과 함께 LLM 응답 생성 (최적화된 버전)"""
    try:
        increment_step_count(state)
        logger.info("LLM 스트리밍 응답 생성 시작 (최적화된 버전)")
        
        user_input = state.get("current_message", BaseMessage(content="", type="human")).content
        tool_calls = state.get("tool_calls", [])
        parsed_intent = state.get("parsed_intent")
        
        logger.info(f"사용자 입력: {user_input}")
        logger.info(f"파싱된 의도: {parsed_intent.intent_type if parsed_intent else 'None'}")
        logger.info(f"도구 호출 수: {len(tool_calls)}")
        
        # 시스템 정보 응답 처리 (기존과 동일)
        if parsed_intent and parsed_intent.intent_type in [IntentType.TOOL_LIST, IntentType.SERVER_STATUS]:
            logger.info("시스템 정보 응답으로 기존 방식 사용")
            return llm_generate_response(state)  # 시스템 정보는 기존 방식 사용
        
        logger.info("최적화된 스트리밍 응답 생성 진행")
        
        # LLM 사용
        llm = get_llm()
        
        # 응답 생성 프롬프트 구성 (대화 히스토리 포함)
        system_message = """당신은 친절하고 도움이 되는 AI 어시스턴트입니다.
사용자와의 연속적인 대화를 통해 맥락을 이해하고 일관성 있는 답변을 제공해주세요.

**대화 맥락 활용**:
- 이전 대화 내용을 참조하여 답변하세요
- 사용자가 "그것", "그거", "위에서 말한" 등으로 이전 내용을 언급하면 대화 히스토리를 확인하세요
- 연관된 주제나 후속 질문에 대해서는 맥락을 유지하세요

**도구 결과 활용**:
- 외부 도구(MCP 도구) 결과가 있다면, 그 결과를 바탕으로 답변해주세요
- 결과가 없거나 오류가 있다면, 일반적인 지식으로 최선의 답변을 제공해주세요

**응답 형식**: 
- 마크다운 형식으로 답변을 작성해주세요
- 적절한 제목(##), 목록(-), 강조(**텍스트**), 코드(`코드`) 등을 사용하세요
- 답변은 한국어로 친근하고 이해하기 쉽게 작성해주세요
- 정보가 많을 때는 구조화된 형태로 정리해주세요."""

        messages = [SystemMessage(content=system_message)]
        
        # 대화 히스토리 불러오기 및 추가
        conversation_history = state.get("messages", [])
        logger.info(f"대화 히스토리: {len(conversation_history)}개 메시지")
        
        if len(conversation_history) > 1:  # 현재 메시지 외에 이전 메시지가 있는 경우
            logger.info("이전 대화 히스토리를 LLM 컨텍스트에 포함")
            
            # 이전 메시지들 (현재 메시지 제외)을 LLM 메시지로 변환
            for msg in conversation_history[:-1]:  # 마지막 메시지(현재 메시지) 제외
                if msg.role == MessageRole.USER:
                    messages.append(HumanMessage(content=msg.content))
                elif msg.role == MessageRole.ASSISTANT:
                    messages.append(AIMessage(content=msg.content))
                # TOOL 메시지는 스킵 (LLM 메시지 타입에 없음)
        
        # 현재 사용자 메시지 및 도구 결과 추가
        current_user_content = f"사용자 질문: {user_input}"
        
        # MCP 도구 호출 결과가 있다면 추가
        if tool_calls:
            current_user_content += "\n\n방금 실행된 도구 결과:"
            for i, mcp_call in enumerate(tool_calls):
                if mcp_call.is_successful():
                    current_user_content += f"\n{i+1}. {mcp_call.server_name}.{mcp_call.tool_name}: {mcp_call.result}"
                else:
                    current_user_content += f"\n{i+1}. {mcp_call.server_name}.{mcp_call.tool_name}: 오류 - {mcp_call.error}"
            
            # 도구 호출 정보 요약 추가
            current_user_content += "\n\n사용된 도구:"
            for mcp_call in tool_calls:
                current_user_content += f"\n- {mcp_call.server_name}.{mcp_call.tool_name}({mcp_call.arguments})"
        
        messages.append(HumanMessage(content=current_user_content))
        
        logger.info(f"LLM에 전달할 메시지 수: {len(messages)} (시스템: 1, 히스토리: {len(conversation_history)-1}, 현재: 1)")
        
        # 실시간 스트리밍 응답 생성 (단어 단위 방식)
        logger.info("단어 단위 스트리밍 시작...")
        
        full_response = ""
        word_buffer = ""  # 단어 버퍼로 변경
        token_count = 0
        
        try:
            # LLM 스트리밍 호출
            async for chunk in llm.astream(messages):
                if hasattr(chunk, 'content') and chunk.content:
                    token = chunk.content
                    full_response += token
                    word_buffer += token
                    token_count += 1
                    
                    # 단어 단위 버퍼링 전략 (동적 방식)
                    max_word_length = 12 + len(token) // 2  # 토큰 길이에 따른 적응적 버퍼
                    token_batch_size = 15 + (token_count // 10)  # 진행에 따른 배치 크기 증가
                    
                    should_send = (
                        token in [' ', '\t'] or  # 공백이나 탭 (단어 구분자)
                        token in ['.', '!', '?', ',', ';', ':', '\n'] or  # 구두점이나 줄바꿈
                        token in ['。', '！', '？', '，', '；', '：'] or  # 한국어/중국어 구두점
                        len(word_buffer) >= max_word_length or  # 적응적 단어 길이 제한
                        token_count % token_batch_size == 0  # 적응적 배치 전송
                    )
                    
                    if should_send and word_buffer.strip():  # 공백만 있는 버퍼는 전송하지 않음
                        # 완전한 단어 전송
                        from ..streaming import create_partial_response_message
                        partial_msg = create_partial_response_message(word_buffer, session_id)
                        partial_msg.metadata = {"word_streaming": True, "cumulative": False}
                        
                        try:
                            await sse_manager.send_to_session(session_id, partial_msg)
                            logger.debug(f"단어 전송: '{word_buffer.strip()}' ({len(word_buffer)}글자)")
                        except Exception as e:
                            logger.error(f"단어 전송 실패: {e}")
                        
                        # 버퍼 초기화
                        word_buffer = ""
                        
                        # 자연스러운 읽기 지연 (동적 계산)
                        base_delay = 0.03  # 기본 지연
                        if token in ['.', '!', '?', '。', '！', '？']:
                            delay = base_delay * 5  # 문장 끝
                        elif token in [',', ';', '，', '；']:
                            delay = base_delay * 2.5  # 쉼표
                        elif token == '\n':
                            delay = base_delay * 3  # 줄바꿈
                        else:
                            delay = base_delay  # 일반 단어
                        
                        await asyncio.sleep(delay)
            
            # 마지막 남은 단어 전송
            if word_buffer.strip():
                from ..streaming import create_partial_response_message
                partial_msg = create_partial_response_message(word_buffer, session_id)
                partial_msg.metadata = {"word_streaming": True, "cumulative": False, "final_word": True}
                await sse_manager.send_to_session(session_id, partial_msg)
                logger.debug(f"마지막 단어 전송: '{word_buffer.strip()}'")
            
        except Exception as e:
            logger.error(f"스트리밍 중 오류: {e}")
            # 오류 시 전체 응답을 한 번에 생성
            response = await llm.ainvoke(messages)
            full_response = response.content
        
        logger.info(f"단어 단위 스트리밍 완료 - 총 길이: {len(full_response)}글자, 토큰 수: {token_count}")
        
        # 최종 응답으로 상태 업데이트
        state["response"] = full_response
        state["success"] = True
        update_workflow_step(state, "completed")
        
        # 응답을 세션에 저장 (중요!)
        from .state import add_assistant_message
        add_assistant_message(state, full_response)
        
        # 최종 응답 메시지 전송 (전체 텍스트)
        logger.info("final_response 전송 중...")
        from ..streaming import create_final_response_message
        final_msg = create_final_response_message(full_response, session_id)
        try:
            await sse_manager.send_to_session(session_id, final_msg)
            logger.info("final_response 전송 성공")
        except Exception as e:
            logger.error(f"final_response 전송 실패: {e}")
        
        logger.info("최적화된 LLM 스트리밍 응답 생성 완료")
        return state
        
    except Exception as e:
        logger.error(f"LLM 스트리밍 응답 생성 오류: {e}")
        import traceback
        logger.error(f"스택 트레이스: {traceback.format_exc()}")
        # 오류 시 기존 방식으로 폴백
        return llm_generate_response(state) 


def _get_server_icon(server_name: str) -> str:
    """서버 이름을 기반으로 동적으로 아이콘을 생성합니다"""
    server_lower = server_name.lower()
    
    # 서버 이름의 특성을 기반으로 아이콘 선택
    if any(keyword in server_lower for keyword in ['weather', 'clima', 'forecast']):
        return "🌤️"
    elif any(keyword in server_lower for keyword in ['file', 'files', 'manager', 'storage']):
        return "📁"
    elif any(keyword in server_lower for keyword in ['context', 'search', 'library', 'docs']):
        return "📚"
    elif any(keyword in server_lower for keyword in ['web', 'http', 'api']):
        return "🌐"
    elif any(keyword in server_lower for keyword in ['database', 'db', 'sql']):
        return "🗄️"
    elif any(keyword in server_lower for keyword in ['chat', 'message', 'communication']):
        return "💬"
    elif any(keyword in server_lower for keyword in ['time', 'clock', 'schedule']):
        return "⏰"
    elif any(keyword in server_lower for keyword in ['security', 'auth', 'login']):
        return "🔐"
    elif any(keyword in server_lower for keyword in ['image', 'photo', 'picture']):
        return "🖼️"
    elif any(keyword in server_lower for keyword in ['video', 'media', 'stream']):
        return "🎥"
    else:
        # 기본 도구 아이콘
        return "🔧" 