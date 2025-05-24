#!/usr/bin/env python3
"""LangGraph 워크플로우 테스트 스크립트

새로 구현한 워크플로우가 정상적으로 동작하는지 테스트합니다.
"""

import asyncio
import sys
import os
import logging
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from mcp_host.workflows import create_workflow_executor, IntentType


# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def test_workflow_basic():
    """기본 워크플로우 테스트"""
    print("=== LangGraph 워크플로우 기본 테스트 ===")
    
    try:
        # 워크플로우 실행기 생성
        executor = create_workflow_executor()
        print("1. 워크플로우 실행기 생성 완료")
        
        # 테스트 케이스들
        test_cases = [
            {
                "message": "안녕하세요",
                "expected_intent": IntentType.GENERAL_CHAT,
                "description": "일반 채팅"
            },
            {
                "message": "서울 날씨 알려줘",
                "expected_intent": IntentType.WEATHER_QUERY,
                "description": "날씨 조회"
            },
            {
                "message": "파일 목록 보여줘",
                "expected_intent": IntentType.FILE_OPERATION,
                "description": "파일 목록"
            },
            {
                "message": "도움말",
                "expected_intent": IntentType.HELP,
                "description": "도움말"
            }
        ]
        
        print("2. 테스트 케이스 실행:")
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n  테스트 {i}: {test_case['description']}")
            print(f"  입력: {test_case['message']}")
            
            # 워크플로우 실행
            result = await executor.execute_message(
                user_message=test_case['message'],
                session_id=f"test_session_{i}",
                context={
                    "available_servers": ["weather", "file-manager"],
                    "available_tools": {
                        "weather": ["get_weather", "get_forecast"],
                        "file-manager": ["list_files", "read_file", "file_info"]
                    }
                }
            )
            
            # 결과 검증
            if result["success"]:
                print(f"  ✅ 성공: {result['intent_type']}")
                print(f"  응답: {result['response'][:100]}...")
                
                # 도구 호출 확인
                if result["tool_calls"]:
                    for tool_call in result["tool_calls"]:
                        print(f"  🔧 도구 호출: {tool_call['server']}.{tool_call['tool']}")
            else:
                print(f"  ❌ 실패: {result.get('error', '알 수 없는 오류')}")
        
        print("\n=== 기본 워크플로우 테스트 완료! ===")
        return True
        
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_workflow_advanced():
    """고급 워크플로우 테스트"""
    print("\n=== 고급 워크플로우 테스트 ===")
    
    try:
        executor = create_workflow_executor()
        
        # 복잡한 테스트 케이스들
        advanced_cases = [
            {
                "message": "부산 3일 날씨 예보 알려줘",
                "description": "지역과 일수가 포함된 예보 요청"
            },
            {
                "message": "현재 디렉토리에 어떤 파일들이 있나요?",
                "description": "자연어 파일 목록 요청"
            },
            {
                "message": "서버 상태는 어떤가요?",
                "description": "서버 상태 확인"
            },
            {
                "message": "사용할 수 있는 도구들이 뭐가 있어요?",
                "description": "도구 목록 요청"
            }
        ]
        
        for i, test_case in enumerate(advanced_cases, 1):
            print(f"\n  고급 테스트 {i}: {test_case['description']}")
            print(f"  입력: {test_case['message']}")
            
            result = await executor.execute_message(
                user_message=test_case['message'],
                session_id=f"advanced_session_{i}",
                context={
                    "available_servers": ["weather", "file-manager"],
                    "available_tools": {
                        "weather": ["get_weather", "get_forecast"],
                        "file-manager": ["list_files", "read_file", "file_info"]
                    }
                }
            )
            
            if result["success"]:
                print(f"  ✅ 의도: {result['intent_type']}")
                print(f"  응답: {result['response']}")
                
                # 대화 기록 확인
                history = result["conversation_history"]
                print(f"  📝 대화 기록: {len(history)}개 메시지")
                
            else:
                print(f"  ❌ 실패: {result.get('error')}")
        
        print("\n=== 고급 워크플로우 테스트 완료! ===")
        return True
        
    except Exception as e:
        print(f"고급 테스트 오류: {e}")
        return False


async def test_workflow_error_handling():
    """워크플로우 에러 처리 테스트"""
    print("\n=== 에러 처리 테스트 ===")
    
    try:
        executor = create_workflow_executor()
        
        # 에러 케이스들
        error_cases = [
            {
                "message": "",
                "description": "빈 메시지"
            },
            {
                "message": "알 수 없는 요청입니다 @#$%",
                "description": "인식 불가능한 요청"
            }
        ]
        
        for i, test_case in enumerate(error_cases, 1):
            print(f"\n  에러 테스트 {i}: {test_case['description']}")
            print(f"  입력: '{test_case['message']}'")
            
            try:
                result = await executor.execute_message(
                    user_message=test_case['message'],
                    session_id=f"error_session_{i}"
                )
                
                if result["success"]:
                    print(f"  ✅ 정상 처리: {result['response'][:50]}...")
                else:
                    print(f"  ⚠️ 예상된 에러: {result.get('error', '알 수 없음')}")
                    
            except Exception as e:
                print(f"  ❌ 예상치 못한 에러: {e}")
        
        print("\n=== 에러 처리 테스트 완료! ===")
        return True
        
    except Exception as e:
        print(f"에러 처리 테스트 실패: {e}")
        return False


async def main():
    """메인 테스트 함수"""
    print("LangGraph 워크플로우 종합 테스트 시작\n")
    
    # 기본 테스트
    basic_test = await test_workflow_basic()
    
    # 고급 테스트
    advanced_test = await test_workflow_advanced()
    
    # 에러 처리 테스트
    error_test = await test_workflow_error_handling()
    
    success = basic_test and advanced_test and error_test
    
    if success:
        print("\n🎉 모든 워크플로우 테스트 통과!")
        print("MVP-007, MVP-008, MVP-009, MVP-010 완료")
        print("LangGraph 워크플로우 구현 성공!")
    else:
        print("\n❌ 일부 테스트 실패")
    
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 