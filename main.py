#!/usr/bin/env python3
"""LangGraph MCP 호스트 서버 메인 실행 스크립트

FastAPI 서버를 시작하여 MCP 호스트 서비스를 제공합니다.
"""

import asyncio
import logging
import uvicorn
import os # os 모듈 추가
from dotenv import load_dotenv # dotenv 추가
from mcp_host.services import create_app

# .env 파일 로드 (애플리케이션 시작 시)
# .env 파일이 프로젝트 루트에 있어야 합니다.
load_dotenv()

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

# Phoenix 활성화 여부 확인 (환경 변수 PHOENIX_ENABLED가 "true"일 경우)
# 기본값은 False (안전하게 비활성화)
phoenix_enabled = os.getenv("PHOENIX_ENABLED", "false").lower() == "true"

if phoenix_enabled:
    logger.info("Phoenix 추적 기능이 활성화되었습니다.")
    # Phoenix 초기화 및 LangChain 계측
    try:
        import phoenix as px
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from phoenix.otel import register as phoenix_register # 'register' 이름 충돌 방지

        # Phoenix UI 로컬 실행
        # launch_app()은 백그라운드에서 UI 서버를 시작합니다.
        # 이미 실행 중인 세션이 있으면 해당 세션을 반환합니다.
        phoenix_session = px.launch_app()
        logger.info(f"Phoenix UI가 다음 주소에서 실행 중입니다: {phoenix_session.url}")

        # OpenTelemetry Tracer 등록 (프로젝트 이름 지정)
        # phoenix_register 함수는 OpenTelemetry TracerProvider를 반환합니다.
        tracer_provider = phoenix_register(project_name="mcp_host_traces")

        # LangChain 계측
        # LangChainInstrumentor는 LangChain의 다양한 구성 요소를 자동으로 계측합니다.
        # skip_dep_check=True는 의존성 검사를 건너뛰어 일부 환경에서의 오류를 방지할 수 있습니다.
        LangChainInstrumentor(tracer_provider=tracer_provider).instrument(skip_dep_check=True)
        logger.info("Phoenix를 사용하여 LangChain 계측 완료")

    except ImportError:
        logger.warning("Phoenix 관련 패키지를 찾을 수 없어 LangChain 추적을 시작할 수 없습니다. "
                       "'arize-phoenix'와 'openinference-instrumentation-langchain'을 설치하세요.")
    except Exception as e:
        logger.error(f"Phoenix 초기화 또는 LangChain 계측 중 오류 발생: {e}")
else:
    logger.info("Phoenix 추적 기능이 비활성화되었습니다. PHOENIX_ENABLED=true로 설정하여 활성화할 수 있습니다.")
    # Phoenix 비활성화 시 phoenix_session 객체가 없을 수 있으므로, URL을 None으로 명시적 처리
    # phoenix_session 변수가 이 블록에서 정의되지 않았으므로 직접 접근 불가.
    # create_app 호출 시 조건부로 phoenix_session.url을 사용하거나 None을 전달.

# FastAPI 앱 인스턴스 생성 (uvicorn이 찾을 수 있도록 모듈 레벨에서 정의)
# create_app 호출 시 Phoenix 상태와 URL 전달
app = create_app(
    phoenix_enabled=phoenix_enabled,
    phoenix_url=phoenix_session.url if phoenix_enabled and 'phoenix_session' in locals() and phoenix_session else None
)


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