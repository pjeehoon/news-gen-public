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
from typing import List, Dict, Optional, Tuple
import requests
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
# file_cache 경고 방지
import googleapiclient.discovery
googleapiclient.discovery.cache_discovery = False
from dotenv import load_dotenv
import yt_dlp
import asyncio
import base64
from datetime import datetime
from pathlib import Path

load_dotenv()

logger = logging.getLogger(__name__)

class ExternalSearchClient:
    """외부 검색 서비스 클라이언트"""
    
    def __init__(self):
        # API 키 설정
        self.youtube_api_key = os.getenv('YOUTUBE_API_KEY')
        self.google_api_key = os.getenv('GOOGLE_API_KEY')
        self.google_cse_id = os.getenv('GOOGLE_CSE_ID')
        self.runware_api_key = os.getenv('RUNWARE_API_KEY')
        
        # HTTP 헤더 설정
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
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
        # 먼저 yt-dlp 사용 시도 (무료, 제한 없음)
        logger.info("yt-dlp를 사용한 YouTube 검색 시도")
        try:
            videos = self._search_youtube_ytdlp(query, max_results)
            if videos:  # 결과가 있으면 반환
                return videos
            else:
                logger.warning("yt-dlp 검색 결과 없음")
        except Exception as e:
            logger.warning(f"yt-dlp 검색 실패: {e}")
        
        # yt-dlp에서 결과가 없거나 실패 시 API 사용 (백업)
        if self.youtube:
            try:
                logger.info("yt-dlp 실패, YouTube API로 재시도")
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
                if "quotaExceeded" in str(e):
                    logger.error("YouTube API 할당량 초과")
                else:
                    logger.error(f"YouTube API 오류: {e}")
            except Exception as e:
                logger.error(f"YouTube API 검색 실패: {e}")
        else:
            logger.warning("YouTube API 키가 설정되지 않았습니다")
        
        # 모든 방법 실패 시 빈 리스트 반환
        return []
    
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
    
    def search_wikipedia(self, query: str, num_results: int = 5, lang: str = 'ko') -> List[Dict]:
        """Wikipedia API를 사용한 검색 (API 키 불필요)"""
        try:
            # Wikipedia API 엔드포인트
            base_url = f"https://{lang}.wikipedia.org/w/api.php"
            
            # 검색 파라미터
            search_params = {
                'action': 'query',
                'format': 'json',
                'list': 'search',
                'srsearch': query,
                'srlimit': num_results,
                'utf8': 1,
                'srprop': 'snippet|titlesnippet|size|wordcount|timestamp'
            }
            
            # 검색 수행
            response = requests.get(base_url, params=search_params, headers=self.headers)
            response.raise_for_status()
            
            search_data = response.json()
            search_results = search_data.get('query', {}).get('search', [])
            
            results = []
            for item in search_results:
                # 각 페이지의 URL 생성
                page_title = item.get('title', '').replace(' ', '_')
                page_url = f"https://{lang}.wikipedia.org/wiki/{page_title}"
                
                # 페이지 내용 요약 가져오기
                extract_params = {
                    'action': 'query',
                    'format': 'json',
                    'prop': 'extracts|info',
                    'exintro': True,
                    'explaintext': True,
                    'exsectionformat': 'plain',
                    'exsentences': 3,
                    'inprop': 'url',
                    'titles': item.get('title', '')
                }
                
                extract_response = requests.get(base_url, params=extract_params, headers=self.headers)
                extract_data = extract_response.json()
                
                pages = extract_data.get('query', {}).get('pages', {})
                page_id = list(pages.keys())[0] if pages else None
                
                if page_id and page_id != '-1':
                    page_info = pages[page_id]
                    extract = page_info.get('extract', '')
                    canonical_url = page_info.get('canonicalurl', page_url)
                else:
                    extract = item.get('snippet', '').replace('<span class="searchmatch">', '').replace('</span>', '')
                    canonical_url = page_url
                
                result = {
                    'title': item.get('title', ''),
                    'url': canonical_url,
                    'snippet': extract,
                    'size': item.get('size', 0),
                    'wordcount': item.get('wordcount', 0),
                    'timestamp': item.get('timestamp', ''),
                    'source': 'wikipedia'
                }
                results.append(result)
            
            logger.info(f"Wikipedia 검색 완료: {len(results)}개 결과")
            return results
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Wikipedia API 요청 실패: {e}")
            return []
        except Exception as e:
            logger.error(f"Wikipedia 검색 실패: {e}")
            return []
    
    # SerpAPI 관련 메서드 제거 (사용하지 않음)


