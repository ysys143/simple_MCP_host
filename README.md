# LangGraph MCP 호스트 구현

이 프로젝트는 LangGraph를 사용하여 Model Context Protocol(MCP) 호스트를 구현하는 예제입니다.

## 프로젝트 구조

```
MCP_test/
├── mcp_host/
│   ├── __init__.py
│   ├── protocols/          # MCP 프로토콜 인터페이스
│   ├── adapters/          # 외부 시스템 어댑터
│   ├── workflows/         # LangGraph 워크플로우
│   └── services/          # 비즈니스 로직 서비스
├── examples/              # 사용 예제
├── tests/                 # 테스트 코드
└── requirements.txt
```

## MCP 호스트의 핵심 기능

1. **리소스 관리**: 외부 리소스와의 연결 및 관리
2. **도구 통합**: 다양한 도구들의 통합 인터페이스
3. **워크플로우 실행**: LangGraph 기반 상태 관리 및 실행
4. **컨텍스트 제공**: AI 모델에게 적절한 컨텍스트 제공

## 설치 및 실행

```bash
pip install -r requirements.txt
python -m mcp_host.main
```

## 참고 자료

- [MCP 공식 문서](https://modelcontextprotocol.io/)
- [LangGraph 문서](https://langchain-ai.github.io/langgraph/)
- [Anthropic MCP GitHub](https://github.com/modelcontextprotocol) 