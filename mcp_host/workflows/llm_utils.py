"""LLM 유틸리티 모듈

OpenAI ChatGPT 인스턴스 관리와 관련 유틸리티 함수들을 제공합니다.
단일 책임 원칙: LLM 인스턴스 관리만 담당합니다.
"""

import logging
import os
from typing import Optional

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

# LLM 인스턴스 (싱글톤 패턴)
_llm_instance: Optional[ChatOpenAI] = None


def get_llm() -> ChatOpenAI:
    """ChatOpenAI LLM 인스턴스를 반환합니다
    
    환경변수에서 OpenAI API 키를 읽어와 LLM을 초기화합니다.
    싱글톤 패턴으로 인스턴스를 재사용합니다.
    
    Returns:
        ChatOpenAI: 설정된 OpenAI 채팅 모델
        
    Raises:
        ValueError: OPENAI_API_KEY 환경변수가 설정되지 않은 경우
    """
    global _llm_instance
    
    if _llm_instance is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY 환경변수가 설정되지 않았습니다. "
                "OpenAI API 키를 설정해주세요."
            )
        
        _llm_instance = ChatOpenAI(
            model="gpt-4o-mini",  # 빠르고 경제적인 모델
            temperature=0.1,      # 일관된 응답을 위해 낮은 온도
            max_tokens=1000,      # 적절한 응답 길이
        )
        logger.info("OpenAI ChatGPT 모델 초기화 완료")
    
    return _llm_instance


def reset_llm_instance():
    """LLM 인스턴스를 재설정합니다 (테스트용)"""
    global _llm_instance
    _llm_instance = None
    logger.info("LLM 인스턴스 재설정 완료")


def get_llm_config() -> dict:
    """현재 LLM 설정 정보를 반환합니다"""
    if _llm_instance is None:
        return {"status": "not_initialized"}
    
    return {
        "status": "initialized",
        "model": getattr(_llm_instance, "model_name", "unknown"),
        "temperature": getattr(_llm_instance, "temperature", "unknown"),
        "max_tokens": getattr(_llm_instance, "max_tokens", "unknown")
    } 