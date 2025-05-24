"""FastAPI MCP 호스트 애플리케이션

MCP 서버들과 연결하여 LangGraph 워크플로우를 실행하는 웹 애플리케이션입니다.
단일 책임 원칙에 따라 웹 서버 기능만 담당합니다.
"""

import logging
import json
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..adapters.enhanced_client import EnhancedMCPClient
from ..workflows import create_workflow_executor, MCPWorkflowExecutor


# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    """채팅 요청 모델"""
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class ChatResponse(BaseModel):
    """채팅 응답 모델"""
    success: bool
    response: str
    intent_type: Optional[str] = None
    tool_calls: list = []
    error: Optional[str] = None


class MCPHostApp:
    """MCP 호스트 애플리케이션 클래스
    
    단일 책임 원칙: FastAPI 애플리케이션 라이프사이클 관리만 담당
    개방-폐쇄 원칙: 새로운 엔드포인트 추가 시 기존 코드 수정 없이 확장 가능
    의존성 역전 원칙: 추상 인터페이스에 의존하여 테스트 가능한 구조
    """
    
    def __init__(self):
        """애플리케이션 초기화"""
        self.mcp_client: Optional[EnhancedMCPClient] = None
        self.workflow_executor: Optional[MCPWorkflowExecutor] = None
        self._logger = logging.getLogger(__name__)
    
    async def startup(self):
        """애플리케이션 시작 시 초기화 작업"""
        try:
            self._logger.info("MCP 호스트 애플리케이션 시작")
            
            # Enhanced MCP Client 초기화 (JSON 파일 직접 사용)
            self.mcp_client = EnhancedMCPClient()
            await self.mcp_client.initialize("mcp_servers.json")
            
            # 도구 로드 확인
            tools = self.mcp_client.get_tools()
            self._logger.info(f"로드된 도구: {len(tools)}개")
            
            # 워크플로우 실행기 초기화
            self.workflow_executor = create_workflow_executor()
            
            self._logger.info("MCP 호스트 애플리케이션 시작 완료")
            
        except Exception as e:
            self._logger.error(f"애플리케이션 시작 오류: {e}")
            raise
    
    async def shutdown(self):
        """애플리케이션 종료 시 정리 작업"""
        try:
            self._logger.info("MCP 호스트 애플리케이션 종료")
            
            if self.mcp_client:
                await self.mcp_client.close()
                self._logger.info("MCP 클라이언트 종료 완료")
            
        except Exception as e:
            self._logger.error(f"애플리케이션 종료 오류: {e}")
    
    async def process_message(self, message: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """메시지 처리 (워크플로우 실행)
        
        Args:
            message: 사용자 메시지
            session_id: 세션 ID
            
        Returns:
            처리 결과 딕셔너리
        """
        if not self.workflow_executor:
            raise RuntimeError("워크플로우 실행기가 초기화되지 않았습니다")
        
        if not self.mcp_client:
            raise RuntimeError("MCP 클라이언트가 초기화되지 않았습니다")
        
        try:
            # 컨텍스트 정보 생성
            context = {
                "available_servers": self.mcp_client.get_server_names(),
                "available_tools": {
                    "all": self.mcp_client.get_tool_names()
                }
            }
            
            # 워크플로우 실행 (MCP 클라이언트 전달)
            result = await self.workflow_executor.execute_message(
                user_message=message,
                session_id=session_id,
                context=context,
                mcp_client=self.mcp_client
            )
            
            return result
            
        except Exception as e:
            self._logger.error(f"메시지 처리 오류: {e}")
            return {
                "success": False,
                "error": str(e),
                "response": "죄송합니다. 요청을 처리하는 중 오류가 발생했습니다."
            }


# 전역 애플리케이션 인스턴스
_app_instance = MCPHostApp()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI 라이프사이클 관리"""
    # 시작
    await _app_instance.startup()
    yield
    # 종료
    await _app_instance.shutdown()


def create_app() -> FastAPI:
    """FastAPI 애플리케이션 생성 팩토리 함수
    
    Returns:
        설정된 FastAPI 애플리케이션
    """
    # FastAPI 애플리케이션 생성
    app = FastAPI(
        title="LangGraph MCP 호스트",
        description="MCP 서버들과 연결하여 LangGraph 워크플로우를 실행하는 호스트",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # CORS 설정
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 프로덕션에서는 제한 필요
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 정적 파일 서빙
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")
    
    @app.get("/")
    async def root():
        """루트 페이지 - HTML 채팅 UI 제공"""
        static_file = os.path.join(static_dir, "index.html")
        if os.path.exists(static_file):
            return FileResponse(static_file)
        else:
            return {"message": "LangGraph MCP 호스트가 실행 중입니다. /static/index.html 파일이 없습니다."}
    
    @app.get("/health")
    async def health_check():
        """헬스 체크 엔드포인트"""
        if _app_instance.mcp_client and _app_instance.workflow_executor:
            servers = _app_instance.mcp_client.get_server_names()
            tools_count = len(_app_instance.mcp_client.get_tools())
            
            return {
                "status": "healthy",
                "connected_servers": servers,
                "available_tools_count": tools_count
            }
        else:
            return {
                "status": "initializing",
                "message": "서비스 초기화 중입니다"
            }
    
    @app.post("/chat", response_model=ChatResponse)
    async def chat_endpoint(request: ChatRequest):
        """REST API 채팅 엔드포인트"""
        try:
            result = await _app_instance.process_message(
                message=request.message,
                session_id=request.session_id
            )
            
            return ChatResponse(
                success=result["success"],
                response=result["response"],
                intent_type=result.get("intent_type"),
                tool_calls=result.get("tool_calls", []),
                error=result.get("error")
            )
            
        except Exception as e:
            logger.error(f"채팅 엔드포인트 오류: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket 채팅 엔드포인트"""
        await websocket.accept()
        logger.info("WebSocket 연결 수락")
        
        try:
            while True:
                # 메시지 수신
                data = await websocket.receive_text()
                logger.info(f"WebSocket 메시지 수신: {data}")
                
                try:
                    # JSON 파싱
                    message_data = json.loads(data)
                    user_message = message_data.get("message", "")
                    session_id = message_data.get("session_id")
                    
                    if not user_message.strip():
                        await websocket.send_text(json.dumps({
                            "success": False,
                            "error": "빈 메시지입니다",
                            "response": "메시지를 입력해주세요."
                        }))
                        continue
                    
                    # 메시지 처리
                    result = await _app_instance.process_message(
                        message=user_message,
                        session_id=session_id
                    )
                    
                    # 결과 전송
                    await websocket.send_text(json.dumps(result, ensure_ascii=False))
                    
                except json.JSONDecodeError:
                    # 단순 텍스트 메시지로 처리
                    result = await _app_instance.process_message(message=data)
                    await websocket.send_text(json.dumps(result, ensure_ascii=False))
                    
                except Exception as e:
                    logger.error(f"메시지 처리 오류: {e}")
                    await websocket.send_text(json.dumps({
                        "success": False,
                        "error": str(e),
                        "response": "메시지 처리 중 오류가 발생했습니다."
                    }, ensure_ascii=False))
        
        except WebSocketDisconnect:
            logger.info("WebSocket 연결 종료")
        except Exception as e:
            logger.error(f"WebSocket 오류: {e}")
    
    @app.get("/servers")
    async def get_servers():
        """연결된 서버 목록 조회"""
        if _app_instance.mcp_client:
            servers = {}
            for name in _app_instance.mcp_client.get_server_names():
                servers[name] = {
                    "connected": True,
                    "tools": []  # 개별 서버별 도구는 현재 API에서 지원하지 않음
                }
            return {"servers": servers}
        else:
            return {"servers": {}}
    
    @app.get("/tools")
    async def get_tools():
        """사용 가능한 도구 목록 조회"""
        if _app_instance.mcp_client:
            tools = _app_instance.mcp_client.get_tools()
            tool_names = _app_instance.mcp_client.get_tool_names()
            return {
                "total_tools": len(tools),
                "tools": tool_names,
                "tools_by_server": {"all": tool_names}
            }
        else:
            return {"total_tools": 0, "tools": [], "tools_by_server": {}}
    
    return app 