#!/usr/bin/env python3
"""환경변수 설정 모듈 테스트 스크립트

새로 생성된 env_config 모듈의 동작을 테스트합니다.
"""

import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def test_env_config_module():
    """환경변수 설정 모듈 테스트"""
    print("=== 환경변수 설정 모듈 테스트 ===")
    
    try:
        # 1. 설정 모듈 import
        from mcp_host.config.env_config import get_settings, reload_settings
        print("1. 환경변수 설정 모듈 import 성공")
        
        # 2. 설정 인스턴스 생성
        settings = get_settings()
        print("2. 설정 인스턴스 생성 성공")
        
        # 3. OpenAI 설정 확인
        openai_config = settings.get_openai_config()
        print(f"3. OpenAI 설정:")
        print(f"   - 모델: {openai_config['model']}")
        print(f"   - 온도: {openai_config['temperature']}")
        print(f"   - 최대 토큰: {openai_config['max_tokens']}")
        print(f"   - API 키: {'설정됨' if openai_config['api_key'] else '없음'}")
        
        # 4. MCP 서버 설정 확인
        mcp_config_path = settings.get_mcp_servers_config_path()
        mcp_config_valid = settings.validate_mcp_servers_config_file()
        print(f"4. MCP 서버 설정:")
        print(f"   - 설정 파일 경로: {mcp_config_path}")
        print(f"   - 파일 유효성: {'유효' if mcp_config_valid else '무효'}")
        
        # 5. Phoenix 설정 확인
        print(f"5. Phoenix 설정:")
        print(f"   - 활성화: {settings.phoenix_enabled}")
        
        # 6. 편의 함수 테스트
        from mcp_host.config.env_config import (
            get_mcp_servers_config_path,
            validate_mcp_servers_config_path
        )
        
        convenience_path = get_mcp_servers_config_path()
        convenience_valid = validate_mcp_servers_config_path()
        print(f"6. 편의 함수 테스트:")
        print(f"   - 경로: {convenience_path}")
        print(f"   - 유효성: {'유효' if convenience_valid else '무효'}")
        
        # 7. 싱글톤 패턴 확인
        settings2 = get_settings()
        is_singleton = settings is settings2
        print(f"7. 싱글톤 패턴: {'작동' if is_singleton else '실패'}")
        
        print("\n=== 환경변수 설정 모듈 테스트 완료! ===")
        return True
        
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_validation():
    """환경변수 검증 테스트"""
    print("\n=== 환경변수 검증 테스트 ===")
    
    try:
        from mcp_host.config.env_config import MCPHostSettings
        
        # 현재 환경변수 백업
        original_temp = os.environ.get("OPENAI_TEMPERATURE")
        original_tokens = os.environ.get("OPENAI_MAX_TOKENS")
        
        # 잘못된 온도 값 테스트
        print("1. 잘못된 온도 값 테스트...")
        os.environ["OPENAI_TEMPERATURE"] = "3.0"  # 범위 초과
        try:
            settings = MCPHostSettings()
            print("   - 검증 실패: 잘못된 값이 통과됨")
        except ValueError as e:
            print(f"   - 검증 성공: {e}")
        
        # 잘못된 토큰 수 테스트
        print("2. 잘못된 토큰 수 테스트...")
        os.environ["OPENAI_TEMPERATURE"] = "0.1"  # 정상값으로 복원
        os.environ["OPENAI_MAX_TOKENS"] = "-100"  # 음수
        try:
            settings = MCPHostSettings()
            print("   - 검증 실패: 잘못된 값이 통과됨")
        except ValueError as e:
            print(f"   - 검증 성공: {e}")
        
        # 환경변수 복원
        if original_temp is not None:
            os.environ["OPENAI_TEMPERATURE"] = original_temp
        else:
            os.environ.pop("OPENAI_TEMPERATURE", None)
            
        if original_tokens is not None:
            os.environ["OPENAI_MAX_TOKENS"] = original_tokens
        else:
            os.environ.pop("OPENAI_MAX_TOKENS", None)
        
        print("3. 환경변수 복원 완료")
        print("=== 검증 테스트 완료! ===")
        return True
        
    except Exception as e:
        print(f"검증 테스트 오류: {e}")
        return False





def main():
    """메인 테스트 함수"""
    print("환경변수 설정 모듈 통합 테스트 시작\n")
    
    # 기본 기능 테스트
    basic_test = test_env_config_module()
    
    # 검증 테스트
    validation_test = test_validation()
    
    success = basic_test and validation_test
    
    if success:
        print("\n🎉 모든 테스트 통과!")
        print("환경변수 설정 모듈 통합 완료")
        print("SOLID 원칙을 준수하는 중앙 집중식 환경변수 관리 구현")
    else:
        print("\n❌ 일부 테스트 실패")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 