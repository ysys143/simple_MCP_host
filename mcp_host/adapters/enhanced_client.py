"""향상된 MCP 클라이언트

langchain-mcp-adapters를 활용하여 실제 MCP 서버 연결을 제공합니다.
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

# main.py에서 설정한 json_rpc 로거를 이름으로 가져옵니다.
json_rpc_logger = logging.getLogger('json_rpc')


class EnhancedMCPClient:
    """langchain-mcp-adapters 기반 향상된 MCP 클라이언트
    
    MultiServerMCPClient를 사용하여 실제 MCP 서버들과 연결하고
    도구를 관리합니다.
    
    단일 책임 원칙: MCP 서버들과의 연결 및 도구 관리만 담당
    개방-폐쇄 원칙: 새로운 서버 유형 추가 시 기존 코드 수정 없이 확장 가능
    """
    
    def __init__(self):
        """클라이언트 초기화"""
        self._client: Optional[MultiServerMCPClient] = None
        self._tools: List[Any] = []
        self._tools_dict: Dict[str, Any] = {}  # 도구 이름으로 빠른 검색
        self._logger = logging.getLogger(__name__)
        self._server_config: Dict[str, Dict[str, Any]] = {}
    
    async def initialize(self, config_path: str) -> None:
        """클라이언트 초기화 및 서버 연결
        
        Args:
            config_path: 서버 설정 파일 경로 (JSON)
        """
        try:
            # JSON 설정 파일 직접 로드
            with open(config_path, 'r', encoding='utf-8') as f:
                self._server_config = json.load(f)
            
            self._logger.info(f"서버 설정 로드됨: {list(self._server_config.keys())}")
            
            # MultiServerMCPClient 생성
            self._client = MultiServerMCPClient(self._server_config)
            
            # 도구 로드 (올바른 방법 사용)
            await self._load_tools()
            
            self._logger.info(f"Enhanced MCP Client 초기화 완료: {len(self._tools)}개 도구 로드됨")
            
        except Exception as e:
            self._logger.error(f"클라이언트 초기화 실패: {e}")
            raise
    
    async def _load_tools(self) -> None:
        """MCP 서버들로부터 도구 로드 (client.get_tools() 사용)"""
        try:
            if not self._client:
                raise ValueError("클라이언트가 초기화되지 않음")
            
            # MultiServerMCPClient.get_tools() 호출
            self._tools = await self._client.get_tools()
            
            # 도구 딕셔너리 생성 (빠른 검색용)
            self._tools_dict = {tool.name: tool for tool in self._tools}
            
            self._logger.info(f"실제 도구 로드 완료: {len(self._tools)}개")
            
            # 도구 목록 로깅
            for tool in self._tools:
                tool_name = getattr(tool, 'name', '이름없음')
                tool_desc = getattr(tool, 'description', '설명없음')
                self._logger.info(f"실제 도구: {tool_name} - {tool_desc}")
                
        except Exception as e:
            self._logger.error(f"실제 도구 로드 실패: {e}")
            self._tools = []
            self._tools_dict = {}
            raise
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any], session_id: Optional[str] = "UNKNOWN_SESSION") -> Any:
        """MCP 도구를 실제로 호출합니다
        
        Args:
            server_name: 서버 이름
            tool_name: 도구 이름
            arguments: 도구 인자
            session_id: 현재 요청의 세션 ID (로깅용)
            
        Returns:
            도구 실행 결과
            
        Raises:
            ValueError: 도구를 찾을 수 없는 경우
            Exception: 도구 실행 실패
        """
        # <<< 추가된 로깅 시작 >>>
        self._logger.info(f"[EnhancedMCPClient.call_tool ENTRY] server_name: {server_name}, tool_name: {tool_name}, received arguments: {arguments}, type: {type(arguments)}")
        # <<< 추가된 로깅 끝 >>>

        # JSON-RPC 요청 객체 생성 (로깅용)
        request_payload = {
            "jsonrpc": "2.0",
            "method": "tools/call", 
            "params": {
                "server": server_name,
                "name": tool_name,
                "arguments": arguments # 여기서 arguments가 어떻게 사용되는지 중요
            },
            "id": f"mcp-host-{Path(session_id).name}-{int(asyncio.get_event_loop().time() * 1000)}"
        }
        
        # 요청 로깅
        json_rpc_logger.info(f"[SESSION:{session_id}] [REQUEST] -> {json.dumps(request_payload, ensure_ascii=False)}")
        
        try:
            # 도구 찾기
            if tool_name not in self._tools_dict:
                available_tools = list(self._tools_dict.keys())
                raise ValueError(f"도구 '{tool_name}'을 찾을 수 없습니다. 사용 가능한 도구: {available_tools}")
            
            tool = self._tools_dict[tool_name]
            
            # 도구 실행
            self._logger.info(f"실제 MCP 도구 호출: {server_name}.{tool_name}") # 기존 내부 로깅
            
            # <<< 추가된 로깅 시작 >>>
            self._logger.info(f"[EnhancedMCPClient.call_tool PRE-INVOKE] Calling tool.ainvoke with arguments: {arguments}, type: {type(arguments)}")
            # <<< 추가된 로깅 끝 >>>
            result = await tool.ainvoke(arguments) 
            
            self._logger.info(f"MCP 도구 호출 성공: {tool_name}") # 기존 내부 로깅

            # JSON-RPC 응답 객체 생성 (로깅용)
            response_payload = {
                "jsonrpc": "2.0",
                "result": result, 
                "id": request_payload["id"] 
            }
            # 응답 로깅
            json_rpc_logger.info(f"[SESSION:{session_id}] [RESPONSE] <- {json.dumps(response_payload, ensure_ascii=False, default=str)}")

            return result
            
        except Exception as e:
            self._logger.error(f"MCP 도구 호출 실패 {server_name}.{tool_name}: {e}") # 기존 내부 로깅
            
            # JSON-RPC 에러 응답 객체 생성 (로깅용)
            error_response_payload = {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32000, 
                    "message": f"Tool execution failed: {str(e)}",
                    "data": {
                        "server": server_name,
                        "tool": tool_name,
                        "arguments": arguments
                    }
                },
                "id": request_payload["id"]
            }
            # 에러 응답 로깅
            json_rpc_logger.error(f"[SESSION:{session_id}] [RESPONSE_ERROR] <- {json.dumps(error_response_payload, ensure_ascii=False)}")
            
            raise
    
    def get_tools(self) -> List[Any]:
        """로드된 도구 목록 반환
        
        Returns:
            LangChain 도구 목록
        """
        return self._tools.copy()
    
    def get_tool_names(self) -> List[str]:
        """도구 이름 목록 반환
        
        Returns:
            도구 이름 리스트
        """
        return [getattr(tool, 'name', '이름없음') for tool in self._tools]
    
    async def close(self) -> None:
        """클라이언트 연결 해제"""
        try:
            if self._client:
                # MultiServerMCPClient는 자동으로 연결 해제됨
                self._client = None
                self._tools = []
                self._tools_dict = {}
                self._logger.info("Enhanced MCP Client 연결 해제 완료")
                
        except Exception as e:
            self._logger.warning(f"연결 해제 중 오류: {e}")
    
    def get_server_count(self) -> int:
        """설정된 서버 수 반환"""
        return len(self._server_config)
    
    def get_server_names(self) -> List[str]:
        """서버 이름 목록 반환"""
        return list(self._server_config.keys())
    
    def get_tools_info(self) -> Dict[str, List[Dict[str, str]]]:
        """서버별 도구 정보를 구조화하여 반환
        
        Returns:
            서버별 도구 정보 딕셔너리
            예: {"weather": [{"name": "get_weather", "description": "..."}]}
        """
        tools_by_server = {}
        
        # 각 서버의 도구들을 분류
        for server_name in self._server_config.keys():
            tools_by_server[server_name] = []
        
        # 도구들을 서버별로 분류
        for tool in self._tools:
            tool_name = getattr(tool, 'name', '이름없음')
            tool_desc = getattr(tool, 'description', '설명없음')
            
            # 도구 이름이나 설명에서 서버 추정 (임시 방법)
            assigned_server = None
            if 'weather' in tool_name.lower() or 'forecast' in tool_name.lower():
                assigned_server = 'weather'
            elif 'file' in tool_name.lower() or 'list' in tool_name.lower() or 'read' in tool_name.lower():
                assigned_server = 'file-manager'
            
            # 기본적으로 첫 번째 서버에 할당 (더 나은 방법 필요)
            if assigned_server is None and self._server_config:
                assigned_server = list(self._server_config.keys())[0]
            
            if assigned_server and assigned_server in tools_by_server:
                tools_by_server[assigned_server].append({
                    'name': tool_name,
                    'description': tool_desc
                })
        
        return tools_by_server
    
    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료"""
        await self.close()


def create_enhanced_client() -> EnhancedMCPClient:
    """향상된 MCP 클라이언트 팩토리 함수
    
    Returns:
        EnhancedMCPClient 인스턴스
    """
    return EnhancedMCPClient() 