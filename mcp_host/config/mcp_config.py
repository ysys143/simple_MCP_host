"""MCP 서버 설정 관리 모듈

이 모듈은 외부 MCP 서버들의 설정을 관리하는 클래스들을 제공합니다.
SOLID 원칙을 따라 단일 책임 원칙과 의존성 역전 원칙을 적용했습니다.
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod


@dataclass
class MCPServerConfig:
    """단일 MCP 서버의 설정을 담는 데이터 클래스
    
    단일 책임 원칙: MCP 서버 하나의 설정 정보만을 담당
    """
    name: str
    command: str
    args: List[str]
    env: Dict[str, str]
    cwd: Optional[str] = None
    description: Optional[str] = None
    
    def __post_init__(self):
        """설정 유효성 검증
        
        명령어와 인자 리스트가 적절한지 확인합니다.
        """
        if not self.command.strip():
            raise ValueError(f"서버 '{self.name}'의 command가 비어있습니다")
        if not isinstance(self.args, list):
            raise ValueError(f"서버 '{self.name}'의 args는 리스트여야 합니다")


class ConfigReader(ABC):
    """설정 읽기 인터페이스
    
    개방-폐쇄 원칙: 새로운 설정 소스(DB, API 등)를 추가할 때 
    기존 코드 수정 없이 확장 가능
    """
    
    @abstractmethod
    def read_servers_config(self, source: str) -> Dict[str, Any]:
        """설정 소스에서 서버 설정을 읽어옵니다"""
        pass


class JSONConfigReader(ConfigReader):
    """JSON 파일에서 설정을 읽는 구현체
    
    리스코프 치환 원칙: ConfigReader를 완전히 대체 가능
    """
    
    def read_servers_config(self, source: str) -> Dict[str, Any]:
        """JSON 파일에서 MCP 서버 설정을 읽어옵니다
        
        Args:
            source: JSON 설정 파일 경로
            
        Returns:
            서버 설정 딕셔너리
            
        Raises:
            FileNotFoundError: 설정 파일이 없을 때
            json.JSONDecodeError: JSON 형식이 잘못되었을 때
        """
        config_path = Path(source)
        
        if not config_path.exists():
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {source}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)


class MCPConfigManager:
    """MCP 서버 설정 관리자
    
    단일 책임 원칙: MCP 서버 설정의 읽기와 관리만 담당
    의존성 역전 원칙: ConfigReader 추상화에 의존하여 구체적인 구현에 독립적
    """
    
    def __init__(self, config_reader: ConfigReader):
        """설정 관리자 초기화
        
        의존성 주입을 통해 설정 읽기 전략을 외부에서 결정할 수 있도록 합니다.
        이는 테스트 시 MockConfigReader 등을 주입할 수 있게 해줍니다.
        
        Args:
            config_reader: 설정을 읽을 ConfigReader 구현체
        """
        self._config_reader = config_reader
        self._servers: Dict[str, MCPServerConfig] = {}
    
    def load_servers(self, config_path: str) -> Dict[str, MCPServerConfig]:
        """설정 파일에서 모든 MCP 서버 설정을 로드합니다
        
        Args:
            config_path: 설정 파일 경로
            
        Returns:
            서버 이름을 키로 하는 MCPServerConfig 딕셔너리
            
        Raises:
            ValueError: 설정 형식이 잘못되었을 때
        """
        try:
            config_data = self._config_reader.read_servers_config(config_path)
            
            # 두 가지 형식 지원: {"servers": {...}} 또는 직접 {...}
            if 'servers' in config_data:
                servers_data = config_data['servers']
            else:
                # 최상위가 서버 설정인 경우 (현재 mcp_servers.json 형식)
                servers_data = config_data
            
            self._servers.clear()
            
            for server_name, server_config in servers_data.items():
                self._servers[server_name] = self._create_server_config(
                    server_name, server_config
                )
            
            return self._servers.copy()
            
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise ValueError(f"설정 파일 읽기 실패: {e}")
    
    def _create_server_config(self, name: str, config: Dict[str, Any]) -> MCPServerConfig:
        """개별 서버 설정 객체를 생성합니다
        
        Args:
            name: 서버 이름
            config: 서버 설정 딕셔너리
            
        Returns:
            MCPServerConfig 객체
        """
        return MCPServerConfig(
            name=name,
            command=config.get('command', ''),
            args=config.get('args', []),
            env=config.get('env', {}),
            cwd=config.get('cwd'),
            description=config.get('description')
        )
    
    def get_server(self, name: str) -> Optional[MCPServerConfig]:
        """서버 이름으로 설정을 조회합니다"""
        return self._servers.get(name)
    
    def get_all_servers(self) -> Dict[str, MCPServerConfig]:
        """모든 서버 설정을 반환합니다"""
        return self._servers.copy()
    
    def get_server_names(self) -> List[str]:
        """등록된 모든 서버 이름을 반환합니다"""
        return list(self._servers.keys())


def create_config_manager() -> MCPConfigManager:
    """기본 설정 관리자를 생성합니다
    
    팩토리 함수로 기본적인 JSON 설정 읽기 방식의 MCPConfigManager를 생성합니다.
    이는 의존성 주입의 복잡성을 숨기고 간단한 사용법을 제공합니다.
    
    Returns:
        JSON 파일 읽기가 가능한 MCPConfigManager 인스턴스
    """
    json_reader = JSONConfigReader()
    return MCPConfigManager(json_reader) 