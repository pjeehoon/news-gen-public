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
from pydantic import BaseModel
from datetime import datetime
import requests
from pathlib import Path
import openai
from dotenv import load_dotenv
import base64
import asyncio

from scripts.utils import setup_logging, APIKeyManager, RateLimiter
from scripts.token_tracker import TokenTracker
from scripts.external_search import RunwareImageGenerator

load_dotenv()

logger = setup_logging("image_generator")


class NewsImageGenerator:
    """뉴스 기사용 AI 이미지 생성기"""
    
    def __init__(self, use_fast_mode=False):
        # API 설정
        self.api_manager = APIKeyManager()
        if not self.api_manager.has_valid_key():
            raise ValueError("No valid API key found")
        
        self.client = openai.OpenAI(api_key=self.api_manager.get_active_key())
        self.rate_limiter = RateLimiter(calls_per_minute=50)  # 이미지 생성은 더 높은 제한
        self.token_tracker = TokenTracker()
        
        # Runware 생성기 초기화
        self.runware_generator = RunwareImageGenerator()
        
        # 이미지 생성 설정
        self.model = "gpt-image-1"  # GPT Image 1 사용
        self.quality = "low"  # low, medium, high
        self.size = "1024x1024"  # 가장 저렴한 옵션
        
        # Runware 설정
        self.runware_model = "runware:100@1"  # FLUX.1 Schnell - 빠르고 비용 효율적인 모델 (기본값)
        self.use_runware_first = True  # Runware를 우선 사용
        self.use_fast_model = True  # 기본적으로 빠른 모델 사용
        self.enhance_prompts = True  # Runware prompt enhancement 사용
        
        # 환경 변수로 우선순위 설정 가능
        if os.getenv('IMAGE_GEN_FAST_MODE', '').lower() == 'false':
            self.use_fast_model = False
        if os.getenv('IMAGE_GEN_PREFER_OPENAI', '').lower() == 'false':
            self.use_runware_first = True
        if os.getenv('IMAGE_GEN_ENHANCE_PROMPTS', '').lower() == 'false':
            self.enhance_prompts = False
        
        # 저장 경로 설정
        self.base_output_dir = Path("output/images")
        
    def generate_image_prompt(self, article_data: Dict) -> Dict[str, str]:
        """기사 데이터에서 AI 기반 이미지 프롬프트 생성 (positivePrompt, negativePrompt 반환)"""
        
        # Pydantic 모델 정의 (structured output용)
        class ImagePrompts(BaseModel):
            positivePrompt: str
            negativePrompt: str
        
        title = article_data.get("title", "")
        category = article_data.get("category", "")
        keywords = article_data.get("keywords", [])
        summary = article_data.get("three_line_summary", "")
        
        # 전체 기사 내용 추출
        full_article = article_data.get("comprehensive_article", "")
        if not full_article:
            # comprehensive_article이 없으면 generated_article 시도
            full_article = article_data.get("generated_article", "")
        
        # 너무 긴 기사는 처음 2000자로 제한 (토큰 한계 고려)
        if len(full_article) > 2000:
            full_article = full_article[:2000] + "..."
        
        # AI를 사용해서 기사 내용 기반 이미지 프롬프트 생성
        system_prompt = """You are an expert at creating image generation prompts for news articles.
Create both positive and negative prompts based on the news content provided.

Guidelines:
1. Carefully analyze the full article content to identify key visual elements, scenes, and symbolic representations
2. Focus on visual elements that can be photographed, not abstract concepts
3. Avoid showing specific people's faces or identifiable individuals
4. Use symbolic representations for complex topics
5. Emphasize professional news photography style
6. Keep prompts concise but comprehensive, capturing the article's main visual story
7. A positive prompt should describe what you want to see in the image based on the article's content
8. A negative prompt should list elements to avoid that might misrepresent the story
9. The generated prompts should be in English, though the news content is in Korean
10. Prioritize visual elements that best represent the article's core message and impact
11. It should follow the stype of professional news photography, photorealistic, high quality, 8K resolution, documentary style, neutral perspective, suitable for news publication
12. It should not follow the stype of "cartoon, anime, illustration, painting, drawing, blurry, low quality, distorted, text, watermark, logo, signature, unrealistic, fantasy, sci-fi, oversaturated colors, unnatural lighting, unrealistic colors"

SAFETY GUIDELINES:
- For accident or tragedy stories, focus on locations, safety equipment, or symbolic representations
- Avoid explicit descriptions of violence, injuries, or death
- For sensitive topics, use metaphorical or abstract representations
- Focus on environmental context rather than human suffering
- Emphasize safety awareness and prevention aspects
"""
        
        user_prompt = f"""Create photorealistic news image prompts for this article:

Title: {title}
Category: {category}
Keywords: {', '.join(keywords)}
Summary: {summary}

Full Article Content:
{full_article}

Based on the full article content above, generate image prompts that capture the most important visual elements and the core essence of this news story. Focus on scenes, locations, objects, or symbolic representations mentioned in the article."""
        
        try:
            # Structured output 사용
            model_name = os.getenv("DETAIL_MODEL", "gpt-4.1-nano")
            response = self.client.beta.chat.completions.parse(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format=ImagePrompts,
                temperature=0.7,
                max_tokens=400
            )
            
            # Structured output은 자동으로 파싱됨
            parsed_response = response.choices[0].message.parsed
            
            if parsed_response:
                positive_prompt = parsed_response.positivePrompt
                negative_prompt = parsed_response.negativePrompt
            else:
                # 파싱 실패시 폴백
                raise ValueError("Failed to parse structured output")
            
            
            # 기본 negative prompt 추가
            if not negative_prompt:
                negative_prompt = "cartoon, anime, illustration, painting, drawing, blurry, low quality, distorted, text, watermark, logo, signature, unrealistic, fantasy, sci-fi"
            
            result = {
                "positivePrompt": positive_prompt,
                "negativePrompt": negative_prompt
            }
            
            logger.info(f"AI generated prompts - Positive: {positive_prompt[:100]}... Negative: {negative_prompt[:50]}...")
            return result
            
        except Exception as e:
            logger.error(f"AI prompt generation failed: {e}")
            return None
    
    
    def generate_image(self, article_data: Dict) -> Optional[Dict]:
        """기사에 맞는 이미지 생성 (Runware 우선, OpenAI 폴백)"""
        
        # 프롬프트 생성
        prompts = self.generate_image_prompt(article_data)
        if prompts is None:
            return None
        
        # 안전하게 키 접근
        positive_prompt = prompts.get("positivePrompt")
        negative_prompt = prompts.get("negativePrompt")
        
        # 필수 키가 없는 경우 처리
        if not positive_prompt:
            logger.error("positivePrompt not found in generated prompts")
            return None
        
        # negative_prompt가 없는 경우 기본값 제공
        if not negative_prompt:
            negative_prompt = "cartoon, anime, illustration, painting, drawing, blurry, low quality, distorted, text, watermark, logo, signature, unrealistic, fantasy, sci-fi, oversaturated colors, unnatural lighting, unrealistic colors"
            logger.warning("negativePrompt not found, using default value")
        
        article_id = article_data.get("topic_id", "unknown")
        article_title = article_data.get("title", "")
        
        # Runware 먼저 시도
        if self.use_runware_first and self.runware_generator and hasattr(self.runware_generator, 'Runware'):
            logger.info(f"Trying Runware image generation for: {article_title[:50]}...")
            
            try:
                # Runware 이미지 생성 (동기 방식) - positive와 negative prompt 모두 전달
                results = self.runware_generator.generate_image(
                    positivePrompt=positive_prompt,
                    negativePrompt=negative_prompt,
                    width=1024,
                    height=768,
                    model=self.runware_model,
                    num_images=1,
                    use_fast_model=self.use_fast_model,
                    enhance_prompts=self.enhance_prompts
                )
                
                if results and len(results) > 0:
                    result = results[0]
                    
                    # Runware가 제공하는 정확한 비용 사용
                    actual_cost = result.get('cost', 0)
                    
                    # 이미지 저장 (Runware는 이미 로컬에 저장함)
                    if result.get('local_path'):
                        # 기존 경로 구조에 맞게 이동
                        saved_path = self._move_runware_image(result['local_path'], article_data)
                        
                        # 비용 추적 (Runware의 실제 비용 사용)
                        self.token_tracker.track_image_generation(
                            model=self.runware_model,
                            quality="standard",
                            size="1024x768",
                            article_id=article_id,
                            article_title=article_title,
                            actual_cost_usd=actual_cost  # 실제 비용 전달
                        )
                        
                        logger.info(f"Runware image generated successfully. Cost: ${actual_cost:.6f}")
                        
                        return {
                            "success": True,
                            "image_path": str(saved_path),
                            "prompt": positive_prompt,
                            "revised_prompt": positive_prompt,
                            "negative_prompt": negative_prompt,
                            "model": self.runware_model,
                            "quality": "standard",
                            "size": "1024x768",
                            "provider": "runware",
                            "actual_cost_usd": actual_cost
                        }
            except Exception as e:
                logger.warning(f"Runware generation failed, falling back to OpenAI: {e}")
        
        # OpenAI로 폴백
        try:
            # Rate limiting
            self.rate_limiter.wait_if_needed()
            
            # 이미지 생성 API 호출
            logger.info(f"Using OpenAI image generation for: {article_title[:50]}...")
            
            response = self.client.images.generate(
                model=self.model,
                prompt=positive_prompt,  # OpenAI는 positive prompt만 사용
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
            
            revised_prompt = getattr(image_data, 'revised_prompt', positive_prompt)
            
            # 비용 추적
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
                "prompt": positive_prompt,
                "revised_prompt": revised_prompt,
                "negative_prompt": negative_prompt,
                "model": self.model,
                "quality": self.quality,
                "size": self.size,
                "provider": "openai"
            }
            
            return result
            
        except Exception as e:
            logger.error(f"OpenAI image generation also failed: {e}")
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
    
    def _move_runware_image(self, source_path: str, article_data: Dict) -> Path:
        """Runware가 생성한 이미지를 기존 디렉토리 구조로 이동"""
        
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source image not found: {source}")
        
        # 날짜별 디렉토리 생성
        now = datetime.now()
        date_dir = self.base_output_dir / f"{now.year:04d}" / f"{now.month:02d}" / f"{now.day:02d}"
        date_dir.mkdir(parents=True, exist_ok=True)
        
        # 파일명 생성
        article_id = article_data.get("topic_id", f"article_{now.strftime('%Y%m%d%H%M%S')}")
        filename = f"{article_id}_1024x1024.jpg"
        target_path = date_dir / filename
        
        # 파일 이동
        import shutil
        shutil.move(str(source), str(target_path))
        
        logger.info(f"Image moved to: {target_path}")
        
        # 상대 경로 반환 (output 디렉토리 기준)
        relative_path = target_path.relative_to(Path("output"))
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
        
        # # 품질이 낮은 기사는 스킵 (선택사항)
        # quality_rating = article_data.get("quality_rating", "")
        # if quality_rating in ["D", "F"]:
        #     logger.info(f"Skipping image generation for low quality article: {quality_rating}")
        #     return False
        
        return True


# 간편 함수
def generate_news_image(article_data: Dict, use_fast_mode: bool = False) -> Optional[Dict]:
    """뉴스 기사용 이미지 생성 (간편 함수)"""
    generator = NewsImageGenerator(use_fast_mode=use_fast_mode)
    
    if not generator.should_generate_image(article_data):
        return None
    
    return generator.generate_image(article_data)