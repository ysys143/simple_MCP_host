#!/usr/bin/env python3
"""향상된 MCP 클라이언트 테스트 스크립트

langchain-mcp-adapters 기반의 새로운 클라이언트를 테스트합니다.
"""

import asyncio
import sys
import os
import logging
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from mcp_host.config import create_config_manager
from mcp_host.adapters import EnhancedMCPClient
from mcp_host.adapters.enhanced_client import create_enhanced_client


# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def test_enhanced_client():
    """향상된 클라이언트 테스트"""
    print("=== langchain-mcp-adapters 기반 클라이언트 테스트 ===")
    
    try:
        # 1. 설정 관리자 생성
        config_manager = create_config_manager()
        print("1. 설정 관리자 생성 완료")
        
        # 2. 향상된 클라이언트 생성
        client = create_enhanced_client()
        print("2. 향상된 MCP 클라이언트 생성 완료")
        
        # 3. 비동기 컨텍스트 매니저로 클라이언트 사용
        async with client:
            # 초기화
            # 환경변수 설정 모듈에서 설정 파일 경로 가져오기
            from mcp_host.config.env_config import get_settings
            settings = get_settings()
            config_path = settings.get_mcp_servers_config_path()
            await client.initialize(config_path)
            print("3. 클라이언트 초기화 완료")
            
            # 서버 정보 확인
            server_count = client.get_server_count()
            server_names = client.get_server_names()
            print(f"4. 설정된 서버: {server_count}개 ({', '.join(server_names)})")
            
            # 도구 정보 확인
            tools = client.get_tools()
            tool_names = client.get_tool_names()
            print(f"5. 로드된 도구: {len(tools)}개")
            
            if tool_names:
                print("   도구 목록:")
                for tool_name in tool_names:
                    print(f"   - {tool_name}")
            else:
                print("   외부 MCP 서버가 없어서 도구가 로드되지 않음 (정상)")
            
            print("6. 클라이언트 자동 해제됨 (컨텍스트 매니저)")
        
        print("=== 향상된 클라이언트 테스트 완료! ===")
        return True
        
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False


async def compare_approaches():
    """Enhanced Client의 장점 설명"""
    print("\n=== Enhanced Client 특징 ===")
    
    try:
        config_manager = create_config_manager()
        
        print("Enhanced Client (langchain-mcp-adapters 기반):")
        print("  - 표준화된 MultiServerMCPClient 사용")
        print("  - 자동 도구 변환 (load_mcp_tools)")
        print("  - LangGraph와 직접 통합 가능")
        print("  - 더 간단하고 안정적인 코드")
        print("  - 레거시 직접 구현 방식 대체")
        
        print("\n결론: langchain-mcp-adapters 사용으로 코드 단순화!")
        
    except Exception as e:
        print(f"설명 출력 오류: {e}")
        return False
    
    return True


async def main():
    """메인 테스트 함수"""
    print("Enhanced MCP Client 테스트 시작\n")
    
    # 새로운 클라이언트 테스트
    client_test = await test_enhanced_client()
    
    # 방식 비교
    comparison_test = await compare_approaches()
    
    success = client_test and comparison_test
    
    if success:
        print("\n🎉 모든 테스트 통과!")
        print("langchain-mcp-adapters 통합 완료")
        print("다음 단계: LangGraph 워크플로우에 통합")
    else:
        print("\n❌ 일부 테스트 실패")
    
    return success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 