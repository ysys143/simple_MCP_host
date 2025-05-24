# LangGraph MCP 호스트 MVP 구현 요구사항 정의서

## 1. 프로젝트 개요

### 1.1 목적
MCP Python SDK와 LangGraph를 사용하여 몇 시간 안에 구현 가능한 **LLM 기반 MCP 호스트 시스템**을 구축한다. OpenAI ChatGPT를 활용한 자연어 이해와 워크플로우 기반 MCP 도구 호출을 통해 사용자가 채팅으로 외부 MCP 서버의 도구들을 자연스럽게 활용할 수 있는 중간 계층을 제공한다.

### 1.2 MVP 범위
- **포함사항**: 
  - LLM 기반 자연어 이해 (OpenAI ChatGPT)
  - 키워드 기반 폴백 시스템
  - Enhanced MCP 클라이언트 (langchain-mcp-adapters)
  - LangGraph 하이브리드 워크플로우
  - 웹 채팅 UI, FastAPI 백엔드
- **외부 의존성**: 별도 레포지토리의 날씨 MCP 서버, OpenAI API
- **제외사항**: 복잡한 워크플로우, Docker, 관찰성, 복잡한 UI, 인증, 데이터베이스

## 2. 기능 요구사항

### 2.1 핵심 기능 (MVP)

#### 2.1.1 LLM 기반 자연어 이해
- **FR-001**: OpenAI ChatGPT를 활용한 사용자 의도 분석
- **FR-002**: 자연어 요청의 매개변수 추출 및 구조화
- **FR-003**: 의도 분류 (날씨, 파일 작업, 서버 상태, 도움말, 일반 대화)
- **FR-004**: LLM 실패 시 키워드 기반 폴백 시스템

#### 2.1.2 Enhanced MCP 호스트 클라이언트
- **FR-005**: langchain-mcp-adapters 기반 MCP 클라이언트 구현
- **FR-006**: 외부 MCP 서버 연결 관리 (stdio 프로토콜)
- **FR-007**: MCP 도구 발견 및 자동 변환 (load_mcp_tools)
- **FR-008**: MCP 도구 호출 및 결과 처리

#### 2.1.3 LangGraph 하이브리드 워크플로우
- **FR-009**: StateGraph 기반 LLM + 키워드 하이브리드 워크플로우
- **FR-010**: LLM 의도 분석 노드 (llm_parse_intent)
- **FR-011**: LLM MCP 도구 호출 노드 (llm_call_mcp_tool)
- **FR-012**: LLM 응답 생성 노드 (llm_generate_response)
- **FR-013**: 키워드 기반 폴백 노드들 (parse_message, call_mcp_tool, generate_response)

#### 2.1.4 웹 채팅 인터페이스
- **FR-014**: 간단한 HTML/JavaScript 채팅 UI
- **FR-015**: WebSocket 기반 실시간 메시지 송수신
- **FR-016**: 연결된 MCP 서버 및 도구 목록 표시

#### 2.1.5 FastAPI 백엔드
- **FR-017**: WebSocket 엔드포인트 (/ws)
- **FR-018**: LangGraph 하이브리드 워크플로우 실행
- **FR-019**: Enhanced MCP Client와 LLM 워크플로우 연결

#### 2.1.6 외부 MCP 서버 연동
- **FR-020**: 설정 파일 기반 MCP 서버 목록 관리
- **FR-021**: 동적 MCP 서버 연결/해제
- **FR-022**: MCP 서버 상태 모니터링

## 3. 시스템 아키텍처

### 3.1 LLM 기반 MCP 호스트 구조
```
웹 브라우저 (채팅 UI)
       ↕ WebSocket
FastAPI 서버 (MCP 호스트)
       ↕ LangGraph 하이브리드 워크플로우
       ├─ LLM 기반 (OpenAI ChatGPT)
       │  ├─ llm_parse_intent
       │  ├─ llm_call_mcp_tool  
       │  └─ llm_generate_response
       └─ 키워드 기반 (폴백)
          ├─ parse_message
          ├─ call_mcp_tool
          └─ generate_response
       ↕ Enhanced MCP Client (langchain-mcp-adapters)
외부 MCP 서버들 (별도 레포)
├── weather-mcp-server
├── file-mcp-server  
└── api-mcp-server
```

