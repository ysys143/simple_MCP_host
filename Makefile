# MCP 호스트 프로젝트 Makefile

.PHONY: help test test-pytest test-basic server clean install dev logs check format lint run-bg stop-bg status

# 기본 목표
help:
	@echo "🤖 MCP 호스트 프로젝트"
	@echo ""
	@echo "사용 가능한 명령어:"
	@echo "  make test        - 모든 테스트 실행"
	@echo "  make test-pytest - pytest로 테스트 실행"
	@echo "  make test-basic  - 기본 통합 테스트 실행"
	@echo "  make server      - MCP 호스트 서버 시작"
	@echo "  make run-bg      - 서버를 백그라운드에서 실행"
	@echo "  make stop-bg     - 백그라운드 서버 중지"
	@echo "  make status      - 서버 상태 확인"
	@echo "  make logs        - 로그 파일 확인"
	@echo "  make install     - 의존성 설치"
	@echo "  make dev         - 개발 환경 설정"
	@echo "  make check       - 코드 품질 검사"
	@echo "  make format      - 코드 포맷팅"
	@echo "  make lint        - 린트 검사"
	@echo "  make clean       - 캐시 파일 정리"

# 테스트 실행
test:
	@echo "🧪 모든 테스트 실행 중..."
	@python mcp_host/tests/test_basic.py

# pytest 실행 (가상환경 활성화)
test-pytest:
	@echo "🧪 pytest 실행 중..."
	@if [ -f .venv/bin/activate ]; then \
		source .venv/bin/activate && python -m pytest mcp_host/tests/ -v; \
	else \
		python -m pytest mcp_host/tests/ -v; \
	fi

# 기본 통합 테스트만 실행
test-basic:
	@echo "🧪 기본 통합 테스트 실행 중..."
	@python mcp_host/tests/test_basic.py

# 서버 시작
server:
	@echo "🚀 MCP 호스트 서버 시작 중..."
	@python main.py

# 백그라운드에서 서버 실행
run-bg:
	@echo "🚀 백그라운드에서 서버 시작 중..."
	@nohup python main.py > logs/server.log 2>&1 & echo $$! > .server.pid
	@echo "서버가 백그라운드에서 시작되었습니다. PID: $$(cat .server.pid)"
	@echo "로그 확인: make logs"

# 백그라운드 서버 중지
stop-bg:
	@if [ -f .server.pid ]; then \
		echo "🛑 백그라운드 서버 중지 중... PID: $$(cat .server.pid)"; \
		kill $$(cat .server.pid) 2>/dev/null || echo "서버가 이미 중지되었습니다."; \
		rm -f .server.pid; \
	else \
		echo "실행 중인 백그라운드 서버가 없습니다."; \
	fi

# 서버 상태 확인
status:
	@if [ -f .server.pid ]; then \
		if ps -p $$(cat .server.pid) > /dev/null 2>&1; then \
			echo "✅ 서버가 실행 중입니다. PID: $$(cat .server.pid)"; \
			echo "포트 8000에서 서비스 중: http://localhost:8000"; \
		else \
			echo "❌ 서버가 중지되었습니다."; \
			rm -f .server.pid; \
		fi \
	else \
		echo "❌ 백그라운드 서버가 실행되지 않았습니다."; \
	fi

# 로그 확인
logs:
	@echo "📋 최근 로그 확인 중..."
	@mkdir -p logs
	@if [ -f logs/server.log ]; then \
		echo "=== 서버 로그 (최근 50줄) ==="; \
		tail -50 logs/server.log; \
	else \
		echo "로그 파일이 없습니다. 서버를 먼저 실행해주세요."; \
	fi

# 의존성 설치
install:
	@echo "📦 의존성 설치 중..."
	@uv pip install -r requirements.txt

# 개발 환경 설정
dev: install
	@echo "🛠️ 개발 환경 설정 중..."
	@mkdir -p logs
	@mkdir -p static
	@echo "🛠️ 개발 환경 설정 완료"

# 코드 품질 검사
check: format lint test-basic
	@echo "✅ 코드 품질 검사 완료"

# 코드 포맷팅
format:
	@echo "🎨 코드 포맷팅 중..."
	@if command -v black >/dev/null 2>&1; then \
		black mcp_host/ --line-length 120; \
	else \
		echo "⚠️ black이 설치되지 않았습니다. 'uv pip install black'으로 설치하세요."; \
	fi

# 린트 검사
lint:
	@echo "🔍 린트 검사 중..."
	@if command -v flake8 >/dev/null 2>&1; then \
		flake8 mcp_host/ --max-line-length=120 --ignore=E203,W503; \
	else \
		echo "⚠️ flake8이 설치되지 않았습니다. 'uv pip install flake8'으로 설치하세요."; \
	fi

# 캐시 정리
clean:
	@echo "🧹 캐시 파일 정리 중..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@rm -f .server.pid 2>/dev/null || true
	@echo "🧹 캐시 파일 정리 완료" 