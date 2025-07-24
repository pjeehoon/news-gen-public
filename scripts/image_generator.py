#!/usr/bin/env python3
"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

"""
AI 이미지 생성 모듈
- GPT Image 1을 사용한 뉴스 이미지 생성
- 기사 내용에 맞는 적절한 이미지 생성
"""

import os
import json
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime
import requests
from pathlib import Path
import openai
from dotenv import load_dotenv
import base64

from scripts.utils import setup_logging, APIKeyManager, RateLimiter
from scripts.token_tracker import TokenTracker

load_dotenv()

logger = setup_logging("image_generator")


class NewsImageGenerator:
    """뉴스 기사용 AI 이미지 생성기"""
    
    def __init__(self):
        # API 설정
        self.api_manager = APIKeyManager()
        if not self.api_manager.has_valid_key():
            raise ValueError("No valid API key found")
        
        self.client = openai.OpenAI(api_key=self.api_manager.get_active_key())
        self.rate_limiter = RateLimiter(calls_per_minute=50)  # 이미지 생성은 더 높은 제한
        self.token_tracker = TokenTracker()
        
        # 이미지 생성 설정
        self.model = "gpt-image-1"  # GPT Image 1 사용
        self.quality = "low"  # low, medium, high
        self.size = "1024x1024"  # 가장 저렴한 옵션
        
        # 저장 경로 설정
        self.base_output_dir = Path("output/images")
        
    def generate_image_prompt(self, article_data: Dict) -> str:
        """기사 데이터에서 상세한 이미지 프롬프트 생성"""
        
        title = article_data.get("title", "")
        category = article_data.get("category", "")
        keywords = article_data.get("keywords", [])
        summary = article_data.get("three_line_summary", "")
        
        # 카테고리별 포토리얼리스틱 시각적 가이드
        category_guides = {
            "정치": {
                "scene": "realistic government building exterior or modern conference room interior",
                "elements": "architectural details of government buildings, empty podiums, conference tables, official documents on desks",
                "lighting": "natural window light or professional indoor lighting",
                "composition": "architectural photography angle, leading lines",
                "texture": "real marble textures, polished wood, glass reflections",
                "atmosphere": "formal, professional, journalistic neutrality",
                "colors": "natural building materials, subtle blue and gray tones",
                "style": "architectural photography, documentary style"
            },
            "경제": {
                "scene": "realistic modern office building lobby or trading floor environment",
                "elements": "glass office buildings, stock market displays, business district architecture, financial documents",
                "lighting": "natural daylight through windows, professional office lighting",
                "composition": "architectural perspective, leading lines of buildings",
                "texture": "reflective glass surfaces, polished floors, metal and concrete",
                "atmosphere": "professional business environment, economic activity",
                "colors": "natural glass and steel tones, subtle blue accents",
                "style": "commercial architecture photography, business documentary"
            },
            "사회": {
                "scene": "realistic urban street scene or public space",
                "elements": "city architecture, public transportation, parks, sidewalks, urban infrastructure",
                "lighting": "natural outdoor lighting, golden hour or overcast sky",
                "composition": "street photography perspective, environmental context",
                "texture": "real concrete, brick, glass, urban materials",
                "atmosphere": "authentic city life, community spaces",
                "colors": "natural urban colors, realistic sky and foliage",
                "style": "documentary street photography, photojournalism"
            },
            "국제": {
                "scene": "realistic international landmark or global business district",
                "elements": "iconic architecture, international airports, shipping ports, diplomatic buildings",
                "lighting": "natural daylight, different time zones suggested",
                "composition": "wide establishing shot, geographic context",
                "texture": "varied architectural materials, natural landscapes",
                "atmosphere": "global connectivity, international relations",
                "colors": "natural earth tones, sky blues, neutral palette",
                "style": "travel photography, documentary journalism"
            },
            "IT/과학": {
                "scene": "realistic modern laboratory or tech company office",
                "elements": "laboratory equipment, server rooms, clean tech workspaces, research facilities",
                "lighting": "bright clean lighting, professional lab illumination",
                "composition": "technical photography, detail focus",
                "texture": "stainless steel, glass, plastic, electronic components",
                "atmosphere": "innovation center, research environment",
                "colors": "clean whites, metallic grays, subtle tech blues",
                "style": "technical photography, scientific documentation"
            },
            "문화": {
                "scene": "realistic cultural venue or artistic space",
                "elements": "museums, galleries, theaters, cultural centers, artistic installations",
                "lighting": "gallery lighting, natural museum light",
                "composition": "architectural interior, artistic framing",
                "texture": "varied artistic materials, architectural details",
                "atmosphere": "cultural sophistication, artistic environment",
                "colors": "gallery whites, natural material tones",
                "style": "cultural documentary, architectural photography"
            }
        }
        
        # 카테고리별 가이드 가져오기
        guide = category_guides.get(category, category_guides["사회"])
        
        # 핵심 키워드에서 구체적인 주제 추출 (영문 변환 필요)
        key_elements = keywords[:3] if keywords else [title.split()[0]]
        
        # ChatGPT를 사용해서 한국어 키워드를 영어로 번역
        english_elements = self._translate_keywords_to_english(key_elements, title, category)
        
        # 키워드 기반 구체적 시각 요소 생성
        specific_elements = []
        for keyword in key_elements:
            if "사기" in keyword or "범죄" in keyword:
                specific_elements.append("warning signs, caution symbols, shield icons")
            elif "건강" in keyword or "질병" in keyword:
                specific_elements.append("medical symbols, health icons, protective elements")
            elif "경제" in keyword or "돈" in keyword or "가격" in keyword:
                specific_elements.append("financial charts, money flow visualization, economic indicators")
            elif "기술" in keyword or "AI" in keyword or "디지털" in keyword:
                specific_elements.append("digital patterns, AI visualization, tech interfaces")
            elif "환경" in keyword or "기후" in keyword:
                specific_elements.append("nature elements, environmental symbols, green energy")
        
        # GPT Image 1에 최적화된 포토리얼리스틱 프롬프트 구성
        prompt = f"""A photorealistic professional news photography capturing {', '.join(english_elements)}.

SCENE DESCRIPTION:
{guide['scene']}. Ultra-realistic environment with natural textures and accurate materials.

MAIN SUBJECTS:
- {guide['elements']}
- {', '.join(specific_elements) if specific_elements else 'symbolic representations of the news theme'}
All elements rendered with photorealistic detail and professional photography standards.

PHOTOGRAPHY SPECIFICATIONS:
- Shot with professional camera equipment, 50mm lens
- {guide['lighting']} with natural light behavior and realistic shadows
- Shallow depth of field for subject emphasis
- {guide['composition']} following rule of thirds
- Professional news photography style, editorial standards
- High dynamic range capturing all detail

COLOR AND ATMOSPHERE:
- Natural color grading with {guide['colors']}
- {guide['atmosphere']} conveyed through realistic environmental details
- Accurate color reproduction, no oversaturation
- Professional post-processing for news media

TECHNICAL DETAILS:
- Photorealistic rendering with ultra-high detail
- Sharp focus on main subjects with natural bokeh
- Professional commercial photography quality
- Clean, uncluttered composition suitable for news header
- Natural perspective and proportions
- Realistic material properties and reflections

IMPORTANT RESTRICTIONS:
- No identifiable human faces or specific individuals
- No recognizable logos, brands, or trademarks
- No national flags or political party symbols
- No graphic violence or disturbing imagery
- No text overlays or written words
- Maintain editorial neutrality and professionalism"""
        
        logger.info(f"Generated detailed image prompt: {prompt[:200]}...")
        return prompt
    
    def _translate_keywords_to_english(self, keywords: list, title: str, category: str) -> list:
        """ChatGPT를 사용해서 한국어 키워드를 영어로 번역"""
        
        # API 호출을 위한 프롬프트 구성
        keywords_text = ", ".join(keywords)
        
        system_prompt = """You are a translator specializing in news keywords for image generation. 
        Translate Korean keywords to English with these guidelines:
        
        1. For Korean place names (cities, regions), use descriptive terms instead:
           - 서울, 부산, 대구 → "major Korean city", "urban metropolis"
           - 충청권, 영남권 → "central Korean region", "southern Korean region"
           - 한강, 낙동강 → "major river", "urban riverside"
        
        2. For Korean names (people, companies), use role descriptions:
           - 정치인 이름 → "political figure", "government official"
           - 기업명 → "major corporation", "tech company"
        
        3. For abstract concepts, use visual representations:
           - 폭염 → "extreme heat weather", "summer heatwave conditions"
           - 논란 → "controversy situation", "public debate"
        
        4. Keep weather and natural phenomena descriptive:
           - 폭우 → "torrential rain", "heavy rainfall"
           - 태풍 → "tropical storm", "typhoon weather"
        
        Output only the translated keywords, separated by commas."""
        
        user_prompt = f"""Translate these Korean news keywords to English for image generation:
        Keywords: {keywords_text}
        News Title: {title}
        Category: {category}
        
        Remember to use descriptive terms instead of proper nouns.
        Focus on visual elements that can be depicted in a photograph."""
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=100
            )
            
            # 응답에서 영어 키워드 추출
            translated_text = response.choices[0].message.content.strip()
            english_keywords = [kw.strip() for kw in translated_text.split(",")]
            
            logger.info(f"Keywords translated: {keywords} -> {english_keywords}")
            
            # 비어있거나 너무 긴 키워드 필터링
            english_keywords = [kw for kw in english_keywords if kw and len(kw) < 50]
            
            return english_keywords[:3]  # 최대 3개만 사용
            
        except Exception as e:
            logger.error(f"Keyword translation failed: {e}")
            
            # 폴백: 카테고리 기반 기본 영문 키워드
            fallback_keywords = {
                "정치": ["political development", "government policy", "public affairs"],
                "경제": ["economic trend", "financial market", "business activity"],
                "사회": ["social issue", "community life", "public concern"],
                "국제": ["global affair", "international relations", "world news"],
                "IT/과학": ["technology innovation", "scientific discovery", "digital advancement"],
                "문화": ["cultural event", "artistic expression", "lifestyle trend"]
            }
            
            return fallback_keywords.get(category, ["news event", "current affair", "breaking story"])[:len(keywords)]
    
    def generate_image(self, article_data: Dict) -> Optional[Dict]:
        """기사에 맞는 이미지 생성"""
        
        try:
            # Rate limiting
            self.rate_limiter.wait_if_needed()
            
            # 프롬프트 생성
            prompt = self.generate_image_prompt(article_data)
            
            # 이미지 생성 API 호출
            logger.info(f"Generating image for article: {article_data.get('title', '')[:50]}...")
            
            response = self.client.images.generate(
                model=self.model,
                prompt=prompt,
                quality=self.quality,
                size=self.size
            )
            
            # 결과 추출
            image_data = response.data[0]
            
            # GPT Image 1은 URL을 반환할 수 있음
            if hasattr(image_data, 'b64_json') and image_data.b64_json:
                # base64 형식
                image_base64 = image_data.b64_json
                logger.info("Image generated successfully (base64 format)")
                image_path = self._save_image_from_base64(image_base64, article_data)
            elif hasattr(image_data, 'url') and image_data.url:
                # URL 형식
                image_url = image_data.url
                logger.info("Image generated successfully (URL format)")
                image_path = self._save_image(image_url, article_data)
            else:
                raise ValueError("No image data found in response")
            
            revised_prompt = getattr(image_data, 'revised_prompt', prompt)
            
            # 비용 추적
            article_id = article_data.get("topic_id", "unknown")
            article_title = article_data.get("title", "")
            
            self.token_tracker.track_image_generation(
                model=self.model,
                quality=self.quality,
                size=self.size,
                article_id=article_id,
                article_title=article_title
            )
            
            result = {
                "success": True,
                "image_path": str(image_path),
                "prompt": prompt,
                "revised_prompt": revised_prompt,
                "model": self.model,
                "quality": self.quality,
                "size": self.size
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _save_image_from_base64(self, image_base64: str, article_data: Dict) -> Path:
        """base64 이미지를 디코딩하여 저장"""
        
        # 날짜별 디렉토리 생성
        now = datetime.now()
        date_dir = self.base_output_dir / f"{now.year:04d}" / f"{now.month:02d}" / f"{now.day:02d}"
        date_dir.mkdir(parents=True, exist_ok=True)
        
        # 파일명 생성
        article_id = article_data.get("topic_id", f"article_{now.strftime('%Y%m%d%H%M%S')}")
        filename = f"{article_id}_{self.size}.jpg"
        file_path = date_dir / filename
        
        # base64 디코딩 및 저장
        image_bytes = base64.b64decode(image_base64)
        with open(file_path, 'wb') as f:
            f.write(image_bytes)
        
        logger.info(f"Image saved: {file_path}")
        
        # 상대 경로 반환 (output 디렉토리 기준)
        relative_path = file_path.relative_to(Path("output"))
        return Path("images") / relative_path.relative_to(Path("images"))
    
    def _save_image(self, image_url: str, article_data: Dict) -> Path:
        """생성된 이미지를 다운로드하고 저장 (URL 방식 - 레거시)"""
        
        # 날짜별 디렉토리 생성
        now = datetime.now()
        date_dir = self.base_output_dir / f"{now.year:04d}" / f"{now.month:02d}" / f"{now.day:02d}"
        date_dir.mkdir(parents=True, exist_ok=True)
        
        # 파일명 생성
        article_id = article_data.get("topic_id", f"article_{now.strftime('%Y%m%d%H%M%S')}")
        filename = f"{article_id}_{self.size}.jpg"
        file_path = date_dir / filename
        
        # 이미지 다운로드
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        
        # 파일로 저장
        with open(file_path, 'wb') as f:
            f.write(response.content)
        
        logger.info(f"Image saved: {file_path}")
        
        # 상대 경로 반환 (output 디렉토리 기준)
        relative_path = file_path.relative_to(Path("output"))
        return Path("images") / relative_path.relative_to(Path("images"))
    
    def should_generate_image(self, article_data: Dict) -> bool:
        """이미지 생성 여부 결정"""
        
        # 버전 1 기사만 생성
        version = article_data.get("version", 1)
        if version > 1:
            logger.info(f"Skipping image generation for version {version}")
            return False
        
        # 이미 이미지가 있는 경우 스킵
        if article_data.get("generated_image_path"):
            logger.info("Image already exists, skipping generation")
            return False
        
        # 품질이 낮은 기사는 스킵 (선택사항)
        quality_rating = article_data.get("quality_rating", "")
        if quality_rating in ["D", "F"]:
            logger.info(f"Skipping image generation for low quality article: {quality_rating}")
            return False
        
        return True


# 간편 함수
def generate_news_image(article_data: Dict) -> Optional[Dict]:
    """뉴스 기사용 이미지 생성 (간편 함수)"""
    generator = NewsImageGenerator()
    
    if not generator.should_generate_image(article_data):
        return None
    
    return generator.generate_image(article_data)