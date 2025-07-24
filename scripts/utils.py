#!/usr/bin/env python3
"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

"""
Utility functions for KONA project
"""

import os
import time
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()


# Configure logging
def setup_logging(name: str = "kona") -> logging.Logger:
    """
    Set up logging configuration
    
    표준화된 로깅 설정을 구성합니다.
    파일과 콘솔에 동시에 로그를 출력합니다.
    
    Args:
        name: 로거 이름 (기본값: "kona")
        
    Returns:
        구성된 로거 객체
    """
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"{name}_{datetime.now().strftime('%Y%m%d')}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    )

    return logging.getLogger(name)


class APIKeyManager:
    """
    Manage API keys for different services
    
    환경 변수에서 API 키를 관리하고 현재 활성 모델에 따라
    적절한 API 키를 제공합니다.
    
    Attributes:
        claude_key: Claude API 키
        gpt4_key: OpenAI API 키
        active_model: 현재 활성 모델
        debug: 디버그 모드 여부
    """

    def __init__(self):
        """"환경 변수에서 API 키와 설정을 로드합니다."""
        self.claude_key = os.getenv("CLAUDE_API_KEY")
        self.gpt4_key = os.getenv("OPENAI_API_KEY")
        self.active_model = os.getenv("AI_MODEL", "claude").lower()
        self.debug = os.getenv("DEBUG", "False").lower() == "true"

    def get_active_key(self) -> Optional[str]:
        """
        Get the API key for the active model
        
        현재 활성 모델에 해당하는 API 키를 반환합니다.
        
        Returns:
            API 키 문자열 (없으면 None)
        """
        if self.active_model == "claude":
            return self.claude_key
        elif self.active_model in ["openai", "gpt-4", "gpt-4.1-nano", "gpt-4o", "gpt-3.5-turbo"]:
            return self.gpt4_key
        return None

    def has_valid_key(self) -> bool:
        """
        Check if a valid API key exists
        
        유효한 API 키가 설정되어 있는지 확인합니다.
        
        Returns:
            유효한 키가 있으면 True, 없으면 False
        """
        return self.get_active_key() is not None


class RateLimiter:
    """
    Simple rate limiter for API calls
    
    API 호출 속도를 제한하여 제한을 초과하지 않도록 합니다.
    
    Attributes:
        calls_per_minute: 분당 허용 호출 수
        calls: 최근 호출 시간 리스트
    """

    def __init__(self, calls_per_minute: int = 10):
        """
        Rate limiter 초기화
        
        Args:
            calls_per_minute: 분당 허용 API 호출 수 (기본값: 10)
        """
        self.calls_per_minute = calls_per_minute
        self.calls = []

    def wait_if_needed(self):
        """
        Wait if rate limit would be exceeded
        
        속도 제한을 초과할 경우 적절한 시간만큼 대기합니다.
        1분 이상 오래된 호출 기록은 자동으로 제거합니다.
        """
        now = time.time()
        # Remove calls older than 1 minute
        self.calls = [call_time for call_time in self.calls if now - call_time < 60]

        if len(self.calls) >= self.calls_per_minute:
            # Wait until the oldest call is more than 1 minute old
            sleep_time = 60 - (now - self.calls[0]) + 1
            if sleep_time > 0:
                logging.info(f"Rate limit reached. Waiting {sleep_time:.1f} seconds...")
                time.sleep(sleep_time)

        self.calls.append(now)


def clean_text(text: str) -> str:
    """
    Clean text for processing
    
    텍스트를 처리용으로 정리합니다.
    과도한 공백을 제거하고 HTML 태그를 제거합니다.
    
    Args:
        text: 정리할 텍스트
        
    Returns:
        정리된 텍스트
    """
    if not text:
        return ""

    # Remove excessive whitespace
    text = " ".join(text.split())

    # Remove HTML tags if any
    import re

    text = re.sub(r"<[^>]+>", "", text)

    return text.strip()


def truncate_text(text: str, max_length: int = 500) -> str:
    """
    Truncate text to maximum length
    
    텍스트를 최대 길이로 자릅니다.
    가능하면 문장이나 단어 경계에서 자릅니다.
    
    Args:
        text: 자를 텍스트
        max_length: 최대 길이 (기본값: 500)
        
    Returns:
        자른 텍스트
    """
    if len(text) <= max_length:
        return text

    # Find the last complete sentence within the limit
    sentences = text[:max_length].split(".")
    if len(sentences) > 1:
        return ".".join(sentences[:-1]) + "."

    # If no sentence boundary, truncate at word boundary
    words = text[:max_length].split()
    return " ".join(words[:-1]) + "..."


def load_latest_news_data() -> Optional[Dict[str, Any]]:
    """
    Load the most recent news data file
    
    가장 최근 뉴스 데이터 파일을 찾아 로드합니다.
    네이버 뉴스 디렉토리를 우선적으로 확인합니다.
    
    Returns:
        뉴스 데이터 디텍셔너리 (실패 시 None)
    """
    import json

    # 먼저 네이버 뉴스 디렉토리 확인
    naver_dir = Path("news_data/naver")
    if naver_dir.exists():
        naver_files = sorted(naver_dir.glob("all_news_*.json"), reverse=True)
        if naver_files:
            latest_file = naver_files[0]
            logging.info(f"Loading Naver news data from: {latest_file}")

            try:
                with open(latest_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 네이버 뉴스 형식을 표준 형식으로 변환
                    if "data" in data:
                        return {
                            "news": {"naver": data["data"]},
                            "collected_at": data.get("collected_at", ""),
                            "total_articles": data.get("total_articles", 0),
                        }
                    return {"news": {"naver": data}}
            except Exception as e:
                logging.error(f"Error loading Naver news data: {e}")

    # 일반 뉴스 디렉토리 확인
    news_dir = Path("news_data")
    if not news_dir.exists():
        return None

    # Find the most recent news file
    news_files = sorted(news_dir.glob("news_*.json"), reverse=True)
    if not news_files:
        return None

    latest_file = news_files[0]
    logging.info(f"Loading news data from: {latest_file}")

    try:
        with open(latest_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Error loading news data: {e}")
        return None


def save_generated_article(
    article: Dict[str, Any], output_dir: Path = Path("generated_articles")
) -> str:
    """
    Save a generated article to file
    
    생성된 기사를 JSON 파일로 저장합니다.
    파일명은 제목과 타임스탬프를 기반으로 생성합니다.
    
    Args:
        article: 저장할 기사 데이터
        output_dir: 출력 디렉토리 (기본값: "generated_articles")
        
    Returns:
        저장된 파일 경로
    """
    import json

    output_dir.mkdir(exist_ok=True)

    # Create filename from title and timestamp
    safe_title = "".join(c for c in article["title"] if c.isalnum() or c in (" ", "-", "_"))[:50]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = output_dir / f"{safe_title}_{timestamp}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(article, f, ensure_ascii=False, indent=2)

    return str(filename)
