"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

"""
기사 캐싱 및 업데이트 관리 시스템
- 동일 주제 기사 반복 방지
- 기존 분석 데이터 재사용
- 새로운 사실 발견 시 업데이트
"""

import json
import os
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
from difflib import SequenceMatcher
import sys
from pathlib import Path

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.utils import truncate_text

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ArticleCacheManager:
    """기사 캐싱 및 업데이트 관리"""
    
    def __init__(self, cache_dir: str = "cache/articles"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.topic_index_file = f"{cache_dir}/topic_index.json"
        self.topic_index = self._load_topic_index()
        
    def _load_topic_index(self) -> Dict:
        """주제별 인덱스 로드"""
        if os.path.exists(self.topic_index_file):
            with open(self.topic_index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def _save_topic_index(self):
        """주제별 인덱스 저장"""
        with open(self.topic_index_file, 'w', encoding='utf-8') as f:
            json.dump(self.topic_index, f, ensure_ascii=False, indent=2)
    
    def _generate_topic_hash(self, title: str, keywords: List[str]) -> str:
        """주제 해시 생성"""
        # 제목과 키워드를 조합하여 주제 식별
        topic_string = f"{title}::{':'.join(sorted(keywords))}"
        return hashlib.md5(topic_string.encode()).hexdigest()[:12]
    
    def load_article(self, topic_id: str) -> Optional[Dict]:
        """특정 ID의 기사 로드"""
        cache_file = os.path.join(self.cache_dir, f"{topic_id}.json")
        
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        return None
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """두 텍스트의 유사도 계산"""
        return SequenceMatcher(None, text1, text2).ratio()
    
    def check_existing_article(self, title: str, keywords: List[str], 
                             similarity_threshold: float = 0.7) -> Optional[Dict]:
        """기존 기사 존재 여부 확인"""
        similar_articles = []
        # 유사한 주제 찾기
        for topic_id, topic_data in self.topic_index.items():
            # 제목 유사도 확인
            title_similarity = self._calculate_similarity(
                title.lower(), 
                topic_data['main_title'].lower()
            )
            
            # 키워드 겹침 확인
            existing_keywords = set(topic_data['keywords'])
            new_keywords = set(keywords)
            if len(existing_keywords) > 0 and len(new_keywords) > 0:
                keyword_overlap = len(existing_keywords & new_keywords) / min(
                    len(existing_keywords), len(new_keywords)
                )
            else:
                keyword_overlap = 0
            
            # 종합 유사도
            total_similarity = (title_similarity * 0.3) + (keyword_overlap * 0.7)
            
            if total_similarity >= similarity_threshold:
                logger.info(f"유사한 기존 기사 발견: {topic_data['main_title']} (유사도: {total_similarity:.2f})")
                
                # 캐시된 데이터 로드
                cache_file = f"{self.cache_dir}/{topic_id}.json"
                if os.path.exists(cache_file):
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        similar_articles.append((total_similarity, json.load(f)))
        
        if len(similar_articles) > 0:
            similar_articles.sort(key=lambda x: x[0], reverse=True)
            return similar_articles[0][1]
        else:
            return None
        
    def save_article_cache(self, article_data: Dict, keywords: List[str]) -> str:
        """기사 데이터 캐싱"""
        
        # topic_id가 이미 있으면 사용, 없으면 생성
        if 'topic_id' in article_data:
            topic_id = article_data['topic_id']
        else:
            # 주제 해시 생성
            topic_id = self._generate_topic_hash(
                article_data['main_article']['title'], 
                keywords
            )
        
        # 버전 정보 가져오기 (없으면 1)
        version = article_data.get('version', 1)
        
        # 캐시 데이터 구성
        cache_data = {
            'topic_id': topic_id,
            'created_at': article_data.get('created_at', datetime.now().isoformat()),
            'last_updated': datetime.now().isoformat(),
            'version': version,
            'main_article': article_data['main_article'],
            'analysis': article_data.get('analysis', {}),
            'related_articles': article_data.get('related_articles', []),
            'generated_article': article_data.get('comprehensive_article', ''),
            'comprehensive_article': article_data.get('comprehensive_article', ''),  # 둘 다 저장
            'quality_scores': article_data.get('quality_scores', {}),
            'keywords': keywords,
            'update_history': article_data.get('update_history', []),
            'version_history': article_data.get('version_history', []),  # 버전 히스토리 포함
            'tags': article_data.get('tags', {'category_tags': [], 'content_tags': []}),  # 태그 추가
            'source_articles': article_data.get('source_articles', [])  # 소스 기사 URL 목록 추가
        }
        
        # 캐시 파일 저장
        cache_file = f"{self.cache_dir}/{topic_id}.json"
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        
        # 인덱스 업데이트
        # comprehensive_article에서 제목 추출
        comprehensive_title = article_data['main_article']['title']  # 기본값
        comprehensive_content = article_data.get('comprehensive_article', '')
        if comprehensive_content:
            # 첫 번째 # 제목 찾기
            import re
            title_match = re.search(r'^#\s+(.+?)$', comprehensive_content, re.MULTILINE)
            if title_match:
                comprehensive_title = title_match.group(1).strip()
        
        self.topic_index[topic_id] = {
            'main_title': comprehensive_title,
            'generated_title': article_data.get('generated_title'),  # AI 생성 제목 추가
            'keywords': keywords,
            'created_at': cache_data['created_at'],
            'last_updated': cache_data['last_updated'],
            'version': version,
            'tags': article_data.get('tags', {'category_tags': [], 'content_tags': []}),  # 태그 추가
            'source_articles': article_data.get('source_articles', [])  # 소스 기사 URL 목록 추가
        }
        
        # version_history가 있으면 인덱스에도 추가
        if 'version_history' in article_data:
            self.topic_index[topic_id]['version_history'] = article_data['version_history']
        if 'parent_id' in article_data:
            self.topic_index[topic_id]['parent_id'] = article_data['parent_id']
        
        self._save_topic_index()
        
        logger.info(f"기사 캐시 저장 완료: {topic_id} (버전 {version})")
        return topic_id
    
    def check_for_updates(self, cached_data: Dict, new_articles: List[Dict]) -> Dict:
        """새로운 정보 확인 및 업데이트 필요성 판단"""
        
        updates_needed = {
            'has_updates': False,
            'new_facts': [],
            'new_developments': [],
            'corrections': [],
            'additional_sources': []
        }
        
        # 기존 기사 내용
        existing_content = cached_data.get('generated_article', '')
        existing_facts = cached_data.get('analysis', {}).get('facts_vs_allegations', {})
        
        # 새로운 기사들 분석
        for article in new_articles:
            content = article.get('content', '')
            
            # 새로운 날짜/시간 정보
            if '오늘' in content or '방금' in content or '속보' in content:
                updates_needed['has_updates'] = True
                updates_needed['new_developments'].append({
                    'source': article.get('title', ''),
                    'type': 'breaking_news'
                })
            
            # 기존에 없던 정보 찾기
            content_similarity = self._calculate_similarity(
                existing_content[:1000], 
                content[:1000]
            )
            
            if content_similarity < 0.5:  # 충분히 다른 내용
                updates_needed['has_updates'] = True
                updates_needed['new_facts'].append({
                    'source': article.get('title', ''),
                    'content_preview': truncate_text(content, 200)
                })
        
        return updates_needed
    
    def update_article(self, topic_id: str, updates: Dict, new_analysis: Dict) -> Dict:
        """기존 기사 업데이트"""
        
        cache_file = f"{self.cache_dir}/{topic_id}.json"
        if not os.path.exists(cache_file):
            logger.error(f"캐시 파일을 찾을 수 없음: {topic_id}")
            return None
        
        # 기존 데이터 로드
        with open(cache_file, 'r', encoding='utf-8') as f:
            cached_data = json.load(f)
        
        # 버전 증가
        cached_data['version'] += 1
        cached_data['last_updated'] = datetime.now().isoformat()
        
        # 업데이트 이력 추가
        cached_data['update_history'].append({
            'version': cached_data['version'],
            'updated_at': cached_data['last_updated'],
            'updates': updates,
            'reason': updates.get('reason', 'new_information')
        })
        
        # 새로운 분석 결과 병합
        if new_analysis:
            # 기존 분석과 병합
            for key, value in new_analysis.items():
                if key in cached_data['analysis']:
                    if isinstance(value, list):
                        # 리스트는 추가
                        cached_data['analysis'][key].extend(value)
                    elif isinstance(value, dict):
                        # 딕셔너리는 업데이트
                        cached_data['analysis'][key].update(value)
                else:
                    cached_data['analysis'][key] = value
        
        # 캐시 파일 업데이트
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cached_data, f, ensure_ascii=False, indent=2)
        
        # 인덱스 업데이트
        if topic_id in self.topic_index:
            self.topic_index[topic_id]['last_updated'] = cached_data['last_updated']
            self.topic_index[topic_id]['version'] = cached_data['version']
            self._save_topic_index()
        
        logger.info(f"기사 업데이트 완료: {topic_id} (버전 {cached_data['version']})")
        return cached_data
    
    def should_regenerate_article(self, cached_data: Dict, 
                                hours_threshold: int = 6) -> bool:
        """기사 재생성 필요 여부 판단"""
        
        # 마지막 업데이트 시간 확인
        last_updated = datetime.fromisoformat(cached_data['last_updated'])
        time_diff = datetime.now() - last_updated
        
        # 시간 경과 확인
        if time_diff > timedelta(hours=hours_threshold):
            return True
        
        # 주요 업데이트가 3회 이상 누적된 경우
        significant_updates = [
            u for u in cached_data.get('update_history', [])
            if u.get('updates', {}).get('has_updates', False)
        ]
        
        if len(significant_updates) >= 3:
            return True
        
        return False
    
    def get_topic_summary(self) -> List[Dict]:
        """캐시된 주제 요약 반환"""
        
        summaries = []
        for topic_id, topic_data in self.topic_index.items():
            summaries.append({
                'topic_id': topic_id,
                'title': topic_data['main_title'],
                'keywords': topic_data['keywords'],
                'created_at': topic_data['created_at'],
                'last_updated': topic_data['last_updated'],
                'version': topic_data['version']
            })
        
        # 최신 업데이트 순으로 정렬
        summaries.sort(key=lambda x: x['last_updated'], reverse=True)
        return summaries


def test_cache_manager():
    """캐시 매니저 테스트"""
    
    manager = ArticleCacheManager()
    
    # 테스트 데이터
    test_article = {
        'main_article': {
            'title': '이진숙 교육부 장관 후보자 지명 철회',
            'url': 'https://example.com/news/1'
        },
        'analysis': {
            'facts_vs_allegations': {
                'confirmed_facts': ['지명 철회 확정'],
                'unconfirmed_allegations': ['논문 표절 의혹']
            }
        },
        'comprehensive_article': '이진숙 후보자가 지명 철회되었습니다...'
    }
    
    keywords = ['이진숙', '교육부', '장관', '지명철회']
    
    # 1. 캐시 저장
    topic_id = manager.save_article_cache(test_article, keywords)
    print(f"저장된 주제 ID: {topic_id}")
    
    # 2. 유사 기사 확인
    similar = manager.check_existing_article(
        '이진숙 교육부장관 후보 지명철회 소식',
        ['이진숙', '교육부', '철회']
    )
    print(f"유사 기사 발견: {similar is not None}")
    
    # 3. 주제 요약
    summaries = manager.get_topic_summary()
    print(f"캐시된 주제 수: {len(summaries)}")


if __name__ == "__main__":
    test_cache_manager()