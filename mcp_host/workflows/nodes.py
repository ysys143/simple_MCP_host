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


def parse_message(state: ChatState) -> ChatState:
    """메시지 파싱 노드: LLM 기반 동적 의도 분석으로 리다이렉트
    
    Args:
        state: 현재 워크플로우 상태
        
    Returns:
        LLM 의도 분석으로 리다이렉트된 상태
    """
    logger = logging.getLogger(__name__)
    
    try:
        # 현재 메시지 확인
        current_message = state.get("current_message")
        if not current_message:
            raise ValueError("현재 메시지가 없습니다")
        
        logger.info(f"LLM 기반 동적 의도 분석으로 리다이렉트: {current_message.content}")
        
        # LLM 의도 분석으로 바로 이동
        update_workflow_step(state, "llm_parse_intent")
        
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
    
    # 세션 ID 가져오기
    session_id = state.get("session_id", "UNKNOWN_WORKFLOW_SESSION")

    try:
        parsed_intent = state.get("parsed_intent")
        if not parsed_intent:
            raise ValueError("파싱된 의도가 없습니다")
        
        logger.info(f"MCP 도구 호출: {parsed_intent.target_server}.{parsed_intent.target_tool}")
        
        # MCP 클라이언트에서 도구 스키마 확인 및 매개변수 검증
        mcp_client = state.get("mcp_client")
        if not mcp_client:
            raise ValueError("MCP 클라이언트가 없습니다")
        
        # 도구 스키마 기반 매개변수 검증 및 보정
        validated_parameters = await _validate_and_correct_parameters(
            mcp_client, 
            parsed_intent.target_tool, 
            parsed_intent.parameters
        )
        
        # 서버명이 없는 경우 도구명으로 자동 추론
        target_server = parsed_intent.target_server
        if not target_server:
            # MCP 클라이언트에서 도구명으로 서버 찾기
            target_server = _find_server_for_tool(mcp_client, parsed_intent.target_tool)
            if not target_server:
                raise ValueError(f"도구 '{parsed_intent.target_tool}'에 대한 서버를 찾을 수 없습니다")
        
        # 도구 호출 객체 생성 (검증된 매개변수 사용)
        tool_call = MCPToolCall(
            server_name=target_server,
            tool_name=parsed_intent.target_tool,
            arguments=validated_parameters
        )
        
        # 실제 MCP 클라이언트를 통한 도구 호출
        if hasattr(mcp_client, 'call_tool'):
            try:
                start_time = datetime.now()
                
                # 비동기 호출
                result = await mcp_client.call_tool(
                    server_name=target_server,
                    tool_name=parsed_intent.target_tool,
                    arguments=validated_parameters,
                    session_id=session_id
                )
                
                end_time = datetime.now()
                
                tool_call.result = str(result)
                tool_call.execution_time_ms = int((end_time - start_time).total_seconds() * 1000)
                
                logger.info(f"실제 MCP 도구 호출 성공: {tool_call.tool_name}")
                
            except Exception as e:
                logger.warning(f"MCP 도구 호출 실패: {e}")
                tool_call.error = str(e)
                tool_call.execution_time_ms = 0
        else:
            # MCP 클라이언트가 없는 경우
            logger.warning("MCP 클라이언트가 없습니다")
            tool_call.error = "MCP 클라이언트가 초기화되지 않았습니다"
            tool_call.execution_time_ms = 0
        
        # tool_calls 리스트에 추가 (LLM이 참조할 수 있도록)
        if "tool_calls" not in state:
            state["tool_calls"] = []
        state["tool_calls"].append(tool_call)
        
        # 다음 단계로 (LLM 응답 생성)
        update_workflow_step(state, "llm_generate_response")
        
        logger.info(f"MCP 도구 호출 완료: {tool_call.tool_name}")
        return state
        
    except Exception as e:
        logger.error(f"MCP 도구 호출 오류: {e}")
        set_error(state, f"도구 호출 실패: {e}")
        return state


def _find_server_for_tool(mcp_client, tool_name: str) -> Optional[str]:
    """MCP 클라이언트에서 도구명으로 해당 서버를 찾습니다"""
    logger = logging.getLogger(__name__)
    
    try:
        # 모든 서버에서 도구 검색
        server_names = mcp_client.get_server_names()
        
        for server_name in server_names:
            try:
                # 각 서버의 도구 목록 확인
                tools = mcp_client.get_tools_for_server(server_name)
                for tool in tools:
                    if getattr(tool, 'name', '') == tool_name:
                        logger.info(f"도구 '{tool_name}'을 서버 '{server_name}'에서 발견")
                        return server_name
            except Exception as e:
                logger.debug(f"서버 '{server_name}'에서 도구 검색 실패: {e}")
                continue
        
        logger.warning(f"도구 '{tool_name}'을 어떤 서버에서도 찾을 수 없습니다")
        return None
        
    except Exception as e:
        logger.error(f"서버 검색 중 오류: {e}")
        return None


