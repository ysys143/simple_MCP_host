#!/usr/bin/env python3
"""MCP 설정 시스템 테스트 스크립트

첫번째 단계 완료를 확인하기 위한 간단한 테스트입니다.
"""

import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from mcp_host.config import create_config_manager


def test_config_system():
    """설정 시스템 동작 테스트"""
    print("=== MCP 설정 시스템 테스트 ===")
    
    try:
        # 설정 관리자 생성
        config_manager = create_config_manager()
        print("1. 설정 관리자 생성 완료")
        
        # 설정 파일 로드
        servers = config_manager.load_servers("mcp_servers.json")
        print(f"2. 설정 파일 로드 완료 - {len(servers)}개 서버 발견")
        
        # 서버 목록 출력
        print("\n발견된 MCP 서버들:")
        for name, config in servers.items():
            print(f"  - {name}: {config.description}")
            print(f"    명령어: {config.command} {' '.join(config.args)}")
            print(f"    작업 디렉토리: {config.cwd}")
            print()
        
        # 개별 서버 조회 테스트
        weather_server = config_manager.get_server("weather")
        if weather_server:
            print(f"3. 개별 서버 조회 성공: {weather_server.name}")
        else:
            print("3. 개별 서버 조회 실패")
        
        print("=== 첫번째 단계 완료! ===")
        
    except Exception as e:
        print(f"오류 발생: {e}")
        return False
    
    return True


if __name__ == "__main__":
    success = test_config_system()
    sys.exit(0 if success else 1) 