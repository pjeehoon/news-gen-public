#!/usr/bin/env python3
"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

"""
외부 검색 API 구현 - YouTube Data API, Google Custom Search API 사용
"""

import os
import logging
from typing import List, Dict, Optional
import requests
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
# file_cache 경고 방지
import googleapiclient.discovery
googleapiclient.discovery.cache_discovery = False
from dotenv import load_dotenv
import yt_dlp

load_dotenv()

logger = logging.getLogger(__name__)

class ExternalSearchClient:
    """외부 검색 서비스 클라이언트"""
    
    def __init__(self):
        # API 키 설정
        self.youtube_api_key = os.getenv('YOUTUBE_API_KEY')
        self.google_api_key = os.getenv('GOOGLE_API_KEY')
        self.google_cse_id = os.getenv('GOOGLE_CSE_ID')
        
        # YouTube API 클라이언트 초기화
        if self.youtube_api_key:
            try:
                self.youtube = build('youtube', 'v3', developerKey=self.youtube_api_key, cache_discovery=False)
            except Exception as e:
                logger.error(f"YouTube API 초기화 실패: {e}")
                self.youtube = None
        else:
            logger.warning("YOUTUBE_API_KEY가 설정되지 않았습니다")
            self.youtube = None
    
    def search_youtube_videos(self, query: str, max_results: int = 5) -> List[Dict]:
        """YouTube 동영상 검색"""
        # 먼저 API 사용 시도
        if self.youtube:
            try:
                # YouTube API 검색 요청
                search_response = self.youtube.search().list(
                    q=query,
                    part='id,snippet',
                    type='video',
                    maxResults=max_results,
                    order='relevance',
                    regionCode='KR',
                    relevanceLanguage='ko'
                ).execute()
                
                videos = []
                for item in search_response.get('items', []):
                    video_data = {
                        'title': item['snippet']['title'],
                        'url': f"https://www.youtube.com/watch?v={item['id']['videoId']}",
                        'videoId': item['id']['videoId'],
                        'channel': {
                            'name': item['snippet']['channelTitle'],
                            'url': f"https://www.youtube.com/channel/{item['snippet']['channelId']}"
                        },
                        'description': item['snippet'].get('description', ''),
                        'publishedAt': item['snippet']['publishedAt'],
                        'thumbnail': item['snippet']['thumbnails']['high']['url']
                    }
                    videos.append(video_data)
                
                logger.info(f"YouTube API 검색 완료: {len(videos)}개 동영상")
                return videos
                
            except HttpError as e:
                # 할당량 초과 에러인 경우 스크래핑으로 전환
                if "quotaExceeded" in str(e):
                    logger.warning("YouTube API 할당량 초과, 스크래핑으로 전환")
                else:
                    logger.error(f"YouTube API 오류: {e}")
            except Exception as e:
                logger.error(f"YouTube API 검색 실패: {e}")
        
        # API 실패 시 yt-dlp 사용
        logger.info("yt-dlp를 사용한 YouTube 검색 시도")
        return self._search_youtube_ytdlp(query, max_results)
    
    def _search_youtube_ytdlp(self, query: str, max_results: int = 5) -> List[Dict]:
        """yt-dlp를 사용한 YouTube 검색 (API 키 불필요)"""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'force_generic_extractor': False,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # YouTube 검색
                search_url = f"ytsearch{max_results}:{query}"
                result = ydl.extract_info(search_url, download=False)
                
                videos = []
                for entry in result.get('entries', []):
                    # 메타데이터 추출
                    video_data = {
                        'title': entry.get('title', ''),
                        'url': f"https://www.youtube.com/watch?v={entry['id']}",
                        'link': f"https://www.youtube.com/watch?v={entry['id']}",
                        'videoId': entry.get('id', ''),
                        'channel': {
                            'name': entry.get('uploader', ''),
                            'url': entry.get('uploader_url', '')
                        },
                        'description': entry.get('description', '')[:200] if entry.get('description') else '',
                        'publishedAt': entry.get('upload_date', ''),
                        'thumbnail': entry.get('thumbnail', ''),
                        'duration': entry.get('duration', 0),
                        'viewCount': entry.get('view_count', 0)
                    }
                    videos.append(video_data)
                
                logger.info(f"yt-dlp YouTube 검색 완료: {len(videos)}개 동영상")
                return videos
                
        except Exception as e:
            logger.error(f"yt-dlp YouTube 검색 실패: {e}")
            return []
    
    def search_google(self, query: str, num_results: int = 10) -> List[Dict]:
        """Google Custom Search API를 사용한 검색"""
        if not self.google_api_key or not self.google_cse_id:
            logger.warning("Google 검색 API 키가 설정되지 않았습니다")
            return []
        
        try:
            # Google Custom Search API 요청
            url = "https://www.googleapis.com/customsearch/v1"
            params = {
                'key': self.google_api_key,
                'cx': self.google_cse_id,
                'q': query,
                'num': min(num_results, 10),  # 최대 10개
                'hl': 'ko',
                'gl': 'kr'
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            results = []
            
            for item in data.get('items', []):
                result = {
                    'title': item.get('title', ''),
                    'url': item.get('link', ''),
                    'snippet': item.get('snippet', ''),
                    'displayLink': item.get('displayLink', '')
                }
                results.append(result)
            
            logger.info(f"Google 검색 완료: {len(results)}개 결과")
            return results
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Google API 요청 실패: {e}")
            return []
        except Exception as e:
            logger.error(f"Google 검색 실패: {e}")
            return []
    
    # SerpAPI 관련 메서드 제거 (사용하지 않음)


# 전역 클라이언트 인스턴스
_search_client = None

def get_search_client() -> ExternalSearchClient:
    """싱글톤 검색 클라이언트"""
    global _search_client
    if _search_client is None:
        _search_client = ExternalSearchClient()
    return _search_client


# 간편 함수들
def search_youtube(query: str, max_results: int = 5) -> List[Dict]:
    """YouTube 검색"""
    client = get_search_client()
    return client.search_youtube_videos(query, max_results)

def search_google(query: str, num_results: int = 10) -> List[Dict]:
    """Google 검색"""
    client = get_search_client()
    results = client.search_google(query, num_results)
    
    return results


if __name__ == "__main__":
    # 테스트
    logging.basicConfig(level=logging.INFO)
    
    print("=== 외부 검색 API 테스트 ===")
    
    # YouTube 검색 테스트
    print("\n1. YouTube 검색 테스트")
    videos = search_youtube("강선우 갑질", 3)
    for video in videos:
        print(f"- {video.get('title', 'Unknown')}")
    
    # Google 검색 테스트
    print("\n2. Google 검색 테스트")
    results = search_google("강선우 의원", 5)
    for result in results:
        print(f"- {result.get('title', 'Unknown')}")