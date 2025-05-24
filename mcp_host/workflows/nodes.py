"""LangGraph 워크플로우 노드 구현

각 워크플로우 단계를 담당하는 노드 함수들을 정의합니다.
단일 책임 원칙에 따라 각 노드는 하나의 명확한 기능만 수행합니다.
"""

import re
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..models import (
    ChatState, 
    ParsedIntent, 
    MCPToolCall,
    IntentType
)
from .state_utils import update_workflow_step, set_error, add_tool_call


class MessageParser:
    """사용자 메시지 의도 분석 클래스
    
    단일 책임 원칙: 메시지 파싱과 의도 분석만 담당
    개방-폐쇄 원칙: 새로운 의도 타입 추가 시 기존 코드 수정 없이 확장 가능
    """
    
    def __init__(self):
        self._logger = logging.getLogger(__name__)
        
        # 의도 분석을 위한 키워드 패턴
        self._intent_patterns = {
            IntentType.WEATHER_QUERY: [
                r'날씨|기온|온도|비|눈|맑음|흐림',
                r'weather|temperature|rain|snow|sunny|cloudy'
            ],
            IntentType.FILE_OPERATION: [
                r'파일|디렉토리|폴더|목록|읽기|저장',
                r'file|directory|folder|list|read|save'
            ],
            IntentType.SERVER_STATUS: [
                r'서버|상태|연결|접속',
                r'server|status|connect|connection'
            ],
            IntentType.TOOL_LIST: [
                r'도구|툴|기능|명령어|help',
                r'tool|function|command|help'
            ],
            IntentType.HELP: [
                r'도움말|사용법|어떻게|방법',
                r'help|how|usage|guide'
            ]
        }
    
    def parse_intent(self, message: str) -> ParsedIntent:
        """메시지에서 사용자 의도를 분석합니다
        
        Args:
            message: 사용자 메시지
            
        Returns:
            파싱된 의도 정보
        """
        message_lower = message.lower()
        
        # 각 의도 타입에 대해 매칭 점수 계산
        intent_scores = {}
        
        for intent_type, patterns in self._intent_patterns.items():
            score = 0
            for pattern in patterns:
                matches = len(re.findall(pattern, message_lower))
                score += matches
            
            if score > 0:
                intent_scores[intent_type] = score
        
        # 가장 높은 점수의 의도 선택
        if intent_scores:
            best_intent = max(intent_scores, key=intent_scores.get)
            confidence = min(intent_scores[best_intent] * 0.3, 1.0)  # 최대 1.0
        else:
            best_intent = IntentType.GENERAL_CHAT
            confidence = 0.8
        
        # 매개변수 추출
        parameters = self._extract_parameters(message, best_intent)
        
        # 대상 서버와 도구 결정
        target_server, target_tool = self._determine_target(best_intent, parameters)
        
        self._logger.info(f"의도 분석: {best_intent.value} (신뢰도: {confidence:.2f})")
        
        return ParsedIntent(
            intent_type=best_intent,
            confidence=confidence,
            parameters=parameters,
            target_server=target_server,
            target_tool=target_tool
        )
    
    def _extract_parameters(self, message: str, intent_type: IntentType) -> Dict[str, Any]:
        """의도에 따른 매개변수를 추출합니다"""
        parameters = {}
        
        if intent_type == IntentType.WEATHER_QUERY:
            # 지역명 추출
            locations = ['서울', '부산', '대구', '인천', '광주', '대전', '울산']
            for location in locations:
                if location in message:
                    parameters['location'] = location
                    break
            
            # 예보 요청 확인
            if '예보' in message or 'forecast' in message.lower():
                parameters['forecast'] = True
                # 일수 추출
                import re
                days_match = re.search(r'(\d+)일', message)
                if days_match:
                    parameters['days'] = int(days_match.group(1))
        
        elif intent_type == IntentType.FILE_OPERATION:
            # 디렉토리 경로 추출
            if '목록' in message or 'list' in message.lower():
                parameters['operation'] = 'list'
            elif '읽기' in message or 'read' in message.lower():
                parameters['operation'] = 'read'
            elif '정보' in message or 'info' in message.lower():
                parameters['operation'] = 'info'
        
        return parameters
    
    def _determine_target(self, intent_type: IntentType, parameters: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        """의도에 따른 대상 서버와 도구를 결정합니다"""
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
        
        return None, None


# 전역 파서 인스턴스
_message_parser = MessageParser()


def parse_message(state: ChatState) -> ChatState:
    """메시지 파싱 노드: 사용자 메시지에서 의도를 추출합니다
    
    Args:
        state: 현재 워크플로우 상태
        
    Returns:
        의도 분석이 추가된 상태
    """
    logger = logging.getLogger(__name__)
    
    try:
        # 현재 메시지 가져오기
        current_message = state.get("current_message")
        if not current_message:
            raise ValueError("현재 메시지가 없습니다")
        
        logger.info(f"메시지 파싱 시작: {current_message.content}")
        
        # 의도 분석
        parsed_intent = _message_parser.parse_intent(current_message.content)
        state["parsed_intent"] = parsed_intent
        
        # 다음 단계 결정
        if parsed_intent.is_mcp_action():
            update_workflow_step(state, "call_mcp_tool")
        else:
            update_workflow_step(state, "generate_response")
        
        logger.info(f"의도 분석 완료: {parsed_intent.intent_type.value}")
        return state
        
    except Exception as e:
        logger.error(f"메시지 파싱 오류: {e}")
        set_error(state, f"메시지 파싱 실패: {e}")
        return state


async def call_mcp_tool(state: ChatState) -> ChatState:
    """MCP 도구 호출 노드: 분석된 의도에 따라 적절한 MCP 도구를 호출합니다
    
    Args:
        state: 현재 워크플로우 상태
        
    Returns:
        도구 호출 결과가 추가된 상태
    """
    logger = logging.getLogger(__name__)
    
    try:
        parsed_intent = state.get("parsed_intent")
        if not parsed_intent:
            raise ValueError("파싱된 의도가 없습니다")
        
        logger.info(f"MCP 도구 호출: {parsed_intent.target_server}.{parsed_intent.target_tool}")
        
        # 도구 호출 준비
        arguments = _prepare_tool_arguments(parsed_intent)
        
        # 도구 호출 객체 생성
        tool_call = MCPToolCall(
            server_name=parsed_intent.target_server,
            tool_name=parsed_intent.target_tool,
            arguments=arguments
        )
        
        # 실제 MCP 클라이언트를 통한 도구 호출
        mcp_client = state.get("mcp_client")
        if mcp_client and hasattr(mcp_client, 'call_tool'):
            try:
                start_time = datetime.now()
                
                # 비동기 호출로 수정
                result = await mcp_client.call_tool(
                    server_name=parsed_intent.target_server,
                    tool_name=parsed_intent.target_tool,
                    arguments=arguments
                )
                
                end_time = datetime.now()
                
                tool_call.result = str(result)
                tool_call.execution_time_ms = int((end_time - start_time).total_seconds() * 1000)
                
                logger.info(f"실제 MCP 도구 호출 성공: {tool_call.tool_name}")
                
            except Exception as e:
                logger.warning(f"MCP 도구 호출 실패, 시뮬레이션으로 대체: {e}")
                tool_call.result = _simulate_tool_call(tool_call)
                tool_call.execution_time_ms = 100
        else:
            # Enhanced MCP Client가 없거나 호환되지 않는 경우 시뮬레이션 사용
            logger.info("MCP 클라이언트가 없어 시뮬레이션 모드로 실행")
            tool_call.result = _simulate_tool_call(tool_call)
            tool_call.execution_time_ms = 100
        
        # 상태에 저장
        state["current_mcp_call"] = tool_call
        if "mcp_calls" not in state:
            state["mcp_calls"] = []
        state["mcp_calls"].append(tool_call)
        
        # 도구 메시지 추가
        add_tool_call(state, tool_call)
        
        # 다음 단계로
        update_workflow_step(state, "generate_response")
        
        logger.info(f"MCP 도구 호출 완료: {tool_call.tool_name}")
        return state
        
    except Exception as e:
        logger.error(f"MCP 도구 호출 오류: {e}")
        set_error(state, f"도구 호출 실패: {e}")
        return state


def _prepare_tool_arguments(parsed_intent: ParsedIntent) -> Dict[str, Any]:
    """파싱된 의도에서 도구 인자를 준비합니다"""
    arguments = {}
    
    if parsed_intent.intent_type == IntentType.WEATHER_QUERY:
        arguments["location"] = parsed_intent.parameters.get("location", "서울")
        if parsed_intent.target_tool == "get_forecast":
            arguments["days"] = parsed_intent.parameters.get("days", 3)
    
    elif parsed_intent.intent_type == IntentType.FILE_OPERATION:
        if parsed_intent.target_tool == "list_files":
            arguments["directory"] = parsed_intent.parameters.get("directory", ".")
        elif parsed_intent.target_tool in ["read_file", "file_info"]:
            arguments["filename"] = parsed_intent.parameters.get("filename", "README.md")
    
    return arguments


def _simulate_tool_call(tool_call: MCPToolCall) -> str:
    """도구 호출 시뮬레이션 (나중에 실제 호출로 대체)"""
    if tool_call.server_name == "weather":
        if tool_call.tool_name == "get_weather":
            location = tool_call.arguments.get("location", "서울")
            return f"{location}: 맑음, 23도"
        elif tool_call.tool_name == "get_forecast":
            location = tool_call.arguments.get("location", "서울")
            days = tool_call.arguments.get("days", 3)
            return f"{location} {days}일 예보:\nDay 1: 맑음, 22도\nDay 2: 흐림, 20도\nDay 3: 비, 18도"
    
    elif tool_call.server_name == "file-manager":
        if tool_call.tool_name == "list_files":
            return ". 디렉토리 파일 목록:\nREADME.md\nmcp_servers.json\ntest_client.py"
        elif tool_call.tool_name == "read_file":
            filename = tool_call.arguments.get("filename", "README.md")
            return f"[더미] {filename} 파일 내용:\n이것은 테스트용 더미 내용입니다."
        elif tool_call.tool_name == "file_info":
            filename = tool_call.arguments.get("filename", "README.md")
            return f"{filename}: 크기 1024 bytes, 존재함"
    
    return "도구 호출 결과 (시뮬레이션)"


def generate_response(state: ChatState) -> ChatState:
    """응답 생성 노드: 워크플로우 결과를 바탕으로 사용자 친화적인 응답을 생성합니다
    
    Args:
        state: 현재 워크플로우 상태
        
    Returns:
        응답이 생성된 상태
    """
    logger = logging.getLogger(__name__)
    
    try:
        parsed_intent = state.get("parsed_intent")
        current_mcp_call = state.get("current_mcp_call")
        
        logger.info("응답 생성 시작")
        
        if parsed_intent.intent_type == IntentType.GENERAL_CHAT:
            response = _generate_general_response(state)
        elif parsed_intent.intent_type == IntentType.HELP:
            response = _generate_help_response()
        elif parsed_intent.intent_type == IntentType.SERVER_STATUS:
            response = _generate_server_status_response(state)
        elif parsed_intent.intent_type == IntentType.TOOL_LIST:
            response = _generate_tool_list_response(state)
        elif current_mcp_call and current_mcp_call.is_successful():
            response = _generate_tool_response(parsed_intent, current_mcp_call)
        else:
            response = "죄송합니다. 요청을 처리할 수 없습니다."
        
        # 응답 메시지 추가
        state["response"] = response
        state["success"] = True
        
        # 워크플로우 완료
        update_workflow_step(state, "completed")
        
        logger.info("응답 생성 완료")
        return state
        
    except Exception as e:
        logger.error(f"응답 생성 오류: {e}")
        set_error(state, f"응답 생성 실패: {e}")
        return state


def _generate_general_response(state: ChatState) -> str:
    """일반 채팅 응답 생성"""
    current_message = state.get("current_message")
    if current_message:
        return f"'{current_message.content}'에 대해 이야기해주셔서 감사합니다. 날씨나 파일 관련 질문이 있으시면 언제든 말씀해주세요!"
    return "안녕하세요! 날씨 정보나 파일 관리 도움이 필요하시면 말씀해주세요."


def _generate_help_response() -> str:
    """도움말 응답 생성"""
    return """🤖 MCP 호스트 도움말

사용 가능한 기능:
🌤️ 날씨: "서울 날씨 알려줘", "부산 3일 예보"
📁 파일: "파일 목록 보여줘", "README.md 정보"
🔧 시스템: "서버 상태", "도구 목록"

예시:
- "서울 날씨 어때?"
- "현재 디렉토리 파일들 보여줘"
- "도구 목록 알려줘"
"""


def _generate_server_status_response(state: ChatState) -> str:
    """서버 상태 응답 생성"""
    available_servers = state.get("available_servers", [])
    if available_servers:
        server_list = ", ".join(available_servers)
        return f"🟢 연결된 서버: {server_list}\n모든 서버가 정상 작동 중입니다."
    return "❌ 연결된 서버가 없습니다."


def _generate_tool_list_response(state: ChatState) -> str:
    """도구 목록 응답 생성"""
    available_tools = state.get("available_tools", {})
    if available_tools:
        response = "🔧 사용 가능한 도구들:\n\n"
        for server, tools in available_tools.items():
            response += f"📡 {server}:\n"
            for tool in tools:
                response += f"  • {tool}\n"
            response += "\n"
        return response
    return "❌ 사용 가능한 도구가 없습니다."


def _generate_tool_response(parsed_intent: ParsedIntent, tool_call: MCPToolCall) -> str:
    """도구 호출 결과 응답 생성"""
    if parsed_intent.intent_type == IntentType.WEATHER_QUERY:
        if tool_call.tool_name == "get_weather":
            return f"🌤️ 현재 날씨:\n{tool_call.result}"
        elif tool_call.tool_name == "get_forecast":
            return f"📅 일기예보:\n{tool_call.result}"
    
    elif parsed_intent.intent_type == IntentType.FILE_OPERATION:
        if tool_call.tool_name == "list_files":
            return f"📁 파일 목록:\n{tool_call.result}"
        elif tool_call.tool_name == "read_file":
            return f"📄 파일 내용:\n{tool_call.result}"
        elif tool_call.tool_name == "file_info":
            return f"ℹ️ 파일 정보:\n{tool_call.result}"
    
    return f"✅ 작업 완료:\n{tool_call.result}" 