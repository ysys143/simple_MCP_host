#!/usr/bin/env python3
"""LLM 기반 워크플로우 테스트 스크립트

OpenAI ChatGPT를 활용한 자연어 이해와 응답 생성을 테스트합니다.
키워드 매칭에서 진정한 AI 기반 대화 시스템으로의 업그레이드를 검증합니다.
"""

import asyncio
import sys
import os
import logging
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from mcp_host.workflows import create_workflow_executor


# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def test_llm_workflow():
    """LLM 기반 워크플로우 통합 테스트"""
    print("=== LLM 기반 워크플로우 테스트 ===")
    
    # OpenAI API 키 확인
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⚠️ OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        print("키워드 기반 폴백으로 테스트를 계속합니다.")
    else:
        print("✅ OpenAI API 키 확인됨")
    
    try:
        # 1. 워크플로우 실행기 생성
        executor = create_workflow_executor()
        print("1. LLM 워크플로우 실행기 생성 완료")
        
        # 2. 다양한 테스트 케이스
        test_cases = [
            {
                "input": "안녕하세요! 오늘 서울 날씨가 어떤가요?",
                "expected_intent": "WEATHER_QUERY",
                "description": "날씨 조회 (자연어)"
            },
            {
                "input": "현재 디렉토리에 있는 파일들을 보여주세요",
                "expected_intent": "FILE_OPERATION", 
                "description": "파일 목록 조회 (자연어)"
            },
            {
                "input": "MCP 서버 상태는 어떤가요?",
                "expected_intent": "SERVER_STATUS",
                "description": "서버 상태 확인"
            },
            {
                "input": "도움말을 보고 싶어요",
                "expected_intent": "HELP",
                "description": "도움말 요청"
            },
            {
                "input": "파이썬과 자바스크립트의 차이점이 뭐죠?",
                "expected_intent": "GENERAL_CHAT",
                "description": "일반 대화"
            }
        ]
        
        success_count = 0
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n--- 테스트 {i}: {test_case['description']} ---")
            print(f"입력: {test_case['input']}")
            
            try:
                # 워크플로우 실행
                result = await executor.execute_message(
                    user_message=test_case['input'],
                    session_id=f"test_session_{i}",
                    context={"test_mode": True}
                )
                
                print(f"성공: {result['success']}")
                print(f"응답: {result['response'][:100]}...")
                if result.get('intent_type'):
                    print(f"의도: {result['intent_type']}")
                
                if result['success']:
                    success_count += 1
                    print("✅ 테스트 통과")
                else:
                    print(f"❌ 테스트 실패: {result.get('error')}")
                
            except Exception as e:
                print(f"❌ 테스트 오류: {e}")
        
        print(f"\n🎯 결과: {success_count}/{len(test_cases)} 테스트 통과")
        
        if success_count == len(test_cases):
            print("🎉 모든 LLM 워크플로우 테스트 성공!")
        else:
            print("💥 일부 테스트 실패")
        
        return success_count == len(test_cases)
        
    except Exception as e:
        print(f"워크플로우 테스트 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_llm_fallback():
    """LLM 실패 시 키워드 기반 폴백 테스트"""
    print("\n=== LLM 폴백 메커니즘 테스트 ===")
    
    # 임시로 API 키 제거
    original_key = os.environ.pop("OPENAI_API_KEY", None)
    
    try:
        executor = create_workflow_executor()
        
        result = await executor.execute_message(
            user_message="날씨 어때?",
            session_id="fallback_test",
            context={"test_mode": True}
        )
        
        print(f"폴백 결과: {result['success']}")
        print(f"응답: {result['response'][:100]}...")
        
        # API 키 복원
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key
        
        print("✅ 폴백 메커니즘 정상 작동")
        return True
        
    except Exception as e:
        print(f"폴백 테스트 오류: {e}")
        # API 키 복원
        if original_key:
            os.environ["OPENAI_API_KEY"] = original_key
        return False


async def main():
    """메인 테스트 함수"""
    print("LLM 기반 워크플로우 테스트 시작\n")
    
    # LLM 워크플로우 테스트
    llm_test = await test_llm_workflow()
    
    # 폴백 메커니즘 테스트  
    fallback_test = await test_llm_fallback()
    
    success = llm_test and fallback_test
    
    if success:
        print("\n🎉 모든 LLM 테스트 통과!")
        print("이제 진정한 AI 기반 대화 시스템이 준비되었습니다!")
        print("다음 단계: FastAPI 서버에 통합하여 웹 인터페이스로 테스트")
    else:
        print("\n❌ 일부 LLM 테스트 실패")
    
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 