class RunwareImageGenerator:
    """Runware AI 이미지 생성기"""
    
    def __init__(self):
        self.api_key = os.getenv('RUNWARE_API_KEY')
        if not self.api_key:
            logger.warning("RUNWARE_API_KEY가 설정되지 않았습니다")
            self.runware = None
            return
            
        try:
            from runware import Runware
            self.Runware = Runware
            self.runware = None  # 연결은 나중에
            self.is_connected = False
            logger.info("Runware 클라이언트 초기화 완료")
        except ImportError:
            logger.error("runware 패키지가 설치되지 않았습니다. 'pip install runware' 실행 필요")
            self.runware = None
    
    async def connect(self):
        """Runware 서비스에 연결"""
        if not self.api_key or not hasattr(self, 'Runware'):
            return False
            
        try:
            self.runware = self.Runware(api_key=self.api_key)
            await self.runware.connect()
            self.is_connected = True
            logger.info("Runware 서비스 연결 성공")
            return True
        except Exception as e:
            logger.error(f"Runware 연결 실패: {e}")
            self.is_connected = False
            return False
    
    async def enhance_prompts(self, positive_prompt: str, negative_prompt: str = None) -> Tuple[str, str]:
        """Runware의 prompt enhancement를 사용하여 프롬프트 개선"""
        if not self.is_connected:
            if not await self.connect():
                return positive_prompt, negative_prompt
        
        try:
            from runware import IPromptEnhance
            
            # Positive prompt 개선 - 뉴스 사진 스타일 유지
            # Runware enhancement가 예술적 스타일을 추가하는 경향이 있으므로 신중히 사용
            # 프롬프트가 너무 길면 처음 250자만 사용 (300자 제한 고려)
            if len(positive_prompt) > 250:
                truncated_prompt = positive_prompt[:250] + "..."
            else:
                truncated_prompt = positive_prompt
            
            news_focused_prompt = f"{truncated_prompt}, photojournalism, news photography"
            # 전체 길이가 300자를 넘지 않도록 다시 체크
            if len(news_focused_prompt) > 300:
                news_focused_prompt = news_focused_prompt[:297] + "..."
            
            positive_enhancer = IPromptEnhance(
                prompt=news_focused_prompt,
                promptVersions=1,  # 하나의 개선된 버전만 생성
                promptMaxLength=300  # 충분한 길이로 설정
            )
            
            enhanced_positives = await self.runware.promptEnhance(promptEnhancer=positive_enhancer)
            if enhanced_positives:
                enhanced_positive = enhanced_positives[0].text
                # 예술적 스타일 키워드 제거 (뉴스 사진에 부적합)
                art_keywords = ['artstation', 'concept art', 'digital painting', 'illustration', 
                               'trending on artstation', 'highly detailed artstation', 
                               'dramatic lighting', 'cinematic lighting', 'fantasy art',
                               'greg rutkowski', 'ilya kuvshinov', 'krenz cushart']
                for keyword in art_keywords:
                    enhanced_positive = enhanced_positive.replace(f', {keyword}', '').replace(keyword, '')
            else:
                enhanced_positive = positive_prompt
            
            # Negative prompt 개선 (있는 경우)
            enhanced_negative = negative_prompt
            if negative_prompt:
                negative_enhancer = IPromptEnhance(
                    prompt=negative_prompt,
                    promptVersions=1,
                    promptMaxLength=64
                )
                enhanced_negatives = await self.runware.promptEnhance(promptEnhancer=negative_enhancer)
                if enhanced_negatives:
                    enhanced_negative = enhanced_negatives[0].text
                else:
                    enhanced_negative = negative_prompt
            
            logger.info(f"Prompts enhanced successfully")
            logger.debug(f"Enhanced positive: {enhanced_positive[:100]}...")
            logger.debug(f"Enhanced negative: {enhanced_negative[:50]}..." if enhanced_negative else "No negative prompt")
            return enhanced_positive, enhanced_negative
            
        except Exception as e:
            logger.warning(f"Prompt enhancement failed: {e}")
            return positive_prompt, negative_prompt
    
    async def generate_image_async(self, positivePrompt: str, negativePrompt: str = None, 
                                   width: int = 1024, height: int = 768, 
                                   model: str = "runware:100@1", num_images: int = 1,
                                   use_fast_model: bool = True, enhance_prompts: bool = True) -> List[Dict]:
        """비동기 이미지 생성"""
        if not self.is_connected:
            if not await self.connect():
                return []
        
        # Prompt enhancement 적용 (선택적)
        if enhance_prompts:
            logger.info("Applying Runware prompt enhancement...")
            positivePrompt, negativePrompt = await self.enhance_prompts(positivePrompt, negativePrompt)
        
        # prompt 변수명 통일 (positivePrompt -> prompt)
        prompt = positivePrompt
        
        try:
            from runware import IImageInference
            import uuid
            
            # 모델 선택: 빠른 생성 vs 고품질
            if use_fast_model:
                model = "runware:100@1"  # FLUX.1 Schnell - 빠른 생성
                steps = 20
            else:
                model = "runware:101@1"  # FLUX.1 Dev - 고품질
                steps = 30  # 더 나은 품질을 위해 스텝 증가
            
            # 네거티브 프롬프트가 제공되지 않은 경우 기본값 사용
            if negativePrompt is None:
                negativePrompt = "cartoon, anime, illustration, painting, drawing, blurry, low quality, distorted, text, watermark, logo, signature, unrealistic, fantasy, sci-fi, oversaturated colors, unnatural lighting, unrealistic colors"
            
            # 고유 taskUUID 생성
            task_uuid = str(uuid.uuid4())
            
            # 이미지 생성 요청 (taskType 제거 - Runware SDK 업데이트)
            request = IImageInference(
                taskUUID=task_uuid,
                positivePrompt=prompt,
                negativePrompt=negativePrompt,
                model=model,
                width=width,
                height=height,
                numberResults=num_images,
                outputType="URL",
                outputFormat="PNG",
                includeCost=True,  # 비용 정보 포함
                steps=steps,
                CFGScale=7.5,
                scheduler="Euler Beta"  # 안정적인 스케줄러
            )
            
            logger.info(f"Runware 이미지 생성 시작: {prompt[:50]}...")
            images = await self.runware.imageInference(requestImage=request)
            
            results = []
            for idx, image in enumerate(images):
                result = {
                    'url': image.imageURL,
                    'seed': getattr(image, 'seed', None),
                    'cost': getattr(image, 'cost', 0),
                    'prompt': prompt,
                    'model': model,
                    'size': f"{width}x{height}"
                }
                
                # 이미지 다운로드 및 저장
                if image.imageURL:
                    saved_path = await self._save_image(image.imageURL, f"runware_test_{idx}")
                    result['local_path'] = str(saved_path)
                
                results.append(result)
                
            logger.info(f"Runware 이미지 {len(results)}개 생성 완료")
            return results
            
        except Exception as e:
            logger.error(f"Runware 이미지 생성 실패: {e}")
            return []
    
    async def _save_image(self, image_url: str, filename_prefix: str) -> Path:
        """이미지를 로컬에 저장"""
        try:
            # 저장 디렉토리 생성 (실제 환경에서는 날짜별 디렉토리 사용)
            save_dir = Path("output/test_images")
            save_dir.mkdir(parents=True, exist_ok=True)
            
            # 파일명 생성
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{filename_prefix}_{timestamp}.jpg"
            file_path = save_dir / filename
            
            # 이미지 다운로드
            response = requests.get(image_url)
            response.raise_for_status()
            
            # 파일 저장
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"이미지 저장: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"이미지 저장 실패: {e}")
            return Path("error")
    
    def generate_image(self, positivePrompt: str, negativePrompt: str = None, **kwargs) -> List[Dict]:
        """동기 방식 이미지 생성 (편의 메서드)"""
        try:
            # asyncio.run()을 사용하여 깔끔하게 처리
            return asyncio.run(self.generate_image_async(positivePrompt, negativePrompt, **kwargs))
        except Exception as e:
            logger.error(f"동기 이미지 생성 실패: {e}")
            return []
    
    async def disconnect(self):
        """Runware 연결 종료"""
        if self.is_connected and self.runware:
            try:
                # Runware SDK는 자동으로 연결을 관리하므로 별도 종료 불필요
                self.is_connected = False
                logger.info("Runware 연결 종료 처리 완료")
            except Exception as e:
                logger.error(f"Runware 연결 종료 실패: {e}")


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

