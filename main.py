#!/usr/bin/env python3
"""LangGraph MCP 호스트 서버 메인 실행 스크립트

FastAPI 서버를 시작하여 MCP 호스트 서비스를 제공합니다.
"""

import asyncio
import logging
import uvicorn
from mcp_host.services import create_app

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

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
            reload=False,  # 프로덕션에서는 False
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