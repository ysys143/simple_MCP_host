# MCP 호스트 v0.3 기능 명세서

## 개요

현재 동작하는 MCP 호스트에 3가지 핵심 기능을 추가합니다:

1. **멀티턴 대화**: 세션 기반 대화 컨텍스트 유지
2. **SSE 스트리밍**: 실시간 응답 스트리밍  
3. **ReAct 패턴**: 추론-행동-관찰 사이클

## 현재 상태

```
✅ 기본 FastAPI + LangGraph 워크플로우 동작
✅ MCP 클라이언트 연동 완료
✅ 단일 요청-응답 처리 가능
```

## 추가할 기능

### 1. 멀티턴 대화

**목표**: 이전 대화 내용을 기억하는 연속 대화

**핵심 요구사항**:
- 세션 ID로 대화 추적
- 최대 50턴까지 컨텍스트 유지
- 30분 비활성 시 세션 만료

**API 변경**:
```python
# 기존
POST /chat
{"message": "안녕"}

# 새로 추가
POST /chat  
{"message": "안녕", "session_id": "sess_123"}
```

### 2. SSE 스트리밍

**목표**: 응답을 실시간으로 스트리밍

**핵심 요구사항**:
- 응답 생성 과정을 실시간 전송
- 연결 끊김 시 자동 재연결
- 최대 50개 동시 연결

**새 API**:
```python
POST /api/v3/chat/stream
{"message": "날씨 알려줘", "session_id": "sess_123"}

# SSE 응답:
data: {"type": "thinking", "content": "위치를 확인하겠습니다"}
data: {"type": "acting", "content": "날씨 도구 호출 중"}  
data: {"type": "response", "content": "서울은 현재 맑습니다"}
```

### 3. ReAct 패턴

**목표**: AI가 단계별로 사고하고 행동하는 과정 노출

**핵심 요구사항**:
- Think(추론) → Act(행동) → Observe(관찰) 반복
- 최대 5회 반복 제한
- 각 단계를 SSE로 스트리밍

**동작 예시**:
```
사용자: "내일 서울 날씨 좋으면 공원 추천해줘"

1. Think: "날씨 확인 후 공원 정보가 필요하겠습니다"
2. Act: weather.get_forecast(location="서울", days=1) 
3. Observe: "내일 서울은 맑음 예상"
4. Think: "날씨가 좋으니 공원을 추천해야겠습니다"
5. Act: "한강공원, 남산공원을 추천드립니다"
```

## 구현 계획

### Phase 1: SSE 스트리밍 (2일)
```
mcp_host/streaming/
├── message_types.py    # 스트림 메시지 타입
├── sse_manager.py      # SSE 연결 관리  
└── stream_handler.py   # 스트리밍 처리
```

### Phase 2: 멀티턴 세션 (1일)  
```
mcp_host/sessions/
├── session_manager.py  # 세션 생명주기
├── memory_store.py     # 메모리 기반 저장소
└── context_manager.py  # 대화 컨텍스트
```

### Phase 3: ReAct 패턴 (2일)
```
mcp_host/react/
├── react_executor.py   # ReAct 실행기
├── reasoning_node.py   # 추론 노드
├── action_node.py      # 행동 노드
└── observation_node.py # 관찰 노드
```

## 성공 기준

- ✅ 세션으로 대화 연결 가능
- ✅ SSE로 실시간 응답 받기 가능  
- ✅ ReAct 과정이 단계별로 노출됨
- ✅ 기존 기능 정상 동작 유지

## 제외 사항

- 복잡한 보안 기능 (기본 CORS만)
- 고급 성능 최적화 (기본 동작에 집중)
- 데이터베이스 연동 (메모리 저장소 사용)
- 복잡한 UI (기본 테스트 가능한 수준)
