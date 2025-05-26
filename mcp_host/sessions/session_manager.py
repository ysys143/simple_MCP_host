"""세션 기반 멀티턴 대화 관리

세션별 대화 히스토리와 컨텍스트를 메모리에 저장하여 
연속적인 대화를 지원합니다.

SOLID 원칙:
- 단일 책임: 세션 생명주기와 대화 히스토리 관리만 담당
- 개방-폐쇄: 새로운 저장소 백엔드로 확장 가능
- 의존성 역전: 추상 저장소 인터페이스에 의존
"""

import asyncio
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from ..models import ChatMessage, MessageRole, ChatState
import logging

logger = logging.getLogger(__name__)


@dataclass
class SessionData:
    """세션 데이터 구조"""
    session_id: str
    messages: List[ChatMessage] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    max_messages: int = 50  # 최대 메시지 수
    
    def add_message(self, message: ChatMessage) -> None:
        """메시지 추가 및 제한 관리"""
        self.messages.append(message)
        self.last_accessed = datetime.now()
        
        # 최대 메시지 수 초과시 오래된 메시지 제거 (시스템 메시지 제외)
        if len(self.messages) > self.max_messages:
            # 첫 번째 사용자 메시지는 보존하고 중간 메시지들 제거
            user_messages = [msg for msg in self.messages if msg.role == MessageRole.USER]
            if len(user_messages) > 1:
                # 첫 번째와 마지막 몇 개 메시지 보존
                preserved_count = min(10, self.max_messages // 2)
                self.messages = self.messages[:1] + self.messages[-preserved_count:]
    
    def get_conversation_context(self, limit: int = 20) -> List[Dict[str, Any]]:
        """대화 컨텍스트를 반환 (LLM 입력용)"""
        recent_messages = self.messages[-limit:] if limit else self.messages
        return [
            {
                "role": msg.role.value.lower(),
                "content": msg.content,
                "timestamp": msg.timestamp.isoformat()
            }
            for msg in recent_messages
        ]
    
    def is_expired(self, timeout_minutes: int = 30) -> bool:
        """세션 만료 여부 확인"""
        return datetime.now() - self.last_accessed > timedelta(minutes=timeout_minutes)


class SessionManager:
    """세션 기반 멀티턴 대화 관리자
    
    메모리 기반으로 세션별 대화 히스토리와 컨텍스트를 관리합니다.
    향후 Redis나 데이터베이스로 확장 가능하도록 설계되었습니다.
    """
    
    def __init__(self, session_timeout_minutes: int = 30, cleanup_interval_minutes: int = 5):
        """
        Args:
            session_timeout_minutes: 세션 타임아웃 시간 (분)
            cleanup_interval_minutes: 정리 작업 주기 (분)
        """
        self.sessions: Dict[str, SessionData] = {}
        self.session_timeout = session_timeout_minutes
        self.cleanup_interval = cleanup_interval_minutes
        self._cleanup_task: Optional[asyncio.Task] = None
        self._logger = logging.getLogger(f"{__name__}.SessionManager")
        
    async def start(self) -> None:
        """세션 관리자 시작 (정리 작업 스케줄링)"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            self._logger.info(f"세션 관리자 시작 - 타임아웃: {self.session_timeout}분")
    
    async def stop(self) -> None:
        """세션 관리자 중지"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            self._logger.info("세션 관리자 중지")
    
    def create_or_get_session(self, session_id: str) -> SessionData:
        """세션 생성 또는 기존 세션 반환
        
        Args:
            session_id: 세션 식별자
            
        Returns:
            SessionData: 세션 데이터
        """
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionData(session_id=session_id)
            self._logger.info(f"새 세션 생성: {session_id}")
        else:
            # 기존 세션 접근 시간 업데이트
            self.sessions[session_id].last_accessed = datetime.now()
            self._logger.debug(f"기존 세션 접근: {session_id}")
        
        return self.sessions[session_id]
    
    def add_user_message(self, session_id: str, content: str) -> ChatMessage:
        """사용자 메시지 추가
        
        Args:
            session_id: 세션 식별자
            content: 메시지 내용
            
        Returns:
            ChatMessage: 추가된 메시지
        """
        session = self.create_or_get_session(session_id)
        message = ChatMessage(
            role=MessageRole.USER,
            content=content,
            timestamp=datetime.now()
        )
        session.add_message(message)
        self._logger.debug(f"사용자 메시지 추가 - 세션: {session_id}, 길이: {len(content)}")
        return message
    
    def add_assistant_message(self, session_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> ChatMessage:
        """어시스턴트 메시지 추가
        
        Args:
            session_id: 세션 식별자
            content: 메시지 내용
            metadata: 메타데이터 (선택적)
            
        Returns:
            ChatMessage: 추가된 메시지
        """
        session = self.create_or_get_session(session_id)
        message = ChatMessage(
            role=MessageRole.ASSISTANT,
            content=content,
            timestamp=datetime.now(),
            metadata=metadata
        )
        session.add_message(message)
        self._logger.debug(f"어시스턴트 메시지 추가 - 세션: {session_id}, 길이: {len(content)}")
        return message
    
    def get_conversation_history(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """대화 히스토리 반환 (LLM 컨텍스트용)
        
        Args:
            session_id: 세션 식별자
            limit: 반환할 메시지 수 제한
            
        Returns:
            List[Dict]: 대화 히스토리
        """
        if session_id not in self.sessions:
            return []
        
        session = self.sessions[session_id]
        return session.get_conversation_context(limit)
    
    def update_session_context(self, session_id: str, context_updates: Dict[str, Any]) -> None:
        """세션 컨텍스트 업데이트
        
        Args:
            session_id: 세션 식별자
            context_updates: 업데이트할 컨텍스트 데이터
        """
        session = self.create_or_get_session(session_id)
        session.context.update(context_updates)
        self._logger.debug(f"세션 컨텍스트 업데이트 - 세션: {session_id}")
    
    def get_session_context(self, session_id: str) -> Dict[str, Any]:
        """세션 컨텍스트 반환
        
        Args:
            session_id: 세션 식별자
            
        Returns:
            Dict: 세션 컨텍스트
        """
        if session_id not in self.sessions:
            return {}
        return self.sessions[session_id].context.copy()
    
    def get_session_stats(self, session_id: str) -> Optional[Dict[str, Any]]:
        """세션 통계 반환
        
        Args:
            session_id: 세션 식별자
            
        Returns:
            Dict: 세션 통계 정보
        """
        if session_id not in self.sessions:
            return None
        
        session = self.sessions[session_id]
        return {
            "session_id": session_id,
            "message_count": len(session.messages),
            "created_at": session.created_at.isoformat(),
            "last_accessed": session.last_accessed.isoformat(),
            "context_keys": list(session.context.keys())
        }
    
    def delete_session(self, session_id: str) -> bool:
        """세션 삭제
        
        Args:
            session_id: 세션 식별자
            
        Returns:
            bool: 삭제 성공 여부
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
            self._logger.info(f"세션 삭제: {session_id}")
            return True
        return False
    
    def get_active_sessions_count(self) -> int:
        """활성 세션 수 반환"""
        return len(self.sessions)
    
    async def _cleanup_loop(self) -> None:
        """만료된 세션 정리 루프"""
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval * 60)  # 분을 초로 변환
                await self._cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"세션 정리 중 오류: {e}")
    
    async def _cleanup_expired_sessions(self) -> None:
        """만료된 세션들 정리"""
        expired_sessions = [
            session_id for session_id, session_data in self.sessions.items()
            if session_data.is_expired(self.session_timeout)
        ]
        
        for session_id in expired_sessions:
            del self.sessions[session_id]
            self._logger.info(f"만료된 세션 정리: {session_id}")
        
        if expired_sessions:
            self._logger.info(f"총 {len(expired_sessions)}개 만료 세션 정리 완료")


# 전역 세션 관리자 인스턴스 (싱글톤 패턴)
_session_manager: Optional[SessionManager] = None

def get_session_manager() -> SessionManager:
    """세션 관리자 싱글톤 인스턴스 반환"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager

async def initialize_session_manager() -> SessionManager:
    """세션 관리자 초기화 및 시작"""
    manager = get_session_manager()
    await manager.start()
    return manager

async def shutdown_session_manager() -> None:
    """세션 관리자 종료"""
    global _session_manager
    if _session_manager:
        await _session_manager.stop()
        _session_manager = None 