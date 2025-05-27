#!/usr/bin/env python3
"""실제 MCP 도구 호출 테스트"""

import asyncio
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from mcp_host.adapters.enhanced_client import create_enhanced_client
from mcp_host.config import create_config_manager


async def test_real_mcp():
    """실제 MCP 도구 호출 테스트"""
    print('🔧 실제 MCP 도구 호출 테스트')
    
    config_manager = create_config_manager()
    client = create_enhanced_client()
    
    try:
        from mcp_host.config.env_config import get_settings
        settings = get_settings()
        config_path = settings.get_mcp_servers_config_path()
        await client.initialize(config_path)
        print(f'✅ 클라이언트 초기화: {len(client.get_tools())}개 도구')
        
        # 도구 목록 확인
        tools = client.get_tool_names()
        print(f'📋 사용 가능한 도구: {tools}')
        
        # 실제 도구 호출 테스트
        if 'get_weather' in tools:
            print('\n🌤️ get_weather 호출 테스트...')
            result = await client.call_tool('weather', 'get_weather', {'location': '서울'})
            print(f'✅ 결과: {result}')
        else:
            print('❌ get_weather 도구를 찾을 수 없습니다')
        
        if 'list_files' in tools:
            print('\n📁 list_files 호출 테스트...')
            result = await client.call_tool('file-manager', 'list_files', {'directory': '.'})
            print(f'✅ 결과: {result}')
        else:
            print('❌ list_files 도구를 찾을 수 없습니다')
        
    except Exception as e:
        print(f'❌ 테스트 실패: {e}')
        import traceback
        traceback.print_exc()
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_real_mcp()) 