def search_wikipedia(query: str, num_results: int = 5, lang: str = 'ko') -> List[Dict]:
    """Wikipedia 검색"""
    client = get_search_client()
    return client.search_wikipedia(query, num_results, lang)


async def test_runware():
    """Runware 이미지 생성 테스트 (비동기)"""
    print("\n3. Runware 이미지 생성 테스트")
    image_gen = RunwareImageGenerator()
    
    if image_gen.runware is not None or hasattr(image_gen, 'Runware'):
        # 테스트 프롬프트들
        test_prompts = [
            {
                "prompt": "Photorealistic professional news photography, Seoul metropolitan cityscape, ultra high quality RAW photograph. SCENE: Modern Seoul skyline with Han River, glass skyscrapers reflecting sunset. Shot with professional DSLR camera, 50mm f/1.4 lens, golden hour natural lighting. TECHNICAL: Associated Press style, ultra-sharp focus, 8K resolution, hyperdetailed textures",
                "desc": "서울 도시 풍경 (고품질)"
            },
            {
                "prompt": "Professional corporate boardroom interior, photorealistic news editorial photography. Empty conference table with leather chairs, floor-to-ceiling windows, natural daylight. Documentary photojournalism style, shallow depth of field, clean composition suitable for business news header",
                "desc": "비즈니스 회의실 (빠른 생성)",
                "fast": True
            }
        ]
        
        for test in test_prompts:
            print(f"\n테스트: {test['desc']}")
            print(f"프롬프트: {test['prompt'][:60]}...")
            
            # 이미지 생성
            results = await image_gen.generate_image_async(
                prompt=test['prompt'],
                width=1024,
                height=768,
                num_images=1,
                use_fast_model=test.get('fast', False)
            )
            
            if results:
                for result in results:
                    print(f"✓ 이미지 생성 성공")
                    print(f"  - URL: {result.get('url', 'N/A')}...")
                    print(f"  - 로컬 저장: {result.get('local_path', 'N/A')}")
                    print(f"  - 비용: ${result.get('cost', 0):.6f}")
                    print(f"  - 모델: {result.get('model')}")
                    print(f"  - 크기: {result.get('size')}")
            else:
                print("✗ 이미지 생성 실패")
        
        # 연결 종료
        await image_gen.disconnect()
    else:
        print("Runware API 키가 설정되지 않았거나 패키지가 설치되지 않았습니다.")
        print("설치: pip install runware")
        print("환경변수: RUNWARE_API_KEY=your_api_key")


