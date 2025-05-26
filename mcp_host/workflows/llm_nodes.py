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

# LLM 인스턴스 (싱글톤 패턴)
_llm_instance = None


def get_llm() -> ChatOpenAI:
    """ChatOpenAI LLM 인스턴스를 반환합니다
    
    환경변수에서 OpenAI API 키를 읽어와 LLM을 초기화합니다.
    싱글톤 패턴으로 인스턴스를 재사용합니다.
    
    Returns:
        ChatOpenAI: 설정된 OpenAI 채팅 모델
        
    Raises:
        ValueError: OPENAI_API_KEY 환경변수가 설정되지 않은 경우
    """
    global _llm_instance
    
    if _llm_instance is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY 환경변수가 설정되지 않았습니다. "
                "OpenAI API 키를 설정해주세요."
            )
        
        _llm_instance = ChatOpenAI(
            model="gpt-4o-mini",  # 빠르고 경제적인 모델
            temperature=0.1,      # 일관된 응답을 위해 낮은 온도
            max_tokens=1000,      # 적절한 응답 길이
        )
        logger.info("OpenAI ChatGPT 모델 초기화 완료")
    
    return _llm_instance


def llm_parse_intent(state: ChatState) -> ChatState:
    """LLM을 사용하여 사용자 의도를 분석합니다
    
    기존의 키워드 매칭 대신 ChatGPT가 자연어로 사용자 의도를 이해합니다.
    더 정확하고 유연한 의도 분석이 가능합니다.
    
    Args:
        state: 현재 워크플로우 상태
        
    Returns:
        의도 분석이 완료된 상태
    """
    try:
        current_message = state.get("current_message")
        if not current_message:
            raise ValueError("현재 메시지가 없습니다")
        
        # 사용자 입력에서 이모지 제거 (UTF-8 인코딩 에러 방지)
        user_input = current_message.content
        # 이모지 제거 정규식
        user_input_clean = re.sub(r'[\U00010000-\U0010ffff]|[\u2600-\u27BF]|[\uD800-\uDBFF][\uDC00-\uDFFF]', '', user_input)
        user_input_clean = user_input_clean.strip()
        
        logger.info(f"LLM 의도 분석 시작: {user_input_clean}")
        
        # LLM을 사용한 의도 분석
        llm = get_llm()
        
        # 의도 분석 프롬프트
        intent_prompt = ChatPromptTemplate.from_messages([
            ("system", """당신은 사용자의 요청을 분석하여 의도를 파악하는 AI입니다.
다음 중 하나의 의도로 분류해주세요:

1. WEATHER_QUERY: 날씨 관련 질문 (현재 날씨, 예보 등)
2. FILE_OPERATION: 파일/디렉토리 작업 (목록 보기, 파일 읽기 등)  
3. SERVER_STATUS: MCP 서버 상태 확인
4. TOOL_LIST: 사용 가능한 도구 목록 요청
5. HELP: 도움말이나 사용법 문의
6. GENERAL_CHAT: 일반적인 대화

응답 형식:
INTENT: [의도]
CONFIDENCE: [0.0-1.0 신뢰도]
PARAMETERS: [추출된 매개변수들, JSON 형식]
REASONING: [분류 근거]

예시:
INTENT: WEATHER_QUERY
CONFIDENCE: 0.95
PARAMETERS: {{"location": "서울", "forecast": true, "days": 3}}
REASONING: 사용자가 서울의 3일 예보를 요청했습니다."""),
            ("human", "{user_input}")
        ])
        
        # LLM 호출
        chain = intent_prompt | llm
        response = chain.invoke({"user_input": user_input_clean})
        response_text = response.content
        
        # 응답 파싱 (원본 user_input 사용)
        parsed_intent = _parse_llm_intent_response(response_text, user_input)
        state["parsed_intent"] = parsed_intent
        
        # 다음 단계 결정
        if parsed_intent.is_mcp_action():
            update_workflow_step(state, "llm_call_mcp_tool")
        else:
            update_workflow_step(state, "llm_generate_response")
        
        logger.info(f"LLM 의도 분석 완료: {parsed_intent.intent_type.value}")
        return state
        
    except Exception as e:
        logger.error(f"LLM 의도 분석 오류: {e}")
        # 실패 시 기존 키워드 방식으로 폴백
        logger.info("키워드 기반 의도 분석으로 폴백")
        update_workflow_step(state, "parse_message")
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
        
        logger.info(f"LLM MCP 도구 호출: {parsed_intent.target_server}.{parsed_intent.target_tool}")
        
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
                            # 서버별 섹션 추가
                            server_icon = "🌤️" if server_name == "weather" else "📁" if server_name == "file-manager" else "🔧"
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
                        server_icon = "🌤️" if server_name == "weather" else "📁" if server_name == "file-manager" else "🔧"
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
        
        for line in lines:
            line = line.strip()
            if line.startswith("INTENT:"):
                intent_type_str = line.replace("INTENT:", "").strip()
            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.replace("CONFIDENCE:", "").strip())
                except ValueError:
                    confidence = 0.5
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
        
        # 대상 서버와 도구 결정
        target_server, target_tool = _determine_target_from_intent(intent_type, parameters)
        
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


