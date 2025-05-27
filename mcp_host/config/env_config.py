"""MCP 호스트 환경변수 설정 모듈

모든 환경변수를 중앙에서 관리하고 타입 검증을 제공합니다.
단일 책임 원칙: 환경변수 설정 관리만 담당
개방-폐쇄 원칙: 새로운 환경변수 추가 시 기존 코드 수정 없이 확장 가능
"""

import os
from pathlib import Path
from typing import Optional
from functools import lru_cache

from pydantic import Field, validator
from pydantic_settings import BaseSettings


class MCPHostSettings(BaseSettings):
    """MCP 호스트 환경변수 설정 클래스
    
    Pydantic BaseSettings를 사용하여 환경변수를 타입 안전하게 관리합니다.
    모든 환경변수는 이 클래스를 통해 접근해야 합니다.
    """
    
    # OpenAI API 설정
    openai_api_key: str = Field(..., description="OpenAI API 키 (필수)")
    openai_model: str = Field(default="gpt-4.1", description="사용할 OpenAI 모델명")
    openai_temperature: float = Field(default=0.1, ge=0.0, le=2.0, description="모델 온도 (0.0-2.0)")
    openai_max_tokens: int = Field(default=1000, gt=0, description="최대 토큰 수")
    
    # MCP 서버 설정
    mcp_servers_config: str = Field(default="./mcp_servers.json", description="MCP 서버 설정 파일 경로")
    
    # Phoenix 모니터링 설정
    phoenix_enabled: bool = Field(default=True, description="Phoenix 모니터링 활성화 여부")
    
    class Config:
        """Pydantic 설정"""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False  # 환경변수 대소문자 구분 안함
    
    @validator("openai_temperature")
    def validate_temperature(cls, v):
        """온도 값 검증"""
        if not 0.0 <= v <= 2.0:
            raise ValueError(f"온도는 0.0-2.0 범위여야 합니다. 현재 값: {v}")
        return v
    
    @validator("openai_max_tokens")
    def validate_max_tokens(cls, v):
        """최대 토큰 수 검증"""
        if v <= 0:
            raise ValueError(f"최대 토큰 수는 양수여야 합니다. 현재 값: {v}")
        return v
    
    @validator("mcp_servers_config")
    def validate_mcp_config_path(cls, v):
        """MCP 서버 설정 파일 경로 검증"""
        # 상대 경로인 경우 절대 경로로 변환
        if not os.path.isabs(v):
            v = os.path.abspath(v)
        return v
    
    def get_mcp_servers_config_path(self) -> str:
        """MCP 서버 설정 파일 경로 반환
        
        Returns:
            MCP 서버 설정 파일의 절대 경로
        """
        return self.mcp_servers_config
    
    def validate_mcp_servers_config_file(self) -> bool:
        """MCP 서버 설정 파일이 유효한지 확인
        
        Returns:
            파일이 존재하고 읽을 수 있으면 True, 아니면 False
        """
        try:
            path = Path(self.mcp_servers_config)
            return path.exists() and path.is_file() and path.suffix == '.json'
        except Exception:
            return False
    
    def get_openai_config(self) -> dict:
        """OpenAI 설정을 딕셔너리로 반환
        
        Returns:
            OpenAI 설정 딕셔너리
        """
        return {
            "api_key": self.openai_api_key,
            "model": self.openai_model,
            "temperature": self.openai_temperature,
            "max_tokens": self.openai_max_tokens
        }


@lru_cache()
def get_settings() -> MCPHostSettings:
    """환경변수 설정 인스턴스를 반환하는 싱글톤 함수
    
    lru_cache 데코레이터를 사용하여 한 번만 로드하고 재사용합니다.
    
    Returns:
        MCPHostSettings 인스턴스
        
    Raises:
        ValueError: 필수 환경변수가 없거나 잘못된 값인 경우
    """
    try:
        return MCPHostSettings()
    except Exception as e:
        raise ValueError(f"환경변수 설정 로드 실패: {e}")


def reload_settings() -> MCPHostSettings:
    """설정을 다시 로드합니다 (테스트용)
    
    캐시를 클리어하고 새로운 설정 인스턴스를 생성합니다.
    주로 테스트에서 환경변수를 변경한 후 사용합니다.
    
    Returns:
        새로운 MCPHostSettings 인스턴스
    """
    get_settings.cache_clear()
    return get_settings()


# 편의 함수들 (기존 코드와의 호환성을 위해)
def get_mcp_servers_config_path() -> str:
    """MCP 서버 설정 파일 경로를 반환하는 편의 함수
    
    기존 utils.py의 함수와 호환성을 위해 제공됩니다.
    
    Returns:
        MCP 서버 설정 파일 경로
    """
    settings = get_settings()
    return settings.get_mcp_servers_config_path()


def validate_mcp_servers_config_path(config_path: Optional[str] = None) -> bool:
    """MCP 서버 설정 파일 경로가 유효한지 확인하는 편의 함수
    
    기존 utils.py의 함수와 호환성을 위해 제공됩니다.
    
    Args:
        config_path: 확인할 설정 파일 경로 (None이면 현재 설정 사용)
        
    Returns:
        파일이 존재하고 읽을 수 있으면 True, 아니면 False
    """
    if config_path is None:
        settings = get_settings()
        return settings.validate_mcp_servers_config_file()
    else:
        try:
            path = Path(config_path)
            return path.exists() and path.is_file() and path.suffix == '.json'
        except Exception:
            return False 