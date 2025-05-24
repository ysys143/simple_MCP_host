"""pytest 스타일 워크플로우 테스트

pytest-asyncio를 사용한 비동기 워크플로우 테스트 예시입니다.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from mcp_host.workflows import create_workflow_executor, IntentType


@pytest.mark.asyncio
class TestMCPWorkflow:
    """MCP 워크플로우 테스트 클래스"""
    
    async def test_workflow_executor_creation(self):
        """워크플로우 실행기 생성 테스트"""
        executor = create_workflow_executor()
        assert executor is not None
        
    @pytest.mark.parametrize("message,expected_intent", [
        ("안녕하세요", "general_chat"),
        ("서울 날씨 알려줘", "weather_query"),
        ("파일 목록 보여줘", "file_operation"),
        ("도움말", "help")
    ])
    async def test_intent_classification(self, message, expected_intent, sample_context):
        """의도 분류 테스트"""
        executor = create_workflow_executor()
        
        result = await executor.execute_message(
            user_message=message,
            session_id="test_session",
            context=sample_context
        )
        
        assert result["success"] is True
        # 의도 타입은 문자열로 반환되므로 문자열 비교
        assert expected_intent in result["intent_type"].lower()
        
    async def test_weather_query_with_tool_call(self, sample_context):
        """날씨 조회 시 도구 호출 테스트"""
        executor = create_workflow_executor()
        
        result = await executor.execute_message(
            user_message="서울 날씨 알려줘",
            session_id="weather_test",
            context=sample_context
        )
        
        assert result["success"] is True
        assert "weather" in result["intent_type"].lower()
        # 도구 호출이 시뮬레이션되었는지 확인
        assert len(result["tool_calls"]) > 0
        
    async def test_file_operation_with_tool_call(self, sample_context):
        """파일 작업 시 도구 호출 테스트"""
        executor = create_workflow_executor()
        
        result = await executor.execute_message(
            user_message="파일 목록 보여줘",
            session_id="file_test",
            context=sample_context
        )
        
        assert result["success"] is True
        assert "file" in result["intent_type"].lower()
        assert len(result["tool_calls"]) > 0
        
    async def test_empty_message_handling(self, sample_context):
        """빈 메시지 처리 테스트"""
        executor = create_workflow_executor()
        
        result = await executor.execute_message(
            user_message="",
            session_id="empty_test",
            context=sample_context
        )
        
        # 빈 메시지도 적절히 처리되어야 함
        assert result["success"] is True
        assert len(result["response"]) > 0  # 응답이 있어야 함
        
    async def test_conversation_history(self, sample_context):
        """대화 기록 누적 테스트"""
        executor = create_workflow_executor()
        session_id = "history_test"
        
        # 첫 번째 메시지
        result1 = await executor.execute_message(
            user_message="안녕하세요",
            session_id=session_id,
            context=sample_context
        )
        
        # 두 번째 메시지
        result2 = await executor.execute_message(
            user_message="날씨 어때요?",
            session_id=session_id,
            context=sample_context
        )
        
        # 대화 기록이 누적되는지 확인
        assert len(result2["conversation_history"]) >= 2
        
    @pytest.fixture
    def mock_mcp_client(self):
        """MCP 클라이언트 모킹 픽스처"""
        mock_client = AsyncMock()
        mock_client.get_tools.return_value = [
            {"name": "get_weather", "description": "날씨 조회"},
            {"name": "list_files", "description": "파일 목록"}
        ]
        return mock_client
        
    async def test_with_mocked_client(self, mock_mcp_client, sample_context):
        """모킹된 MCP 클라이언트와 함께 테스트"""
        executor = create_workflow_executor()
        
        result = await executor.execute_message(
            user_message="서울 날씨",
            session_id="mock_test",
            context=sample_context,
            mcp_client=mock_mcp_client
        )
        
        assert result["success"] is True 