### 3.2 레포지토리 구조
```
# 이 레포지토리 (MCP 호스트)
MCP_test/
├── mcp_host/
│   ├── __main__.py          # CLI 엔트리포인트
│   ├── adapters/
│   │   └── enhanced_client.py # Enhanced MCP Client
│   ├── config.py            # MCP 서버 설정
│   ├── models.py            # 데이터 모델 (Pydantic)
│   ├── workflows/
│   │   ├── executor.py      # 하이브리드 워크플로우 실행기
│   │   ├── nodes.py         # 키워드 기반 노드들
│   │   ├── llm_nodes.py     # LLM 기반 노드들
│   │   └── state_utils.py   # 상태 유틸리티
│   ├── services/
│   │   └── app.py           # FastAPI 애플리케이션
│   ├── scripts/
│   │   └── run_tests.py     # 테스트 실행기
│   └── tests/
│       ├── test_config.py
│       ├── test_enhanced_client.py  
│       ├── test_workflow.py
│       └── test_llm_workflow.py     # LLM 테스트
├── static/
│   └── index.html          # 채팅 UI
├── app.py                  # FastAPI 서버 런처
├── main.py                 # uvicorn 서버 런처
├── mcp_servers.json        # MCP 서버 설정
├── requirements.txt
├── Makefile               # 편리한 명령어
└── README.md

# 별도 레포지토리 (예시)
weather-mcp-server/
├── server.py
├── requirements.txt
└── README.md
```

### 3.3 MCP 서버 설정 파일
```json
{
  "servers": {
    "weather": {
      "command": "python",
      "args": ["/path/to/weather-mcp-server/server.py"],
      "env": {}
    },
    "file-manager": {
      "command": "python", 
      "args": ["/path/to/file-mcp-server/server.py"],
      "env": {}
    }
  }
}
```

## 4. 구현 사양

### 4.1 LLM 기반 의도 분석 (llm_nodes.py)
```python
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate

def get_llm() -> ChatOpenAI:
    """ChatOpenAI LLM 인스턴스를 반환합니다 (싱글톤)"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다")
    
    return ChatOpenAI(
        model="gpt-4o-mini",  # 빠르고 경제적인 모델
        temperature=0.1,      # 일관된 응답
        max_tokens=1000,      # 적절한 응답 길이
    )

def llm_parse_intent(state: ChatState) -> ChatState:
    """LLM을 사용하여 사용자 의도를 분석합니다"""
    user_input = state["current_message"].content
    
    # 의도 분석 프롬프트
    intent_prompt = ChatPromptTemplate.from_messages([
        ("system", """사용자 요청을 분석하여 의도를 파악하세요:
1. WEATHER_QUERY: 날씨 관련 질문
2. FILE_OPERATION: 파일/디렉토리 작업
3. SERVER_STATUS: MCP 서버 상태 확인
4. TOOL_LIST: 사용 가능한 도구 목록 요청
5. HELP: 도움말이나 사용법 문의
6. GENERAL_CHAT: 일반적인 대화

응답 형식:
INTENT: [의도]
CONFIDENCE: [0.0-1.0 신뢰도]
PARAMETERS: [JSON 형식 매개변수]
REASONING: [분류 근거]"""),
        ("human", "{user_input}")
    ])
    
    llm = get_llm()
    response = (intent_prompt | llm).invoke({"user_input": user_input})
    
    # 응답 파싱하여 ParsedIntent 생성
    parsed_intent = _parse_llm_intent_response(response.content, user_input)
    state["parsed_intent"] = parsed_intent
    
    # 다음 단계 결정
    if parsed_intent.is_mcp_action():
        state["next_step"] = "llm_call_mcp_tool"
    else:
        state["next_step"] = "llm_generate_response"
    
    return state
```

