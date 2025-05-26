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

### 4. JSON-RPC 호출 로깅 (신규)

**목표**: MCP 도구 호출 시 주고받는 JSON-RPC 메시지를 로그 파일로 저장하여 디버깅 및 분석 용이성 확보

**핵심 요구사항**:
- `mcp_host`가 외부 MCP 서버와 통신하는 모든 JSON-RPC 요청 및 응답 로깅
- 로그 파일 위치: `logs/mcp_json_rpc.log`
- 로그 정보: 타임스탬프, 세션 ID, 방향 (REQUEST/RESPONSE), 전체 JSON-RPC 객체
- Python의 `logging` 모듈 사용

## 구현 계획

### Phase 1: SSE 스트리밍 (2일)
```