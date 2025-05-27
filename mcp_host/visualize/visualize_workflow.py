#!/usr/bin/env python3
"""MCP Host 워크플로우 시각화 스크립트

LangGraph 워크플로우를 다양한 형식으로 시각화하는 독립적인 스크립트입니다.
"""

import argparse
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from mcp_host.workflows.graph import create_workflow
from mcp_host.workflows.visualization import (
    visualize_workflow, 
    print_workflow_structure,
    export_workflow_mermaid
)


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(
        description="MCP Host 워크플로우 시각화 도구",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python visualize_workflow.py --console                    # 콘솔에 ASCII 출력
  python visualize_workflow.py --mermaid                    # Mermaid 다이어그램 출력
  python visualize_workflow.py --save workflow.html         # HTML 파일로 저장
  python visualize_workflow.py --export docs/graphs         # 문서 디렉토리에 내보내기
        """
    )
    
    # 출력 옵션
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--console", "-c",
        action="store_true",
        help="콘솔에 워크플로우 구조 출력 (ASCII 형식)"
    )
    output_group.add_argument(
        "--mermaid", "-m",
        action="store_true",
        help="Mermaid 다이어그램을 콘솔에 출력"
    )
    output_group.add_argument(
        "--ascii", "-a",
        action="store_true",
        help="ASCII 다이어그램을 콘솔에 출력"
    )
    
    # 파일 저장 옵션
    parser.add_argument(
        "--save", "-s",
        type=str,
        metavar="FILE",
        help="지정된 파일에 시각화 결과 저장 (확장자에 따라 형식 결정)"
    )
    parser.add_argument(
        "--export", "-e",
        type=str,
        metavar="DIR",
        help="지정된 디렉토리에 Mermaid HTML 및 .mmd 파일 내보내기"
    )
    
    # 형식 옵션
    parser.add_argument(
        "--format", "-f",
        choices=["mermaid", "ascii", "dot"],
        default="mermaid",
        help="출력 형식 선택 (기본값: mermaid)"
    )
    
    args = parser.parse_args()
    
    # 기본 동작: 아무 옵션이 없으면 콘솔 출력
    if not any([args.console, args.mermaid, args.ascii, args.save, args.export]):
        args.console = True
    
    try:
        # 워크플로우 생성
        print("워크플로우 생성 중...")
        workflow = create_workflow()
        print("✅ 워크플로우 생성 완료\n")
        
        # 콘솔 출력
        if args.console:
            print_workflow_structure(workflow)
        
        # Mermaid 다이어그램 출력
        if args.mermaid:
            print("Mermaid 다이어그램:")
            print("-" * 50)
            mermaid_content = visualize_workflow(workflow, "mermaid")
            print(mermaid_content)
            print("-" * 50)
        
        # ASCII 다이어그램 출력
        if args.ascii:
            print("ASCII 다이어그램:")
            print("-" * 50)
            ascii_content = visualize_workflow(workflow, "ascii")
            print(ascii_content)
            print("-" * 50)
        
        # 파일 저장
        if args.save:
            save_path = Path(args.save)
            
            # 확장자에 따라 형식 결정
            if save_path.suffix.lower() == '.html':
                format_type = "mermaid"
            elif save_path.suffix.lower() in ['.txt', '.ascii']:
                format_type = "ascii"
            elif save_path.suffix.lower() in ['.dot', '.gv']:
                format_type = "dot"
            else:
                format_type = args.format
            
            print(f"파일 저장 중: {save_path} ({format_type} 형식)")
            visualize_workflow(workflow, format_type, str(save_path))
            print(f"✅ 파일 저장 완료: {save_path}")
        
        # 디렉토리 내보내기
        if args.export:
            print(f"디렉토리 내보내기: {args.export}")
            output_file = export_workflow_mermaid(workflow, args.export)
            if output_file:
                print(f"✅ 내보내기 완료: {output_file}")
            else:
                print("❌ 내보내기 실패")
        
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 