### 4.2 Enhanced MCP Client (enhanced_client.py)
```python
from langchain_mcp_adapters import MultiServerMCPClient
from mcp_host.config import create_config_manager

class EnhancedMCPClient:
    """langchain-mcp-adapters 기반 향상된 MCP 클라이언트"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.mcp_client = None
        self.available_tools = {}
    
    async def connect(self):
        """모든 설정된 MCP 서버에 연결"""
        server_configs = self.config_manager.get_all_server_configs()
        
        # MultiServerMCPClient 초기화
        self.mcp_client = MultiServerMCPClient()
        
        for server_name, config in server_configs.items():
            try:
                await self.mcp_client.add_server(
                    server_name,
                    command=config["command"],
                    args=config["args"]
                )
                logger.info(f"✅ {server_name} 서버 연결 성공")
            except Exception as e:
                logger.error(f"❌ {server_name} 서버 연결 실패: {e}")
        
        # 사용 가능한 도구 로드
        await self._load_available_tools()
    
    async def _load_available_tools(self):
        """사용 가능한 도구 목록을 로드합니다"""
        from langchain_mcp_adapters import load_mcp_tools
        
        try:
            tools = await load_mcp_tools(self.mcp_client)
            self.available_tools = {tool.name: tool for tool in tools}
            logger.info(f"로드된 도구: {list(self.available_tools.keys())}")
        except Exception as e:
            logger.error(f"도구 로드 실패: {e}")
```

### 4.3 하이브리드 워크플로우 (executor.py)
```python
from langgraph.graph import StateGraph, END
from .nodes import parse_message, call_mcp_tool, generate_response
from .llm_nodes import llm_parse_intent, llm_call_mcp_tool, llm_generate_response

def create_workflow_executor() -> MCPWorkflowExecutor:
    """LLM과 키워드 기반 하이브리드 워크플로우 생성"""
    workflow = StateGraph(ChatState)
    
    # === LLM 기반 노드들 (기본) ===
    workflow.add_node("llm_parse_intent", llm_parse_intent)
    workflow.add_node("llm_call_mcp_tool", llm_call_mcp_tool) 
    workflow.add_node("llm_generate_response", llm_generate_response)
    
    # === 키워드 기반 노드들 (폴백용) ===
    workflow.add_node("parse_message", parse_message)
    workflow.add_node("call_mcp_tool", call_mcp_tool)
    workflow.add_node("generate_response", generate_response)
    
    # === 진입점과 흐름 설정 ===
    workflow.set_entry_point("llm_parse_intent")  # LLM 우선 시도
    
    # LLM 기반 흐름
    workflow.add_conditional_edges(
        "llm_parse_intent",
        _decide_next_step,
        {
            "llm_call_mcp_tool": "llm_call_mcp_tool",
            "llm_generate_response": "llm_generate_response", 
            "parse_message": "parse_message",  # 폴백
        }
    )
    
    workflow.add_edge("llm_call_mcp_tool", "llm_generate_response")
    workflow.add_edge("llm_generate_response", END)
    
    # 키워드 기반 폴백 흐름
    workflow.add_conditional_edges(
        "parse_message",
        _decide_next_step,
        {
            "call_mcp_tool": "call_mcp_tool",
            "generate_response": "generate_response",
        }
    )
    
    workflow.add_edge("call_mcp_tool", "generate_response")
    workflow.add_edge("generate_response", END)
    
    return MCPWorkflowExecutor(workflow.compile())
```

### 4.4 FastAPI 호스트 (services/app.py)
```python
from fastapi import FastAPI, WebSocket
from mcp_host.workflows import create_workflow_executor
from mcp_host.adapters.enhanced_client import EnhancedMCPClient

class MCPHostApp:
    """MCP 호스트 FastAPI 애플리케이션"""
    
    def __init__(self):
        self.app = FastAPI(title="LangGraph MCP 호스트")
        self.mcp_client = None
        self.workflow_executor = None
        
    async def startup(self):
        """애플리케이션 시작 시 초기화"""
        # Enhanced MCP Client 초기화
        config_manager = create_config_manager()
        self.mcp_client = EnhancedMCPClient(config_manager)
        await self.mcp_client.connect()
        
        # LLM 하이브리드 워크플로우 실행기 생성
        self.workflow_executor = create_workflow_executor()
        
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        
        while True:
            message = await websocket.receive_text()
            
            # 하이브리드 워크플로우 실행
            result = await self.workflow_executor.execute_message(
                user_message=message,
                session_id="websocket_session",
                mcp_client=self.mcp_client
            )
            
            await websocket.send_text(result["response"])
```

