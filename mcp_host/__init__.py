"""
LangGraph MCP 호스트 구현

이 패키지는 Model Context Protocol(MCP)을 LangGraph와 통합하여
AI 모델이 외부 리소스와 안전하게 상호작용할 수 있도록 하는
호스트 시스템을 제공합니다.
"""

__version__ = "1.0.0"
__author__ = "MCP Host Team"

# 현재 구현된 모듈들 import
from .config import MCPHostSettings, get_settings, MCPConfigManager, create_config_manager
from .adapters import MCPClient
from .workflows import create_workflow_executor
from .models import ChatState, IntentType, ParsedIntent, MCPToolCall, MessageRole, ChatMessage

# TODO: 다음 단계에서 구현 예정
# from .protocols import MCPProtocol
# from .services import MCPHostService
# from .workflows import MCPWorkflow

__all__ = [
    # 환경변수 설정 관리
    "MCPHostSettings",
    "get_settings",
    # MCP 서버 설정 관리
    "MCPConfigManager",
    "create_config_manager",
    # 클라이언트 관리
    "MCPClient",
    # TODO: 다음 단계에서 추가
    # "MCPProtocol",
    # "MCPHostService", 
    # "MCPWorkflow",
    'create_workflow_executor',
    'ChatState',
    'IntentType', 
    'ParsedIntent',
    'MCPToolCall',
    'MessageRole',
    'ChatMessage'
] 