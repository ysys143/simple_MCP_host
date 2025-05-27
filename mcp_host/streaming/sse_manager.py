"""SSE 연결 관리자

SSE(Server-Sent Events) 연결들의 생명주기를 관리합니다.
연결 생성, 메시지 브로드캐스트, 연결 정리 등의 기능을 제공합니다.
"""

import asyncio
import logging
import uuid
from typing import Dict, Set, AsyncGenerator, Optional
from contextlib import asynccontextmanager

from .message_types import StreamMessage, create_session_start_message, create_session_end_message


logger = logging.getLogger(__name__)


class SSEConnection:
    """개별 SSE 연결을 나타내는 클래스"""
    
    def __init__(self, connection_id: str, session_id: str):
        self.connection_id = connection_id
        self.session_id = session_id
        self.queue: asyncio.Queue = asyncio.Queue()
        self.is_active = True
        self.created_at = asyncio.get_event_loop().time()
        
    async def send_message(self, message: StreamMessage) -> bool:
        """메시지를 연결의 큐에 추가"""
        if not self.is_active:
            return False
            
        try:
            await self.queue.put(message)
            return True
        except Exception as e:
            logger.error(f"메시지 전송 실패 (연결: {self.connection_id}): {e}")
            self.is_active = False
            return False
    
    async def get_messages(self) -> AsyncGenerator[str, None]:
        """SSE 형식으로 메시지를 생성하는 제너레이터"""
        try:
            while self.is_active:
                try:
                    # 타임아웃으로 주기적으로 연결 상태 확인
                    message = await asyncio.wait_for(self.queue.get(), timeout=30.0)
                    yield message.to_sse_format()
                except asyncio.TimeoutError:
                    # Heartbeat 전송
                    yield ": heartbeat\n\n"
                except Exception as e:
                    logger.error(f"메시지 생성 오류 (연결: {self.connection_id}): {e}")
                    break
        finally:
            self.is_active = False
            logger.info(f"SSE 연결 종료: {self.connection_id}")
    
    def close(self):
        """연결 종료"""
        self.is_active = False