if __name__ == "__main__":
    # 테스트
    logging.basicConfig(level=logging.INFO)
    
    print("=== 외부 검색 API 테스트 ===")
    
    # # YouTube 검색 테스트
    # print("\n1. YouTube 검색 테스트")
    # videos = search_youtube("강선우 갑질", 3)
    # for video in videos:
    #     print(f"- {video.get('title', 'Unknown')}")
    
    # # Google 검색 테스트
    # print("\n2. Google 검색 테스트")
    # results = search_google("강선우 의원", 5)
    # for result in results:
    #     print(f"- {result.get('title', 'Unknown')}")
    
    # Wikipedia 검색 테스트
    print("\n3. Wikipedia 검색 테스트")
    
    # 테스트 1: 일반적인 검색
    print("\n[한국어 검색 - 인공지능]")
    wiki_results = search_wikipedia("인공지능", 3)
    for result in wiki_results:
        print(f"\n제목: {result.get('title', 'Unknown')}")
        print(f"URL: {result.get('url', 'N/A')}")
        print(f"요약: {result.get('snippet', '')[:100]}...")
        print(f"단어 수: {result.get('wordcount', 0)}")
    
    # 테스트 2: 뉴스 관련 검색
    print("\n\n[뉴스 관련 검색 - 윤석열]")
    news_results = search_wikipedia("윤석열", 2)
    for result in news_results:
        print(f"\n제목: {result.get('title', 'Unknown')}")
        print(f"요약: {result.get('snippet', '')[:150]}...")
    
    # 테스트 3: 영문 검색
    print("\n\n[영문 검색 - artificial intelligence]")
    en_results = search_wikipedia("artificial intelligence", 2, lang='en')
    for result in en_results:
        print(f"\n제목: {result.get('title', 'Unknown')}")
        print(f"요약: {result.get('snippet', '')[:150]}...")
    
    # Runware 이미지 생성 테스트 (비동기로 실행)
    # asyncio.run(test_runware())