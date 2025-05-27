"""LLM 유틸리티 모듈

OpenAI ChatGPT 인스턴스 관리와 관련 유틸리티 함수들을 제공합니다.
단일 책임 원칙: LLM 인스턴스 관리만 담당합니다.

환경변수 설정은 mcp_host.config.env_config 모듈에서 중앙 관리됩니다.
"""

import logging
from typing import Optional

from langchain_openai import ChatOpenAI
from ..config.env_config import get_settings

logger = logging.getLogger(__name__)

# LLM 인스턴스 (싱글톤 패턴)
_llm_instance: Optional[ChatOpenAI] = None


def get_llm() -> ChatOpenAI:
    """ChatOpenAI LLM 인스턴스를 반환합니다
    
    환경변수 설정 모듈에서 설정을 가져와 LLM을 초기화합니다.
    싱글톤 패턴으로 인스턴스를 재사용합니다.
    
    Returns:
        ChatOpenAI: 설정된 OpenAI 채팅 모델
        
    Raises:
        ValueError: 환경변수 설정이 잘못된 경우
    """
    global _llm_instance
    
    if _llm_instance is None:
        try:
            # 환경변수 설정 모듈에서 설정 가져오기
            settings = get_settings()
            openai_config = settings.get_openai_config()
            
            _llm_instance = ChatOpenAI(
                model=openai_config["model"],
                temperature=openai_config["temperature"],
                max_tokens=openai_config["max_tokens"],
                api_key=openai_config["api_key"]
            )
            
            logger.info(
                f"OpenAI ChatGPT 모델 초기화 완료 - "
                f"모델: {openai_config['model']}, "
                f"온도: {openai_config['temperature']}, "
                f"최대토큰: {openai_config['max_tokens']}"
            )
            
        except Exception as e:
            raise ValueError(f"LLM 초기화 실패: {e}")
    
    return _llm_instance


def reset_llm_instance():
    """LLM 인스턴스를 재설정합니다 (테스트용)"""
    global _llm_instance
    _llm_instance = None
    logger.info("LLM 인스턴스 재설정 완료")


def get_llm_config() -> dict:
    """현재 LLM 설정 정보를 반환합니다"""
    try:
        settings = get_settings()
        openai_config = settings.get_openai_config()
        
        if _llm_instance is None:
            return {
                "status": "not_initialized",
                "configured_model": openai_config["model"],
                "configured_temperature": openai_config["temperature"],
                "configured_max_tokens": openai_config["max_tokens"]
            }
        
        return {
            "status": "initialized",
            "model": getattr(_llm_instance, "model_name", openai_config["model"]),
            "temperature": getattr(_llm_instance, "temperature", openai_config["temperature"]),
            "max_tokens": getattr(_llm_instance, "max_tokens", openai_config["max_tokens"])
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        } 