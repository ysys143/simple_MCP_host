#!/usr/bin/env python3
"""LLM 기반 하이브리드 워크플로우 통합 테스트

실제 OpenAI API를 사용하여 LLM 기능을 테스트합니다.
"""

import asyncio
import os
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

async def test_llm_workflow():
    """LLM 기반 워크플로우 전체 테스트"""
    print("🤖 LLM 기반 하이브리드 워크플로우 테스트 시작")
    print("=" * 50)
    
    try:
        from mcp_host.workflows.executor import create_workflow_executor
        from mcp_host.adapters.client import create_client
        from mcp_host.config import create_config_manager
        
        # MCP 클라이언트 초기화
        print("1. MCP 클라이언트 초기화...")
        config_manager = create_config_manager()
        client = create_client(config_manager)
        await client.initialize("mcp_servers.json")
        print(f"✅ MCP 클라이언트 준비 완료: {client.get_server_count()}개 서버, {len(client.get_tools())}개 도구")
        
        # 워크플로우 실행기 생성
        print("\n2. LLM 하이브리드 워크플로우 생성...")
        executor = create_workflow_executor()
        print("✅ 워크플로우 실행기 준비 완료")
        
        # 테스트 시나리오들
        test_cases = [
            {
                "name": "🌤️ 자연어 날씨 질문",
                "input": "안녕하세요! 오늘 서울 날씨가 어떤가요?",
                "expected_intent": "WEATHER_QUERY"
            },
            {
                "name": "📁 자연어 파일 질문", 
                "input": "현재 디렉토리에 있는 파일들을 보여주세요",
                "expected_intent": "FILE_OPERATION"
            },
            {
                "name": "💬 일반 대화",
                "input": "파이썬과 자바스크립트의 차이점이 뭔가요?",
                "expected_intent": "GENERAL_CHAT"
            },
            {
                "name": "🌧️ 구체적인 예보 요청",
                "input": "부산 3일 날씨 예보 알려주세요",
                "expected_intent": "WEATHER_QUERY"
            }
        ]
        
        print(f"\n3. {len(test_cases)}개 테스트 시나리오 실행...")
        print("-" * 50)
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n[테스트 {i}] {test_case['name']}")
            print(f"입력: {test_case['input']}")
            
            try:
                result = await executor.execute_message(
                    user_message=test_case['input'],
                    session_id=f"test_{i}",
                    mcp_client=client
                )
                
                if result.get("success"):
                    print(f"✅ 성공: {result.get('intent_type', 'Unknown')}")
                    response = result.get('response', 'No response')
                    print(f"응답: {response[:100]}..." if len(response) > 100 else f"응답: {response}")
                    if result.get('tool_calls'):
                        print(f"도구 호출: {len(result['tool_calls'])}개")
                        for tool_call in result['tool_calls']:
                            print(f"  - {tool_call['server']}.{tool_call['tool']}")
                else:
                    print(f"❌ 실패: {result.get('error', 'Unknown error')}")
                    
            except Exception as e:
                print(f"❌ 오류: {e}")
                import traceback
                traceback.print_exc()
            
            print("-" * 30)
        
        print("\n4. LLM vs 키워드 비교 테스트...")
        
        # 같은 질문을 LLM과 키워드 방식으로 처리해보기
        test_input = "서울 날씨"
        print(f"입력: {test_input}")
        
        try:
            result = await executor.execute_message(
                user_message=test_input,
                session_id="comparison_test",
                mcp_client=client
            )
            
            response = result.get('response', '')
            print(f"결과: {result.get('intent_type')} - {response[:80]}..." if len(response) > 80 else f"결과: {result.get('intent_type')} - {response}")
            
        except Exception as e:
            print(f"❌ 비교 테스트 오류: {e}")
        
        # 정리
        await client.close()
        print("\n🎉 LLM 하이브리드 워크플로우 테스트 완료!")
        
    except Exception as e:
        print(f"❌ 전체 테스트 실패: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # OpenAI API 키 확인
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        print("💡 .env 파일을 확인하세요.")
        exit(1)
    
    print(f"🔑 OpenAI API 키: {os.getenv('OPENAI_API_KEY')[:10]}...")
    
    # 테스트 실행
    asyncio.run(test_llm_workflow()) 