async def _validate_and_correct_parameters(mcp_client, tool_name: str, llm_parameters: Dict[str, Any]) -> Dict[str, Any]:
    """도구 스키마를 기반으로 LLM이 제공한 매개변수를 검증하고 보정합니다"""
    logger = logging.getLogger(__name__)
    
    try:
        # 사용 가능한 도구에서 해당 도구 찾기
        tools = mcp_client.get_tools()
        tool_schema = None
        
        for tool in tools:
            if getattr(tool, 'name', '') == tool_name:
                tool_schema = tool
                break
        
        if not tool_schema:
            logger.warning(f"도구 '{tool_name}' 스키마를 찾을 수 없습니다. 원본 매개변수 사용")
            return llm_parameters
        
        # 스키마에서 예상되는 필드 추출 (Pydantic v1/v2 호환)
        expected_fields = []
        input_schema = getattr(tool_schema, 'args_schema', None)
        
        if input_schema:
            # Pydantic v1 호환성
            if hasattr(input_schema, '__fields__'):
                expected_fields = list(input_schema.__fields__.keys())
            # Pydantic v2 호환성
            elif hasattr(input_schema, 'model_fields'):
                expected_fields = list(input_schema.model_fields.keys())
        
        # 도구 이름 기반 추론 (스키마가 없는 경우)
        if not expected_fields:
            if 'weather' in tool_name.lower() or 'forecast' in tool_name.lower():
                expected_fields = ['location']
            elif 'file' in tool_name.lower():
                expected_fields = ['filename']
            elif any(keyword in tool_name.lower() for keyword in ['search', 'resolve', 'library']):
                expected_fields = ['libraryName']
            else:
                expected_fields = ['input']  # 기본값
        
        if not expected_fields:
            logger.debug(f"도구 '{tool_name}'의 스키마 필드를 찾을 수 없습니다. 원본 매개변수 사용")
            return llm_parameters
        
        # LLM 매개변수를 스키마에 맞게 매핑
        corrected_parameters = {}
        
        # 1. 정확히 일치하는 필드들 먼저 매핑
        for field in expected_fields:
            if field in llm_parameters:
                corrected_parameters[field] = llm_parameters[field]
        
        # 2. 일치하지 않는 LLM 매개변수들을 스키마 필드에 매핑 시도
        used_llm_keys = set(corrected_parameters.keys())
        remaining_llm_params = {k: v for k, v in llm_parameters.items() if k not in used_llm_keys}
        remaining_schema_fields = [f for f in expected_fields if f not in corrected_parameters]
        
        # 남은 매개변수들을 순서대로 매핑
        for i, (llm_key, llm_value) in enumerate(remaining_llm_params.items()):
            if i < len(remaining_schema_fields):
                schema_field = remaining_schema_fields[i]
                corrected_parameters[schema_field] = llm_value
                logger.debug(f"매개변수 매핑: {llm_key} -> {schema_field}")
        
        # 3. 여전히 비어있는 필수 필드가 있다면 LLM 매개변수의 첫 번째 값으로 채움
        if remaining_schema_fields and llm_parameters:
            first_value = list(llm_parameters.values())[0]
            
            # 값 정리 (이중 인코딩 제거)
            if isinstance(first_value, str):
                # "\"부산\"" -> "부산" 변환
                first_value = first_value.strip('"').strip("'").strip()
                if first_value.startswith('\\"') and first_value.endswith('\\"'):
                    first_value = first_value[2:-2]
            
            for field in remaining_schema_fields:
                if field not in corrected_parameters:
                    corrected_parameters[field] = first_value
                    logger.debug(f"기본값 매핑: {field} = {first_value}")
        
        logger.info(f"매개변수 검증 완료: {llm_parameters} -> {corrected_parameters}")
        return corrected_parameters
        
    except Exception as e:
        logger.warning(f"매개변수 검증 실패: {e}. 원본 매개변수 사용")
        return llm_parameters


def generate_response(state: ChatState) -> ChatState:
    """응답 생성 노드: LLM 기반 응답 생성으로 리다이렉트
    
    Args:
        state: 현재 워크플로우 상태
        
    Returns:
        LLM 응답 생성으로 리다이렉트된 상태
    """
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("LLM 기반 응답 생성으로 리다이렉트")
        
        # LLM 응답 생성으로 바로 이동
        update_workflow_step(state, "llm_generate_response")
        
        return state
        
    except Exception as e:
        logger.error(f"응답 생성 오류: {e}")
        set_error(state, f"응답 생성 실패: {e}")
        return state 