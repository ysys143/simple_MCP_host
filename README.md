# MCP 호스트 - AI 대화 시스템

> LangGraph와 Model Context Protocol을 활용한 지능형 AI 대화 시스템

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)
![LangGraph](https://img.shields.io/badge/LangGraph-latest-orange.svg)
![LangChain MCP](https://img.shields.io/badge/LangChain_MCP-latest-red.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## 🌟 주요 기능

- **🤖 실시간 AI 대화**: OpenAI GPT 모델을 활용한 자연스러운 대화
- **🔧 다중 도구 통합**: 날씨, 파일 관리, 문서 검색 등 다양한 MCP 서버 연동
- **🔗 LangChain MCP 어댑터**: `langchain_mcp_adapters`를 통한 표준 MCP 프로토콜 지원
- **🧠 ReAct 패턴**: 복잡한 요청에 대한 단계별 사고 및 행동 처리
- **⚡ 실시간 스트리밍**: SSE를 통한 토큰 단위 응답 스트리밍
- **🌐 웹 UI**: 직관적이고 현대적인 웹 인터페이스
- **📊 세션 관리**: 대화 히스토리 및 컨텍스트 유지
- **🔄 워크플로우 엔진**: LangGraph 기반 상태 관리 및 실행
- **📈 Phoenix 모니터링**: AI 애플리케이션 추적 및 성능 분석 (선택적)

## 🔄 워크플로우 아키텍처

![워크플로우 그래프](docs/workflow_graph.png)

*LangGraph 기반 워크플로우 구조: 사용자 입력부터 최종 응답까지의 전체 처리 흐름*

### 🤖 두 가지 처리 모드

이 시스템은 요청의 복잡성에 따라 두 가지 다른 모드로 동작합니다:

#### 📋 **일반 Tool Calling 모드**
- **단순한 요청**: "서울 날씨 알려줘", "파일 목록 보여줘"
- **직접 처리**: LLM이 바로 적절한 도구를 선택하여 한 번에 호출
- **빠른 응답**: 최소한의 단계로 즉시 결과 제공
- **예시**: 단일 위치 날씨 조회, 특정 파일 정보 확인

#### 🧠 **ReAct 패턴 모드**
- **복잡한 요청**: "서울, 부산, 대구 날씨를 비교해줘"
- **단계별 사고**: Think → Act → Observe 사이클 반복
- **다중 도구 호출**: 여러 도구를 순차적으로 사용하여 정보 수집
- **종합 분석**: 수집된 정보를 바탕으로 최종 답변 생성
- **예시**: 여러 위치 비교, 복합적인 분석 작업


## 🚀 빠른 시작

### 1. 저장소 클론
```bash
git clone <repository-url>
cd MCP_test
```

### 2. 환경 설정
```bash
# 개발 환경 설정 (의존성 설치 + 디렉토리 생성)
make dev

# 환경변수 설정
cp .env_example .env
# .env 파일에서 OPENAI_API_KEY 설정
```

### 3. 서버 실행
```bash
# 개발 모드로 실행
make server

# 또는 백그라운드에서 실행
make run-bg
```

### 4. 웹 UI 접속
브라우저에서 `http://localhost:8000`으로 접속하여 AI와 대화를 시작하세요!

#### 📹 기본 사용법 데모
<video width="800" controls>
  <source src="docs/basic.mov" type="video/quicktime">
  Your browser does not support the video tag.
</video>

*기본적인 웹 UI 사용법과 AI와의 대화 과정을 보여주는 데모 영상입니다. (파일 크기: 31MB)*

#### 📹 ReAct 모드 날씨 검색 데모
<video width="800" controls>
  <source src="docs/react.mov" type="video/quicktime">
  Your browser does not support the video tag.
</video>

*ReAct 패턴을 통한 복합적인 날씨 검색 및 리포트 생성 과정을 보여주는 데모 영상입니다. Think → Act → Observe 사이클을 통해 단계별로 정보를 수집하고 분석합니다. (파일 크기: 105MB)*

### 5. Phoenix 모니터링 
Phoenix를 활성화한 경우, 웹 UI 상단의 "Phoenix UI" 링크를 클릭하여 AI 추적 대시보드에 접속할 수 있습니다.

#### 📹 Phoenix 모니터링 데모
<video width="800" controls>
  <source src="docs/phoenix.mov" type="video/quicktime">
  Your browser does not support the video tag.
</video>

*Phoenix UI를 통한 AI 애플리케이션 추적 및 성능 분석 과정을 보여주는 데모 영상입니다. (파일 크기: 108MB)*

## 📦 설치 및 설정

### 요구사항
- Python 3.11+
- Node.js 18+ (Context7 MCP 서버용)
- OpenAI API 키
- uv (Python 패키지 관리자)
- LangChain MCP Adapters (`langchain_mcp_adapters`)

### 상세 설치 가이드

1. **Python 및 Node.js 환경 준비**
   ```bash
   # Python 3.11+ 확인
   python --version
   
   # Node.js 18+ 확인 (Context7 서버용)
   node --version
   npm --version
   
   # uv 설치 (없는 경우)
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **프로젝트 설정**
   ```bash
   # 의존성 설치
   make install
   
   # 또는 직접 설치
   uv pip install -r requirements.txt
   ```

3. **환경변수 설정**
   ```bash
   cp .env_example .env
   ```
   
   `.env` 파일에서 다음 값들을 설정하세요:
   ```env
   OPENAI_API_KEY=your_openai_api_key_here
   OPENAI_MODEL=gpt-4o-mini
   OPENAI_TEMPERATURE=0.1
   OPENAI_MAX_TOKENS=1000
   MCP_SERVERS_CONFIG=./mcp_servers.json
   
   # Phoenix 모니터링 (선택적)
   PHOENIX_ENABLED=true
   ```

## 🎯 사용법

### 웹 UI 사용
1. 서버 실행: `make server`
2. 브라우저에서 `http://localhost:8000` 접속
3. 채팅창에 메시지 입력
4. AI의 실시간 응답 확인

### 지원되는 요청 예시

#### 📋 일반 Tool Calling 모드
- **날씨 조회**: "서울 날씨 알려줘" (더미 날씨 서버)
- **파일 관리**: "파일 목록 보여줘" (더미 파일 서버)
- **문서 검색**: "React 라이브러리 정보 찾아줘" (Context7 실제 서버)
- **시스템 정보**: "서버 상태 확인해줘", "사용 가능한 도구 목록"

#### 🧠 ReAct 패턴 모드
- **복합 날씨 분석**: "서울, 부산, 대구 날씨를 비교해줘"
- **다중 파일 작업**: "프로젝트 파일들을 분석하고 구조를 설명해줘"
- **종합 정보 수집**: "React와 Vue.js 라이브러리를 비교 분석해줘"

### 현재 구성된 MCP 서버들
이 프로젝트는 다음 3개의 MCP 서버로 구성되어 있습니다:

#### 🧪 더미 서버들 (테스트/데모용)
- **Weather Server** (`examples/dummy_weather_server.py`)
  - 간단한 날씨 정보 제공 (하드코딩된 더미 데이터)
  - 도구: `get_weather`, `get_forecast`
  
- **File Manager** (`examples/dummy_file_server.py`)
  - 기본적인 파일 관리 기능 (읽기 전용)
  - 도구: `list_files`, `read_file`, `file_info`

#### 🌐 실제 서버
- **Context7** (NPM 패키지: `@upstash/context7-mcp`)
  - 실제 라이브러리 문서 검색 및 정보 제공
  - 온라인 문서 데이터베이스 연동
  - 도구: 라이브러리 검색, 문서 조회 등



> 💡 **워크플로우 동작 방식**: 위의 워크플로우 그래프에서 볼 수 있듯이, 복잡한 요청은 ReAct 패턴을 통해 단계별로 처리되며, 각 MCP 서버의 도구들이 필요에 따라 호출됩니다.

### API 엔드포인트

#### 메시지 전송
```bash
curl -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "안녕하세요", "session_id": "test-session"}'
```

#### SSE 스트리밍
```javascript
const eventSource = new EventSource('/api/stream/test-session');
eventSource.onmessage = function(event) {
  const data = JSON.parse(event.data);
  console.log(data);
};
```

## 📁 프로젝트 구조

```
MCP_test/
├── mcp_host/                   # 메인 패키지
│   ├── adapters/              # MCP 클라이언트 어댑터
│   │   └── client.py          # langchain_mcp_adapters 기반 클라이언트
│   ├── config/                # 설정 관리
│   ├── models/                # 데이터 모델
│   ├── services/              # 비즈니스 로직
│   ├── sessions/              # 세션 관리
│   ├── streaming/             # SSE 스트리밍
│   ├── visualize/             # 시각화 도구
│   └── workflows/             # LangGraph 워크플로우
│       ├── nodes.py           # 워크플로우 노드
│       ├── llm_nodes.py       # LLM 기반 노드
│       ├── react_nodes.py     # ReAct 패턴 노드
│       └── graph.py           # 워크플로우 그래프
├── examples/                  # MCP 서버 예제
│   ├── dummy_weather_server.py # 더미 날씨 서버
│   └── dummy_file_server.py   # 더미 파일 관리 서버
├── static/                    # 정적 파일 (CSS, JS)
├── logs/                      # 로그 파일
├── tests/                     # 테스트 코드
├── main.py                    # 서버 진입점
├── mcp_servers.json          # MCP 서버 설정 (3개 서버)
├── Makefile                  # 개발 도구
└── requirements.txt          # 의존성
```

## 🛠️ 개발 가이드

### Makefile 명령어

```bash
# 테스트
make test-basic              # 기본 통합 테스트
make test-pytest            # 전체 pytest 실행

# 서버 관리
make server                 # 개발 모드 실행
make run-bg                 # 백그라운드 실행
make stop-bg                # 백그라운드 서버 중지
make status                 # 서버 상태 확인
make logs                   # 로그 확인

# 코드 품질
make check                  # 전체 품질 검사
make format                 # 코드 포맷팅 (Black)
make lint                   # 린트 검사 (Flake8)

# 유지보수
make clean                  # 캐시 정리
make dev                    # 개발 환경 설정
```

### 테스트 실행
```bash
# 빠른 기본 테스트
make test-basic

# 전체 테스트 (pytest 필요)
make test-pytest
```

### 코드 품질 관리
```bash
# 코드 포맷팅
make format

# 린트 검사
make lint

# 전체 품질 검사 (포맷팅 + 린트 + 테스트)
make check
```

## ⚙️ 설정

### MCP 서버 설정 (`mcp_servers.json`)
현재 프로젝트에서 사용하는 실제 설정:

```json
{
  "weather": {
    "command": "python",
    "args": ["/path/to/MCP_test/examples/dummy_weather_server.py"],
    "transport": "stdio"
  },
  "file-manager": {
    "command": "python", 
    "args": ["/path/to/MCP_test/examples/dummy_file_server.py"],
    "transport": "stdio",
    "env": {
      "PYTHONPATH": "/path/to/MCP_test",
      "SAFE_MODE": "true"
    }
  },
  "context7": {
    "command": "npx",
    "args": [
      "-y",
      "@upstash/context7-mcp@latest"
    ],
    "transport": "stdio"
  }
}
```

#### 서버별 특징:
- **더미 서버들**: Python FastMCP로 구현, 로컬 파일 실행
- **Context7**: NPM 패키지로 설치, 실제 온라인 서비스 연동

### 환경변수 상세 설명

| 변수명 | 설명 | 기본값 | 필수 |
|--------|------|--------|------|
| `OPENAI_API_KEY` | OpenAI API 키 | - | ✅ |
| `OPENAI_MODEL` | 사용할 GPT 모델 | `gpt-4o-mini` | ❌ |
| `OPENAI_TEMPERATURE` | 모델 창의성 (0.0-2.0) | `0.1` | ❌ |
| `OPENAI_MAX_TOKENS` | 최대 토큰 수 | `1000` | ❌ |
| `MCP_SERVERS_CONFIG` | MCP 서버 설정 파일 경로 | `./mcp_servers.json` | ❌ |
| `PHOENIX_ENABLED` | Phoenix 모니터링 활성화 | `false` | ❌ |

## 🔧 트러블슈팅

### 자주 발생하는 문제들

#### 1. OpenAI API 키 오류
```
Error: OpenAI API key not found
```
**해결방법**: `.env` 파일에 올바른 `OPENAI_API_KEY` 설정

#### 2. MCP 서버 연결 실패
```
Error: Failed to connect to MCP server
```
**해결방법**: 
- `mcp_servers.json` 설정 확인 (경로가 절대경로로 설정되어 있는지)
- 더미 서버들: Python 파일이 존재하고 실행 가능한지 확인
- Context7 서버: Node.js와 `npx` 명령어가 사용 가능하고 인터넷 연결이 되어 있는지 확인
- `langchain_mcp_adapters` 패키지가 올바르게 설치되었는지 확인

#### 3. 포트 충돌
```
Error: Port 8000 already in use
```
**해결방법**: 
- 기존 프로세스 종료: `make stop-bg`
- 또는 다른 포트 사용: `PORT=8001 python main.py`

#### 4. 의존성 오류
```
ModuleNotFoundError: No module named 'xxx'
```
**해결방법**: `make install` 또는 `uv pip install -r requirements.txt`

#### 5. Node.js 관련 오류
```
Error: npx command not found
```
**해결방법**: 
- Node.js 18+ 설치: [https://nodejs.org/](https://nodejs.org/)
- macOS: `brew install node`
- Ubuntu: `sudo apt install nodejs npm`
- Windows: Node.js 공식 설치 프로그램 사용

#### 6. Phoenix UI 접속 불가
```
Phoenix UI 링크가 비활성화되어 있음
```
**해결방법**: 
- `.env` 파일에서 `PHOENIX_ENABLED=true` 설정 확인
- 서버 재시작 후 첫 번째 대화 시작 (링크가 자동 활성화됨)
- Phoenix 관련 패키지 설치: `uv pip install arize-phoenix openinference-instrumentation-langchain`

### 로그 확인
```bash
# 실시간 로그 확인
make logs

# 또는 직접 확인
tail -f logs/server.log
```

## 🤝 기여하기

### 개발 환경 설정
1. 저장소 포크
2. 로컬에 클론: `git clone <your-fork>`
3. 개발 환경 설정: `make dev`
4. 브랜치 생성: `git checkout -b feature/your-feature`

### 코딩 스타일
- **포맷팅**: Black (120자 제한)
- **린트**: Flake8
- **타입 힌트**: 모든 함수에 타입 힌트 추가
- **문서화**: Docstring 작성 (Google 스타일)

### Pull Request 가이드라인
1. 코드 품질 검사 통과: `make check`
2. 테스트 추가 및 통과: `make test-basic`
3. 명확한 커밋 메시지 작성
4. PR 설명에 변경사항 상세 기술

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 🔗 관련 링크

- [Model Context Protocol 공식 문서](https://modelcontextprotocol.io/)
- [LangChain MCP Adapters](https://github.com/langchain-ai/langchain/tree/master/libs/community/langchain_community/adapters/mcp)
- [LangGraph 문서](https://langchain-ai.github.io/langgraph/)
- [FastAPI 문서](https://fastapi.tiangolo.com/)
- [OpenAI API 문서](https://platform.openai.com/docs/)
- [Arize Phoenix 문서](https://docs.arize.com/phoenix/) - AI 애플리케이션 모니터링

## 🚀 향후 추가 예정 기능

### 📊 MCP 서버 모니터링 대시보드
- **서버 상태 상세 보기**: 현재 '서버 3개 - 도구 7개' 표시를 클릭하면 상세 정보 확인
  - 각 MCP 서버별 연결 상태 및 초기화 진행 상황
  - 서버별 사용 가능한 도구 목록과 설명
  - 실시간 서버 헬스체크 및 응답 시간
  - 도구별 호출 횟수 및 성공/실패 통계

### 🔍 실시간 데이터 통신 모니터링
- **통합 개발자 뷰**: 챗봇 화면과 동일한 인터페이스에서 데이터 흐름 확인
  - JSON-RPC 요청/응답 실시간 표시
  - MCP 프로토콜 메시지 추적
  - LangGraph 워크플로우 상태 변화 시각화
  - ReAct 패턴 사고 과정 단계별 표시
  - 토큰 사용량 및 API 호출 비용 추적
- **Phoenix 통합 강화**: 현재 별도 창에서 제공되는 Phoenix UI를 메인 인터페이스에 통합

### 🎯 추가 계획 기능
- **커스텀 MCP 서버 추가**: 웹 UI에서 새로운 서버 설정 및 테스트
- **워크플로우 추적 기능**: 실행 중인 LangGraph 노드의 플로우를 실시간으로 추적 및 시각화
- **대화 히스토리 관리**: 세션별 대화 저장 및 검색
---

**Made with ❤️ using LangGraph and MCP** 