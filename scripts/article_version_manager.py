"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

import json
import os
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timezone
import hashlib
from collections import Counter
import re
import logging

logger = logging.getLogger(__name__)

class ArticleVersionManager:
    def __init__(self, cache_dir: str = "cache/articles"):
        self.cache_dir = cache_dir
        self.topic_index_path = os.path.join(cache_dir, "topic_index.json")
        self.load_topic_index()
    
    def load_topic_index(self):
        """주제 인덱스 로드"""
        if os.path.exists(self.topic_index_path):
            with open(self.topic_index_path, 'r', encoding='utf-8') as f:
                self.topic_index = json.load(f)
        else:
            self.topic_index = {}
    
    def save_topic_index(self):
        """주제 인덱스 저장"""
        with open(self.topic_index_path, 'w', encoding='utf-8') as f:
            json.dump(self.topic_index, f, ensure_ascii=False, indent=2)
    
    def extract_key_entities(self, title: str, content: str = "") -> List[str]:
        """제목과 내용에서 주요 개체(인물, 조직 등) 추출"""
        # 간단한 규칙 기반 추출 (향후 NER 모델로 개선 가능)
        entities = []
        
        # 인용부호 내의 내용 제거
        text = re.sub(r'"[^"]*"', '', title + " " + content)
        
        # 주요 패턴
        patterns = [
            r'([가-힣]+)\s*(대통령|장관|의원|후보자|위원장|대표|총리)',  # 인물
            r'([가-힣]+부|[가-힣]+청|[가-힣]+위원회)',  # 정부기관
            r'([가-힣]+당)',  # 정당
            r'([가-힣]+공항|[가-힣]+항공)',  # 장소/조직
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text)
            # 튜플인 경우 첫 번째 그룹만 추출
            for match in matches:
                if isinstance(match, tuple):
                    entities.append(match[0])
                else:
                    entities.append(match)
        
        # 특정 인물명 직접 추출 (띄어쓰기 없는 3글자 이름)
        name_matches = re.findall(r'[가-힣]{2,3}(?=\s|,|\.)', text)
        for name in name_matches:
            if len(name) == 3 and name[0] in '김이박최정강조윤장임':  # 일반적인 성씨
                entities.append(name)
        
        return list(set(entities))
    
    def calculate_similarity(self, title1: str, title2: str, 
                           keywords1: List[str], keywords2: List[str],
                           entities1: List[str], entities2: List[str]) -> float:
        """두 기사의 유사도 계산 (0~1)"""
        # 제목이 완전히 동일한 경우 즉시 높은 유사도 반환
        if title1.strip() == title2.strip():
            return 0.95
        
        # 1. 키워드 유사도
        keywords_set1 = set(keywords1)
        keywords_set2 = set(keywords2)
        if keywords_set1 or keywords_set2:
            keyword_sim = len(keywords_set1 & keywords_set2) / len(keywords_set1 | keywords_set2)
        else:
            keyword_sim = 0
        
        # 2. 개체 유사도 (더 중요)
        entities_set1 = set(entities1)
        entities_set2 = set(entities2)
        if entities_set1 or entities_set2:
            entity_sim = len(entities_set1 & entities_set2) / len(entities_set1 | entities_set2)
        else:
            entity_sim = 0
        
        # 3. 제목 단어 유사도
        title_words1 = set(title1.split())
        title_words2 = set(title2.split())
        if title_words1 or title_words2:
            title_sim = len(title_words1 & title_words2) / len(title_words1 | title_words2)
        else:
            title_sim = 0
        
        # 가중 평균 (개체 유사도에 더 높은 가중치)
        similarity = (entity_sim * 0.5) + (keyword_sim * 0.3) + (title_sim * 0.2)
        
        return similarity
    
    def find_related_article_by_sources(self, new_source_articles: List[str]) -> Optional[str]:
        """소스 기사 URL 기반으로 관련된 기존 토픽 찾기
        
        Args:
            new_source_articles: 새 기사의 소스 URL 리스트
            
        Returns:
            관련 토픽 ID 또는 None
        """
        new_sources = set(new_source_articles)
        
        for article_id, article_info in self.topic_index.items():
            existing_sources = set(article_info.get('source_articles', []))
            
            # 교집합이 있으면 같은 토픽
            if existing_sources & new_sources:
                logger.info(f"소스 기반 매칭: {len(existing_sources & new_sources)}개 공통 소스 발견")
                return article_id
        
        return None  # 새 토픽
    
    def find_related_article(self, new_title: str, new_keywords: List[str], 
                           new_content: str = "", threshold: float = 0.5,
                           time_limit_hours: float = 6.0,
                           new_source_articles: List[str] = None) -> Optional[str]:
        """관련된 기존 기사 찾기 - 소스 기사 URL 기반만 사용
        
        Args:
            new_title: 새 기사 제목
            new_keywords: 새 기사 키워드
            new_content: 새 기사 내용
            threshold: 유사도 임계값 (사용하지 않음)
            time_limit_hours: 동일 토픽 재작성 방지 시간 (사용하지 않음)
            new_source_articles: 새 기사의 소스 URL 리스트
        """
        # 소스 기사 기반으로만 확인
        if new_source_articles:
            related_id = self.find_related_article_by_sources(new_source_articles)
            if related_id:
                return related_id
        
        # 소스 기사가 없거나 매칭이 없으면 None 반환 (새 토픽)
        return None
    
    def check_update_necessity_by_sources(self, existing_sources: List[str], 
                                         new_sources: List[str]) -> Dict[str, Any]:
        """소스 기사 기반 업데이트 필요성 판단
        
        Returns:
            {
                "needs_update": bool,
                "new_sources": List[str],  # 새로 추가된 소스들
                "reason": str
            }
        """
        existing_set = set(existing_sources)
        new_set = set(new_sources)
        
        # 모든 소스가 동일하면 업데이트 불필요
        if existing_set == new_set:
            return {
                "needs_update": False,
                "new_sources": [],
                "reason": "모든 소스 기사가 동일함"
            }
        
        # 새로운 소스가 있으면 업데이트
        new_only = new_set - existing_set
        if new_only:
            return {
                "needs_update": True,
                "new_sources": list(new_only),
                "reason": f"{len(new_only)}개의 새로운 소스 발견"
            }
        
        # 소스가 줄어든 경우 (일반적으로 발생하지 않음)
        return {
            "needs_update": False,
            "new_sources": [],
            "reason": "기존 소스의 부분집합"
        }
    
    def check_update_necessity(self, existing_article: Dict, new_article: Dict) -> Tuple[bool, List[str]]:
        """업데이트 필요성 판단 - 소스 기반 우선"""
        significant_changes = []
        
        # 0. 소스 기사 기반 확인 (우선순위 최상)
        if 'source_articles' in existing_article and 'source_articles' in new_article:
            source_check = self.check_update_necessity_by_sources(
                existing_article['source_articles'],
                new_article['source_articles']
            )
            if source_check['needs_update']:
                significant_changes.append(source_check['reason'])
                return True, significant_changes
            elif not source_check['needs_update'] and source_check['reason'] == "모든 소스 기사가 동일함":
                # 소스가 완전히 동일하면 업데이트 불필요
                return False, ["소스 기사가 모두 동일하여 업데이트 불필요"]
        
        # 1. 주요 수치 변경 확인
        existing_numbers = re.findall(r'\d+', existing_article.get('content', ''))
        new_numbers = re.findall(r'\d+', new_article.get('content', ''))
        
        if set(existing_numbers) != set(new_numbers):
            significant_changes.append("주요 수치 변경")
        
        # 2. 새로운 인물/조직 등장
        existing_entities = self.extract_key_entities(
            existing_article.get('title', ''), 
            existing_article.get('content', '')
        )
        new_entities = self.extract_key_entities(
            new_article.get('title', ''), 
            new_article.get('content', '')
        )
        
        new_entity_additions = set(new_entities) - set(existing_entities)
        if new_entity_additions:
            significant_changes.append(f"새로운 주요 인물/조직: {', '.join(new_entity_additions)}")
        
        # 3. 주요 상태 변경 키워드
        status_keywords = ['확정', '철회', '취소', '결정', '발표', '사망', '실종', '증가', '감소']
        for keyword in status_keywords:
            if keyword in new_article.get('content', '') and keyword not in existing_article.get('content', ''):
                significant_changes.append(f"상태 변경: {keyword}")
        
        # 4. 시간 경과 확인 (24시간 이상)
        if 'created_at' in existing_article:
            existing_time = datetime.fromisoformat(existing_article['created_at'])
            # datetime.now()를 UTC로 변환하여 비교
            current_time_utc = datetime.now(timezone.utc)
            time_diff = current_time_utc - existing_time
            if time_diff.total_seconds() > 86400:  # 24시간
                significant_changes.append("24시간 이상 경과")
        
        # 업데이트 필요 여부 결정
        needs_update = len(significant_changes) > 0
        
        return needs_update, significant_changes
    
    def create_article_version(self, article_data: Dict, parent_id: Optional[str] = None) -> str:
        """새 기사 버전 생성"""
        # 기사 ID 생성
        article_id = hashlib.md5(
            f"{article_data['title']}_{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:12]
        
        # 버전 정보 설정
        if parent_id and parent_id in self.topic_index:
            version = self.topic_index[parent_id].get('version', 1) + 1
            version_history = self.topic_index[parent_id].get('version_history', [])
            version_history.append({
                'version': version - 1,
                'article_id': parent_id,
                'title': self.topic_index[parent_id]['main_title'],
                'created_at': self.topic_index[parent_id]['created_at']
            })
        else:
            version = 1
            version_history = []
        
        # 주제 인덱스 업데이트
        self.topic_index[article_id] = {
            'main_title': article_data['title'],
            'keywords': article_data.get('keywords', []),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'version': version,
            'parent_id': parent_id,
            'version_history': version_history,
            'content_preview': article_data.get('content', '')[:200],  # 처음 200자 저장
            'tags': article_data.get('tags', {'category_tags': [], 'content_tags': []}),  # 태그 정보 추가
            'source_articles': article_data.get('source_articles', [])  # 소스 기사 URL 목록 추가
        }
        
        # 부모 기사가 있다면 히스토리에 보존 (삭제하지 않음)
        if parent_id and parent_id in self.topic_index:
            # 부모 기사 정보를 히스토리에 보존
            parent_info = self.topic_index[parent_id].copy()
            self.topic_index[article_id]['version_history'].insert(0, {
                'version': parent_info['version'],
                'article_id': parent_id,
                'title': parent_info['main_title'],
                'created_at': parent_info['created_at']
            })
            # 부모 기사는 삭제하지 않음 (버전 체인 유지)
        
        self.save_topic_index()
        
        return article_id
    
    def get_article_history(self, article_id: str) -> List[Dict]:
        """기사의 버전 히스토리 가져오기 (부모 버전 포함)"""
        if article_id not in self.topic_index:
            return []
        
        history = []
        current_id = article_id
        
        # 부모 체인을 따라가며 모든 버전 수집
        while current_id:
            if current_id not in self.topic_index:
                break
                
            article_info = self.topic_index[current_id]
            
            # 현재 버전 정보 추가
            version_info = {
                'version': article_info['version'],
                'article_id': current_id,
                'title': article_info['main_title'],
                'created_at': article_info['created_at'],
                'is_current': current_id == article_id
            }
            history.append(version_info)
            
            # 부모로 이동
            current_id = article_info.get('parent_id')
        
        # 버전 번호로 정렬 (최신 버전이 먼저)
        history.sort(key=lambda x: x['version'], reverse=True)
        
        return history