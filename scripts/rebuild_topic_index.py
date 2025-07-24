#!/usr/bin/env python3
"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

"""
GitHub Actions에서 실행 시 topic_index.json 재구성
기존 HTML 기사들을 스캔해서 중복 체크를 위한 인덱스 생성
"""

import json
import os
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup
import re
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_metadata_from_html(html_path):
    """HTML 파일에서 메타데이터 추출"""
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        
        # 제목 추출
        title = soup.find('h1', class_='article-title')
        if not title:
            title = soup.find('h1')
        title_text = title.text.strip() if title else ""
        
        # 날짜 추출
        date_elem = soup.find('p', class_='date')
        if date_elem:
            date_text = date_elem.text.strip()
            # "2025년 07월 22일" 형식을 파싱
            date_match = re.search(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', date_text)
            if date_match:
                year, month, day = date_match.groups()
                created_at = f"{year}-{month.zfill(2)}-{day.zfill(2)}T00:00:00+00:00"
            else:
                created_at = datetime.now().isoformat()
        else:
            # 파일명에서 날짜 추출 시도
            filename = os.path.basename(html_path)
            date_match = re.search(r'(\d{8})', filename)
            if date_match:
                date_str = date_match.group(1)
                year = date_str[:4]
                month = date_str[4:6]
                day = date_str[6:8]
                created_at = f"{year}-{month}-{day}T00:00:00+00:00"
            else:
                # 파일 수정 시간 사용
                mtime = os.path.getmtime(html_path)
                created_at = datetime.fromtimestamp(mtime).isoformat() + "+00:00"
        
        # 키워드/태그 추출
        keywords = []
        tag_container = soup.find('div', class_='tags')
        if tag_container:
            tags = tag_container.find_all(['span', 'a'], class_='tag')
            keywords = [tag.text.strip() for tag in tags]
        
        # 내용 미리보기 추출
        content_elem = soup.find('div', class_='article-content')
        if content_elem:
            # 첫 200자 추출
            content_text = content_elem.text.strip()
            content_preview = content_text[:200]
        else:
            content_preview = ""
        
        # article ID는 파일명에서 추출
        article_id = os.path.splitext(os.path.basename(html_path))[0]
        # "article_" 접두사 제거
        if article_id.startswith('article_'):
            article_id = article_id[8:]
        
        return {
            'article_id': article_id,
            'main_title': title_text,
            'keywords': keywords,
            'created_at': created_at,
            'last_updated': created_at,
            'version': 1,
            'parent_id': None,
            'version_history': [],
            'content_preview': content_preview,
            'tags': {'category_tags': [], 'content_tags': keywords}
        }
    
    except Exception as e:
        logger.error(f"Error processing {html_path}: {e}")
        return None

def rebuild_topic_index():
    """topic_index.json 재구성"""
    
    # cache 디렉토리 생성
    cache_dir = Path("cache/articles")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    topic_index = {}
    
    # 가능한 기사 위치들
    article_locations = [
        Path("output/articles"),
        Path("output/smart_articles"),
        Path("articles"),
        Path("smart_articles")
    ]
    
    total_articles = 0
    
    for location in article_locations:
        if location.exists():
            logger.info(f"Scanning {location}...")
            html_files = list(location.glob("article_*.html"))
            
            for html_file in html_files:
                metadata = extract_metadata_from_html(html_file)
                if metadata:
                    article_id = metadata['article_id']
                    if article_id not in topic_index:
                        topic_index[article_id] = metadata
                        total_articles += 1
                        logger.debug(f"Added: {metadata['main_title'][:50]}...")
    
    # topic_index.json 저장
    topic_index_path = cache_dir / "topic_index.json"
    with open(topic_index_path, 'w', encoding='utf-8') as f:
        json.dump(topic_index, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Rebuilt topic_index.json with {total_articles} articles")
    return topic_index_path

if __name__ == "__main__":
    rebuild_topic_index()