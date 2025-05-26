#!/usr/bin/env python3
"""LangGraph MCP 호스트 서버 메인 실행 스크립트

FastAPI 서버를 시작하여 MCP 호스트 서비스를 제공합니다.
"""

import asyncio
import logging
import uvicorn
from mcp_host.services import create_app

# 로깅 설정
# 기본 로깅 설정 (루트 로거 또는 애플리케이션 전반 로거)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# JSON-RPC 호출 기록을 위한 별도 로거 설정
json_rpc_logger = logging.getLogger('json_rpc')
json_rpc_logger.setLevel(logging.INFO)
# 다른 핸들러로 전파되지 않도록 설정 (선택 사항, 필요에 따라 조정)
# json_rpc_logger.propagate = False 

# 파일 핸들러 생성
# logs 디렉토리가 없으면 생성해야 합니다. (이 코드는 있다고 가정)
file_handler = logging.FileHandler('logs/mcp_json_rpc.log', encoding='utf-8')
file_handler.setLevel(logging.INFO)

# 포맷터 생성 및 핸들러에 추가
# 세션 ID, 방향 등 필요한 정보를 포함하도록 포맷 조정 가능
# 여기서는 기본 포맷을 사용하고, 로그 메시지 자체에 해당 정보를 포함시킵니다.
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# 로거에 핸들러 추가
if not json_rpc_logger.handlers: # 핸들러 중복 추가 방지
    json_rpc_logger.addHandler(file_handler)

logger = logging.getLogger(__name__)

# FastAPI 앱 인스턴스 생성 (uvicorn이 찾을 수 있도록 모듈 레벨에서 정의)
app = create_app()


def main():
    """메인 함수: FastAPI 서버 시작"""
    try:
        logger.info("LangGraph MCP 호스트 서버 시작")
        
        # Uvicorn 서버 설정
        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=8000,
            log_level="info",
            reload=True,  # 개발 중 자동 재시작 활성화
            access_log=True
        )
        
        # 서버 실행
        server = uvicorn.Server(config)
        asyncio.run(server.serve())
        
    except KeyboardInterrupt:
        logger.info("서버 종료 (Ctrl+C)")
    except Exception as e:
        logger.error(f"서버 실행 오류: {e}")
        raise


if __name__ == "__main__":
    main() 