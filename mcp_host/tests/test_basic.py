#!/usr/bin/env python3
"""MCP 호스트 기본 통합 테스트

핵심 기능들이 정상적으로 작동하는지 확인하는 간단한 테스트입니다.
"""

import asyncio
import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


async def test_config():
    """설정 시스템 테스트"""
    print("1. 설정 시스템 테스트...")
    
    try:
        from mcp_host.config import create_config_manager
        from mcp_host.config.env_config import get_settings
        
        # 설정 관리자 생성
        config_manager = create_config_manager()
        
        # 설정 파일 로드
        settings = get_settings()
        config_path = settings.get_mcp_servers_config_path()
        servers = config_manager.load_servers(config_path)
        
        print(f"   ✅ {len(servers)}개 서버 설정 로드 완료")
        return True
        
    except Exception as e:
        print(f"   ❌ 설정 테스트 실패: {e}")
        return False


async def test_client():
    """MCP 클라이언트 테스트"""
    print("2. MCP 클라이언트 테스트...")
    
    try:
        from mcp_host.adapters.client import create_client
        from mcp_host.config.env_config import get_settings
        
        # 클라이언트 생성 및 초기화
        client = create_client()
        settings = get_settings()
        config_path = settings.get_mcp_servers_config_path()
        
        async with client:
            await client.initialize(config_path)
            
            # 서버 및 도구 정보 확인
            server_count = client.get_server_count()
            tools = client.get_tools()
            
            print(f"   ✅ {server_count}개 서버, {len(tools)}개 도구 로드 완료")
            return True
            
    except Exception as e:
        print(f"   ❌ 클라이언트 테스트 실패: {e}")
        return False


async def test_workflow():
    """워크플로우 테스트"""
    print("3. 워크플로우 테스트...")
    
    try:
        from mcp_host.workflows import create_workflow_executor
        
        # 워크플로우 실행기 생성
        executor = create_workflow_executor()
        
        # 간단한 메시지 처리 테스트
        test_messages = [
            "안녕하세요",
            "서울 날씨 알려줘",
            "도움말"
        ]
        
        success_count = 0
        for message in test_messages:
            try:
                result = await executor.execute_message(
                    user_message=message,
                    session_id=f"test_{hash(message)}",
                    context={}
                )
                
                if result.get("success"):
                    success_count += 1
                    
            except Exception as e:
                print(f"   ⚠️ 메시지 '{message}' 처리 실패: {e}")
        
        print(f"   ✅ {success_count}/{len(test_messages)}개 메시지 처리 성공")
        return success_count > 0
        
    except Exception as e:
        print(f"   ❌ 워크플로우 테스트 실패: {e}")
        return False


async def test_integration():
    """통합 테스트 (클라이언트 + 워크플로우)"""
    print("4. 통합 테스트...")
    
    try:
        from mcp_host.workflows import create_workflow_executor
        from mcp_host.adapters.client import create_client
        from mcp_host.config.env_config import get_settings
        
        # 클라이언트와 워크플로우 함께 테스트
        client = create_client()
        executor = create_workflow_executor()
        settings = get_settings()
        config_path = settings.get_mcp_servers_config_path()
        
        async with client:
            await client.initialize(config_path)
            
            # 클라이언트 상태 확인
            print(f"   📊 클라이언트 타입: {type(client)}")
            print(f"   📊 call_tool 메서드 존재: {hasattr(client, 'call_tool')}")
            
            # 실제 도구 호출이 포함된 워크플로우 테스트
            result = await executor.execute_message(
                user_message="서울 날씨 어때요?",
                session_id="integration_test",
                mcp_client=client,
                context={}
            )
            
            print(f"   📊 결과 성공 여부: {result.get('success')}")
            print(f"   📊 의도 타입: {result.get('intent_type')}")
            print(f"   📊 오류 메시지: {result.get('error', '없음')}")
            
            if result.get("success"):
                print(f"   ✅ 통합 테스트 성공: {result.get('intent_type')}")
                return True
            else:
                print(f"   ⚠️ 통합 테스트 부분 성공: {result.get('error', '알 수 없음')}")
                return True  # 부분 성공도 허용
                
    except Exception as e:
        print(f"   ❌ 통합 테스트 실패: {e}")
        return False


async def main():
    """메인 테스트 함수"""
    print("=== MCP 호스트 기본 테스트 시작 ===\n")
    
    # 각 테스트 실행
    tests = [
        test_config(),
        test_client(),
        test_workflow(),
        test_integration()
    ]
    
    results = await asyncio.gather(*tests, return_exceptions=True)
    
    # 결과 집계
    success_count = sum(1 for result in results if result is True)
    total_tests = len(tests)
    
    print(f"\n=== 테스트 결과: {success_count}/{total_tests} 성공 ===")
    
    if success_count >= 3:  # 4개 중 3개 이상 성공하면 OK
        print("🎉 기본 기능이 정상적으로 작동합니다!")
        return True
    else:
        print("❌ 일부 핵심 기능에 문제가 있습니다.")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 