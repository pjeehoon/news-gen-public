"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

"""
실시간 이슈 트렌드 분석 시스템
네이버의 실시간 인기 뉴스와 검색 트렌드를 분석
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import requests
from bs4 import BeautifulSoup
from collections import Counter
import re

logger = logging.getLogger(__name__)

class RealtimeTrendAnalyzer:
    """실시간 트렌드 분석기"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.output_dir = "news_data/trends"
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 의견 기사 필터링 패턴
        self.opinion_patterns = [
            '[사설]', '【사설】', '＜사설＞', '<사설>', '(사설)',
            '[칼럼]', '【칼럼】', '＜칼럼＞', '<칼럼>', '(칼럼)',
            '[기고]', '【기고】', '＜기고＞', '<기고>', '(기고)',
            '[특별기고]', '[시론]', '[논단]', '[기자수첩]', '[데스크칼럼]',
            '[편집국에서]', '[여적]', '[만물상]', '[천자칼럼]', '[춘추칼럼]',
            '[세상읽기]', '[시평]', '[독자투고]', '[독자기고]', '[오피니언]',
            '[사내칼럼]', '[취재수첩]', '[기자칼럼]', '[아침논단]', '[광화문에서]',
            '[여의도포럼]', '[분수대]', '[녹취록]', '[인터뷰]', '[대담]'
        ]
    
    def get_naver_hot_news(self) -> List[Dict]:
        """네이버 메인의 많이 본 뉴스 수집"""
        logger.info("네이버 많이 본 뉴스 수집 시작")
        
        try:
            # 네이버 뉴스 홈에서 많이 본 뉴스 수집
            url = "https://news.naver.com/main/ranking/popularDay.naver"
            logger.info(f"네이버 뉴스 요청 중: {url}")
            response = requests.get(url, headers=self.headers)
            logger.info(f"응답 상태 코드: {response.status_code}, 크기: {len(response.text)} bytes")
            soup = BeautifulSoup(response.text, 'html.parser')
            
            hot_news = []
            
            # 랭킹 박스 찾기
            ranking_boxes = soup.find_all('div', class_='rankingnews_box')
            
            # 각 카테고리별로 뉴스 수집 (다양성 확보)
            category_names = ['종합', '정치', '경제', '사회', '생활/문화', '세계', 'IT/과학']
            news_per_category = 10  # 각 카테고리에서 10개씩
            
            for box_idx, box in enumerate(ranking_boxes[:6]):  # 최대 6개 카테고리
                # 카테고리 이름 추출 시도
                category_header = box.find_previous_sibling(['h4', 'h5']) or box.find_parent().find(['h4', 'h5'])
                if category_header:
                    category_name = category_header.get_text(strip=True)
                else:
                    category_name = category_names[box_idx] if box_idx < len(category_names) else f"카테고리{box_idx+1}"
                
                news_items = box.find_all('li')
                
                # 각 카테고리에서 상위 뉴스 수집
                for item_idx, item in enumerate(news_items[:news_per_category]):
                    link_tag = item.find('a')
                    if link_tag:
                        title = link_tag.get_text(strip=True)
                        link = link_tag.get('href', '')
                        if not link.startswith('http'):
                            link = 'https://news.naver.com' + link
                        
                        # 사설, 칼럼, 기고 등 의견 기사 필터링
                        if self._is_opinion_article(title):
                            logger.info(f"의견 기사 제외: {title[:30]}...")
                            continue
                        
                        hot_news.append({
                            'rank': len(hot_news) + 1,
                            'title': title,
                            'link': link,
                            'source': 'naver_ranking',
                            'category': category_name,
                            'collected_at': datetime.now().isoformat()
                        })
            
            # 못 찾은 경우 다른 선택자 시도
            if not hot_news:
                # 대체 선택자 시도
                news_list = soup.find('ol', class_='rankingnews_list')
                if news_list:
                    items = news_list.find_all('li')
                    for idx, item in enumerate(items[:10], 1):
                        link_tag = item.find('a')
                        if link_tag:
                            title = link_tag.get_text(strip=True)
                            link = link_tag.get('href', '')
                            
                            # 사설, 칼럼, 기고 등 의견 기사 필터링
                            if self._is_opinion_article(title):
                                logger.info(f"의견 기사 제외: {title[:30]}...")
                                continue
                            
                            hot_news.append({
                                'rank': idx,
                                'title': title,
                                'link': link,
                                'source': 'naver_ranking',
                                'collected_at': datetime.now().isoformat()
                            })
            
            logger.info(f"많이 본 뉴스 {len(hot_news)}개 수집 완료")
            return hot_news
            
        except Exception as e:
            logger.error(f"네이버 핫 뉴스 수집 실패: {e}")
            return []
    
    def get_trending_keywords(self, news_list: List[Dict]) -> List[Tuple[str, int]]:
        """뉴스 제목에서 트렌딩 키워드 추출"""
        logger.info("트렌딩 키워드 분석 시작")
        
        # 불용어 리스트
        stopwords = {'은', '는', '이', '가', '을', '를', '의', '에', '와', '과', '도', 
                    '로', '으로', '만', '에서', '까지', '부터', '했다', '한다', '하는',
                    '위해', '따라', '및', '등', '것', '수', '중', '할', '된', '대해'}
        
        # 모든 제목에서 명사 추출
        all_words = []
        for news in news_list:
            title = news.get('title', '')
            # 한글, 영어, 숫자만 추출
            words = re.findall(r'[가-힣]+|[a-zA-Z]+|[0-9]+', title)
            # 2글자 이상만 필터링
            words = [w for w in words if len(w) >= 2 and w not in stopwords]
            all_words.extend(words)
        
        # 빈도수 계산
        word_counter = Counter(all_words)
        trending_keywords = word_counter.most_common(20)
        
        logger.info(f"트렌딩 키워드 {len(trending_keywords)}개 추출 완료")
        return trending_keywords
    
    def analyze_trend_categories(self, news_list: List[Dict]) -> Dict[str, int]:
        """트렌드 카테고리 분석"""
        # 수집된 뉴스의 실제 카테고리 정보 사용
        category_count = {}
        
        for news in news_list:
            # 뉴스에 카테고리 정보가 있으면 사용
            if 'category' in news:
                category = news['category']
                if category not in category_count:
                    category_count[category] = 0
                category_count[category] += 1
            else:
                # 카테고리 정보가 없으면 제목 기반 분석 (이전 방식)
                title = news.get('title', '')
                categories = {
                    '정치': ['대통령', '국회', '정당', '선거', '의원', '정부', '청와대', '총리'],
                    '경제': ['주식', '부동산', '금리', '환율', '투자', '시장', '경제', '기업'],
                    '사회': ['사건', '사고', '범죄', '재판', '경찰', '검찰', '법원', '시민'],
                    '연예': ['배우', '가수', '아이돌', '드라마', '영화', '방송', '연예인', 'TV'],
                    '스포츠': ['축구', '야구', '농구', '골프', '선수', '감독', '경기', '리그'],
                    '국제': ['미국', '중국', '일본', '러시아', '북한', '유럽', '외교', '국제'],
                    'IT/과학': ['AI', '인공지능', '스마트폰', '앱', '게임', '인터넷', 'SNS', '기술', '과학']
                }
                
                for category, keywords in categories.items():
                    if any(keyword in title for keyword in keywords):
                        if category not in category_count:
                            category_count[category] = 0
                        category_count[category] += 1
                        break  # 한 카테고리에만 분류
        
        return category_count
    
    def get_time_based_trends(self) -> Dict:
        """시간대별 트렌드 분석"""
        current_hour = datetime.now().hour
        
        # 시간대별 특성
        time_characteristics = {
            'morning': (6, 9, "출근길 주요 이슈"),
            'late_morning': (9, 12, "오전 주요 뉴스"),
            'lunch': (12, 14, "점심시간 화제"),
            'afternoon': (14, 18, "오후 주요 이슈"),
            'evening': (18, 21, "저녁 주요 뉴스"),
            'night': (21, 24, "밤 시간 이슈"),
            'dawn': (0, 6, "새벽 속보")
        }
        
        for period, (start, end, description) in time_characteristics.items():
            if start <= current_hour < end or (period == 'dawn' and (current_hour >= 0 or current_hour < 6)):
                return {
                    'period': period,
                    'description': description,
                    'current_hour': current_hour
                }
        
        return {'period': 'unknown', 'description': '시간대 분석 불가', 'current_hour': current_hour}
    
    def detect_emerging_issues(self, current_trends: List[Dict], 
                              previous_trends: List[Dict] = None) -> List[Dict]:
        """급상승 이슈 감지"""
        if not previous_trends:
            return []
        
        emerging = []
        
        # 이전 트렌드를 딕셔너리로 변환
        prev_dict = {item['title']: item['rank'] for item in previous_trends}
        
        for current in current_trends:
            title = current['title']
            current_rank = current['rank']
            
            # 새로 등장했거나 순위가 크게 상승한 경우
            if title not in prev_dict:
                emerging.append({
                    'title': title,
                    'type': 'new',
                    'current_rank': current_rank,
                    'change': 'NEW'
                })
            elif prev_dict[title] - current_rank >= 3:  # 3순위 이상 상승
                emerging.append({
                    'title': title,
                    'type': 'rising',
                    'current_rank': current_rank,
                    'previous_rank': prev_dict[title],
                    'change': prev_dict[title] - current_rank
                })
        
        return emerging
    
    def analyze_realtime_trends(self) -> Dict:
        """실시간 트렌드 종합 분석"""
        logger.info("=== 실시간 트렌드 분석 시작 ===")
        
        # 1. 네이버 핫 뉴스 수집
        hot_news = self.get_naver_hot_news()
        
        # 2. 트렌딩 키워드 추출
        trending_keywords = self.get_trending_keywords(hot_news)
        
        # 3. 카테고리 분석
        category_analysis = self.analyze_trend_categories(hot_news)
        
        # 4. 시간대 분석
        time_analysis = self.get_time_based_trends()
        
        # 5. 이전 트렌드와 비교 (있다면)
        previous_file = self.get_latest_trend_file()
        emerging_issues = []
        
        if previous_file:
            with open(previous_file, 'r', encoding='utf-8') as f:
                previous_data = json.load(f)
                previous_trends = previous_data.get('hot_news', [])
                emerging_issues = self.detect_emerging_issues(hot_news, previous_trends)
        
        # 결과 종합
        result = {
            'timestamp': datetime.now().isoformat(),
            'time_analysis': time_analysis,
            'hot_news': hot_news,
            'trending_keywords': trending_keywords,
            'category_distribution': category_analysis,
            'emerging_issues': emerging_issues,
            'summary': self.create_trend_summary(hot_news, trending_keywords, emerging_issues)
        }
        
        # 결과 저장
        self.save_trend_data(result)
        
        logger.info("=== 실시간 트렌드 분석 완료 ===")
        return result
    
    def create_trend_summary(self, hot_news: List[Dict], 
                           keywords: List[Tuple[str, int]], 
                           emerging: List[Dict]) -> Dict:
        """트렌드 요약 생성"""
        summary = {
            'total_trending_news': len(hot_news),
            'top_keywords': [kw[0] for kw in keywords[:5]],
            'emerging_count': len(emerging),
            'analysis_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # 가장 핫한 이슈 3개
        if hot_news:
            summary['top_issues'] = [news['title'] for news in hot_news[:3]]
        
        # 급상승 이슈
        if emerging:
            summary['emerging_titles'] = [e['title'] for e in emerging[:3]]
        
        return summary
    
    def get_latest_trend_file(self) -> str:
        """가장 최근 트렌드 파일 찾기"""
        files = [f for f in os.listdir(self.output_dir) if f.startswith('trend_')]
        if not files:
            return None
        
        files.sort(reverse=True)
        return os.path.join(self.output_dir, files[0])
    
    def save_trend_data(self, data: Dict):
        """트렌드 데이터 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.output_dir}/trend_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"트렌드 데이터 저장: {filename}")
        
        # HTML 리포트도 생성
        self.generate_html_report(data, timestamp)
    
    def _format_emerging_issue(self, issue: Dict) -> str:
        """급상승 이슈 포맷팅"""
        badge = '<span class="new-badge">NEW</span>' if issue.get('type') == 'new' else f'↑{issue.get("change", "")}'
        return f'''
        <div class="emerging">
            {badge}
            {issue.get('title', '')}
        </div>
        '''
    
    def generate_html_report(self, data: Dict, timestamp: str):
        """HTML 형식의 트렌드 리포트 생성"""
        html_content = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>실시간 트렌드 분석 - {timestamp}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .section {{
            background: white;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .trend-item {{
            padding: 10px;
            border-bottom: 1px solid #eee;
        }}
        .trend-item:last-child {{
            border-bottom: none;
        }}
        .rank {{
            display: inline-block;
            width: 30px;
            height: 30px;
            background: #007bff;
            color: white;
            text-align: center;
            line-height: 30px;
            border-radius: 50%;
            margin-right: 10px;
        }}
        .keyword {{
            display: inline-block;
            padding: 5px 10px;
            background: #e9ecef;
            border-radius: 20px;
            margin: 5px;
        }}
        .emerging {{
            background: #fff3cd;
            padding: 10px;
            border-radius: 5px;
            margin: 5px 0;
        }}
        .new-badge {{
            background: #dc3545;
            color: white;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔥 실시간 트렌드 분석</h1>
        <p>분석 시간: {data['summary']['analysis_time']}</p>
        <p>{data['time_analysis']['description']} ({data['time_analysis']['current_hour']}시)</p>
    </div>
    
    <div class="section">
        <h2>📊 트렌드 요약</h2>
        <p>총 {data['summary']['total_trending_news']}개의 핫 이슈 감지</p>
        <p>급상승 이슈: {data['summary']['emerging_count']}개</p>
        <div>
            <strong>TOP 키워드:</strong>
            {' '.join(f'<span class="keyword">{kw}</span>' for kw in data['summary']['top_keywords'])}
        </div>
    </div>
    
    <div class="section">
        <h2>🏆 실시간 인기 뉴스</h2>
        {''.join(f'''
        <div class="trend-item">
            <span class="rank">{news["rank"]}</span>
            <a href="{news["link"]}" target="_blank">{news["title"]}</a>
        </div>
        ''' for news in data['hot_news'])}
    </div>
    
    <div class="section">
        <h2>🚀 급상승 이슈</h2>
        {''.join(self._format_emerging_issue(issue) for issue in data.get('emerging_issues', []))}
    </div>
    
    <div class="section">
        <h2>🏷️ 트렌딩 키워드</h2>
        <div>
            {' '.join(f'<span class="keyword">{kw[0]} ({kw[1]})</span>' 
                     for kw in data['trending_keywords'][:15])}
        </div>
    </div>
</body>
</html>
"""
        
        html_path = f"output/trends/trend_report_{timestamp}.html"
        os.makedirs("output/trends", exist_ok=True)
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"HTML 리포트 생성: {html_path}")
    
    def _is_opinion_article(self, title: str) -> bool:
        """제목을 기반으로 의견 기사(사설, 칼럼 등) 판별"""
        # 모든 종류의 괄호 ([], (), {}, <>, 【】, ＜＞, （）, ｛｝) 형식이 있는 기사 필터링
        import re
        if re.search(r'[\[\(\{<【＜（｛].+?[\]\)\}>】＞）｝]', title):
            return True
        
        # 제목에 의견 기사 패턴이 포함되어 있는지 확인
        for pattern in self.opinion_patterns:
            if pattern in title:
                return True
        
        # 추가 패턴: 제목 시작 부분에 있는 경우
        title_start = title[:20]  # 제목 앞부분만 확인
        opinion_keywords = ['사설', '칼럼', '기고', '시론', '논단', '시평', '기자수첩']
        for keyword in opinion_keywords:
            if keyword in title_start and (title_start.index(keyword) < 10):
                return True
        
        return False


# 테스트 실행
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    analyzer = RealtimeTrendAnalyzer()
    result = analyzer.analyze_realtime_trends()
    
    print("\n=== 실시간 트렌드 분석 결과 ===")
    print(f"분석 시간: {result['summary']['analysis_time']}")
    print(f"시간대: {result['time_analysis']['description']}")
    print(f"\n🔥 TOP 3 이슈:")
    for i, issue in enumerate(result['summary'].get('top_issues', []), 1):
        print(f"{i}. {issue}")
    
    print(f"\n📈 트렌딩 키워드:")
    for keyword, count in result['trending_keywords'][:5]:
        print(f"- {keyword} ({count}회)")