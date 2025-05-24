"""키워드 기반 워크플로우 테스트

LLM 없이 키워드 기반 시스템만으로 동작을 확인하는 테스트입니다.
OpenAI API 키가 없어도 실행 가능합니다.
"""

import pytest
from unittest.mock import Mock, AsyncMock
from mcp_host.workflows.nodes import parse_message, call_mcp_tool, generate_response
from mcp_host.models import ChatState, IntentType, ParsedIntent
from langchain_core.messages import BaseMessage


@pytest.mark.asyncio
async def test_keyword_parse_message():
    """키워드 기반 메시지 파싱 테스트"""
    # 날씨 요청 테스트
    state = ChatState(
        current_message=BaseMessage(content="서울 날씨 알려줘", type="human"),
        session_id="test",
        context={},
        messages=[],
        tool_calls=[],
        tool_results=[],
        response="",
        success=False,
        error=None,
        step_count=0,
        next_step=None
    )
    
    result = parse_message(state)
    
    assert result["parsed_intent"] is not None
    assert result["parsed_intent"].intent_type == IntentType.WEATHER_QUERY
    assert "서울" in str(result["parsed_intent"].parameters).lower()


@pytest.mark.asyncio
async def test_keyword_file_operation():
    """키워드 기반 파일 작업 테스트"""
    state = ChatState(
        current_message=BaseMessage(content="파일 목록 보여줘", type="human"),
        session_id="test",
        context={},
        messages=[],
        tool_calls=[],
        tool_results=[],
        response="",
        success=False,
        error=None,
        step_count=0,
        next_step=None
    )
    
    result = parse_message(state)
    
    assert result["parsed_intent"] is not None
    assert result["parsed_intent"].intent_type == IntentType.FILE_OPERATION
    

@pytest.mark.asyncio
async def test_keyword_general_chat():
    """키워드 기반 일반 대화 테스트"""
    state = ChatState(
        current_message=BaseMessage(content="안녕하세요", type="human"),
        session_id="test",
        context={},
        messages=[],
        tool_calls=[],
        tool_results=[],
        response="",
        success=False,
        error=None,
        step_count=0,
        next_step=None
    )
    
    result = parse_message(state)
    
    assert result["parsed_intent"] is not None
    assert result["parsed_intent"].intent_type == IntentType.GENERAL_CHAT


@pytest.mark.asyncio
async def test_keyword_response_generation():
    """키워드 기반 응답 생성 테스트"""
    # 일반 대화에 대한 응답 생성
    state = ChatState(
        current_message=BaseMessage(content="안녕하세요", type="human"),
        session_id="test",
        context={},
        messages=[],
        parsed_intent=ParsedIntent(
            intent_type=IntentType.GENERAL_CHAT,
            confidence=0.8,
            parameters={},
            target_server=None,
            target_tool=None
        ),
        tool_calls=[],
        tool_results=[],
        response="",
        success=False,
        error=None,
        step_count=0,
        next_step=None
    )
    
    result = generate_response(state)
    
    assert result["success"] is True
    assert result["response"] != ""
    assert "안녕" in result["response"]


@pytest.mark.asyncio
async def test_keyword_with_mocked_mcp_tool():
    """모킹된 MCP 도구와 함께 키워드 기반 테스트"""
    # Mock MCP client
    mock_client = Mock()
    mock_client.call_tool = AsyncMock(return_value={
        "result": "서울의 현재 날씨는 맑음이며 기온은 22도입니다."
    })
    
    state = ChatState(
        current_message=BaseMessage(content="서울 날씨", type="human"),
        session_id="test",
        context={},
        mcp_client=mock_client,
        messages=[],
        parsed_intent=ParsedIntent(
            intent_type=IntentType.WEATHER_QUERY,
            confidence=0.9,
            parameters={"location": "서울"},
            target_server="weather",
            target_tool="get_weather"
        ),
        tool_calls=[],
        tool_results=[],
        response="",
        success=False,
        error=None,
        step_count=0,
        next_step=None
    )
    
    # 도구 호출 테스트
    tool_result = await call_mcp_tool(state)
    
    # tool_calls에 추가되었는지 확인
    assert len(tool_result["tool_calls"]) > 0
    assert tool_result["tool_calls"][0].server_name == "weather"
    assert tool_result["tool_calls"][0].tool_name == "get_weather"
    
    # 응답 생성 테스트
    response_result = generate_response(tool_result)
    
    assert response_result["success"] is True
    assert response_result["response"] != ""


if __name__ == "__main__":
    import asyncio
    
    async def run_tests():
        print("🧪 키워드 기반 워크플로우 테스트 실행")
        
        # 개별 테스트 실행
        await test_keyword_parse_message()
        print("✅ 키워드 메시지 파싱 테스트 통과")
        
        await test_keyword_file_operation()
        print("✅ 키워드 파일 작업 테스트 통과")
        
        await test_keyword_general_chat()
        print("✅ 키워드 일반 대화 테스트 통과")
        
        await test_keyword_response_generation()
        print("✅ 키워드 응답 생성 테스트 통과")
        
        await test_keyword_with_mocked_mcp_tool()
        print("✅ 키워드 MCP 도구 호출 테스트 통과")
        
        print("🎉 모든 키워드 기반 테스트 완료!")
    
    asyncio.run(run_tests()) 