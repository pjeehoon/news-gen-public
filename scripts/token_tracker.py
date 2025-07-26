#!/usr/bin/env python3
"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

"""
토큰 사용량 및 비용 추적 모듈
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


class TokenTracker:
    """
    토큰 사용량 및 비용 추적
    
    OpenAI API 호출의 토큰 사용량을 추적하고 비용을 계산합니다.
    각 기사별로 메타데이터를 파일로 저장하여 누적 추적이 가능합니다.
    
    Attributes:
        PRICING: 모델별 토큰 가격 정보 (USD per 1K tokens)
        metadata_dir: 메타데이터 저장 디렉토리
    """

    # 가격 정보 (USD per 1K tokens)
    PRICING = {
        "gpt-4": {
            "prompt": 0.03,  # $0.03 per 1K prompt tokens
            "completion": 0.06,  # $0.06 per 1K completion tokens
        },
        "gpt-4-turbo": {
            "prompt": 0.01,  # $0.01 per 1K prompt tokens
            "completion": 0.03,  # $0.03 per 1K completion tokens
        },
        "gpt-4o": {
            "prompt": 0.0025,  # $0.0025 per 1K prompt tokens 
            "completion": 0.01,  # $0.01 per 1K completion tokens
        },
        "gpt-4.1-mini": {
            "prompt": 0.00015,  # $0.15 per 1M prompt tokens = $0.00015 per 1K
            "completion": 0.0006,  # $0.6 per 1M completion tokens = $0.0006 per 1K
        },
        "gpt-4.1-nano": {
            "prompt": 0.0001,  # $0.1 per 1M prompt tokens = $0.0001 per 1K
            "completion": 0.0004,  # $0.4 per 1M completion tokens = $0.0004 per 1K
        },
        "gpt-3.5-turbo": {
            "prompt": 0.0005,  # $0.0005 per 1K prompt tokens
            "completion": 0.0015,  # $0.0015 per 1K completion tokens
        },
    }
    
    # 이미지 생성 가격 정보 (USD per image)
    IMAGE_PRICING = {
        "gpt-image-1": {
            "low": {
                "1024x1024": 0.011,
                "1024x1536": 0.016,
                "1536x1024": 0.016
            },
            "medium": {
                "1024x1024": 0.042,
                "1024x1536": 0.063,
                "1536x1024": 0.063
            },
            "high": {
                "1024x1024": 0.167,
                "1024x1536": 0.25,
                "1536x1024": 0.25
            }
        },
        "dall-e-3": {
            "standard": {
                "1024x1024": 0.04,
                "1024x1792": 0.08,
                "1792x1024": 0.08
            },
            "hd": {
                "1024x1024": 0.08,
                "1024x1792": 0.12,
                "1792x1024": 0.12
            }
        },
        "dall-e-2": {
            "256x256": 0.016,
            "512x512": 0.018,
            "1024x1024": 0.02
        }
    }

    def __init__(self):
        self.metadata_dir = Path("article_metadata")
        self.metadata_dir.mkdir(exist_ok=True)

    def track_api_call(
        self, response, model: str, article_id: str, article_title: str = None
    ) -> Dict:
        """
        API 호출의 토큰 사용량 추적
        
        OpenAI API 응답에서 토큰 사용량을 추출하고 비용을 계산하여 저장합니다.
        
        Args:
            response: OpenAI API 응답 객체
            model: 사용된 모델명
            article_id: 기사 ID
            article_title: 기사 제목 (선택사항)
            
        Returns:
            토큰 사용 메타데이터 디텍셔너리
        """

        # 토큰 사용량 추출
        usage = response.usage
        prompt_tokens = usage.prompt_tokens
        completion_tokens = usage.completion_tokens
        total_tokens = usage.total_tokens

        # 모델명 정규화
        model_key = self._normalize_model_name(model)

        # 비용 계산
        cost_usd = self._calculate_cost(prompt_tokens, completion_tokens, model_key)

        # 메타데이터 생성
        metadata = {
            "id": article_id,
            "title": article_title,
            "created_at": datetime.now().isoformat(),
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cost_usd": cost_usd,
            "pricing": {
                "prompt_price": self.PRICING.get(model_key, {}).get("prompt", 0),
                "completion_price": self.PRICING.get(model_key, {}).get("completion", 0),
            },
        }

        # 파일로 저장
        self._save_metadata(article_id, metadata)

        return metadata

    def _normalize_model_name(self, model: str) -> str:
        """
        모델명 정규화
        
        다양한 형식의 모델명을 가격 테이블에서 사용할 표준 키로 변환합니다.
        
        Args:
            model: 원본 모델명
            
        Returns:
            정규화된 모델명
        """
        model_lower = model.lower()

        if "gpt-4.1-nano" in model_lower:
            return "gpt-4.1-nano"
        elif "gpt-4o" in model_lower:
            return "gpt-4o"
        elif "gpt-4-turbo" in model_lower:
            return "gpt-4-turbo"
        elif "gpt-4" in model_lower:
            return "gpt-4"
        elif "gpt-3.5" in model_lower:
            return "gpt-3.5-turbo"
        else:
            return "gpt-4"  # 기본값

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int, model: str) -> float:
        """
        비용 계산 (USD)
        
        토큰 사용량과 모델별 가격을 기반으로 비용을 계산합니다.
        
        Args:
            prompt_tokens: 프롬프트 토큰 수
            completion_tokens: 응답 토큰 수
            model: 모델명
            
        Returns:
            USD 비용 (소수점 6자리까지)
        """
        pricing = self.PRICING.get(model, self.PRICING["gpt-4"])

        prompt_cost = (prompt_tokens / 1000) * pricing["prompt"]
        completion_cost = (completion_tokens / 1000) * pricing["completion"]

        return round(prompt_cost + completion_cost, 6)

    def _save_metadata(self, article_id: str, metadata: Dict):
        """
        메타데이터 파일로 저장 (기존 데이터가 있으면 토큰 누적)
        
        기사 메타데이터를 JSON 파일로 저장합니다.
        동일한 기사에 대한 여러 API 호출이 있을 경우 토큰을 누적합니다.
        
        Args:
            article_id: 기사 ID
            metadata: 저장할 메타데이터
        """
        filename = self.metadata_dir / f"{article_id}_metadata.json"

        # 기존 메타데이터 확인
        if filename.exists():
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)

                # 토큰 누적
                metadata["prompt_tokens"] += existing_data.get("prompt_tokens", 0)
                metadata["completion_tokens"] += existing_data.get("completion_tokens", 0)
                metadata["total_tokens"] = metadata["prompt_tokens"] + metadata["completion_tokens"]

                # 비용 재계산
                model_key = self._normalize_model_name(metadata["model"])
                metadata["cost_usd"] = self._calculate_cost(
                    metadata["prompt_tokens"], metadata["completion_tokens"], model_key
                )

                # API 호출 횟수 추적
                metadata["api_calls"] = existing_data.get("api_calls", 1) + 1

                # 첫 번째 호출의 생성 시간 유지
                metadata["created_at"] = existing_data.get("created_at", metadata["created_at"])
                metadata["last_updated"] = datetime.now().isoformat()

            except Exception as e:
                print(f"Warning: Could not read existing metadata for {article_id}: {e}")
                metadata["api_calls"] = 1
        else:
            metadata["api_calls"] = 1

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def track_image_generation(
        self, model: str, quality: str, size: str, article_id: str, article_title: str = None,
        actual_cost_usd: float = None
    ) -> Dict:
        """
        이미지 생성 비용 추적
        
        Args:
            model: 이미지 모델명 (예: "gpt-image-1", "dall-e-3", "runware:100@1")
            quality: 품질 설정 (예: "low", "medium", "high", "standard", "hd")
            size: 이미지 크기 (예: "1024x1024", "1024x1536")
            article_id: 기사 ID
            article_title: 기사 제목 (선택사항)
            actual_cost_usd: 실제 비용 (Runware 등에서 제공하는 경우)
            
        Returns:
            이미지 생성 메타데이터 딕셔너리
        """
        # 비용 계산
        if actual_cost_usd is not None:
            # 실제 비용이 제공된 경우 (Runware)
            cost_usd = actual_cost_usd
        else:
            # 가격표 기반 계산 (OpenAI)
            cost_usd = 0
            if model in self.IMAGE_PRICING:
                if model == "dall-e-2":
                    # DALL-E 2는 품질 구분이 없음
                    cost_usd = self.IMAGE_PRICING[model].get(size, 0)
                else:
                    # GPT Image 1과 DALL-E 3는 품질별로 구분
                    quality_pricing = self.IMAGE_PRICING[model].get(quality, {})
                    cost_usd = quality_pricing.get(size, 0)
        
        # 메타데이터 생성
        metadata = {
            "id": article_id,
            "title": article_title,
            "created_at": datetime.now().isoformat(),
            "type": "image_generation",
            "model": model,
            "quality": quality,
            "size": size,
            "cost_usd": cost_usd,
            "provider": "runware" if "runware" in model else "openai"
        }
        
        # 파일로 저장 (기존 메타데이터에 추가)
        self._save_image_metadata(article_id, metadata)
        
        return metadata
    
    def _save_image_metadata(self, article_id: str, metadata: Dict):
        """이미지 생성 메타데이터 저장"""
        filename = self.metadata_dir / f"{article_id}_metadata.json"
        
        # 기존 메타데이터 확인
        if filename.exists():
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                
                # 이미지 생성 정보 추가
                if "image_generations" not in existing_data:
                    existing_data["image_generations"] = []
                
                existing_data["image_generations"].append({
                    "timestamp": metadata["created_at"],
                    "model": metadata["model"],
                    "quality": metadata["quality"],
                    "size": metadata["size"],
                    "cost_usd": metadata["cost_usd"]
                })
                
                # 전체 비용 업데이트
                existing_data["total_cost_usd"] = existing_data.get("cost_usd", 0) + metadata["cost_usd"]
                existing_data["last_updated"] = datetime.now().isoformat()
                
                metadata = existing_data
            except Exception as e:
                print(f"Warning: Could not read existing metadata for {article_id}: {e}")
                metadata["image_generations"] = [{
                    "timestamp": metadata["created_at"],
                    "model": metadata["model"],
                    "quality": metadata["quality"],
                    "size": metadata["size"],
                    "cost_usd": metadata["cost_usd"]
                }]
        else:
            metadata["image_generations"] = [{
                "timestamp": metadata["created_at"],
                "model": metadata["model"],
                "quality": metadata["quality"],
                "size": metadata["size"],
                "cost_usd": metadata["cost_usd"]
            }]
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    def get_total_usage(self) -> Dict:
        """
        전체 사용량 통계
        
        모든 기사의 토큰 사용량과 비용을 집계하여 반환합니다.
        
        Returns:
            전체 통계 디텍셔너리 {
                "total_articles": 총 기사 수,
                "total_prompt_tokens": 총 프롬프트 토큰,
                "total_completion_tokens": 총 응답 토큰,
                "total_tokens": 총 토큰,
                "total_cost_usd": 총 비용 (USD),
                "average_cost_per_article": 기사당 평균 비용
            }
        """
        total_prompt = 0
        total_completion = 0
        total_text_cost = 0
        total_image_cost = 0
        article_count = 0
        total_images = 0

        for metadata_file in self.metadata_dir.glob("*_metadata.json"):
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    total_prompt += data.get("prompt_tokens", 0)
                    total_completion += data.get("completion_tokens", 0)
                    total_text_cost += data.get("cost_usd", 0)
                    
                    # 이미지 생성 비용 추가
                    if "image_generations" in data:
                        for img in data["image_generations"]:
                            total_image_cost += img.get("cost_usd", 0)
                            total_images += 1
                    
                    article_count += 1
            except Exception as e:
                print(f"Error reading {metadata_file}: {e}")

        total_cost = total_text_cost + total_image_cost

        return {
            "total_articles": article_count,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "total_text_cost_usd": round(total_text_cost, 2),
            "total_image_cost_usd": round(total_image_cost, 2),
            "total_cost_usd": round(total_cost, 2),
            "total_images": total_images,
            "average_cost_per_article": round(total_cost / max(article_count, 1), 3),
            "average_images_per_article": round(total_images / max(article_count, 1), 2),
        }
