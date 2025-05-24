#!/usr/bin/env python3
"""MCP 호스트 패키지 메인 엔트리포인트

python -m mcp_host 명령으로 실행 가능한 CLI 인터페이스를 제공합니다.
"""

import sys
import argparse
import subprocess
from pathlib import Path


def run_tests():
    """테스트 실행"""
    print("🧪 MCP 호스트 테스트 실행")
    
    # 프로젝트 루트 찾기
    current_dir = Path(__file__).parent
    project_root = current_dir.parent
    
    # pytest 실행
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "mcp_host/tests/", 
            "-v", "--tb=short"
        ], cwd=project_root)
        return result.returncode
    except Exception as e:
        print(f"pytest 실행 실패: {e}")
        
        # pytest가 없으면 기존 방식으로 폴백
        print("기존 테스트 러너로 폴백...")
        test_runner = current_dir / "scripts" / "run_tests.py"
        result = subprocess.run([sys.executable, str(test_runner)], cwd=project_root)
        return result.returncode


def run_server():
    """서버 실행"""
    print("🚀 MCP 호스트 서버 시작")
    
    current_dir = Path(__file__).parent
    project_root = current_dir.parent
    main_script = project_root / "main.py"
    
    try:
        result = subprocess.run([sys.executable, str(main_script)], cwd=project_root)
        return result.returncode
    except Exception as e:
        print(f"서버 실행 실패: {e}")
        return 1


def show_help():
    """도움말 표시"""
    help_text = """
🤖 MCP 호스트 CLI

사용법:
  python -m mcp_host [command]

명령어:
  test     모든 테스트 실행
  server   MCP 호스트 서버 시작  
  help     이 도움말 표시

예시:
  python -m mcp_host test          # 테스트 실행
  python -m mcp_host server        # 서버 시작
  python -m mcp_host               # 도움말 표시
"""
    print(help_text)


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description="MCP 호스트 CLI",
        add_help=False  # 커스텀 help 사용
    )
    parser.add_argument(
        "command", 
        nargs="?", 
        choices=["test", "server", "help"],
        default="help",
        help="실행할 명령어"
    )
    
    args = parser.parse_args()
    
    if args.command == "test":
        return run_tests()
    elif args.command == "server":
        return run_server()
    elif args.command == "help" or args.command is None:
        show_help()
        return 0
    else:
        print(f"알 수 없는 명령어: {args.command}")
        show_help()
        return 1


if __name__ == "__main__":
    sys.exit(main()) 