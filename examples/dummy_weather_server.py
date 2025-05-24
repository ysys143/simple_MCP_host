#!/usr/bin/env python3
"""더미 날씨 MCP 서버

테스트용 간단한 MCP 서버입니다.
"""

from mcp.server.fastmcp import FastMCP

# MCP 서버 생성
mcp = FastMCP("Weather")

@mcp.tool()
def get_weather(location: str) -> str:
    """특정 위치의 날씨 정보를 가져옵니다
    
    Args:
        location: 날씨를 확인할 위치
        
    Returns:
        날씨 정보 문자열
    """
    # 더미 데이터 반환
    weather_data = {
        "서울": "맑음, 23도",
        "부산": "흐림, 20도", 
        "대구": "비, 18도",
        "인천": "눈, 5도"
    }
    
    return weather_data.get(location, f"{location}: 정보 없음, 예상 온도 20도")

@mcp.tool()
def get_forecast(location: str, days: int = 3) -> str:
    """특정 위치의 일기예보를 가져옵니다
    
    Args:
        location: 예보를 확인할 위치
        days: 예보 일수 (기본값: 3일)
        
    Returns:
        일기예보 문자열
    """
    forecasts = []
    for day in range(1, days + 1):
        forecasts.append(f"Day {day}: 맑음, 22도")
    
    return f"{location} {days}일 예보:\n" + "\n".join(forecasts)

if __name__ == "__main__":
    mcp.run(transport="stdio") 