### 4.5 프론트엔드 (static/index.html)
```html
<!DOCTYPE html>
<html>
<head>
    <title>LangGraph MCP 호스트 (LLM 기반)</title>
    <style>
        body { 
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
            margin: 0; padding: 20px; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        .container {
            max-width: 800px; margin: 0 auto;
            background: white; border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            overflow: hidden;
        }
        .header {
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            color: white; padding: 20px; text-align: center;
        }
        #messages { 
            height: 400px; overflow-y: auto; 
            padding: 20px; background: #f8f9fa;
        }
        .message {
            margin: 10px 0; padding: 12px;
            border-radius: 8px; max-width: 80%;
        }
        .user-message { 
            background: #007bff; color: white;
            margin-left: auto; text-align: right;
        }
        .bot-message { 
            background: #e9ecef; color: #333;
        }
        .input-area {
            padding: 20px; background: white;
            border-top: 1px solid #dee2e6;
        }
        #messageInput { 
            width: calc(100% - 100px); padding: 12px;
            border: 2px solid #dee2e6; border-radius: 25px;
            font-size: 14px; outline: none;
        }
        #messageInput:focus { border-color: #007bff; }
        button { 
            width: 80px; padding: 12px; margin-left: 10px;
            background: #007bff; color: white; border: none;
            border-radius: 25px; cursor: pointer; font-weight: bold;
        }
        button:hover { background: #0056b3; }
        .commands {
            padding: 15px 20px; background: #fff3cd;
            border-top: 1px solid #ffeaa7; font-size: 13px;
        }
        .commands h4 { margin: 0 0 10px 0; color: #856404; }
        .command { 
            display: inline-block; margin: 3px 8px 3px 0;
            padding: 4px 8px; background: #007bff; color: white;
            border-radius: 12px; cursor: pointer; font-size: 12px;
        }
        .command:hover { background: #0056b3; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 LangGraph MCP 호스트</h1>
            <p>ChatGPT 기반 자연어 이해 + MCP 도구 호출</p>
        </div>
        
        <div id="messages"></div>
        
        <div class="input-area">
            <input id="messageInput" type="text" 
                   placeholder="자연어로 요청해보세요... (예: 서울 날씨 알려줘)">
            <button onclick="sendMessage()">전송</button>
        </div>
        
        <div class="commands">
            <h4>💡 명령어 예시 (클릭해서 사용):</h4>
            <span class="command" onclick="sendCommand('안녕하세요! 오늘 서울 날씨가 어떤가요?')">날씨 조회</span>
            <span class="command" onclick="sendCommand('현재 디렉토리 파일 목록을 보여주세요')">파일 목록</span>
            <span class="command" onclick="sendCommand('/servers')">서버 목록</span>
            <span class="command" onclick="sendCommand('/tools')">도구 목록</span>
            <span class="command" onclick="sendCommand('도움말 부탁드려요')">도움말</span>
        </div>
    </div>
    
    <script>
        const ws = new WebSocket('ws://localhost:8000/ws');
        const messages = document.getElementById('messages');
        
        ws.onmessage = function(event) {
            addMessage(event.data, 'bot');
        };
        
        function addMessage(text, sender) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${sender}-message`;
            messageDiv.innerHTML = text.replace(/\n/g, '<br>');
            messages.appendChild(messageDiv);
            messages.scrollTop = messages.scrollHeight;
        }
        
        function sendMessage() {
            const input = document.getElementById('messageInput');
            if (input.value.trim() === '') return;
            
            addMessage(input.value, 'user');
            ws.send(input.value);
            input.value = '';
        }
        
        function sendCommand(command) {
            document.getElementById('messageInput').value = command;
            sendMessage();
        }
        
        document.getElementById('messageInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') sendMessage();
        });
    </script>
