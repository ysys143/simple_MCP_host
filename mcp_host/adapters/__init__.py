"""
langchain-mcp-adapters 통합 모듈

기존의 설정 시스템과 langchain-mcp-adapters를 통합하여
더 간단하고 표준화된 MCP 클라이언트를 제공합니다.
"""

from .client import MCPClient

__all__ = ["MCPClient"] 