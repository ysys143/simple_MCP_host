"""세션 관리 패키지

멀티턴 대화를 위한 세션 기반 대화 히스토리와 컨텍스트 관리를 제공합니다.

주요 구성요소:
- SessionManager: 세션 생명주기 및 대화 히스토리 관리
- SessionData: 세션별 데이터 구조
- 메모리 기반 저장소 (향후 Redis/DB 확장 가능)
"""

from .session_manager import (
    SessionManager,
    SessionData,
    get_session_manager,
    initialize_session_manager,
    shutdown_session_manager
)

__all__ = [
    'SessionManager',
    'SessionData', 
    'get_session_manager',
    'initialize_session_manager',
    'shutdown_session_manager'
] 