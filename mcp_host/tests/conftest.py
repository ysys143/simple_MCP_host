"""pytest 설정 파일

테스트 환경 설정과 공통 픽스처를 제공합니다.
"""

import sys
from pathlib import Path
import pytest
import asyncio
from unittest.mock import AsyncMock

# 프로젝트 루트를 Python 경로에 추가 (pytest용)
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from mcp_host.config import create_config_manager


# pytest-asyncio 설정
pytest_plugins = ('pytest_asyncio',)


@pytest.fixture(scope="session")
def event_loop():
    """세션 스코프 이벤트 루프"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def config_manager():
    """설정 관리자 픽스처"""
    return create_config_manager()


@pytest.fixture  
def sample_context():
    """테스트용 컨텍스트 픽스처"""
    return {
        "available_servers": ["weather", "file-manager"],
        "available_tools": {
            "weather": ["get_weather", "get_forecast"],
            "file-manager": ["list_files", "read_file", "file_info"]
        }
    }


@pytest.fixture
def mock_client():
    """향상된 MCP 클라이언트 모킹 픽스처"""
    mock_client = AsyncMock()
    mock_client.get_tools.return_value = [
        {"name": "get_weather", "description": "현재 날씨 조회"},
        {"name": "get_forecast", "description": "날씨 예보 조회"},
        {"name": "list_files", "description": "파일 목록 조회"},
        {"name": "read_file", "description": "파일 내용 읽기"},
        {"name": "file_info", "description": "파일 정보 조회"}
    ]
    mock_client.get_tool_names.return_value = [
        "get_weather", "get_forecast", "list_files", "read_file", "file_info"
    ]
    mock_client.get_server_names.return_value = ["weather", "file-manager"]
    mock_client.get_server_count.return_value = 2
    return mock_client


@pytest.fixture
def test_messages():
    """테스트용 메시지 모음"""
    return {
        "weather": [
            "서울 날씨 어때요?",
            "부산 3일 예보",
            "오늘 비 와요?",
            "내일 날씨 알려줘"
        ],
        "file": [
            "파일 목록 보여줘",
            "현재 디렉토리 파일들",
            "README.md 내용 보여줘",
            "파일 정보 알려줘"
        ],
        "general": [
            "안녕하세요",
            "반갑습니다",
            "어떻게 지내세요?",
            "좋은 하루입니다"
        ],
        "help": [
            "도움말",
            "사용법 알려줘",
            "뭘 할 수 있어요?",
            "명령어 목록"
        ]
    } 