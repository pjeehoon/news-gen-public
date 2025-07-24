"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

"""
네이버 뉴스 클러스터 수집기
- 네이버 뉴스의 '언론사별 주요뉴스' 기능 활용
- 동일 주제에 대한 다양한 언론사 기사 수집
"""

import requests
from bs4 import BeautifulSoup
import json
import logging
from datetime import datetime
import time
from urllib.parse import urlparse, parse_qs

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class NaverNewsClusterCollector:
    """네이버 뉴스 클러스터 수집기"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    
    def get_cluster_news(self, main_article_url: str) -> list:
        """메인 기사와 관련된 클러스터 뉴스 수집"""
        
        # URL에서 oid와 aid 추출
        parsed = urlparse(main_article_url)
        path_parts = parsed.path.split('/')
        
        oid = None
        aid = None
        
        # URL 패턴: /article/oid/aid
        for i, part in enumerate(path_parts):
            if part == 'article' and i + 2 < len(path_parts):
                oid = path_parts[i + 1]
                aid = path_parts[i + 2]
                break
        
        if not oid or not aid:
            logger.error(f"URL에서 oid/aid 추출 실패: {main_article_url}")
            return []
        
        logger.info(f"기사 ID: oid={oid}, aid={aid}")
        
        # 클러스터 페이지 URL
        cluster_url = f"https://news.naver.com/main/list.naver?mode=LPOD&mid=sec&oid={oid}&aid={aid}&isYeonhapFlash=Y"
        
        try:
            # 먼저 메인 기사 페이지에서 클러스터 링크 찾기
            response = requests.get(main_article_url, headers=self.headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            cluster_articles = []
            
            # 1. "언론사별 주요뉴스" 섹션 찾기
            cluster_section = soup.select_one('div.media_end_linked')
            if cluster_section:
                logger.info("언론사별 주요뉴스 섹션 발견")
                
                # 관련 기사 링크들
                news_links = cluster_section.select('li a')
                for link in news_links:
                    title = link.get_text(strip=True)
                    href = link.get('href', '')
                    
                    # 언론사 정보 추출
                    press_elem = link.find_parent('li')
                    press = ''
                    if press_elem:
                        press_text = press_elem.get_text(strip=True)
                        # 언론사명은 보통 제목 앞에 있음
                        if '·' in press_text:
                            press = press_text.split('·')[0].strip()
                    
                    if href and title:
                        full_url = f"https://news.naver.com{href}" if href.startswith('/') else href
                        cluster_articles.append({
                            'title': title,
                            'url': full_url,
                            'press': press
                        })
                        logger.info(f"수집: {title[:30]}... ({press})")
            
            # 2. "이 기사 주제로 쓴 다른 글" 섹션
            related_section = soup.select_one('div._article_section')
            if related_section:
                logger.info("관련 기사 섹션 발견")
                
                related_links = related_section.select('a.link_news')
                for link in related_links:
                    title = link.get_text(strip=True)
                    href = link.get('href', '')
                    
                    # 언론사 정보
                    press_elem = link.find_next_sibling('span', class_='press')
                    press = press_elem.get_text(strip=True) if press_elem else ''
                    
                    if href and title:
                        full_url = f"https://news.naver.com{href}" if href.startswith('/') else href
                        cluster_articles.append({
                            'title': title,
                            'url': full_url,
                            'press': press
                        })
                        logger.info(f"수집: {title[:30]}... ({press})")
            
            # 3. 네이버 뉴스 클러스터 API 시도 (더 많은 기사)
            cluster_api_url = f"https://news.naver.com/main/ajax/cluster/list.naver"
            params = {
                'oid': oid,
                'aid': aid,
                'type': 'pressList'
            }
            
            try:
                api_response = requests.get(cluster_api_url, params=params, headers=self.headers)
                if api_response.status_code == 200:
                    # HTML 응답 파싱
                    api_soup = BeautifulSoup(api_response.text, 'html.parser')
                    
                    # 언론사별 기사 목록
                    press_items = api_soup.select('li')
                    for item in press_items:
                        link_elem = item.select_one('a')
                        if link_elem:
                            title = link_elem.get_text(strip=True)
                            href = link_elem.get('href', '')
                            
                            # 언론사명 추출
                            press_elem = item.select_one('span.press')
                            press = press_elem.get_text(strip=True) if press_elem else ''
                            
                            if href and title:
                                full_url = f"https://news.naver.com{href}" if href.startswith('/') else href
                                cluster_articles.append({
                                    'title': title,
                                    'url': full_url,
                                    'press': press
                                })
                                logger.info(f"API 수집: {title[:30]}... ({press})")
            except Exception as e:
                logger.warning(f"클러스터 API 호출 실패: {e}")
            
            # 중복 제거
            seen_urls = set()
            unique_articles = []
            for article in cluster_articles:
                if article['url'] not in seen_urls:
                    seen_urls.add(article['url'])
                    unique_articles.append(article)
            
            logger.info(f"총 {len(unique_articles)}개의 관련 기사 수집 완료")
            return unique_articles
            
        except Exception as e:
            logger.error(f"클러스터 뉴스 수집 실패: {e}")
            return []
    
    def get_article_content(self, article_url: str) -> dict:
        """기사 본문 추출"""
        try:
            response = requests.get(article_url, headers=self.headers)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 제목
            title = ""
            title_elem = soup.select_one('h2.media_end_head_headline')
            if not title_elem:
                title_elem = soup.select_one('h3.tit_view')  # 다른 형식
            if title_elem:
                title = title_elem.get_text(strip=True)
            
            # 본문
            content = ""
            content_elem = soup.select_one('article#dic_area')
            if not content_elem:
                content_elem = soup.select_one('div#articleBodyContents')  # 구형식
            if content_elem:
                # 불필요한 요소 제거
                for elem in content_elem.select('div.ab_photo, div.end_photo_org, div.vod_player_wrap, script, style'):
                    elem.decompose()
                content = content_elem.get_text(separator='\n', strip=True)
            
            # 날짜
            date = ""
            date_elem = soup.select_one('span.media_end_head_info_datestamp_time')
            if not date_elem:
                date_elem = soup.select_one('span.t11')  # 구형식
            if date_elem:
                date = date_elem.get_text(strip=True)
            
            # 언론사
            press = ""
            press_elem = soup.select_one('a.media_end_head_top_logo img')
            if press_elem:
                press = press_elem.get('alt', '')
            if not press:
                press_elem = soup.select_one('div.press_logo img')
                if press_elem:
                    press = press_elem.get('alt', '')
            
            return {
                'title': title,
                'content': content,
                'date': date,
                'press': press,
                'url': article_url
            }
            
        except Exception as e:
            logger.error(f"기사 추출 실패: {article_url} - {e}")
            return None
    
    def collect_comprehensive_coverage(self, main_article_url: str, max_articles: int = 10) -> dict:
        """주제에 대한 종합적인 보도 수집"""
        
        logger.info("=== 네이버 뉴스 클러스터 수집 시작 ===")
        
        # 1. 메인 기사 내용 수집
        main_article = self.get_article_content(main_article_url)
        if not main_article:
            logger.error("메인 기사 수집 실패")
            return None
        
        logger.info(f"메인 기사: {main_article['title']}")
        
        # 2. 관련 기사들 수집
        cluster_articles = self.get_cluster_news(main_article_url)
        
        # 3. 각 기사 본문 수집
        all_articles = [main_article]
        
        for i, article_info in enumerate(cluster_articles[:max_articles-1]):
            logger.info(f"\n[{i+2}/{max_articles}] {article_info['title'][:50]}...")
            time.sleep(0.5)  # 서버 부하 방지
            
            article_content = self.get_article_content(article_info['url'])
            if article_content:
                all_articles.append(article_content)
        
        # 4. 결과 정리
        result = {
            'main_article': main_article,
            'related_articles': all_articles[1:],
            'total_articles': len(all_articles),
            'timestamp': datetime.now().isoformat(),
            'press_list': list(set([a['press'] for a in all_articles if a.get('press')]))
        }
        
        logger.info(f"\n=== 수집 완료 ===")
        logger.info(f"총 {len(all_articles)}개 기사 수집")
        logger.info(f"언론사: {', '.join(result['press_list'])}")
        
        return result


if __name__ == "__main__":
    collector = NaverNewsClusterCollector()
    
    # 테스트
    test_url = "https://n.news.naver.com/article/437/0000449307"
    result = collector.collect_comprehensive_coverage(test_url, max_articles=5)
    
    if result:
        # 결과 저장
        output_path = f"output/cluster_news/cluster_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        print(f"\n결과 저장: {output_path}")