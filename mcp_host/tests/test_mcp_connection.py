#!/usr/bin/env python3
"""실제 MCP 연결 테스트

MultiServerMCPClient를 사용한 실제 MCP 서버 연결을 테스트합니다.
"""

import asyncio
import json
import logging
from mcp_host.adapters.enhanced_client import EnhancedMCPClient

# 로깅 설정
logging.basicConfig(level=logging.INFO)


async def test_enhanced_client_connection():
    """Enhanced Client의 실제 MCP 서버 연결 테스트"""
    print("=== Enhanced MCP Client 실제 연결 테스트 ===")
    
    client = EnhancedMCPClient()
    
    try:
        # JSON 설정 로드 및 초기화
        await client.initialize("mcp_servers.json")
        
        # 서버 정보 확인
        servers = client.get_server_names()
        print(f"연결된 서버: {servers}")
        
        # 도구 목록 확인
        tools = client.get_tools()
        print(f"로드된 도구 수: {len(tools)}")
        
        for tool in tools:
            print(f"  - {tool.name}: {getattr(tool, 'description', '설명없음')}")
        
        # 실제 도구 호출 테스트
        if tools:
            print("\n=== 실제 도구 호출 테스트 ===")
            
            # 날씨 도구 테스트
            try:
                result = await client.call_tool("weather", "get_weather", {"location": "서울"})
                print(f"get_weather 결과: {result}")
            except Exception as e:
                print(f"get_weather 호출 실패: {e}")
            
            # 파일 도구 테스트
            try:
                result = await client.call_tool("file-manager", "list_files", {"directory": "."})
                print(f"list_files 결과: {result}")
            except Exception as e:
                print(f"list_files 호출 실패: {e}")
        
        print("\n테스트 성공!")
        return True
        
    except Exception as e:
        print(f"테스트 실패: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        await client.close()


async def test_json_config_loading():
    """JSON 설정 파일 로딩 테스트"""
    print("=== JSON 설정 로딩 테스트 ===")
    
    try:
        with open("mcp_servers.json", 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        print("JSON 설정 로드 성공:")
        for name, server_config in config.items():
            print(f"  {name}: {server_config.get('command')} {server_config.get('args')}")
        
        return True
        
    except Exception as e:
        print(f"JSON 설정 로딩 실패: {e}")
        return False


async def main():
    print("실제 MCP 연결 테스트 시작\n")
    
    # JSON 설정 테스트
    json_ok = await test_json_config_loading()
    
    if json_ok:
        # Enhanced Client 테스트
        client_ok = await test_enhanced_client_connection()
        
        if client_ok:
            print("\n모든 테스트 통과! 실제 MCP 연결이 성공적으로 작동합니다.")
        else:
            print("\n클라이언트 연결 테스트 실패")
    else:
        print("\nJSON 설정 로딩 테스트 실패")


if __name__ == "__main__":
    asyncio.run(main()) 