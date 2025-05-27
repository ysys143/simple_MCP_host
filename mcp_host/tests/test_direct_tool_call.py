#!/usr/bin/env python3
"""직접 도구 호출 테스트

워크플로우를 거치지 않고 Client로 직접 도구 호출 결과를 확인합니다.
"""

import asyncio
from mcp_host.adapters.client import MCPClient

async def test_direct_tool_calls():
    print("=== 직접 도구 호출 테스트 ===")
    
    client = MCPClient()
    
    try:
        await client.initialize("mcp_servers.json")
        
        print("1. 날씨 도구 호출:")
        result1 = await client.call_tool("weather", "get_weather", {"location": "서울"})
        print(f"   결과: {result1}")
        print(f"   타입: {type(result1)}")
        
        print("\n2. 파일 목록 도구 호출:")
        result2 = await client.call_tool("file-manager", "list_files", {"directory": "."})
        print(f"   결과: {result2}")
        print(f"   타입: {type(result2)}")
        
        print("\n3. 예보 도구 호출:")
        result3 = await client.call_tool("weather", "get_forecast", {"location": "부산", "days": 5})
        print(f"   결과: {result3}")
        print(f"   타입: {type(result3)}")
        
    except Exception as e:
        print(f"오류: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await client.close()

if __name__ == "__main__":
    asyncio.run(test_direct_tool_calls()) 