</body>
</html>
```

## 5. 개발 일정 (4-5시간)

### 5.1 30분: MCP 서버 설정 시스템 ✅ 완료
- config.py 및 mcp_servers.json 구현
- 외부 MCP 서버 연결 로직

### 5.2 1시간: Enhanced MCP 클라이언트 ✅ 완료  
- langchain-mcp-adapters 통합
- 다중 서버 연결 관리
- 자동 도구 로드 및 변환

### 5.3 2시간: LLM 기반 하이브리드 워크플로우 ✅ 완료
- LLM 노드 구현 (의도 분석, 도구 호출, 응답 생성)
- 키워드 기반 폴백 시스템
- StateGraph 하이브리드 워크플로우 구성

### 5.4 1시간: FastAPI 백엔드 🚀 진행중
- WebSocket 엔드포인트
- LLM 워크플로우 실행 연결

### 5.5 30분: 프론트엔드 & 통합
- 현대적 HTML/JavaScript 채팅 UI
- 전체 시스템 통합 테스트

## 6. 기술 스택

### 6.1 MCP 호스트
- **Python 3.11+**
- **OpenAI API**: ChatGPT LLM 통합 (gpt-4o-mini)
- **langchain-openai**: LLM 인터페이스
- **langchain-mcp-adapters**: Enhanced MCP 클라이언트  
- **LangGraph**: 하이브리드 워크플로우 관리
- **FastAPI**: WebSocket 지원
- **uvicorn**: ASGI 서버
- **Pydantic**: 데이터 검증 및 타입 안전성

### 6.2 외부 MCP 서버
- **별도 레포지토리**: weather-mcp-server 등
- **FastMCP**: MCP 서버 구현
- **stdio 프로토콜**: 서버 통신

### 6.3 의존성
```txt
# requirements.txt
mcp>=1.9.1
langchain>=0.3.25
langchain-core>=0.3.61
langchain-openai>=0.3.18      # LLM 통합
langchain-mcp-adapters>=0.1.1  # Enhanced MCP Client
langgraph>=0.4.7
fastapi>=0.115.12
uvicorn>=0.34.2
pydantic>=2.11.5
pydantic-settings>=2.9.1
```

## 7. 실행 방법

```bash
# 1. 환경 설정
export OPENAI_API_KEY="your-openai-api-key-here"

# 2. 의존성 설치 
uv pip install -r requirements.txt

# 3. MCP 서버 설정
# mcp_servers.json에서 외부 MCP 서버 경로 설정

# 4. MCP 호스트 실행
python -m mcp_host server
# 또는
make server

# 5. 테스트 실행
python -m mcp_host test
# 또는  
make test

# 6. LLM 워크플로우 테스트
python mcp_host/tests/test_llm_workflow.py

# 7. 프론트엔드 접속
# http://localhost:8000/static/index.html
```

## 8. 데모 시나리오

### 8.1 LLM 기반 자연어 대화
1. 웹 브라우저에서 `localhost:8000/static/index.html` 접속
2. **"안녕하세요! 오늘 서울 날씨가 어떤가요?"** 입력
   - LLM이 WEATHER_QUERY 의도로 분석
   - weather.get_weather 도구 자동 호출
   - 자연스러운 한국어 응답 생성
3. **"현재 디렉토리에 있는 파일들을 보여주세요"** 입력
   - LLM이 FILE_OPERATION 의도로 분석  
   - file-manager.list_files 도구 자동 호출
4. **"파이썬과 자바스크립트의 차이점이 뭐죠?"** 입력
   - LLM이 GENERAL_CHAT으로 분류
   - ChatGPT가 직접 답변 생성

### 8.2 폴백 시스템 테스트
1. OpenAI API 키 없이 실행
2. 키워드 기반 시스템으로 자동 폴백
3. 기본 기능은 계속 동작

## 9. 확장 계획 (MVP 이후)

- **더 많은 MCP 서버**: 파일, API, 데이터베이스 등
- **컨텍스트 기반 대화**: 대화 히스토리 관리
- **멀티 모달**: 이미지, 음성 지원
- **고급 워크플로우**: 조건부 분기, 멀티 도구 체이닝
- **다른 LLM 지원**: Anthropic Claude, Google Gemini 등
- **React UI**: 현대적 프론트엔드
- **Docker 컨테이너화**

## 10. 결론

이 MVP는 **OpenAI ChatGPT를 활용한 자연어 이해**와 **langchain-mcp-adapters 기반 Enhanced MCP Client**를 통해 사용자가 자연어로 외부 MCP 서버들과 상호작용할 수 있는 지능형 호스트 시스템입니다. LLM 기반과 키워드 기반의 하이브리드 아키텍처로 안정성과 확장성을 모두 확보했습니다.
