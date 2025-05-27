#!/usr/bin/env python3
"""테스트 실행 스크립트

mcp_host 패키지의 모든 테스트를 실행합니다.
올바른 Python 경로 설정으로 import 문제를 해결합니다.
"""

import sys
import subprocess
from pathlib import Path

def main():
    """메인 함수"""
    # 현재 파일에서 프로젝트 루트 계산: mcp_host/scripts/run_tests.py -> ../..
    project_root = Path(__file__).parent.parent.parent
    tests_dir = project_root / "mcp_host" / "tests"
    
    # PYTHONPATH 환경변수 설정
    env = {
        **dict(os.environ),
        "PYTHONPATH": str(project_root)
    }
    
    print("🚀 MCP 호스트 테스트 실행")
    print(f"📁 프로젝트 루트: {project_root}")
    print(f"🧪 테스트 디렉토리: {tests_dir}")
    print()
    
    # 개별 테스트 파일들
    test_files = [
        "test_config.py",
        "test_client.py",
        "test_workflow.py"
    ]
    
    success_count = 0
    
    for test_file in test_files:
        test_path = tests_dir / test_file
        if test_path.exists():
            print(f"📝 실행: {test_file}")
            try:
                result = subprocess.run(
                    [sys.executable, str(test_path)],
                    env=env,
                    cwd=project_root,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    print(f"✅ {test_file} 성공")
                    success_count += 1
                else:
                    print(f"❌ {test_file} 실패")
                    print(f"출력: {result.stdout}")
                    print(f"오류: {result.stderr}")
                
            except Exception as e:
                print(f"❌ {test_file} 실행 오류: {e}")
        else:
            print(f"⚠️ {test_file} 파일을 찾을 수 없습니다")
        
        print("-" * 50)
    
    print(f"\n🎯 결과: {success_count}/{len(test_files)} 테스트 통과")
    
    if success_count == len(test_files):
        print("🎉 모든 테스트가 성공했습니다!")
        return 0
    else:
        print("💥 일부 테스트가 실패했습니다.")
        return 1


if __name__ == "__main__":
    import os
    sys.exit(main()) 