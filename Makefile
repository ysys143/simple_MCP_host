# MCP 호스트 프로젝트 Makefile

.PHONY: help test test-pytest server clean install dev

# 기본 목표
help:
	@echo "🤖 MCP 호스트 프로젝트"
	@echo ""
	@echo "사용 가능한 명령어:"
	@echo "  make test        - 모든 테스트 실행"
	@echo "  make test-pytest - pytest로 테스트 실행"
	@echo "  make server      - MCP 호스트 서버 시작"
	@echo "  make install     - 의존성 설치"
	@echo "  make dev         - 개발 환경 설정"
	@echo "  make clean       - 캐시 파일 정리"

# 테스트 실행
test:
	@python -m mcp_host test

# pytest 실행
test-pytest:
	@source .venv/bin/activate && python -m pytest mcp_host/tests/ -v

# 서버 시작
server:
	@python -m mcp_host server

# 의존성 설치
install:
	@uv pip install -r requirements.txt

# 개발 환경 설정
dev: install
	@echo "🛠️ 개발 환경 설정 완료"

# 캐시 정리
clean:
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "🧹 캐시 파일 정리 완료" 