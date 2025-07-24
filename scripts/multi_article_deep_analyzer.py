"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

"""
동일 주제 다중 기사 심층 분석 시스템
- 네이버 뉴스에서 동일 주제의 여러 기사 수집
- YouTube 동영상 및 Google 검색 결과 통합
- 논란의 구체적 내용과 해명 추출
- 다양한 관점 종합
"""

import requests
from bs4 import BeautifulSoup
import json
import logging
from datetime import datetime
import time
import openai
import os
from dotenv import load_dotenv
from urllib.parse import quote
from typing import Dict, List
from scripts.naver_news_cluster_collector import NaverNewsClusterCollector
from scripts.utils import APIKeyManager, RateLimiter, clean_text, truncate_text
import subprocess
import re

load_dotenv()

# setup_logging 사용하여 로깅 표준화
from scripts.utils import setup_logging

logger = setup_logging("multi_article_deep_analyzer")


class MultiArticleDeepAnalyzer:
    """동일 주제 다중 기사 심층 분석기"""

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }

        # API Key Manager 사용
        self.api_manager = APIKeyManager()
        if not self.api_manager.has_valid_key():
            raise ValueError("No valid API key found")

        self.client = openai.OpenAI(api_key=self.api_manager.get_active_key())
        self.rate_limiter = RateLimiter(calls_per_minute=20)  # OpenAI rate limit

        # 모델명을 환경 변수에서 가져오기
        self.model_name = os.getenv("DETAIL_MODEL", "gpt-4.1-nano")
        logger.info(f"Using model: {self.model_name}")

        self.token_tracker = None  # 외부에서 설정 가능
        self.current_article_id = None  # 현재 처리 중인 기사 ID
        self.current_article_title = None  # 현재 처리 중인 기사 제목

    def search_related_articles(self, main_title: str, limit: int = 10) -> list:
        """네이버에서 관련 기사 검색"""
        # 핵심 키워드 추출
        keywords = self.extract_keywords(main_title)

        # 여러 검색 조합 시도
        search_queries = []
        if len(keywords) >= 2:
            search_queries.append(" ".join(keywords[:2]))  # 상위 2개
        if len(keywords) >= 3:
            search_queries.append(" ".join(keywords[:3]))  # 상위 3개
        if len(keywords) >= 1:
            search_queries.append(keywords[0])  # 첫 번째 키워드만

        all_articles = []
        seen_urls = set()

        for search_query in search_queries:
            if not search_query:
                continue

            logger.info(f"검색 키워드: {search_query}")

            # 네이버 뉴스 검색 - 최신순 정렬
            search_url = f"https://search.naver.com/search.naver?where=news&query={quote(search_query)}&sort=1"

            try:
                response = requests.get(search_url, headers=self.headers)
                soup = BeautifulSoup(response.text, "html.parser")

                # 뉴스 항목 선택자 수정
                news_items = soup.select("div.group_news > ul > li")[:limit]

                if not news_items:
                    # 다른 선택자 시도
                    news_items = soup.select("div.list_news > div.bx")[:limit]

                for item in news_items:
                    # 제목
                    title_elem = item.select_one("a.news_tit, a.api_txt_lines")
                    if not title_elem:
                        continue

                    title = title_elem.get_text(strip=True)
                    link = title_elem.get("href", "")
                    
                    # 사설, 칼럼 등 의견 기사 필터링
                    if self._is_opinion_article(title):
                        logger.info(f"의견 기사 제외: {title[:30]}...")
                        continue

                    # 중복 제거
                    if link in seen_urls:
                        continue
                    seen_urls.add(link)

                    # 언론사
                    press_elem = item.select_one("a.info.press, span.info_group > a.press")
                    press = press_elem.get_text(strip=True) if press_elem else ""

                    # 요약
                    desc_elem = item.select_one("div.news_dsc, div.api_txt_lines.dsc_txt_wrap")
                    description = desc_elem.get_text(strip=True) if desc_elem else ""

                    # 네이버 뉴스 링크인 경우만 수집
                    if "n.news.naver.com" in link:
                        all_articles.append(
                            {
                                "title": title,
                                "link": link,
                                "press": press,
                                "description": description,
                            }
                        )
                        logger.info(f"수집: {title} ({press})")

                        if len(all_articles) >= limit:
                            return all_articles[:limit]

            except Exception as e:
                logger.error(f"기사 검색 실패 ({search_query}): {e}")
                continue

        return all_articles[:limit]

    def search_youtube_videos(self, keywords: list, max_results: int = 5, 
                            main_title: str = None, source_articles: list = None) -> list:
        """
        YouTube에서 관련 동영상 검색
        
        주어진 키워드나 원본 기사 제목으로 YouTube 동영상을 검색하고 자막 정보를 가져옵니다.
        
        Args:
            keywords: 검색할 키워드 리스트
            max_results: 최대 검색 결과 수 (기본값: 5)
            main_title: 메인 기사 제목 (더 정확한 검색을 위해)
            source_articles: 원본 기사 리스트 (제목을 검색어로 활용)
            
        Returns:
            동영상 정보 리스트 [{
                "title": 제목,
                "url": URL,
                "channel": 채널명,
                "transcript": 자막 텍스트
            }]
        """
        import re
        
        # 검색어 생성 우선순위
        search_queries = []
        
        # 1. 키워드가 이미 구체적인 검색 구문인 경우 (ChatGPT가 생성한 search_phrases)
        for keyword in keywords[:3]:
            if len(keyword) > 10 and ' ' in keyword:  # 구문으로 보이는 경우
                search_queries.append(keyword)
        
        # 2. 원본 기사 제목 활용
        if source_articles and len(search_queries) < 2:
            for article in source_articles[:2]:  # 상위 2개 기사
                title = article.get('title', '')
                if title:
                    # 언론사명과 특수문자 제거
                    clean_title = re.sub(r'\[.*?\]', '', title)  # [언론사] 제거
                    clean_title = re.sub(r'[""\'\']', '', clean_title)  # 따옴표 제거
                    clean_title = re.sub(r'[…·]', ' ', clean_title)  # 특수문자를 공백으로
                    clean_title = re.sub(r'\s+', ' ', clean_title).strip()
                    
                    if clean_title and len(clean_title) > 5:
                        search_queries.append(clean_title)
        
        # 3. 메인 제목 사용
        if main_title and len(search_queries) < 2:
            clean_main = re.sub(r'\[.*?\]', '', main_title)
            clean_main = re.sub(r'[""\'\']', '', clean_main)
            clean_main = re.sub(r'[…·]', ' ', clean_main)
            clean_main = re.sub(r'\s+', ' ', clean_main).strip()
            if clean_main:
                search_queries.append(clean_main)
        
        # 4. 기본 키워드 조합 (폴백)
        if not search_queries:
            search_query = " ".join(keywords[:3])
            search_queries.append(search_query)
        
        # 중복 제거
        seen = set()
        unique_queries = []
        for query in search_queries:
            if query not in seen:
                seen.add(query)
                unique_queries.append(query)
        
        logger.info(f"YouTube 검색어 목록: {unique_queries[:2]}")
        
        # 첫 번째 검색어로 검색 시도
        try:
            search_query = unique_queries[0]
            logger.info(f"YouTube 검색: {search_query}")

            # 외부 검색 API 사용
            try:
                # 절대 경로 임포트를 먼저 시도 (GitHub Actions 환경)
                import sys
                import os

                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from external_search import search_youtube

                videos = search_youtube(search_query, max_results)
                if videos:
                    logger.info(f"YouTube API/스크래핑으로 {len(videos)}개 동영상 검색 완료")
                    
                    # 트랜스크립트 추가 시도 (우선순위: youtube-transcript-api > yt-dlp)
                    transcript_extracted = False
                    
                    # 1. 먼저 youtube-transcript-api 시도 (가볍고 빠름)
                    try:
                        from youtube_transcript_api import YouTubeTranscriptApi
                        
                        for video in videos:
                            video_id = video.get('videoId', '')
                            if video_id:
                                try:
                                    logger.info(f"트랜스크립트 추출 시도 (youtube-transcript-api): {video.get('title', '')[:50]}...")
                                    # 한국어 우선, 영어 대체로 시도
                                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
                                    
                                    # 자막 텍스트 결합
                                    full_text = ' '.join([entry['text'] for entry in transcript_list])
                                    
                                    # ChatGPT로 관련 부분만 스마트 추출
                                    video['transcript'] = self._extract_relevant_transcript(
                                        full_text, 
                                        keywords,  # 메서드 파라미터의 keywords 사용
                                        video.get('title', '')
                                    )
                                    logger.info(f"트랜스크립트 추출 및 분석 성공")
                                except Exception as e:
                                    # 자막이 없거나 비활성화된 경우
                                    video['transcript'] = ""
                                    logger.debug(f"youtube-transcript-api 실패: {str(e)}")
                            else:
                                video['transcript'] = ""
                        transcript_extracted = True
                        
                    except ImportError:
                        logger.info("youtube-transcript-api가 없습니다. yt-dlp로 시도합니다.")
                    
                    # 2. youtube-transcript-api 실패 시 yt-dlp 사용
                    if not transcript_extracted:
                        try:
                            import yt_dlp
                            
                            for video in videos:
                                video_id = video.get('videoId', '')
                                if video_id:
                                    try:
                                        logger.info(f"트랜스크립트 추출 시도 (yt-dlp): {video.get('title', '')[:50]}...")
                                        
                                        ydl_opts = {
                                            'quiet': True,
                                            'no_warnings': True,
                                            'skip_download': True,
                                            'writesubtitles': True,
                                            'writeautomaticsub': True,
                                            'subtitleslangs': ['ko', 'en'],
                                        }
                                        
                                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                                            info = ydl.extract_info(f"https://youtube.com/watch?v={video_id}", download=False)
                                            
                                            # 자막 데이터 추출
                                            subtitles = info.get('subtitles', {})
                                            automatic_captions = info.get('automatic_captions', {})
                                            
                                            transcript_text = ""
                                            
                                            # 한국어 우선, 영어 대체
                                            for lang in ['ko', 'en']:
                                                if lang in subtitles and subtitles[lang]:
                                                    # 자막 URL에서 텍스트 추출 (간단한 방법)
                                                    transcript_text = f"[{lang}] 자막 사용 가능"
                                                    break
                                                elif lang in automatic_captions and automatic_captions[lang]:
                                                    transcript_text = f"[{lang}] 자동 생성 자막 사용 가능"
                                                    break
                                            
                                            video['transcript'] = transcript_text[:200] if transcript_text else ""
                                            if transcript_text:
                                                logger.info(f"yt-dlp 트랜스크립트 감지 성공")
                                            
                                    except Exception as e:
                                        video['transcript'] = ""
                                        logger.debug(f"yt-dlp 트랜스크립트 추출 실패: {str(e)}")
                                else:
                                    video['transcript'] = ""
                                    
                        except ImportError:
                            logger.warning("youtube-transcript-api와 yt-dlp 모두 없습니다. 트랜스크립트 없이 진행합니다.")
                            for video in videos:
                                video['transcript'] = ""
                        except Exception as e:
                            logger.warning(f"트랜스크립트 추출 중 예상치 못한 오류: {e}")
                            for video in videos:
                                video['transcript'] = ""
                    
                    return videos
            except ImportError:
                logger.warning("external_search 모듈을 찾을 수 없습니다")
            except Exception as e:
                logger.warning(f"YouTube API 검색 실패: {e}")

            # API가 없으면 빈 리스트 반환
            logger.info("YouTube API 키가 없거나 오류 발생 - 검색 건너뜀")
            return []

        except Exception as e:
            logger.error(f"YouTube 검색 오류: {e}")
            return []

    def search_google_articles(self, keywords: list, num_results: int = 10) -> list:
        """Google에서 관련 기사 검색"""
        try:
            search_query = " ".join(keywords[:3])  # 상위 3개 키워드 사용
            logger.info(f"Google 검색: {search_query}")

            # 외부 검색 API 사용
            try:
                # 절대 경로 임포트를 먼저 시도 (GitHub Actions 환경)
                import sys
                import os

                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                from external_search import search_google

                results = search_google(search_query, num_results)
                if results:
                    logger.info(f"Google API로 {len(results)}개 결과 검색 완료")
                    return results
            except ImportError:
                logger.warning("external_search 모듈을 찾을 수 없습니다")
            except Exception as e:
                logger.warning(f"Google API 검색 실패: {e}")

            # API가 없으면 빈 리스트 반환
            logger.info("Google API 키가 없거나 오류 발생 - 검색 건너뜀")
            return []

        except Exception as e:
            logger.error(f"Google 검색 오류: {e}")
            return []

    def extract_keywords(self, title: str, article_content: str = None) -> list:
        """
        ChatGPT API를 사용하여 제목에서 핵심 키워드 추출
        
        뉴스 제목과 선택적으로 본문 내용을 분석하여 YouTube 검색에 
        최적화된 키워드와 검색 구문을 추출합니다.
        
        Args:
            title: 키워드를 추출할 뉴스 제목
            article_content: 선택적 기사 본문 (더 정확한 키워드 추출을 위해)
            
        Returns:
            추출된 키워드 리스트 (중요도 순)
        """
        import json
        
        try:
            # ChatGPT API를 사용한 스마트 키워드 추출
            prompt = f"""
다음 뉴스 제목에서 YouTube 검색에 가장 적합한 키워드를 추출해주세요.

제목: {title}
{f'본문 요약: {article_content[:500]}...' if article_content else ''}

요구사항:
1. YouTube 검색 시 관련 동영상을 찾을 수 있는 구체적인 키워드 5-7개
2. 사건의 핵심 주제, 인물, 장소, 사건명 포함
3. 너무 일반적인 단어(예: 한국, 논란, 사건)는 다른 구체적 단어와 조합
4. 검색어로 사용할 수 있는 자연스러운 구문도 포함
5. 실제 YouTube에서 검색했을 때 관련 영상이 나올 만한 구체적 표현 사용

응답 형식 (JSON):
{{
    "keywords": ["키워드1", "키워드2", "키워드3", ...],
    "search_phrases": ["검색 구문1", "검색 구문2"]
}}

예시:
- 제목: "이주노동자 비닐 결박 사건"
- keywords: ["이주노동자", "비닐 결박", "인권침해", "노동자 학대", "외국인 노동자"]
- search_phrases: ["이주노동자 비닐 결박 사건", "외국인 노동자 인권침해"]
"""

            # Rate limiting 적용
            self.rate_limiter.wait_if_needed()
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "youtube_keywords",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "keywords": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "YouTube 검색용 키워드 (5-7개)"
                                },
                                "search_phrases": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "YouTube 검색용 구문 (2-3개)"
                                }
                            },
                            "required": ["keywords", "search_phrases"],
                            "additionalProperties": False
                        },
                        "strict": True
                    }
                }
            )
            
            # 토큰 사용량 추적
            self.token_tracker.track_api_call(
                response, 
                self.model_name,
                getattr(self, 'current_article_id', None),
                title
            )
            
            # 응답 파싱
            result = json.loads(response.choices[0].message.content)
            keywords = result.get("keywords", [])
            search_phrases = result.get("search_phrases", [])
            
            # 키워드와 검색 구문 결합
            all_keywords = keywords + search_phrases
            
            # 중복 제거하면서 순서 유지
            seen = set()
            unique_keywords = []
            for keyword in all_keywords:
                if keyword not in seen and keyword.strip():
                    seen.add(keyword)
                    unique_keywords.append(keyword)
            
            logger.info(f"ChatGPT로 추출된 키워드: {unique_keywords[:10]}")
            return unique_keywords[:10]  # 최대 10개 반환
            
        except Exception as e:
            logger.error(f"ChatGPT 키워드 추출 실패: {e}")
            # 폴백: 간단한 패턴 기반 추출
            return self._extract_keywords_fallback(title, [])

    def _extract_keywords_fallback(self, title: str, existing_keywords: list) -> list:
        """간단한 패턴 기반 키워드 추출 (폴백 메서드)"""
        import re

        keywords = existing_keywords.copy()

        # 특수문자 제거하고 단어 분리
        clean_title = re.sub(r"[^\w\s]", " ", title)
        words = clean_title.split()

        # 중요 단어 필터링
        for word in words:
            if len(word) >= 2 and word not in keywords and len(keywords) < 10:
                # 뉴스에서 중요한 단어들
                if any(
                    key in word
                    for key in [
                        "살해",
                        "사건",
                        "총격",
                        "논란",
                        "의혹",
                        "폭로",
                        "갑질",
                        "대통령",
                        "장관",
                        "의원",
                        "후보",
                        "사고",
                        "폭발",
                        "화재",
                        "충돌",
                        "피해",
                    ]
                ):
                    keywords.append(word)
                # 숫자가 포함된 단어 (나이, 금액 등)
                elif any(char.isdigit() for char in word):
                    keywords.append(word)

        # 그래도 키워드가 부족하면 긴 단어들 추가
        if len(keywords) < 5:
            long_words = [w for w in words if len(w) >= 3 and w not in keywords]
            keywords.extend(long_words[: 10 - len(keywords)])

        # 키워드가 여전히 없으면 제목 자체를 사용
        if not keywords:
            keywords = [title[:20]]  # 제목의 앞 20자

        return keywords[:10]

    def extract_article_details(self, article_url: str) -> dict:
        """
        기사 본문에서 상세 정보 추출
        
        네이버 뉴스 기사의 본문, 제목, 날짜 등을 추출합니다.
        
        Args:
            article_url: 네이버 뉴스 기사 URL
            
        Returns:
            기사 상세 정보 디텍셔너리 {
                "title": 제목,
                "content": 본문,
                "date": 작성일,
                "url": URL
            } (실패 시 None)
        """
        try:
            response = requests.get(article_url, headers=self.headers)
            soup = BeautifulSoup(response.text, "html.parser")

            # 제목
            title = ""
            title_elem = soup.select_one("h2.media_end_head_headline")
            if title_elem:
                title = title_elem.get_text(strip=True)

            # 본문
            content = ""
            content_elem = soup.select_one("article#dic_area")
            if content_elem:
                # 불필요한 요소 제거
                for elem in content_elem.select(
                    "div.ab_photo, div.end_photo_org, div.vod_player_wrap"
                ):
                    elem.decompose()
                content = content_elem.get_text(separator="\n", strip=True)

            # 날짜
            date = ""
            date_elem = soup.select_one("span.media_end_head_info_datestamp_time")
            if date_elem:
                date = date_elem.get_text(strip=True)

            return {"title": title, "content": content, "date": date, "url": article_url}

        except Exception as e:
            logger.error(f"기사 추출 실패: {article_url} - {e}")
            return None

    def analyze_controversies(self, articles_content: list) -> dict:
        """
        여러 기사에서 논란과 해명 분석
        
        AI를 사용하여 여러 기사에서 논란, 해명, 평가 등을 종합적으로 분석합니다.
        
        Args:
            articles_content: 분석할 기사 내용 리스트
            
        Returns:
            분석 결과 디텍셔너리 {
                "controversies": 논란 사항,
                "clarifications": 해명 내용,
                "evaluations": 평가,
                "facts_vs_allegations": 사실 vs 의혹,
                "timeline": 타임라인,
                "comprehensive_summary": 종합 요약
            }
        """

        # 현재 날짜
        current_date = datetime.now().strftime("%Y년 %m월 %d일")

        # 모든 기사 내용 합치기 (프롬프트 크기 최적화)
        # 기사 수에 따라 내용 길이 조정
        if len(articles_content) >= 6:
            max_content_per_article = 800
        elif len(articles_content) >= 4:
            max_content_per_article = 1000
        else:
            max_content_per_article = 1200
            
        combined_content = "\n\n---\n\n".join(
            [
                f"[{i+1}번 기사]\n제목: {a.get('title', '')}\n작성일: {a.get('date', '날짜 없음')}\n내용: {a.get('content', '')[:max_content_per_article]}"
                for i, a in enumerate(articles_content)
                if a
            ]
        )

        prompt = f"""
다음 기사들을 분석하여 핵심 정보를 추출해주세요.

현재 날짜: {current_date}

{combined_content}

다음 형식으로 간단히 정리해주세요:

1. controversies: 주요 논란들
   - person_name: 인물명
   - issues: [{{"issue_type": "논란 유형", "details": "핵심 내용", "source": "언론사"}}]

2. clarifications: 해명/반박
   - person_name: 인물명  
   - responses: [{{"issue": "논란", "clarification": "해명 내용", "date": "날짜"}}]

3. evaluations: 평가 (최대 3개)
   - source: 평가자
   - opinion: 핵심 의견
   - stance: 긍정적/부정적/중립적

4. facts_vs_allegations:
   - confirmed_facts: ["확인된 사실 1", "확인된 사실 2"]
   - unconfirmed_allegations: ["의혹 1", "의혹 2"]

5. timeline: 주요 사건 (최대 5개)
   - date: 날짜
   - event: 사건

간결하게 핵심만 추출하여 JSON으로 답변하세요.
"""

        try:
            # Rate limiting 적용
            self.rate_limiter.wait_if_needed()
            
            start_time = time.time()
            logger.info(f"논란 분석 API 호출 시작... (기사 {len(articles_content)}개, 프롬프트 길이: {len(prompt)}자)")

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2000,  # 응답 길이 제한
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "controversy_analysis",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "controversies": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "person_name": {"type": "string"},
                                            "issues": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "issue_type": {"type": "string"},
                                                        "details": {"type": "string"},
                                                        "source": {"type": "string"}
                                                    },
                                                    "required": ["issue_type", "details", "source"],
                                                    "additionalProperties": False
                                                }
                                            }
                                        },
                                        "required": ["person_name", "issues"],
                                        "additionalProperties": False
                                    }
                                },
                                "clarifications": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "person_name": {"type": "string"},
                                            "responses": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "issue": {"type": "string"},
                                                        "clarification": {"type": "string"},
                                                        "date": {"type": "string"}
                                                    },
                                                    "required": ["issue", "clarification", "date"],
                                                    "additionalProperties": False
                                                }
                                            }
                                        },
                                        "required": ["person_name", "responses"],
                                        "additionalProperties": False
                                    }
                                },
                                "evaluations": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "source": {"type": "string"},
                                            "opinion": {"type": "string"},
                                            "stance": {"type": "string", "enum": ["긍정적", "부정적", "중립적"]}
                                        },
                                        "required": ["source", "opinion", "stance"],
                                        "additionalProperties": False
                                    }
                                },
                                "facts_vs_allegations": {
                                    "type": "object",
                                    "properties": {
                                        "confirmed_facts": {
                                            "type": "array",
                                            "items": {"type": "string"}
                                        },
                                        "unconfirmed_allegations": {
                                            "type": "array",
                                            "items": {"type": "string"}
                                        }
                                    },
                                    "required": ["confirmed_facts", "unconfirmed_allegations"],
                                    "additionalProperties": False
                                },
                                "timeline": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "date": {"type": "string"},
                                            "event": {"type": "string"}
                                        },
                                        "required": ["date", "event"],
                                        "additionalProperties": False
                                    }
                                }
                            },
                            "required": ["controversies", "clarifications", "evaluations", "facts_vs_allegations", "timeline"],
                            "additionalProperties": False
                        },
                        "strict": True
                    }
                },
                timeout=60  # 60초 타임아웃 추가
            )

            # 토큰 사용량 추적
            if self.token_tracker and self.current_article_id:
                self.token_tracker.track_api_call(
                    response, self.model_name, self.current_article_id, self.current_article_title
                )

            analysis = json.loads(response.choices[0].message.content)
            elapsed_time = time.time() - start_time
            logger.info(f"논란 분석 API 호출 완료 (소요 시간: {elapsed_time:.1f}초)")
            return analysis

        except Exception as e:
            logger.error(f"논란 분석 실패: {e}")
            return None

    def generate_tags(
        self, article_title: str, article_content: str, news_category: str = None
    ) -> Dict[str, List[str]]:
        """기사에 대한 태그 자동 생성 - AI가 자유롭게 생성"""

        # 카테고리 매핑 (폴백용)
        category_mapping = {
            "종합": "종합",
            "정치": "정치",
            "경제": "경제",
            "사회": "사회",
            "생활/문화": "생활문화",
            "IT/과학": "IT과학",
            "연예": "연예",
            "스포츠": "스포츠",
            "국제": "국제",
        }

        try:
            prompt = f"""
다음 기사의 제목과 내용을 분석하여 태그를 생성해주세요.

제목: {article_title}
내용: {article_content[:1500]}

태그 생성 규칙:
1. category_tags: 기사의 분야를 나타내는 태그 (1-2개)
   - 정치, 경제, 사회, 생활/문화, IT/과학, 국제 중에서만 선택 (정확히 이 형태로)
   - 기사 내용에 가장 적합한 카테고리 선택

2. content_tags: 기사의 구체적인 내용을 나타내는 태그 (5-10개)
   - 기사에서 중요한 모든 개념, 주제, 인물, 조직, 사건 등을 자유롭게 추출
   - 미리 정해진 목록에 제한되지 않고 기사 내용에 맞는 태그를 동적으로 생성
   - 태그는 구체적이고 검색하기 쉬운 단어나 짧은 구문
   - 예시:
     * 인물명: "윤석열", "이재명", "일론머스크"
     * 조직/기업: "삼성전자", "국민의힘", "더불어민주당", "테슬라"
     * 사건/이슈: "부동산정책", "반도체수출규제", "코로나19", "우크라이나전쟁"
     * 기술/제품: "ChatGPT", "전기차", "5G", "메타버스"
     * 지역: "서울", "부산", "강남", "판교"
     * 정책/법안: "부동산세제", "최저임금", "탄소중립"
   - 태그는 한국어로 작성하되, 널리 알려진 영어 약어는 그대로 사용 (AI, IT, CEO 등)
   - 동의어보다는 가장 일반적으로 사용되는 표현 선택

반드시 다음 JSON 형식으로만 응답하세요:
{{
    "category_tags": ["카테고리1"],
    "content_tags": ["태그1", "태그2", "태그3", "태그4", "태그5", ...]
}}
"""

            # Rate limiting 적용
            self.rate_limiter.wait_if_needed()

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "당신은 뉴스 기사를 분석하여 검색과 분류에 유용한 태그를 생성하는 전문가입니다. 기사의 모든 중요한 요소를 태그로 추출하세요.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.4,  # 약간 높여서 다양성 증가
                max_tokens=300,  # 더 많은 태그를 위해 증가
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "news_tags",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "category_tags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "기사의 카테고리 태그 (정치, 경제, 사회 등)"
                                },
                                "content_tags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "기사 내용 관련 태그 (인물명, 조직명, 주요 키워드 등)"
                                }
                            },
                            "required": ["category_tags", "content_tags"],
                            "additionalProperties": False
                        },
                        "strict": True
                    }
                }
            )

            # 토큰 사용량 추적
            if self.token_tracker and self.current_article_id:
                self.token_tracker.track_api_call(
                    response, self.model_name, self.current_article_id, self.current_article_title
                )

            tags = json.loads(response.choices[0].message.content)

            # 태그 정제 - 너무 긴 태그 제거, 중복 제거
            if "content_tags" in tags:
                # 중복 제거 및 길이 제한
                unique_tags = []
                seen = set()
                for tag in tags["content_tags"]:
                    tag = tag.strip()
                    if tag and len(tag) <= 20 and tag not in seen:  # 20자 이하
                        unique_tags.append(tag)
                        seen.add(tag.lower())  # 대소문자 구분 없이 중복 체크
                tags["content_tags"] = unique_tags[:15]  # 최대 15개로 제한

            # 카테고리 태그가 없으면 전달받은 카테고리 사용
            if news_category and (not tags.get("category_tags") or len(tags["category_tags"]) == 0):
                mapped_category = category_mapping.get(news_category, news_category)
                tags["category_tags"] = [mapped_category]

            # 최소 태그 수 보장
            if len(tags.get("content_tags", [])) < 3:
                # 제목과 내용에서 추가 키워드 추출
                keywords = self.extract_keywords(article_title, comprehensive_article[:500])
                for keyword in keywords:
                    if keyword not in tags.get("content_tags", []) and len(keyword) <= 20:
                        tags.setdefault("content_tags", []).append(keyword)
                        if len(tags["content_tags"]) >= 5:
                            break

            return tags

        except Exception as e:
            logger.error(f"태그 생성 실패: {e}")
            # 기본 태그 반환
            default_category = (
                category_mapping.get(news_category, "종합") if news_category else "종합"
            )
            # 제목에서라도 키워드 추출 시도
            keywords = self.extract_keywords(article_title, None)[:5]
            return {"category_tags": [default_category], "content_tags": keywords}

    def create_comprehensive_article(self, main_article: dict, analysis: dict, 
                                    version: int = 1, previous_article_content: str = None) -> str:
        """
        종합적인 심층 기사 생성
        
        AI를 사용하여 분석 결과를 바탕으로 종합적인 심층 기사를 작성합니다.
        
        Args:
            main_article: 메인 기사 정보
            analysis: 분석 결과
            
        Returns:
            마크다운 형식의 심층 기사
        """

        # 현재 날짜
        current_date = datetime.now().strftime("%Y년 %m월 %d일")

        # betterNews와 AINews 스타일의 향상된 프롬프트
        system_prompt = """당신은 매우 능력 있는 뉴스 기사 분석 및 작성 AI 저널리스트입니다.
여러 언론사의 기사를 종합하여 균형잡힌 새로운 뉴스 기사를 작성하는 것이 당신의 임무입니다.
객관적이고 사실 기반의 보도를 추구하며, 모든 정보의 검증 가능성을 중시합니다."""

        # 버전 정보 포함
        version_info = f"\n[버전 정보]\n현재 버전: {version}\n"
        if version > 1 and previous_article_content:
            version_info += f"\n[이전 버전 기사]\n{previous_article_content[:2000]}...\n"
        
        prompt = f"""
작성자는 여러 언론사의 기사를 종합하여 새로운 뉴스 기사를 작성하는 AI 저널리스트입니다.
다음 정보를 바탕으로 심층 분석 기사를 작성해주세요.

현재 날짜: {current_date}
{version_info}

[분석 대상 정보]
메인 기사: {json.dumps(main_article, ensure_ascii=False, indent=2)}
종합 분석: {json.dumps(analysis, ensure_ascii=False, indent=2)}
YouTube 영상: {json.dumps(analysis.get('youtube_context', []), ensure_ascii=False, indent=2)}
Google 검색: {json.dumps(analysis.get('google_context', []), ensure_ascii=False, indent=2)}

[기사 작성 지침]

1. **정보 검증 가능성 평가**:
   - 구체적 근거(인용문, 공식 발표, 정보원 등)가 있는 경우 → 해당 정보와 함께 원본 링크를 [언론사명](URL) 형식으로 포함
   - 근거가 부족한 경우 → "확인되지 않은", "추정되는" 등의 표현 사용
   - 예: "[조선일보](https://example.com)에 따르면, 2025년 7월 23일 발표된 보고서에서..."
   - **중요: 언론사명은 반드시 URL에서 추출하여 정확히 표기할 것**
     * www.chosun.com → 조선일보
     * www.donga.com → 동아일보
     * n.news.naver.com → 네이버뉴스

2. **출처 투명성**:
   - "한 관계자", "정통한 소식통" 등 모호한 표현 지양
   - 가능한 한 구체적인 출처 명시
   - 익명 출처의 경우 그 이유 설명

3. **균형잡힌 관점 제시**:
   - 찬성/긍정적 측면과 반대/부정적 측면 모두 포함
   - 중립적/전문가 의견 인용
   - 일반 시민의 관점도 고려

4. **기사 품질 기준**:
   - High: 단순 정보 전달을 넘어 심층 분석과 그 근거 제시
   - Medium: 정보 전달 중심, 분석이 있어도 근거 부족
   - Low: 출처 불명확, 사실 확인 어려움

5. **제목 작성 원칙**:
   - 핵심 사실을 명확하게 전달하는 서술적 제목
   - 클릭베이트나 선정적 표현 절대 금지
   - 5W1H 원칙에 따른 구체적 정보 포함
   - 예: "정부 의대 정원 2천명 증원 결정에 의료계 집단 행동 예고"
   - **중요: 원본 기사의 제목을 그대로 사용하지 말고, 반드시 새롭게 재구성한 독창적인 제목 작성**
   - **저작권 보호를 위해 원문과 완전히 다른 표현과 구조로 작성**

6. **중요 정보 처리**:
   - 새롭게 밝혀진 사실은 "▶ 새로운 사실:" 로 시작
   - 중요한 정보는 **굵은 글씨**로 강조
   - 모든 중요 정보에 원본 기사 링크 직접 삽입

7. **날짜 및 시제**:
   - 모든 날짜는 "YYYY년 MM월 DD일" 형식으로 구체적 명시
   - "오늘", "어제" 등 상대적 시간 표현 금지
   - 최근 사건은 현재 진행형으로 작성

[기사 구성 요소]

마크다운 형식으로 기사를 작성해주세요. 다음 구조를 따라주세요:

# [기사 제목]

[핵심 내용을 200자 내외로 요약하여 도입부 작성]

### 주요 사실과 경과

[시간순으로 주요 사실들을 정리]

### 다양한 관점과 분석

[여러 언론사와 전문가들의 다양한 시각 제시]

### 검증된 사실 vs 미확인 정보

[확인된 사실과 추측성 정보를 명확히 구분]

### 핵심 인물과 이해관계

[관련 인물들과 그들의 입장 정리]

### 향후 전망

[앞으로의 전개 방향과 영향 분석]

### 참고 자료

[인용한 기사들의 링크 목록]

**저작권 준수 지침**:
- 원본 기사의 문장을 그대로 복사하지 말 것
- 사실은 인용하되, 반드시 자신의 언어로 재구성하여 표현
- 직접 인용이 필요한 경우 반드시 인용부호("")와 출처 명시
- 3문장 이상 연속으로 원문과 유사한 구조 금지

중요한 정보나 특별한 진술에 대해서는 본문 내에 마크다운 형식으로 원본 기사 링크를 직접 삽입:
예: "[조선일보](https://example.com/news/123)에 따르면, 2025년 7월 23일 발표된..."

{f'''버전 2 이상에서는 이전 버전과 비교하여 실제로 새로운 정보만 강조:
- "▶ 새로운 사실: **실제로 새롭게 밝혀진 정보**"
- "▶ 업데이트: **기존 정보의 변경사항**"''' if version > 1 else '''주요 사실과 경과를 일반적으로 서술:
- "▶ " 기호 사용하여 중요 사실 표시
- "새로운 사실", "최초 공개" 등의 표현은 사용하지 않음'''}

모든 정보는 객관적으로 기술하고, 특정 정치적 견해를 드러내지 않도록 합니다.
다양한 관점을 균형있게 통합하여 하나의 완결된 기사로 작성해주세요.
"""

        try:
            # Rate limiting 적용
            self.rate_limiter.wait_if_needed()
            
            start_time = time.time()
            logger.info(f"심층 기사 생성 API 호출 시작... (프롬프트 길이: {len(prompt)}자)")

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
                max_tokens=3000
            )

            # 토큰 사용량 추적
            if self.token_tracker and self.current_article_id:
                self.token_tracker.track_api_call(
                    response, self.model_name, self.current_article_id, self.current_article_title
                )

            # 마크다운 텍스트 반환
            elapsed_time = time.time() - start_time
            logger.info(f"심층 기사 생성 API 호출 완료 (소요 시간: {elapsed_time:.1f}초)")
            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"기사 생성 실패: {e}")
            return None

    def analyze_topic(self, main_news_url: str, main_title: str, news_category: str = None, 
                     version: int = 1, previous_article_content: str = None) -> dict:
        """주제에 대한 종합 분석"""

        logger.info(f"=== 다중 기사 심층 분석 시작 ===")
        logger.info(f"메인 기사: {main_title}")

        # 네이버 뉴스 클러스터 수집기 사용
        cluster_collector = NaverNewsClusterCollector()

        # 1. 클러스터 기사 수집 (동일 주제의 다양한 언론사 기사)
        logger.info("\n1단계: 네이버 뉴스 클러스터 수집")
        cluster_result = cluster_collector.collect_comprehensive_coverage(
            main_news_url, max_articles=20  # 10 -> 20으로 증가
        )

        if not cluster_result or not cluster_result.get("main_article"):
            # 클러스터 수집 실패 시 기존 방식으로 폴백
            logger.warning("클러스터 수집 실패, 검색 방식으로 전환")
            return self._analyze_topic_fallback(main_news_url, main_title)

        # 수집된 기사들
        articles_content = [cluster_result["main_article"]] + cluster_result.get(
            "related_articles", []
        )
        
        # URL에서 언론사명 추출하여 각 기사에 추가
        for article in articles_content:
            if 'link' in article and article['link']:
                article['media_from_url'] = self.extract_media_from_url(article['link'])
            elif 'url' in article and article['url']:
                article['media_from_url'] = self.extract_media_from_url(article['url'])
        
        logger.info(f"총 {len(articles_content)}개 기사 수집 완료")
        logger.info(f"언론사: {', '.join(cluster_result['press_list'])}")

        # 키워드 추출 (기사 내용도 함께 전달하여 더 정확한 키워드 추출)
        first_article_content = articles_content[0].get('content', '') if articles_content else ''
        keywords = self.extract_keywords(main_title, first_article_content)

        # 2. YouTube 검색 추가 (원본 기사 정보도 전달)
        logger.info("\n2단계: YouTube 관련 동영상 검색")
        youtube_results = self.search_youtube_videos(
            keywords, 
            max_results=5,
            main_title=main_title,
            source_articles=articles_content
        )
        if youtube_results:
            logger.info(f"YouTube 동영상 {len(youtube_results)}개 발견")
            # YouTube 결과를 분석에 포함
            cluster_result["youtube_videos"] = youtube_results

        # 3. Google 검색 추가
        logger.info("\n3단계: Google 추가 정보 검색")
        google_results = self.search_google_articles(keywords, num_results=10)
        if google_results:
            logger.info(f"Google 검색 결과 {len(google_results)}개 발견")
            # Google 결과를 분석에 포함
            cluster_result["google_articles"] = google_results

        # 4. 논란과 해명 분석
        logger.info("\n4단계: 논란과 해명 종합 분석")
        analysis = self.analyze_controversies(articles_content)

        if not analysis:
            logger.error("분석 실패")
            return None

        # 5. 종합 기사 생성
        logger.info("\n5단계: 심층 기사 생성")

        # YouTube와 Google 정보를 analysis에 추가 (프롬프트 크기 최적화)
        if "youtube_videos" in cluster_result:
            analysis["youtube_context"] = cluster_result["youtube_videos"][:3]  # 최대 3개
        if "google_articles" in cluster_result:
            analysis["google_context"] = cluster_result["google_articles"][:5]  # 최대 5개

        comprehensive_result = self.create_comprehensive_article(
            {"title": main_title, "url": main_news_url}, analysis,
            version=version, previous_article_content=previous_article_content
        )
        
        # 마크다운 텍스트로 반환되므로 직접 사용
        comprehensive_article = comprehensive_result
        
        # 제목은 기사 내용에서 추출 (# 으로 시작하는 첫 줄)
        if comprehensive_article:
            lines = comprehensive_article.split('\n')
            for line in lines:
                if line.strip().startswith('# '):
                    generated_title = line.strip()[2:].strip()
                    break
            else:
                generated_title = main_title
        else:
            generated_title = main_title

        # 태그 생성
        # cluster_result에서 카테고리를 찾고, 없으면 전달받은 카테고리 사용
        category_for_tags = cluster_result.get("category") or news_category
        tags = self.generate_tags(generated_title, comprehensive_article, category_for_tags)

        # 소스 기사 URL 목록 생성
        source_articles = []
        
        # 메인 기사 URL 추가
        source_articles.append(main_news_url)
        
        # 관련 기사 URL들 추가
        for article in articles_content:
            if 'link' in article and article['link']:
                source_articles.append(article['link'])
            elif 'url' in article and article['url']:
                source_articles.append(article['url'])
        
        # 중복 제거
        source_articles = list(dict.fromkeys(source_articles))  # 순서 유지하면서 중복 제거
        
        # 6. 결과 정리 (메타데이터 보존)
        result = {
            "main_article": {"title": main_title, "url": main_news_url},
            "generated_title": generated_title,  # AI가 생성한 제목 추가
            "related_articles": articles_content,  # 전체 기사 메타데이터 보존
            "related_articles_count": len(articles_content),
            "press_diversity": len(cluster_result["press_list"]),
            "press_list": cluster_result["press_list"],
            "analysis": analysis,
            "comprehensive_article": comprehensive_article,
            "tags": tags,  # 태그 추가
            "source_articles": source_articles,  # 소스 기사 URL 목록 추가
            "timestamp": datetime.now().isoformat(),
        }

        # YouTube/Google 정보 추가
        if "youtube_videos" in cluster_result:
            result["youtube_videos"] = cluster_result["youtube_videos"]
            result["youtube_count"] = len(cluster_result["youtube_videos"])
        if "google_articles" in cluster_result:
            result["google_articles"] = cluster_result["google_articles"]
            result["google_count"] = len(cluster_result["google_articles"])

        # 결과 저장
        output_dir = "output/multi_article_analysis"
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"{output_dir}/analysis_{timestamp}.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info(f"\n분석 결과 저장: {output_path}")

        return result

    def _analyze_topic_fallback(self, main_news_url: str, main_title: str) -> dict:
        """클러스터 수집 실패 시 기존 검색 방식으로 분석"""

        # 1. 관련 기사 검색
        logger.info("\n1단계: 관련 기사 검색 (폴백)")
        related_articles = self.search_related_articles(main_title, limit=8)
        logger.info(f"관련 기사 {len(related_articles)}개 발견")

        # 2. 각 기사 본문 수집
        logger.info("\n2단계: 기사 본문 수집")
        articles_content = []

        # 메인 기사 먼저 수집
        main_content = self.extract_article_details(main_news_url)
        if main_content:
            articles_content.append(main_content)

        # 관련 기사들 수집
        for article in related_articles[:5]:  # 상위 5개만
            time.sleep(0.5)  # 서버 부하 방지
            content = self.extract_article_details(article["link"])
            if content:
                articles_content.append(content)
                logger.info(f"수집 완료: {article['title'][:30]}...")
        
        # URL에서 언론사명 추출하여 각 기사에 추가
        for article in articles_content:
            if 'link' in article and article['link']:
                article['media_from_url'] = self.extract_media_from_url(article['link'])
            elif 'url' in article and article['url']:
                article['media_from_url'] = self.extract_media_from_url(article['url'])

        # 3. 논란과 해명 분석
        logger.info("\n3단계: 논란과 해명 종합 분석")
        analysis = self.analyze_controversies(articles_content)

        if not analysis:
            logger.error("분석 실패")
            return None

        # 4. 종합 기사 생성
        logger.info("\n4단계: 심층 기사 생성")
        comprehensive_article = self.create_comprehensive_article(
            {"title": main_title, "url": main_news_url}, analysis,
            version=1, previous_article_content=None  # fallback은 항상 버전 1
        )

        # 소스 기사 URL 목록 생성
        source_articles = []
        
        # 메인 기사 URL 추가
        source_articles.append(main_news_url)
        
        # 관련 기사 URL들 추가
        for article in articles_content:
            if 'link' in article and article['link']:
                source_articles.append(article['link'])
            elif 'url' in article and article['url']:
                source_articles.append(article['url'])
        
        # 중복 제거
        source_articles = list(dict.fromkeys(source_articles))  # 순서 유지하면서 중복 제거
        
        # 5. 결과 정리 (메타데이터 보존)
        result = {
            "main_article": {"title": main_title, "url": main_news_url},
            "related_articles": articles_content,  # 전체 기사 메타데이터 보존
            "related_articles_count": len(articles_content),
            "analysis": analysis,
            "comprehensive_article": comprehensive_article,
            "source_articles": source_articles,  # 소스 기사 URL 목록 추가
            "timestamp": datetime.now().isoformat(),
        }

        # 결과 저장
        output_dir = "output/multi_article_analysis"
        os.makedirs(output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"{output_dir}/analysis_{timestamp}.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        logger.info(f"\n분석 결과 저장: {output_path}")

        return result
    
    def extract_media_from_url(self, url: str) -> str:
        """URL에서 언론사명을 추출"""
        # URL에서 도메인 추출
        import re
        
        # 주요 언론사 URL 매핑
        media_mapping = {
            # 종합일간지
            'chosun.com': '조선일보',
            'donga.com': '동아일보',
            'joongang.co.kr': '중앙일보',
            'hani.co.kr': '한겨레',
            'hankookilbo.com': '한국일보',
            'kmib.co.kr': '국민일보',
            'munhwa.com': '문화일보',
            'seoul.co.kr': '서울신문',
            'segye.com': '세계일보',
            'mk.co.kr': '매일경제',
            'hankyung.com': '한국경제',
            
            # 방송사
            'kbs.co.kr': 'KBS',
            'imbc.com': 'MBC',
            'mbc.co.kr': 'MBC',
            'sbs.co.kr': 'SBS',
            'jtbc.joins.com': 'JTBC',
            'jtbc.co.kr': 'JTBC',
            'ytn.co.kr': 'YTN',
            'news.tvchosun.com': 'TV조선',
            'mbn.co.kr': 'MBN',
            'channela.com': '채널A',
            
            # 통신사
            'yna.co.kr': '연합뉴스',
            'yonhapnews.co.kr': '연합뉴스',
            'newsis.com': '뉴시스',
            'news1.kr': '뉴스1',
            
            # 경제지
            'sedaily.com': '서울경제',
            'fnnews.com': '파이낸셜뉴스',
            'mt.co.kr': '머니투데이',
            'edaily.co.kr': '이데일리',
            'asiae.co.kr': '아시아경제',
            
            # 인터넷 언론
            'ohmynews.com': '오마이뉴스',
            'pressian.com': '프레시안',
            'mediatoday.co.kr': '미디어오늘',
            'nocutnews.co.kr': 'CBS노컷뉴스',
            
            # 지역지
            'busan.com': '부산일보',
            'kgnews.co.kr': '경기일보',
            'idaegu.com': '대구일보',
            'kwangju.co.kr': '광주일보',
            
            # 네이버 뉴스
            'n.news.naver.com': '네이버뉴스',
            'news.naver.com': '네이버뉴스',
        }
        
        # URL에서 도메인 추출
        domain_pattern = r'(?:https?://)?(?:www\.)?([^/]+)'
        match = re.search(domain_pattern, url)
        
        if match:
            domain = match.group(1).lower()
            
            # 정확한 도메인 매칭
            for media_domain, media_name in media_mapping.items():
                if media_domain in domain:
                    return media_name
            
            # 도메인 자체를 언론사명으로 반환 (알 수 없는 경우)
            return domain.split('.')[0].upper()
        
        return "알 수 없음"
    
    def _is_opinion_article(self, title: str) -> bool:
        """제목을 기반으로 의견 기사(사설, 칼럼 등) 판별"""
        # 모든 종류의 괄호 ([], (), {}, <>, 【】, ＜＞, （）, ｛｝) 형식이 있는 기사 필터링
        import re
        if re.search(r'[\[\(\{<【＜（｛].+?[\]\)\}>】＞）｝]', title):
            return True
        
        # 의견 기사 패턴
        opinion_patterns = [
            '[사설]', '【사설】', '＜사설＞', '<사설>', '(사설)',
            '[칼럼]', '【칼럼】', '＜칼럼＞', '<칼럼>', '(칼럼)',
            '[기고]', '【기고】', '＜기고＞', '<기고>', '(기고)',
            '[특별기고]', '[시론]', '[논단]', '[기자수첩]', '[데스크칼럼]',
            '[편집국에서]', '[여적]', '[만물상]', '[천자칼럼]', '[춘추칼럼]',
            '[세상읽기]', '[시평]', '[독자투고]', '[독자기고]', '[오피니언]',
            '[사내칼럼]', '[취재수첩]', '[기자칼럼]', '[아침논단]', '[광화문에서]',
            '[여의도포럼]', '[분수대]', '[녹취록]', '[인터뷰]', '[대담]'
        ]
        
        # 제목에 의견 기사 패턴이 포함되어 있는지 확인
        for pattern in opinion_patterns:
            if pattern in title:
                return True
        
        # 추가 패턴: 제목 시작 부분에 있는 경우
        title_start = title[:20]  # 제목 앞부분만 확인
        opinion_keywords = ['사설', '칼럼', '기고', '시론', '논단', '시평', '기자수첩']
        for keyword in opinion_keywords:
            if keyword in title_start and (title_start.index(keyword) < 10):
                return True
        
        return False

    def _extract_relevant_transcript(self, full_transcript: str, keywords: List[str], video_title: str) -> str:
        """
        ChatGPT를 사용하여 YouTube 트랜스크립트에서 기사와 관련된 부분만 추출
        
        Args:
            full_transcript: 전체 트랜스크립트
            keywords: 기사 키워드 리스트
            video_title: 동영상 제목
            
        Returns:
            관련된 부분만 추출한 트랜스크립트 (최대 1500자)
        """
        if not full_transcript or len(full_transcript) < 100:
            return full_transcript
        
        # 트랜스크립트가 너무 길면 중간 부분 샘플링
        max_input_length = 8000
        if len(full_transcript) > max_input_length:
            # 시작, 중간, 끝 부분을 포함하도록 샘플링
            chunk_size = max_input_length // 3
            start = full_transcript[:chunk_size]
            middle_start = (len(full_transcript) - chunk_size) // 2
            middle = full_transcript[middle_start:middle_start + chunk_size]
            end = full_transcript[-chunk_size:]
            sampled_transcript = f"{start}\n[...중략...]\n{middle}\n[...중략...]\n{end}"
        else:
            sampled_transcript = full_transcript
        
        try:
            # ChatGPT에게 관련 부분 추출 요청
            prompt = f"""다음은 YouTube 동영상 "{video_title}"의 트랜스크립트입니다.

주요 키워드: {', '.join(keywords)}

트랜스크립트:
{sampled_transcript}

위 트랜스크립트에서 주요 키워드와 관련된 핵심 내용만 추출해주세요.
- 인트로, 아웃트로, 광고, 구독 요청 등은 제외
- 키워드와 직접 관련된 발언이나 설명만 포함
- 추출한 내용은 원문 그대로 유지 (요약하지 말 것)
- 최대 1500자 이내로 추출
- 관련 내용이 여러 곳에 흩어져 있다면, 중요도 순으로 선별

추출된 내용만 반환하세요. 추가 설명은 불필요합니다."""
            
            # Rate limiting 적용
            self.rate_limiter.wait_if_needed()
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system", 
                        "content": "당신은 동영상 트랜스크립트에서 핵심 내용을 추출하는 전문가입니다."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=2000  # 충분한 토큰 할당
            )
            
            # 토큰 사용량 추적
            if self.token_tracker and self.current_article_id:
                self.token_tracker.track_api_call(
                    response, self.model_name, self.current_article_id, self.current_article_title
                )
            
            extracted = response.choices[0].message.content.strip()
            
            # 추출된 내용이 너무 짧으면 원본 일부 반환
            if len(extracted) < 100:
                return full_transcript[:1500]
            
            # 1500자 제한
            if len(extracted) > 1500:
                extracted = extracted[:1500] + "..."
            
            return extracted
            
        except Exception as e:
            logger.error(f"ChatGPT 트랜스크립트 추출 실패: {e}")
            # 실패 시 원본의 앞부분 반환
            return full_transcript[:1500] if len(full_transcript) > 1500 else full_transcript


if __name__ == "__main__":
    analyzer = MultiArticleDeepAnalyzer()

    # 테스트
    test_url = "https://n.news.naver.com/article/087/0001130722"
    test_title = "[속보]李대통령, 이진숙 교육부장관 후보자 지명 철회…강선우는 임명 수순"

    result = analyzer.analyze_topic(test_url, test_title, version=1)
