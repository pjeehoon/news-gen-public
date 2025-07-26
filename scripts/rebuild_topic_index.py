#!/usr/bin/env python3
"""
기존 생성된 기사들로부터 topic_index.json을 재구성하는 스크립트
GitHub Actions에서 중복 체크를 위해 사용됨
"""

import os
import json
import re
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def extract_metadata_from_html(html_path: str) -> dict:
    """HTML 파일에서 메타데이터 추출"""
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        
        metadata = {}
        
        # 제목 추출
        title_tag = soup.find('title')
        if title_tag:
            metadata['title'] = title_tag.text.strip()
        
        # article-data script 태그에서 JSON 데이터 추출
        article_data_script = soup.find('script', id='article-data')
        if article_data_script and article_data_script.string:
            try:
                article_data = json.loads(article_data_script.string)
                metadata.update(article_data)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse article data from {html_path}")
        
        # data-* 속성에서 추가 정보 추출
        article_link = soup.find('a', class_='article-link')
        if article_link:
            for attr, value in article_link.attrs.items():
                if attr.startswith('data-'):
                    key = attr.replace('data-', '').replace('-', '_')
                    metadata[key] = value
        
        # 날짜 추출
        date_element = soup.find('span', class_='date')
        if date_element:
            metadata['date'] = date_element.text.strip()
        
        # 파일명에서 topic_id 추출
        filename = os.path.basename(html_path)
        match = re.search(r'article_(\d{8}_\d{6})', filename)
        if match:
            metadata['file_id'] = match.group(1)
        
        return metadata
        
    except Exception as e:
        logger.error(f"Error extracting metadata from {html_path}: {e}")
        return {}

def rebuild_topic_index():
    """topic_index.json 재구성"""
    
    # 캐시 디렉토리 생성
    cache_dir = Path("cache/articles")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # 기존 topic_index.json이 있으면 로드
    topic_index_path = cache_dir / "topic_index.json"
    if topic_index_path.exists():
        try:
            with open(topic_index_path, 'r', encoding='utf-8') as f:
                topic_index = json.load(f)
                logger.info(f"Loaded existing topic index with {len(topic_index)} entries")
        except Exception as e:
            logger.warning(f"Failed to load existing topic index: {e}")
            topic_index = {}
    else:
        topic_index = {}
    
    processed_count = 0
    
    # smart_articles 디렉토리의 HTML 파일들 처리
    smart_articles_dir = Path("output/smart_articles")
    if smart_articles_dir.exists():
        # 모든 HTML 파일 찾기 (article_*.html 패턴뿐만 아니라)
        html_files = list(smart_articles_dir.glob("*.html"))
        logger.info(f"Found {len(html_files)} HTML files in {smart_articles_dir}")
        
        for html_file in html_files:
            # about.html, index.html 등은 제외
            if html_file.name in ['index.html', 'about.html', 'admin.html']:
                continue
                
            metadata = extract_metadata_from_html(str(html_file))
            
            if metadata.get('topic_id'):
                topic_id = metadata['topic_id']
                
                # topic_index 항목 구성
                topic_entry = {
                    'main_title': metadata.get('title', ''),
                    'generated_title': metadata.get('generated_title', metadata.get('title', '')),
                    'keywords': metadata.get('keywords', []),
                    'created_at': metadata.get('created_at', datetime.now().isoformat()),
                    'last_updated': metadata.get('last_updated', datetime.now().isoformat()),
                    'version': metadata.get('version', 1),
                    'tags': metadata.get('tags', {
                        'category_tags': [],
                        'content_tags': []
                    }),
                    'source_articles': metadata.get('source_articles', [])
                }
                
                # version_history가 있으면 추가
                if 'version_history' in metadata:
                    topic_entry['version_history'] = metadata['version_history']
                
                topic_index[topic_id] = topic_entry
                processed_count += 1
                logger.info(f"Processed: {topic_id} - {topic_entry['main_title']}")
    
    # topic_index.json 저장
    topic_index_path = cache_dir / "topic_index.json"
    with open(topic_index_path, 'w', encoding='utf-8') as f:
        json.dump(topic_index, f, ensure_ascii=False, indent=2)
    
    logger.info(f"✅ Topic index rebuilt successfully")
    logger.info(f"   Total articles indexed: {processed_count}")
    logger.info(f"   Index saved to: {topic_index_path}")
    
    # 요약 출력
    if processed_count > 0:
        print(f"\n📊 Index Summary:")
        print(f"   - Total topics: {len(topic_index)}")
        print(f"   - Latest article: {max((entry['created_at'] for entry in topic_index.values()), default='N/A')}")
        print(f"   - Index location: {topic_index_path}")
    else:
        print("\n⚠️  No existing articles found to index")
        print("   This is normal for the first run or after cleaning the project")

if __name__ == "__main__":
    rebuild_topic_index()