class SSEManager:
    """SSE 연결 관리자
    
    단일 책임 원칙: SSE 연결들의 생명주기 관리만 담당
    """
    
    def __init__(self, max_connections: int = 50):
        self.max_connections = max_connections
        self.connections: Dict[str, SSEConnection] = {}
        self.session_connections: Dict[str, Set[str]] = {}  # 세션별 연결 추적
        self._lock = asyncio.Lock()
        self._logger = logging.getLogger(__name__)
        
    async def create_connection(self, session_id: Optional[str] = None) -> tuple[str, SSEConnection]:
        """새 SSE 연결 생성
        
        Args:
            session_id: 세션 ID (없으면 새로 생성)
            
        Returns:
            (connection_id, SSEConnection) 튜플
        """
        async with self._lock:
            # 연결 수 제한 확인
            if len(self.connections) >= self.max_connections:
                raise Exception(f"최대 연결 수 초과 ({self.max_connections})")
            
            # 세션 ID 생성 또는 사용
            if session_id is None:
                session_id = f"session_{uuid.uuid4().hex[:8]}"
            
            # 동일 세션의 기존 연결 정리 (중복 연결 방지)
            if session_id in self.session_connections:
                existing_connections = self.session_connections[session_id].copy()
                self._logger.info(f"세션 {session_id}의 기존 연결 {len(existing_connections)}개 정리 중...")
                
                for existing_conn_id in existing_connections:
                    if existing_conn_id in self.connections:
                        existing_conn = self.connections[existing_conn_id]
                        
                        # 기존 연결에 세션 종료 메시지 전송
                        end_message = create_session_end_message(session_id)
                        await existing_conn.send_message(end_message)
                        
                        # 기존 연결 종료
                        existing_conn.close()
                        del self.connections[existing_conn_id]
                        
                        self._logger.info(f"기존 연결 정리 완료: {existing_conn_id}")
                
                # 세션 연결 목록 초기화
                self.session_connections[session_id].clear()
            
            # 연결 ID 생성
            connection_id = f"conn_{uuid.uuid4().hex[:8]}"
            
            # 연결 생성
            connection = SSEConnection(connection_id, session_id)
            self.connections[connection_id] = connection
            
            # 세션별 연결 추적
            if session_id not in self.session_connections:
                self.session_connections[session_id] = set()
            self.session_connections[session_id].add(connection_id)
            
            self._logger.info(f"SSE 연결 생성: {connection_id} (세션: {session_id})")
            
            # 세션 시작 메시지 전송
            start_message = create_session_start_message(session_id)
            await connection.send_message(start_message)
            
            return connection_id, connection
    
    async def remove_connection(self, connection_id: str):
        """연결 제거"""
        async with self._lock:
            if connection_id in self.connections:
                connection = self.connections[connection_id]
                session_id = connection.session_id
                
                # 세션 종료 메시지 전송
                end_message = create_session_end_message(session_id)
                await connection.send_message(end_message)
                
                # 연결 종료
                connection.close()
                
                # 연결 제거
                del self.connections[connection_id]
                
                # 세션별 연결에서 제거
                if session_id in self.session_connections:
                    self.session_connections[session_id].discard(connection_id)
                    if not self.session_connections[session_id]:
                        del self.session_connections[session_id]
                
                self._logger.info(f"SSE 연결 제거: {connection_id}")
    
    async def send_to_connection(self, connection_id: str, message: StreamMessage) -> bool:
        """특정 연결에 메시지 전송"""
        if connection_id in self.connections:
            connection = self.connections[connection_id]
            return await connection.send_message(message)
        return False
    
    async def send_to_session(self, session_id: str, message: StreamMessage) -> int:
        """세션의 모든 연결에 메시지 전송
        
        Returns:
            메시지가 전송된 연결 수
        """
        sent_count = 0
        if session_id in self.session_connections:
            connection_ids = self.session_connections[session_id].copy()
            for connection_id in connection_ids:
                if await self.send_to_connection(connection_id, message):
                    sent_count += 1
        return sent_count
    
    async def broadcast_message(self, message: StreamMessage) -> int:
        """모든 연결에 메시지 브로드캐스트
        
        Returns:
            메시지가 전송된 연결 수
        """
        sent_count = 0
        connection_ids = list(self.connections.keys())
        for connection_id in connection_ids:
            if await self.send_to_connection(connection_id, message):
                sent_count += 1
        return sent_count
    
    async def cleanup_inactive_connections(self):
        """비활성 연결들 정리"""
        current_time = asyncio.get_event_loop().time()
        inactive_connections = []
        
        for connection_id, connection in self.connections.items():
            if not connection.is_active or (current_time - connection.created_at) > 3600:  # 1시간 타임아웃
                inactive_connections.append(connection_id)
        
        for connection_id in inactive_connections:
            await self.remove_connection(connection_id)
        
        if inactive_connections:
            self._logger.info(f"비활성 연결 {len(inactive_connections)}개 정리 완료")
    
    def get_connection_count(self) -> int:
        """현재 연결 수 반환"""
        return len(self.connections)
    
    def get_session_count(self) -> int:
        """현재 세션 수 반환"""
        return len(self.session_connections)
    
    @asynccontextmanager
    async def get_connection_stream(self, session_id: Optional[str] = None):
        """SSE 연결 스트림을 위한 컨텍스트 매니저"""
        connection_id, connection = await self.create_connection(session_id)
        try:
            yield connection_id, connection.get_messages()
        finally:
            await self.remove_connection(connection_id)


# 전역 SSE 매니저 인스턴스
_sse_manager: Optional[SSEManager] = None


def get_sse_manager() -> SSEManager:
    """전역 SSE 매니저 인스턴스 반환 (싱글톤 패턴)"""
    global _sse_manager
    if _sse_manager is None:
        _sse_manager = SSEManager()
    return _sse_manager 