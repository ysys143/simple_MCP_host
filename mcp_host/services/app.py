"""FastAPI MCP 호스트 애플리케이션

MCP 서버들과 연결하여 LangGraph 워크플로우를 실행하는 웹 애플리케이션입니다.
단일 책임 원칙에 따라 웹 서버 기능만 담당합니다.
"""

import logging
import json
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
import os
import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from ..adapters.enhanced_client import EnhancedMCPClient
from ..workflows import create_workflow_executor, MCPWorkflowExecutor
from ..streaming import (
    get_sse_manager,
    create_thinking_message,
    create_acting_message,
    create_final_response_message,
    create_error_message,
    create_tool_call_message
)


# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    """채팅 요청 모델"""
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    react_mode: bool = False  # ReAct 모드 활성화 여부


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
            
            # 세션 관리자 초기화
            from ..sessions import initialize_session_manager
            await initialize_session_manager()
            self._logger.info("세션 관리자 초기화 완료")
            
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
            
            # 세션 관리자 종료
            from ..sessions import shutdown_session_manager
            await shutdown_session_manager()
            self._logger.info("세션 관리자 종료 완료")
            
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
    
    @app.get("/debug/sse/status")
    async def get_sse_status():
        """SSE 연결 상태 조회 (디버깅용)"""
        sse_manager = get_sse_manager()
        return {
            "connection_count": sse_manager.get_connection_count(),
            "session_count": sse_manager.get_session_count(),
            "sessions": list(sse_manager.session_connections.keys()),
            "connections": list(sse_manager.connections.keys())
        }
    
    @app.post("/debug/sse/send")
    async def debug_send_message(request: dict):
        """SSE 테스트 메시지 전송 (디버깅용)"""
        session_id = request.get("session_id")
        message_content = request.get("message", "테스트 메시지")
        
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id가 필요합니다")
        
        sse_manager = get_sse_manager()
        
        # 테스트 메시지 생성
        test_message = create_final_response_message(message_content, session_id)
        
        # 메시지 전송
        sent_count = await sse_manager.send_to_session(session_id, test_message)
        
        return {
            "success": True,
            "sent_to_connections": sent_count,
            "session_id": session_id,
            "message": message_content
        }
    
    @app.get("/api/v3/chat/stream")
    async def stream_chat(request: Request):
        """SSE 스트리밍 채팅 엔드포인트 (GET 방식으로 연결 생성)"""
        session_id = request.query_params.get("session_id")
        logger.info(f"SSE 연결 요청 - 세션 ID: {session_id}")
        
        sse_manager = get_sse_manager()
        
        async def event_generator():
            try:
                logger.info(f"SSE 연결 생성 시작 - 세션: {session_id}")
                async with sse_manager.get_connection_stream(session_id) as (connection_id, stream):
                    logger.info(f"SSE 연결 생성 완료 - 연결 ID: {connection_id}, 세션: {session_id}")
                    async for message in stream:
                        # heartbeat 메시지는 로깅하지 않음
                        if "heartbeat" not in message:
                            logger.info(f"SSE 메시지 전송 - 연결: {connection_id}, 내용: {message[:100]}...")
                        yield message
            except Exception as e:
                logger.error(f"SSE 스트림 오류 - 세션: {session_id}, 오류: {e}")
                error_msg = create_error_message(str(e), session_id or "unknown")
                yield error_msg.to_sse_format()
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Cache-Control",
                "X-Accel-Buffering": "no"  # Nginx 버퍼링 비활성화
            }
        )
    
    @app.post("/api/v3/chat/send")
    async def send_chat_message(request: ChatRequest):
        """SSE 채팅 메시지 전송 엔드포인트"""
        if not request.session_id:
            raise HTTPException(status_code=400, detail="세션 ID가 필요합니다")
        
        logger.info(f"메시지 전송 요청 - 세션: {request.session_id}, 메시지: {request.message}")
        sse_manager = get_sse_manager()
        
        # 현재 SSE 연결 상태 확인
        connection_count = sse_manager.get_connection_count()
        session_count = sse_manager.get_session_count()
        logger.info(f"현재 SSE 상태 - 연결: {connection_count}개, 세션: {session_count}개")
        
        try:
            # 즉시 시작 메시지 전송
            thinking_msg = create_thinking_message(
                "요청을 접수했습니다. 분석을 시작합니다...",
                request.session_id,
                iteration=1
            )
            sent_count = await sse_manager.send_to_session(request.session_id, thinking_msg)
            logger.info(f"시작 메시지 전송 - 수신자: {sent_count}개")
            
            # 컨텍스트 정보 생성
            context = {
                "available_servers": _app_instance.mcp_client.get_server_names(),
                "available_tools": {
                    "all": _app_instance.mcp_client.get_tool_names()
                }
            }
            
            # 분석 진행 메시지
            await asyncio.sleep(0.1)  # 짧은 지연으로 실시간 효과
            thinking_msg2 = create_thinking_message(
                f"'{request.message}' 메시지의 의도를 분석하고 있습니다...",
                request.session_id,
                iteration=2
            )
            await sse_manager.send_to_session(request.session_id, thinking_msg2)
            
            # 스트리밍 워크플로우 실행
            try:
                result = await _app_instance.workflow_executor.execute_message_with_streaming(
                    user_message=request.message,
                    session_id=request.session_id,
                    sse_manager=sse_manager,
                    context=context,
                    mcp_client=_app_instance.mcp_client,
                    react_mode=request.react_mode  # ReAct 모드 전달
                )
                
                logger.info(f"워크플로우 처리 완료 - 성공: {result.get('success')}")
                return {"success": True, "message": "메시지가 처리되었습니다", "result": result}
                
            except Exception as workflow_error:
                logger.error(f"워크플로우 처리 오류: {workflow_error}")
                
                # 워크플로우 오류 시 즉시 오류 메시지 전송
                error_msg = create_error_message(
                    f"처리 중 오류가 발생했습니다: {str(workflow_error)}",
                    request.session_id
                )
                await sse_manager.send_to_session(request.session_id, error_msg)
                
                return {"success": False, "message": "워크플로우 오류", "error": str(workflow_error)}
                
        except Exception as e:
            logger.error(f"메시지 전송 오류: {e}")
            
            # 즉시 오류 메시지 전송
            error_msg = create_error_message(f"시스템 오류: {str(e)}", request.session_id)
            await sse_manager.send_to_session(request.session_id, error_msg)
            
            raise HTTPException(status_code=500, detail=str(e))
    
    return app 