def _determine_target_from_intent(intent_type: IntentType, parameters: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """의도와 매개변수로부터 대상 서버와 도구를 결정합니다"""
    if intent_type == IntentType.WEATHER_QUERY:
        if parameters.get('forecast'):
            return 'weather', 'get_forecast'
        else:
            return 'weather', 'get_weather'
    
    elif intent_type == IntentType.FILE_OPERATION:
        operation = parameters.get('operation', 'list')
        tool_map = {
            'list': 'list_files',
            'read': 'read_file', 
            'info': 'file_info'
        }
        return 'file-manager', tool_map.get(operation, 'list_files')
    
    elif intent_type in [IntentType.TOOL_LIST, IntentType.SERVER_STATUS, IntentType.HELP, IntentType.GENERAL_CHAT]:
        # 이러한 요청들은 MCP 도구 호출이 아닌 시스템 정보 제공
        return None, None
    
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
            
            # 매 3개 토큰마다 전송
            if self.token_count % 3 == 0:
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
    """토큰 단위 스트리밍과 함께 LLM 응답 생성 (멀티턴 대화 지원)"""
    try:
        increment_step_count(state)
        logger.info("LLM 스트리밍 응답 생성 시작 (멀티턴 대화 포함)")
        
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
        
        logger.info("스트리밍 응답 생성 진행")
        
        # 일반 LLM 사용 (스트리밍 없이)
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
- 정보가 많을 때는 구조화된 형태로 정리해주세요"""

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
        
        logger.info("LLM 응답 생성 중...")
        # 먼저 전체 응답 생성
        response = await llm.ainvoke(messages)
        generated_response = response.content
        
        logger.info(f"LLM 응답 생성 완료, 길이: {len(generated_response)}")
        logger.info(f"응답 일부: {generated_response[:100]}...")
        
        # 문자 단위 스트리밍으로 변경 (최소 단위)
        current_text = ""
        char_count = 0
        
        logger.info(f"문자 단위 스트리밍 시작, 총 {len(generated_response)}글자")
        
        for i, char in enumerate(generated_response):
            current_text += char
            char_count += 1
            
            # 1-2 글자마다 또는 구두점마다 partial_response 전송 (최소 단위)
            should_send = (
                char_count % 1 == 0 or  # 거의 모든 글자마다 (실시간 효과 극대화)
                char in [' ', '\n', '.', ',', '!', '?', ';', ':', '-', ')', ']', '}'] or  # 구두점이나 공백
                i == len(generated_response) - 1  # 마지막 글자
            )
            
            if should_send:
                # 10글자마다만 로깅 (로그 과부하 방지)
                if i % 10 == 0 or i == len(generated_response) - 1:
                    logger.info(f"partial_response 전송 중... ({i+1}/{len(generated_response)})")
                    
                from ..streaming import create_partial_response_message
                partial_msg = create_partial_response_message(current_text.strip(), session_id)
                
                try:
                    await sse_manager.send_to_session(session_id, partial_msg)
                    # 성공 로그도 간소화
                    if i % 20 == 0 or i == len(generated_response) - 1:
                        logger.info(f"partial_response 전송 성공: {len(current_text.strip())} 글자")
                except Exception as e:
                    logger.error(f"partial_response 전송 실패: {e}")
                
                # 실시간 타이핑 효과를 위한 아주 짧은 지연
                if char in [' ', '\n']:
                    await asyncio.sleep(0.02)  # 공백/줄바꿈 시 짧은 지연
                elif char in ['.', '!', '?']:
                    await asyncio.sleep(0.1)   # 문장 끝 시 약간 긴 지연
                else:
                    await asyncio.sleep(0.01)  # 일반 글자는 극도로 짧은 지연
        
        logger.info("모든 partial_response 전송 완료")
        
        # 최종 응답으로 상태 업데이트
        state["response"] = generated_response
        state["success"] = True
        update_workflow_step(state, "completed")
        
        # 응답을 세션에 저장 (중요!)
        from .state import add_assistant_message
        add_assistant_message(state, generated_response)
        
        # 최종 응답 메시지 전송
        logger.info("final_response 전송 중...")
        from ..streaming import create_final_response_message
        final_msg = create_final_response_message(generated_response, session_id)
        try:
            await sse_manager.send_to_session(session_id, final_msg)
            logger.info("final_response 전송 성공")
        except Exception as e:
            logger.error(f"final_response 전송 실패: {e}")
        
        logger.info("LLM 스트리밍 응답 생성 완료")
        return state
        
    except Exception as e:
        logger.error(f"LLM 스트리밍 응답 생성 오류: {e}")
        import traceback
        logger.error(f"스택 트레이스: {traceback.format_exc()}")
        # 오류 시 기존 방식으로 폴백
        return llm_generate_response(state) 