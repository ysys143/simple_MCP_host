#!/usr/bin/env python3
"""더미 파일 관리 MCP 서버

테스트용 간단한 파일 관리 MCP 서버입니다.
"""

from mcp.server.fastmcp import FastMCP
import os

# MCP 서버 생성
mcp = FastMCP("FileManager")

@mcp.tool()
def list_files(directory: str = ".") -> str:
    """디렉토리의 파일 목록을 가져옵니다
    
    Args:
        directory: 조회할 디렉토리 경로 (기본값: 현재 디렉토리)
        
    Returns:
        파일 목록 문자열
    """
    try:
        files = os.listdir(directory)
        return f"{directory} 디렉토리 파일 목록:\n" + "\n".join(files[:10])  # 최대 10개만
    except Exception as e:
        return f"오류: {e}"

@mcp.tool()
def read_file(filename: str) -> str:
    """텍스트 파일의 내용을 읽습니다 (더미 응답)
    
    Args:
        filename: 읽을 파일명
        
    Returns:
        파일 내용 (더미)
    """
    return f"[더미] {filename} 파일 내용:\n이것은 테스트용 더미 내용입니다."

@mcp.tool()
def file_info(filename: str) -> str:
    """파일 정보를 가져옵니다
    
    Args:
        filename: 정보를 확인할 파일명
        
    Returns:
        파일 정보 문자열
    """
    if os.path.exists(filename):
        size = os.path.getsize(filename)
        return f"{filename}: 크기 {size} bytes, 존재함"
    else:
        return f"{filename}: 파일이 존재하지 않음"

if __name__ == "__main__":
    mcp.run(transport="stdio") 