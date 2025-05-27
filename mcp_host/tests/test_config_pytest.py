"""pytest 스타일 설정 테스트

pytest를 사용한 설정 시스템 테스트 예시입니다.
"""

import pytest
from pathlib import Path

from mcp_host.config import create_config_manager, MCPServerConfig


class TestMCPConfig:
    """MCP 설정 테스트 클래스"""
    
    def test_config_manager_creation(self, config_manager):
        """설정 관리자 생성 테스트"""
        assert config_manager is not None
        
    def test_load_servers(self, config_manager):
        """서버 설정 로드 테스트"""
        from mcp_host.config.env_config import get_settings
        settings = get_settings()
        config_path = settings.get_mcp_servers_config_path()
        servers = config_manager.load_servers(config_path)
        
        assert isinstance(servers, dict)
        assert len(servers) >= 2  # weather, file-manager
        assert "weather" in servers
        assert "file-manager" in servers
        
    def test_get_individual_server(self, config_manager):
        """개별 서버 조회 테스트"""
        # 설정 로드
        from mcp_host.config.env_config import get_settings
        settings = get_settings()
        config_path = settings.get_mcp_servers_config_path()
        config_manager.load_servers(config_path)
        
        # weather 서버 조회
        weather_server = config_manager.get_server("weather")
        assert weather_server is not None
        assert weather_server.name == "weather"
        assert isinstance(weather_server, MCPServerConfig)
        
    def test_get_nonexistent_server(self, config_manager):
        """존재하지 않는 서버 조회 테스트"""
        config_manager.load_servers("mcp_servers.json")
        
        nonexistent = config_manager.get_server("nonexistent")
        assert nonexistent is None
        
    def test_get_server_names(self, config_manager):
        """서버 이름 목록 조회 테스트"""
        config_manager.load_servers("mcp_servers.json")
        
        names = config_manager.get_server_names()
        assert isinstance(names, list)
        assert "weather" in names
        assert "file-manager" in names
        
    @pytest.mark.parametrize("server_name,expected_command", [
        ("weather", "python"),
        ("file-manager", "python")
    ])
    def test_server_commands(self, config_manager, server_name, expected_command):
        """매개변수화된 서버 명령어 테스트"""
        config_manager.load_servers("mcp_servers.json")
        
        server = config_manager.get_server(server_name)
        assert server is not None
        assert server.command == expected_command
        
    def test_invalid_config_file(self, config_manager):
        """잘못된 설정 파일 처리 테스트"""
        with pytest.raises(ValueError, match="설정 파일 읽기 실패"):
            config_manager.load_servers("nonexistent.json") 