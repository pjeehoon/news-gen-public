"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

"""
스마트 기사 생성 시스템
- 기존 기사 재사용
- 새로운 정보만 업데이트
- 중복 방지
"""

import json
import logging
from datetime import datetime, timezone
import os
import sys
import re
from typing import Dict, List, Optional, Any, Tuple
import markdown

# 프로젝트 루트에서 실행되도록 경로 설정
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.path_utils import get_output_dir, get_smart_articles_dir, ensure_output_dirs
from scripts.article_cache_manager import ArticleCacheManager
from scripts.article_version_manager import ArticleVersionManager
from scripts.realtime_trend_analyzer import RealtimeTrendAnalyzer
from scripts.multi_article_deep_analyzer import MultiArticleDeepAnalyzer
from scripts.token_tracker import TokenTracker
from scripts.utils import APIKeyManager, RateLimiter, clean_text, truncate_text, get_kst_now, KST
from scripts.article_quality_evaluator import ArticleQualityEvaluator
from scripts.image_generator import generate_news_image
import openai
from dotenv import load_dotenv

load_dotenv()

# setup_logging 사용하여 로깅 표준화
from scripts.utils import setup_logging

logger = setup_logging("smart_article_generator")


class SmartArticleGenerator:
    """
    스마트 기사 생성 시스템
    
    기존 기사를 재사용하고 새로운 정보만 업데이트하여 효율적으로 기사를 생성합니다.
    토큰 사용량을 추적하고, 중복을 방지하며, 버전 관리를 통해 기사의 진화를 추적합니다.
    
    Attributes:
        cache_manager: 기사 캐시 관리자
        version_manager: 기사 버전 관리자
        trend_analyzer: 실시간 트렌드 분석기
        article_analyzer: 다중 기사 심층 분석기
        token_tracker: 토큰 사용량 추적기
        model_name: 사용할 AI 모델명
    """

    def __init__(self) -> None:
        """SmartArticleGenerator 초기화. 필요한 모든 컴포넌트와 API 클라이언트를 설정합니다."""
        self.cache_manager = ArticleCacheManager()
        self.version_manager = ArticleVersionManager()
        self.trend_analyzer = RealtimeTrendAnalyzer()
        self.article_analyzer = MultiArticleDeepAnalyzer()
        self.token_tracker = TokenTracker()
        self.quality_evaluator = ArticleQualityEvaluator()

        # API Key Manager 사용
        self.api_manager = APIKeyManager()
        if not self.api_manager.has_valid_key():
            raise ValueError("No valid API key found")

        self.client = openai.OpenAI(api_key=self.api_manager.get_active_key())
        self.rate_limiter = RateLimiter(calls_per_minute=20)  # OpenAI rate limit

        # 모델명을 환경 변수에서 가져오기
        self.model_name = os.getenv("DETAIL_MODEL", "gpt-4.1-nano")
        logger.info(f"Using model: {self.model_name}")

        self.total_tokens_used = 0
        self.total_cost = 0

    def sanitize_exclusive_terms(self, text: str) -> str:
        """
        독점 보도 관련 표현 제거
        
        뉴스 제목이나 본문에서 [단독], [속보] 등의 독점적 표현을 제거합니다.
        
        Args:
            text: 처리할 텍스트
            
        Returns:
            독점 관련 표현이 제거된 텍스트
        """
        # 제거할 표현들
        exclusive_terms = [
            "[단독]",
            "【단독】",
            "〈단독〉",
            "＜단독＞",
            "(단독)",
            "[독점]",
            "【독점】",
            "〈독점〉",
            "＜독점＞",
            "(독점)",
            "[속보]",
            "【속보】",
            "〈속보〉",
            "＜속보＞",
            "(속보)",
            "[긴급]",
            "【긴급】",
            "〈긴급〉",
            "＜긴급＞",
            "(긴급)",
            "[특종]",
            "【특종】",
            "〈특종〉",
            "＜특종＞",
            "(특종)",
            "단독:",
            "독점:",
            "속보:",
            "긴급:",
            "특종:",
            "단독 -",
            "독점 -",
            "속보 -",
            "긴급 -",
            "특종 -",
            "단독-",
            "독점-",
            "속보-",
            "긴급-",
            "특종-",
            "<단독>",
            "<독점>",
            "<속보>",
            "<긴급>",
            "<특종>",
        ]

        # 먼저 clean_text로 기본 정리 (HTML 태그 제거, 공백 정리 등)
        result = clean_text(text)

        # 독점 보도 관련 표현 제거
        for term in exclusive_terms:
            result = result.replace(term, "").strip()

        # 맨 앞에 오는 하이픈이나 콜론 제거
        result = re.sub(r"^[-:]\s*", "", result)

        return result.strip()

    def extract_keywords_from_title(self, title: str, article_content: str = None) -> List[str]:
        """
        ChatGPT API를 사용하여 제목과 내용에서 주요 키워드 추출
        
        뉴스 제목과 선택적으로 본문 내용을 분석하여 검색과 태그에
        최적화된 키워드를 추출합니다.
        
        Args:
            title: 키워드를 추출할 제목
            article_content: 선택적 기사 본문 (더 정확한 키워드 추출을 위해)
            
        Returns:
            추출된 키워드 리스트 (최대 5개)
        """
        import json
        
        try:
            # ChatGPT API를 사용한 스마트 키워드 추출
            prompt = f"""
다음 뉴스 제목에서 태그와 검색에 사용할 핵심 키워드를 추출해주세요.

제목: {title}
{f'본문 요약: {article_content[:300]}...' if article_content else ''}

요구사항:
1. 태그로 사용하기 적합한 핵심 키워드 5개
2. 인물명, 지역명, 사건명, 핵심 주제어 포함
3. 2-4글자의 명확한 단어 위주
4. 중복 없이 다양한 관점의 키워드

응답 형식 (JSON):
{{
    "keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"]
}}
"""

            # Rate limiting 적용
            self.rate_limiter.wait_if_needed()
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "keywords_extraction",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "keywords": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "minItems": 5,
                                    "maxItems": 5,
                                    "description": "핵심 키워드 5개"
                                }
                            },
                            "required": ["keywords"],
                            "additionalProperties": False
                        },
                        "strict": True
                    }
                }
            )
            
            # 토큰 사용량 추적
            if hasattr(self, "current_article_id"):
                self.token_tracker.track_api_call(
                    response,
                    "gpt-4.1-nano",
                    self.current_article_id,
                    getattr(self, "current_article_title", None),
                )
            
            # 응답 파싱
            result = json.loads(response.choices[0].message.content)
            keywords = result.get("keywords", [])
            
            # 유효한 키워드만 필터링
            valid_keywords = [k.strip() for k in keywords if k.strip() and len(k.strip()) <= 20]
            
            logger.info(f"ChatGPT로 추출된 키워드: {valid_keywords[:5]}")
            return valid_keywords[:5]
            
        except Exception as e:
            logger.error(f"ChatGPT 키워드 추출 실패: {e}")
            # 폴백: 간단한 패턴 기반 추출
            normalized_title = title.replace('"', "'").replace('"', "'").replace('"', "'")

            # 주요 키워드
            important_keywords = [
                "장관",
                "후보",
                "지명",
                "철회",
                "임명",
                "청문회",
                "논란",
                "의혹",
                "폭우",
                "사고",
                "화재",
                "대통령",
                "갑질",
            ]

            # 단어 분리
            words = normalized_title.split()

            for word in words:
                # 끝에 있는 구두점 제거
                clean_word = word.rstrip(",.!?;:").strip()

                # 괄호나 따옴표 제거
                clean_word = clean_word.strip("()[]{}\"'" "").strip()

                # 중요 키워드 체크
                for kw in important_keywords:
                    if kw in clean_word and clean_word not in keywords:
                        keywords.append(clean_word)
                        break

            # 키워드가 없으면 일반적인 단어 추출
            if not keywords:
                words = normalized_title.split()
                keywords = [w.strip(",.!?;:()[]{}\"'" "") for w in words if len(w) > 2][:3]

            # 기본 단어 추출
            words = title.split()
            keywords = [w.strip(",.!?;:()[]{}\"'" "") for w in words if len(w) >= 3][:5]

        return keywords[:5]  # 상위 5개만

    def generate_or_update_article(self, rank: int = 1) -> Dict[str, Any]:
        """
        스마트하게 기사 생성 또는 업데이트
        
        트렌드를 분석하여 지정된 순위의 뉴스에 대한 기사를 생성합니다.
        기존 관련 기사가 있다면 업데이트하고, 없다면 새로 생성합니다.
        
        Args:
            rank: 생성할 뉴스의 순위 (1-10, 기본값: 1)
            
        Returns:
            생성된 기사 정보 디텍셔너리 (생성 실패 시 None)
            {
                "article_id": 기사 ID,
                "title": 제목,
                "content": 본문,
                "url": 원본 URL,
                "keywords": 키워드 리스트,
                "created_at": 생성 시간,
                "is_new": 새 기사 여부,
                "status": 상태 메시지
            }
        """

        logger.info("=== 스마트 기사 생성 시작 ===")

        # 1. 현재 트렌드 분석
        logger.info("1단계: 실시간 트렌드 분석")
        trends = self.trend_analyzer.analyze_realtime_trends()

        if not trends or not trends.get("hot_news"):
            logger.error("트렌드 분석 실패")
            return None

        # 지정된 순위의 뉴스 선택
        if len(trends["hot_news"]) < rank:
            logger.warning(f"{rank}위 뉴스가 없음. 1위로 대체")
            rank = 1

        target_news = trends["hot_news"][rank - 1]
        title = self.sanitize_exclusive_terms(target_news["title"])  # 독점 보도 표현 제거
        url = target_news["link"]
        category = target_news.get("category", None)  # 카테고리 정보 추출

        # 토큰 추적을 위한 article_id 설정
        timestamp = get_kst_now().strftime("%Y%m%d_%H%M%S")
        self.current_article_id = f"article_{timestamp}"
        self.current_article_title = title

        logger.info(f"대상 뉴스: {title}")
        if category:
            logger.info(f"카테고리: {category}")

        # 2. 먼저 심층 분석을 수행하여 소스 기사 URL들을 얻음 (키워드 추출을 위해 순서 변경)
        logger.info("2단계: 심층 분석으로 소스 기사 수집")
        self.article_analyzer.token_tracker = self.token_tracker
        self.article_analyzer.current_article_id = self.current_article_id
        self.article_analyzer.current_article_title = self.current_article_title
        
        analysis_result = self.article_analyzer.analyze_topic(url, title, category)
        
        if not analysis_result:
            logger.error("심층 분석 실패")
            return None
            
        # 소스 기사 URL 추출
        source_articles = analysis_result.get("source_articles", [])
        logger.info(f"수집된 소스 기사: {len(source_articles)}개")
        
        # 3. 분석 결과를 활용한 키워드 추출
        article_content = analysis_result.get("comprehensive_article", "")
        keywords = self.extract_keywords_from_title(title, article_content)
        logger.info(f"추출된 키워드: {keywords}")

        # 4. 버전 관리자를 통한 관련 기사 확인 (소스 기사 기반 우선)
        logger.info("4단계: 관련 기사 확인 (소스 기사 기반)")
        related_article_id = self.version_manager.find_related_article(
            title, keywords, new_source_articles=source_articles
        )

        if related_article_id:
            logger.info(f"관련 기사 발견: {related_article_id}")
            # 캐시에서 기존 기사 로드
            existing_article = self.cache_manager.load_article(related_article_id)
            if existing_article:
                return self._handle_existing_article(
                    existing_article, title, url, keywords, related_article_id, category,
                    analysis_result=analysis_result, source_articles=source_articles
                )
            else:
                logger.warning(f"관련 기사 ID는 있지만 캐시에서 찾을 수 없음: {related_article_id}")
                return self._create_new_article(title, url, keywords, category, 
                                              analysis_result=analysis_result, source_articles=source_articles)
        else:
            logger.info("새로운 주제 - 기사 생성 진행")
            return self._create_new_article(title, url, keywords, category,
                                          analysis_result=analysis_result, source_articles=source_articles)

    def generate_multiple_articles(self, start_rank: int = 1, end_rank: int = 5) -> Dict[str, Any]:
        """
        여러 순위의 기사를 한번에 생성 (중복 방지)
        
        지정된 범위의 순위에 해당하는 뉴스들에 대해 기사를 생성합니다.
        이미 생성된 기사는 건너뛰어 중복을 방지합니다.
        
        Args:
            start_rank: 시작 순위 (기본값: 1)
            end_rank: 끝 순위 (기본값: 5)
            
        Returns:
            생성 결과 요약 디텍셔너리
            {
                "created": 생성된 기사 리스트,
                "skipped": 건너뛴 기사 리스트,
                "failed": 실패한 기사 리스트,
                "total_created": 생성된 기사 수,
                "total_skipped": 건너뛴 기사 수,
                "total_failed": 실패한 기사 수
            }
        """

        logger.info(f"\n{'='*60}")
        logger.info(f"🎯 {start_rank}위~{end_rank}위 기사 일괄 생성 시작")
        logger.info(f"{'='*60}\n")

        results = {
            "created": [],
            "skipped": [],
            "failed": [],
            "total_created": 0,
            "total_skipped": 0,
            "total_failed": 0,
        }

        # 트렌드 분석 (한 번만)
        logger.info("📊 실시간 트렌드 분석 중...")
        try:
            trends = self.trend_analyzer.analyze_realtime_trends()
            logger.info(f"트렌드 분석 결과: {type(trends)}")

            if not trends:
                logger.error("❌ 트렌드 분석 실패: trends가 None")
                return results

            if not trends.get("hot_news"):
                logger.error(
                    f"❌ 트렌드 분석 실패: hot_news가 없음. trends keys: {list(trends.keys())}"
                )
                return results

        except Exception as e:
            logger.error(f"❌ 트렌드 분석 중 예외 발생: {e}", exc_info=True)
            return results

        available_count = len(trends["hot_news"])
        logger.info(f"✅ {available_count}개의 트렌드 뉴스 발견\n")

        # 실제 처리할 범위 조정
        actual_end_rank = min(end_rank, available_count)

        # 각 순위의 뉴스 처리
        for rank in range(start_rank, actual_end_rank + 1):
            logger.info(f"\n{'─'*50}")
            logger.info(f"📰 {rank}위 뉴스 처리 중...")

            target_news = trends["hot_news"][rank - 1]
            title = self.sanitize_exclusive_terms(target_news["title"])  # 독점 보도 표현 제거
            url = target_news["link"]

            logger.info(f"제목: {title[:50]}...")

            # 키워드 추출 (임시로 제목만 사용)
            keywords = self.extract_keywords_from_title(title, None)
            logger.info(f"키워드: {keywords}")

            # 관련 기사 확인
            related_article_id = self.version_manager.find_related_article(title, keywords)

            if related_article_id:
                # 기존 기사가 있는 경우
                existing_article = self.cache_manager.load_article(related_article_id)
                if existing_article:
                    # 마지막 업데이트 시간 확인 (업데이트가 있었다면 그 시간, 없으면 생성 시간)
                    last_time = existing_article.get(
                        "last_updated", existing_article.get("created_at", "")
                    )
                    if last_time:
                        try:
                            # ISO format 문자열을 파싱하고 timezone 처리
                            if last_time.endswith("Z"):
                                last_datetime = datetime.fromisoformat(
                                    last_time.replace("Z", "+00:00")
                                )
                            else:
                                last_datetime = datetime.fromisoformat(last_time)

                            # timezone이 없으면 UTC로 가정
                            if last_datetime.tzinfo is None:
                                last_datetime = last_datetime.replace(tzinfo=timezone.utc)

                            # 현재 시간도 UTC로
                            current_time = datetime.now(KST)
                            time_diff = (current_time - last_datetime).total_seconds() / 3600

                            if time_diff < 1.0:  # 1시간 이내
                                logger.info(
                                    f"⏭️  건너뜀: 동일 토픽 기사가 {time_diff:.1f}시간 전에 작성/업데이트됨"
                                )
                                results["skipped"].append(
                                    {
                                        "rank": rank,
                                        "title": title,
                                        "reason": f"{time_diff:.1f}시간 전 생성된 동일 토픽",
                                        "existing_id": related_article_id,
                                    }
                                )
                                results["total_skipped"] += 1
                                continue
                        except Exception as e:
                            logger.debug(f"Created time parsing failed: {e}")

            # 새 기사 생성
            try:
                logger.info("✍️  새 기사 생성 중...")
                result = self.generate_or_update_article(rank)

                if result and result["status"] in ["created", "updated"]:
                    if result["status"] == "created":
                        logger.info(f"✅ 생성 완료: {result.get('html_path', '')}")
                        results["created"].append(
                            {
                                "rank": rank,
                                "title": title,
                                "article_id": result.get("topic_id"),
                                "html_path": result.get("html_path"),
                            }
                        )
                        results["total_created"] += 1
                    else:  # updated
                        logger.info(
                            f"✅ 업데이트 완료: {result.get('html_path', '')} (버전 {result.get('version', 'N/A')})"
                        )
                        results["created"].append(
                            {
                                "rank": rank,
                                "title": title,
                                "article_id": result.get("topic_id"),
                                "html_path": result.get("html_path"),
                                "version": result.get("version"),
                            }
                        )
                        results["total_created"] += 1
                else:
                    logger.warning(f"⚠️  생성 실패 또는 재사용")
                    results["failed"].append(
                        {
                            "rank": rank,
                            "title": title,
                            "reason": (
                                result.get("message", "알 수 없는 오류") if result else "생성 실패"
                            ),
                        }
                    )
                    results["total_failed"] += 1

            except Exception as e:
                logger.error(f"❌ 오류 발생: {e}")
                results["failed"].append({"rank": rank, "title": title, "reason": str(e)})
                results["total_failed"] += 1

            # 잠시 대기 (API 제한 고려)
            if rank < actual_end_rank:
                import time

                time.sleep(2)

        # 결과 요약 출력
        logger.info(f"\n{'='*60}")
        logger.info("📊 일괄 생성 결과 요약")
        logger.info(f"{'='*60}")
        logger.info(f"✅ 생성됨: {results['total_created']}개")
        logger.info(f"⏭️  건너뜀: {results['total_skipped']}개")
        logger.info(f"❌ 실패: {results['total_failed']}개")

        if results["created"]:
            logger.info("\n✅ 생성/업데이트된 기사:")
            for item in results["created"]:
                if "version" in item:
                    logger.info(
                        f"  - {item['rank']}위: {item['title'][:40]}... (버전 {item['version']})"
                    )
                else:
                    logger.info(f"  - {item['rank']}위: {item['title'][:40]}...")

        if results["skipped"]:
            logger.info("\n⏭️  건너뛴 기사:")
            for item in results["skipped"]:
                logger.info(f"  - {item['rank']}위: {item['title'][:40]}... ({item['reason']})")

        if results["failed"]:
            logger.info("\n❌ 실패한 기사:")
            for item in results["failed"]:
                logger.info(f"  - {item['rank']}위: {item['title'][:40]}... ({item['reason']})")

        logger.info(f"\n{'='*60}\n")

        return results

    def _handle_existing_article(
        self,
        cached_data: Dict[str, Any],
        new_title: str,
        new_url: str,
        keywords: List[str],
        related_article_id: str,
        category: Optional[str] = None,
        analysis_result: Optional[Dict[str, Any]] = None,
        source_articles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        기존 기사 처리
        
        기존에 생성된 관련 기사가 있을 때, 새로운 정보가 있는지 확인하고
        필요한 경우 업데이트하거나 기존 기사를 재사용합니다.
        
        Args:
            cached_data: 캐시된 기존 기사 데이터
            new_title: 새 기사 제목
            new_url: 새 기사 URL
            keywords: 추출된 키워드 리스트
            related_article_id: 관련 기사 ID
            category: 카테고리 정보 (선택사항)
            
        Returns:
            처리 결과 디텍셔너리 (status: reused/updated)
        """

        topic_id = cached_data["topic_id"]
        logger.info(f"기존 기사 처리: {topic_id}")

        # 소스 기사 기반 업데이트 필요성 확인
        needs_update = False
        significant_changes = []
        
        if source_articles and cached_data.get("source_articles"):
            logger.info("소스 기사 기반 업데이트 확인")
            existing_sources = cached_data.get("source_articles", [])
            source_check = self.version_manager.check_update_necessity_by_sources(
                existing_sources, source_articles
            )
            
            if source_check["needs_update"]:
                needs_update = True
                significant_changes.append(source_check["reason"])
                logger.info(f"새로운 소스 발견: {len(source_check['new_sources'])}개")
            elif source_check["reason"] == "모든 소스 기사가 동일함":
                logger.info("모든 소스가 동일 - 업데이트 불필요")
                needs_update = False
        
        # 소스 기반 확인에서 업데이트가 불필요하다고 판단되면 기존 기사 재사용
        if not needs_update and source_articles:
            # 소스가 모두 동일한 경우
            pass
        else:
            # 소스 기반 확인이 없거나 추가 확인이 필요한 경우 기존 방식 사용
            logger.info("추가 업데이트 필요성 확인")
            new_articles = self.article_analyzer.search_related_articles(new_title, limit=5)
            
            # 새로운 기사 정보 준비
            new_article_data = {
                "title": new_title,
                "content": "\n".join([article.get("description", "") for article in new_articles]),
                "source_articles": source_articles or []
            }
            
            # 버전 관리자를 통한 추가 업데이트 필요성 확인
            additional_update, additional_changes = self.version_manager.check_update_necessity(
                cached_data, new_article_data
            )
            
            if additional_update:
                needs_update = True
                significant_changes.extend(additional_changes)

        if not needs_update:
            logger.info("중요한 새로운 정보 없음 - 기존 기사 재사용")

            # 기사 버전 히스토리 가져오기
            version_history = self.version_manager.get_article_history(related_article_id)

            return {
                "status": "reused",
                "message": "기존 기사 재사용 (중요한 새로운 정보 없음)",
                "article": cached_data.get(
                    "generated_article", cached_data.get("comprehensive_article", "")
                ),
                "topic_id": topic_id,
                "version": cached_data.get("version", 1),
                "last_updated": cached_data.get("last_updated", cached_data.get("created_at", "")),
                "version_history": version_history,
            }

        # 중요한 업데이트 수행
        logger.info(f"중요한 새로운 정보 발견: {significant_changes}")

        # analysis_result가 없으면 분석 수행
        if not analysis_result:
            logger.info("심층 분석 수행")
            self.article_analyzer.token_tracker = self.token_tracker
            self.article_analyzer.current_article_id = self.current_article_id
            self.article_analyzer.current_article_title = self.current_article_title
            
            # 버전 정보와 이전 기사 내용 준비
            current_version = cached_data.get("version", 1) + 1  # 업데이트될 버전
            previous_article_content = cached_data.get("comprehensive_article", "")
            
            analysis_result = self.article_analyzer.analyze_topic(
                new_url, new_title, category, 
                version=current_version,
                previous_article_content=previous_article_content
            )
            
            if not analysis_result:
                logger.error("업데이트를 위한 분석 실패")
                return None

        # 업데이트 수행
        return self._update_existing_article_with_analysis(
            cached_data, analysis_result, related_article_id, significant_changes, source_articles
        )

    def _create_new_article(
        self, title: str, url: str, keywords: List[str], category: Optional[str] = None,
        analysis_result: Optional[Dict[str, Any]] = None, source_articles: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """완전히 새로운 기사 생성"""

        # analysis_result가 이미 전달되었다면 재분석하지 않음
        if analysis_result:
            logger.info("3단계: 이미 수행된 분석 결과 사용")
        else:
            # 다중 기사 분석
            logger.info("3단계: 다중 기사 수집 및 분석")
            # 토큰 추적을 위한 정보 전달
            self.article_analyzer.token_tracker = self.token_tracker
            self.article_analyzer.current_article_id = self.current_article_id
            self.article_analyzer.current_article_title = self.current_article_title
            
            # 새 기사는 버전 1로 시작
            analysis_result = self.article_analyzer.analyze_topic(
                url, title, category,
                version=1,
                previous_article_content=None
            )

        if not analysis_result:
            logger.error("기사 분석 실패")
            return None

        # 품질 평가
        logger.info("4단계: 기사 품질 평가")
        article_content = analysis_result["comprehensive_article"]
        
        # 품질 평가 수행
        quality_rating, quality_emoji, quality_details = self.quality_evaluator.evaluate_article({
            "comprehensive_article": article_content,
            "generated_article": article_content
        })
        
        logger.info(f"기사 품질 평가 결과: {quality_rating} {quality_emoji}")

        # 태그 확인 및 생성
        logger.info("5단계: 기사 최종 처리")
        tags = analysis_result.get("tags", {"category_tags": [], "content_tags": []})
        if not tags.get("category_tags") or not tags.get("content_tags"):
            logger.info("태그가 없거나 불완전함. 태그 재생성 중...")
            tags = self._generate_tags_for_article(title, article_content)

        # 최종 기사 데이터
        final_article_data = {
            "main_article": analysis_result["main_article"],
            "generated_title": analysis_result.get("generated_title", title),  # AI 생성 제목 추가
            "analysis": analysis_result["analysis"],
            "related_articles": analysis_result.get("related_articles", []),
            "comprehensive_article": article_content,  # Use the original article content
            "quality_rating": quality_rating,
            "quality_emoji": quality_emoji,
            "quality_details": quality_details,
            "youtube_count": analysis_result.get("youtube_count", 0),
            "google_count": analysis_result.get("google_count", 0),
            "youtube_videos": analysis_result.get("youtube_videos", []),
            "google_articles": analysis_result.get("google_articles", []),
            "tags": tags,  # 검증된 태그
            "source_articles": analysis_result.get("source_articles", []),  # 소스 기사 URL 목록
        }

        # 버전 관리자를 통한 기사 생성
        article_data = {
            "title": title,
            "content": article_content,
            "keywords": keywords,
            "tags": tags,  # 검증된 태그 사용
            "source_articles": analysis_result.get("source_articles", []),  # 소스 기사 URL 목록
        }

        # 새 기사 ID 생성 (버전 1)
        article_id = self.version_manager.create_article_version(article_data)

        # 버전 히스토리 추가
        final_article_data["version"] = 1
        final_article_data["version_history"] = self.version_manager.get_article_history(article_id)

        # 캐시 저장 (새로운 ID 사용)
        final_article_data["topic_id"] = article_id
        self.cache_manager.save_article_cache(final_article_data, keywords)
        
        # 이미지 생성 (버전 1 기사만)
        logger.info("6단계: AI 이미지 생성")
        # 카테고리 정보 추가
        final_article_data["category"] = category  # 카테고리 정보 추가
        final_article_data["keywords"] = keywords  # 키워드 정보 추가
        
        # 세 줄 요약 추출 (없으면 첫 문단 사용)
        if "three_line_summary" not in final_article_data:
            # article_content에서 첫 문단 추출
            first_paragraph = article_content.split('\n\n')[0] if article_content else ""
            final_article_data["three_line_summary"] = first_paragraph[:200]  # 최대 200자
        
        image_result = generate_news_image(final_article_data)
        if image_result and image_result.get("success"):
            final_article_data["generated_image_path"] = image_result["image_path"]
            logger.info(f"이미지 생성 완료: {image_result['image_path']}")
            # 캐시 업데이트
            self.cache_manager.save_article_cache(final_article_data, keywords)
        else:
            logger.warning(f"이미지 생성 실패: {image_result.get('error', 'Unknown error') if image_result else 'No result'}")

        # HTML 생성
        html_output = self._generate_html(
            final_article_data, analysis_result.get("related_articles_count", 1)
        )

        # 결과 저장
        ensure_output_dirs()
        output_dir = get_smart_articles_dir()

        timestamp = get_kst_now().strftime("%Y%m%d_%H%M%S")

        # 버전별 파일명
        version_filename = f"article_{article_id}_v{1}.html"
        version_path = f"{output_dir}/versions/{version_filename}"

        # 버전 디렉토리 생성
        os.makedirs(f"{output_dir}/versions", exist_ok=True)

        # 버전별 HTML 저장
        with open(version_path, "w", encoding="utf-8") as f:
            f.write(html_output)

        # 최신 버전 링크 (기존 방식)
        html_path = f"{output_dir}/article_{timestamp}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_output)

        logger.info(f"새 기사 생성 완료: {html_path}")
        logger.info(f"버전 파일 저장: {version_path}")

        return {
            "status": "created",
            "message": "새로운 기사 생성 완료",
            "article": article_content,
            "topic_id": article_id,
            "version": 1,
            "html_path": html_path,
            # 'quality_scores': 제거
            "version_history": final_article_data["version_history"],
        }

    def _update_existing_article_with_analysis(
        self,
        cached_data: Dict[str, Any],
        analysis_result: Dict[str, Any],
        related_article_id: str,
        significant_changes: List[str],
        source_articles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        분석 결과를 기반으로 기존 기사 업데이트
        
        새로운 분석 결과를 사용하여 기존 기사를 업데이트합니다.
        
        Args:
            cached_data: 캐시된 기존 기사 데이터
            analysis_result: 새로운 분석 결과
            related_article_id: 관련 기사 ID
            significant_changes: 중요한 변경사항 리스트
            source_articles: 소스 기사 URL 목록
            
        Returns:
            업데이트 결과 디텍셔너리
        """
        
        # 새로운 기사 내용
        updated_content = analysis_result["comprehensive_article"]
        
        # 품질 재평가
        logger.info("업데이트된 기사 품질 평가 중...")
        quality_rating, quality_emoji, quality_details = self.quality_evaluator.evaluate_article({
            "comprehensive_article": updated_content,
            "generated_article": updated_content
        })
        
        logger.info(f"업데이트된 기사 품질: {quality_rating} {quality_emoji}")
        
        # 태그 확인 및 생성
        tags = analysis_result.get("tags", {"category_tags": [], "content_tags": []})
        if not tags.get("category_tags") or not tags.get("content_tags"):
            logger.info("태그 재생성 중...")
            tags = self._generate_tags_for_article(
                cached_data["main_article"]["title"], updated_content
            )
        
        # 버전 관리자를 통한 새 버전 생성
        article_data = {
            "title": cached_data["main_article"]["title"],
            "content": updated_content,
            "keywords": cached_data.get("keywords", []),
            "significant_changes": significant_changes,
            "tags": tags,
            "source_articles": source_articles or [],  # 소스 기사 URL 추가
        }
        
        # 새 버전 ID 생성
        new_article_id = self.version_manager.create_article_version(
            article_data, parent_id=related_article_id
        )
        
        # 캐시 업데이트
        cached_data["generated_article"] = updated_content
        cached_data["comprehensive_article"] = updated_content
        cached_data["topic_id"] = new_article_id
        cached_data["version"] = self.version_manager.topic_index[new_article_id]["version"]
        cached_data["version_history"] = self.version_manager.get_article_history(new_article_id)
        cached_data["tags"] = tags
        cached_data["quality_rating"] = quality_rating
        cached_data["quality_emoji"] = quality_emoji
        cached_data["quality_details"] = quality_details
        cached_data["source_articles"] = source_articles or []  # 소스 기사 URL 업데이트
        
        # 분석 결과 업데이트
        cached_data["analysis"] = analysis_result.get("analysis", {})
        cached_data["related_articles"] = analysis_result.get("related_articles", [])
        
        # 새 버전으로 캐시 저장
        self.cache_manager.save_article_cache(cached_data, cached_data.get("keywords", []))
        
        # HTML 생성 (버전 히스토리 포함)
        html_output = self._generate_html(
            cached_data, 
            analysis_result.get("related_articles_count", 1), 
            is_update=True
        )
        
        # 결과 저장
        ensure_output_dirs()
        output_dir = get_smart_articles_dir()
        
        # 버전별 파일명
        version_filename = f"article_{new_article_id}_v{cached_data['version']}.html"
        version_path = f"{output_dir}/versions/{version_filename}"
        
        # 버전 디렉토리 생성
        os.makedirs(f"{output_dir}/versions", exist_ok=True)
        
        # 버전별 HTML 저장
        with open(version_path, "w", encoding="utf-8") as f:
            f.write(html_output)
        
        logger.info(f"업데이트된 기사 저장: {version_path}")
        
        # 최신 버전 링크 업데이트
        latest_filename = f"article_{new_article_id}_latest.html"
        latest_path = f"{output_dir}/{latest_filename}"
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(html_output)
        
        # JSON 메타데이터 저장
        json_filename = f"article_{new_article_id}.json"
        json_path = f"{output_dir}/{json_filename}"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(cached_data, f, ensure_ascii=False, indent=2)
        
        return {
            "status": "updated",
            "message": f"기사 업데이트 완료 (버전 {cached_data['version']})",
            "significant_changes": significant_changes,
            "article": updated_content,
            "topic_id": new_article_id,
            "version": cached_data["version"],
            "version_history": cached_data["version_history"],
            "html_path": latest_path,
            "json_path": json_path,
        }

    def _update_existing_article(
        self,
        cached_data: Dict[str, Any],
        updates: Dict,
        new_articles: List[Dict],
        related_article_id: str,
        significant_changes: List[str],
    ) -> Dict[str, Any]:
        """
        기존 기사 업데이트
        
        중요한 새로운 정보가 발견되었을 때 기존 기사를 업데이트합니다.
        새 버전을 생성하고 버전 히스토리를 관리합니다.
        
        Args:
            cached_data: 캐시된 기존 기사 데이터
            updates: 업데이트할 내용
            new_articles: 새로운 관련 기사 리스트
            related_article_id: 관련 기사 ID
            significant_changes: 중요한 변경사항 리스트
            
        Returns:
            업데이트 결과 디텍셔너리
        """

        # 새로운 정보로 추가 분석
        new_analysis = {
            "new_developments": updates.get("new_developments", []),
            "updated_at": get_kst_now().isoformat(),
        }

        # 업데이트된 기사 생성
        updated_content = self._generate_updated_content(
            cached_data["generated_article"], updates, new_articles
        )

        # 품질 재평가
        logger.info("업데이트된 기사 품질 평가 중...")
        quality_rating, quality_emoji, quality_details = self.quality_evaluator.evaluate_article({
            "comprehensive_article": updated_content,
            "generated_article": updated_content
        })
        
        logger.info(f"업데이트된 기사 품질: {quality_rating} {quality_emoji}")

        # 업데이트 시에도 태그 재생성
        logger.info("기사 업데이트 시 태그 재생성 중...")
        updated_tags = self._generate_tags_for_article(
            cached_data["main_article"]["title"], updated_content
        )

        # 버전 관리자를 통한 새 버전 생성
        article_data = {
            "title": cached_data["main_article"]["title"],
            "content": updated_content,
            "keywords": cached_data.get("keywords", []),
            "significant_changes": significant_changes,
            "tags": updated_tags,  # 업데이트된 태그 추가
        }

        # 새 버전 ID 생성
        new_article_id = self.version_manager.create_article_version(
            article_data, parent_id=related_article_id
        )

        # 캐시 업데이트
        cached_data["generated_article"] = updated_content
        cached_data["comprehensive_article"] = updated_content
        cached_data["topic_id"] = new_article_id
        cached_data["version"] = self.version_manager.topic_index[new_article_id]["version"]
        cached_data["version_history"] = self.version_manager.get_article_history(new_article_id)
        cached_data["tags"] = updated_tags  # 태그도 업데이트
        cached_data["quality_rating"] = quality_rating
        cached_data["quality_emoji"] = quality_emoji
        cached_data["quality_details"] = quality_details

        # 새 버전으로 캐시 저장
        self.cache_manager.save_article_cache(cached_data, cached_data.get("keywords", []))

        updated_data = cached_data

        # HTML 생성 (버전 히스토리 포함)
        html_output = self._generate_html(updated_data, len(new_articles), is_update=True)

        # 결과 저장
        ensure_output_dirs()
        output_dir = get_smart_articles_dir()
        timestamp = get_kst_now().strftime("%Y%m%d_%H%M%S")

        # 버전별 파일명
        version_filename = f"article_{new_article_id}_v{updated_data['version']}.html"
        version_path = f"{output_dir}/versions/{version_filename}"

        # 버전 디렉토리 생성
        os.makedirs(f"{output_dir}/versions", exist_ok=True)

        # 버전별 HTML 저장
        with open(version_path, "w", encoding="utf-8") as f:
            f.write(html_output)

        # 최신 버전 링크 (기존 방식)
        html_path = f"{output_dir}/article_{timestamp}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_output)

        logger.info(f"기사 업데이트 완료: {html_path} (버전 {updated_data['version']})")
        logger.info(f"버전 파일 저장: {version_path}")

        return {
            "status": "updated",
            "message": f'기사 업데이트 완료 (버전 {updated_data["version"]})',
            "article": updated_content,
            "topic_id": new_article_id,
            "version": updated_data["version"],
            "html_path": html_path,
            "updates": updates,
            "significant_changes": significant_changes,
            "version_history": cached_data["version_history"],
        }

    def _generate_updated_content(
        self, original_article: str, updates: Dict, new_articles: List[Dict]
    ) -> str:
        """업데이트된 기사 내용 생성"""

        # 현재 날짜
        current_date = get_kst_now().strftime("%Y년 %m월 %d일")

        # 새로운 정보 요약 (출처 URL 포함)
        new_info_summary = []
        source_urls = []
        
        for dev in updates.get("new_developments", []):
            source = dev['source']
            url = dev.get('url', '')
            new_info_summary.append(f"- {source}: {dev.get('type', 'update')}")
            if url:
                source_urls.append(f"  - {source}: {url}")

        for fact in updates.get("new_facts", []):
            content_preview = fact['content_preview'][:100]
            url = fact.get('url', '')
            new_info_summary.append(f"- 새로운 정보: {content_preview}...")
            if url:
                source_urls.append(f"  - 새로운 정보 출처: {url}")

        # 관련 기사 URL 수집
        article_sources = []
        for idx, article in enumerate(new_articles[:5]):  # 최대 5개까지
            title = article.get('title', f'기사 {idx+1}')
            url = article.get('url', '')
            if url:
                article_sources.append(f"- [{title}]({url})")

        prompt = f"""
다음은 기존 기사입니다:

{original_article}

다음은 새롭게 발견된 정보입니다:

{chr(10).join(new_info_summary)}

출처 URL:
{chr(10).join(source_urls) if source_urls else '(URL 정보 없음)'}

관련 기사들:
{chr(10).join(article_sources) if article_sources else '(관련 기사 없음)'}

현재 날짜: {current_date}

위의 새로운 정보를 반영하여 기사를 업데이트해 주세요.

주의사항:
1. 기존 기사의 주요 내용은 유지하되, 새로운 정보를 적절히 통합
2. 업데이트된 부분은 자연스럽게 녹여내기
3. 시간 순서를 명확히 하여 독자가 사건의 진행을 이해할 수 있도록
4. 날짜는 구체적으로 명시 (YYYY년 MM월 DD일)
5. 기사 끝에 "(최종 업데이트: {current_date})" 추가
6. 마크다운 형식으로 작성 (### 소제목, [링크텍스트](URL) 등)
7. [단독], [독점], [속보], [긴급], [특종] 등의 독점 보도 표현은 절대 사용하지 마세요
8. **중요한 정보나 특별한 진술에 대해서는 본문 내에 마크다운 형식으로 원본 기사 링크를 직접 삽입**
   예: "정부는 [2025년 7월 23일 발표](https://example.com/news/123)에서 새로운 정책을 공개했다."
9. 새롭게 추가된 중요 정보는 출처 링크와 함께 명시

업데이트된 기사를 마크다운 형식으로 작성해주세요.
"""

        try:
            # Rate limiting 적용
            self.rate_limiter.wait_if_needed()

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=3000,
            )

            # 토큰 사용량 추적
            if hasattr(self, "current_article_id"):
                self.token_tracker.track_api_call(
                    response,
                    self.model_name,
                    self.current_article_id,
                    getattr(self, "current_article_title", None),
                )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"기사 업데이트 생성 실패: {e}")
            return original_article

    def _refresh_article(
        self, cached_data: Dict[str, Any], new_title: str, new_url: str
    ) -> Dict[str, Any]:
        """
        오래된 기사 새로고침
        
        작성된지 오래된 기사의 시제와 표현을 현재 시점에 맞게 새로고침합니다.
        기사의 내용은 동일하게 유지하면서 표현만 업데이트합니다.
        
        Args:
            cached_data: 캐시된 기존 기사 데이터
            new_title: 새 기사 제목 (사용되지 않음)
            new_url: 새 기사 URL (사용되지 않음)
            
        Returns:
            새로고침 결과 디텍셔너리
        """

        # 기존 분석 데이터는 유지하면서 표현만 새로고침
        prompt = f"""
다음은 {cached_data['last_updated']}에 작성된 기사입니다:

{cached_data['generated_article']}

현재 날짜: {get_kst_now().strftime("%Y년 %m월 %d일")}

위 기사를 현재 시점에 맞게 새로고침해주세요.
- 내용은 동일하게 유지
- 시제와 표현만 현재 상황에 맞게 조정
- 날짜 표현을 구체적으로 유지

새로고침된 기사를 작성해주세요.
"""

        try:
            # Rate limiting 적용
            self.rate_limiter.wait_if_needed()

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=3000,
            )

            refreshed_content = response.choices[0].message.content

            # 품질 재평가 제거

            return {
                "status": "refreshed",
                "message": "기사 새로고침 완료",
                "article": refreshed_content,
                "topic_id": cached_data["topic_id"],
                "version": cached_data["version"],
                "last_updated": get_kst_now().isoformat(),
            }

        except Exception as e:
            logger.error(f"기사 새로고침 실패: {e}")
            return {
                "status": "reused",
                "message": "기존 기사 재사용",
                "article": cached_data["generated_article"],
                "topic_id": cached_data["topic_id"],
                "version": cached_data["version"],
            }

    def _generate_tags_for_article(self, title: str, content: str) -> Dict[str, Any]:
        """
        기사 제목과 내용을 기반으로 태그 생성
        
        AI를 이용하여 기사의 카테고리 태그와 내용 태그를 자동 생성합니다.
        
        Args:
            title: 기사 제목
            content: 기사 본문
            
        Returns:
            태그 디텍셔너리 {
                "category_tags": [카테고리 태그 리스트],
                "content_tags": [내용 태그 리스트]
            }
        """
        try:
            prompt = f"""
다음 뉴스 기사의 제목과 내용을 보고 태그를 생성해주세요.

제목: {title}

내용 (일부):
{content[:1500]}

태그는 두 종류로 분류해주세요:

1. category_tags (카테고리 태그): 최대 2개
   - 다음 중에서만 선택: 정치, 경제, 사회, 생활/문화, 국제, IT/과학

2. content_tags (내용 태그): 3-5개
   - 기사의 핵심 키워드, 인물명, 기업명, 사건명 등
   - 너무 일반적인 단어보다는 구체적인 태그 선호

JSON 형식으로 응답해주세요:
{{
    "category_tags": ["카테고리1", "카테고리2"],
    "content_tags": ["태그1", "태그2", "태그3"]
}}
"""

            # Rate limiting 적용
            self.rate_limiter.wait_if_needed()

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200,
            )

            # 토큰 사용량 추적
            if hasattr(self, "current_article_id"):
                self.token_tracker.track_api_call(
                    response,
                    self.model_name,
                    self.current_article_id,
                    getattr(self, "current_article_title", None),
                )

            # JSON 파싱
            response_text = response.choices[0].message.content.strip()
            # JSON 블록 추출 (```json ... ``` 형식 처리)
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            tags = json.loads(response_text)

            # 유효성 검사 및 기본값 처리
            if not isinstance(tags, dict):
                raise ValueError("Invalid tags format")

            # category_tags 검증
            valid_categories = ["정치", "경제", "사회", "생활/문화", "국제", "IT/과학"]
            category_tags = []
            for tag in tags.get("category_tags", []):
                if tag in valid_categories:
                    category_tags.append(tag)

            # 최소 1개는 있어야 함
            if not category_tags:
                # 제목에서 카테고리 추측
                if any(word in title for word in ["대통령", "국회", "정부", "선거", "정당"]):
                    category_tags = ["정치"]
                elif any(word in title for word in ["경제", "금융", "주식", "부동산", "기업"]):
                    category_tags = ["경제"]
                elif any(word in title for word in ["AI", "인공지능", "IT", "기술", "과학"]):
                    category_tags = ["IT/과학"]
                else:
                    category_tags = ["사회"]

            # content_tags 검증
            content_tags = tags.get("content_tags", [])
            if not content_tags:
                # 제목과 내용에서 주요 단어 추출
                keywords = self.extract_keywords_from_title(title, comprehensive_article[:500])
                content_tags = keywords[:3] if keywords else ["뉴스"]

            return {
                "category_tags": category_tags[:2],  # 최대 2개
                "content_tags": content_tags[:5],  # 최대 5개
            }

        except Exception as e:
            logger.error(f"태그 생성 실패: {e}")
            # 기본 태그 반환
            return {
                "category_tags": ["사회"],
                "content_tags": self.extract_keywords_from_title(title, None)[:3] or ["뉴스"],
            }

    def _generate_summary_section(self, article_data: Dict) -> str:
        """세줄 요약 및 품질 평가 섹션 생성 - 요약 실패 시 섹션 자체를 표시하지 않음"""
        summary = self._generate_three_line_summary(article_data)
        if summary is None:
            return ""  # 요약 생성 실패 시 빈 문자열 반환
        
        # 품질 평가 정보는 계산하되 표시하지 않음
        # quality_rating = article_data.get("quality_rating", "")
        # quality_emoji = article_data.get("quality_emoji", "")
        # quality_section = ""
        
        # if quality_rating and quality_emoji:
        #     quality_section = f"""
        #     <div style="margin-top: 15px; padding: 10px; background: #f8f9fa; border-radius: 5px;">
        #         <strong>이 기사의 품질:</strong> {quality_rating} {quality_emoji}
        #     </div>
        #     """

        return f"""
        <div class="meta">
            <h3>📝 요약</h3>
            {summary}
        </div>
        """

    def _generate_three_line_summary(self, article_data: Dict) -> str:
        """기사의 3줄 요약 생성"""
        try:
            # 기사 내용 추출
            article_content = article_data.get(
                "comprehensive_article", article_data.get("generated_article", "")
            )
            if not article_content:
                return None  # 요약을 생성할 수 없으면 None 반환

            # OpenAI API로 3줄 요약 생성
            prompt = f"""
다음 기사를 정확히 3줄로 요약해주세요.

요약 규칙:
1. 반드시 3개의 문장으로 작성 (더 많거나 적으면 안됨)
2. 각 문장은 핵심 정보를 담되, 너무 길지 않게
3. 첫 줄: 가장 중요한 핵심 사실
4. 둘 째 줄: 주요 세부사항이나 배경
5. 셋 째 줄: 영향이나 전망
6. 각 줄은 완전한 문장으로 작성
7. 불필요한 수식어나 감정적 표현 제거

반드시 다음 JSON 형식으로 응답하세요:
{{
    "line1": "첫 번째 요약 문장",
    "line2": "두 번째 요약 문장",
    "line3": "세 번째 요약 문장"
}}

기사 내용:
{article_content[:2000]}
"""

            # Rate limiting 적용
            self.rate_limiter.wait_if_needed()

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You must respond ONLY with valid JSON format. No other text or explanation."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=300,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "three_line_summary",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "line1": {
                                    "type": "string",
                                    "description": "첫 번째 요약 문장"
                                },
                                "line2": {
                                    "type": "string",
                                    "description": "두 번째 요약 문장"
                                },
                                "line3": {
                                    "type": "string",
                                    "description": "세 번째 요약 문장"
                                }
                            },
                            "required": ["line1", "line2", "line3"],
                            "additionalProperties": False
                        },
                        "strict": True
                    }
                }
            )

            # 토큰 사용량 추적
            if hasattr(self, "current_article_id"):
                self.token_tracker.track_api_call(
                    response,
                    self.model_name,
                    self.current_article_id,
                    getattr(self, "current_article_title", None),
                )

            summary = response.choices[0].message.content.strip()

            # JSON 응답 파싱
            try:
                import json
                summary_json = json.loads(summary)
                
                # JSON에서 3줄 추출
                cleaned_lines = [
                    summary_json.get("line1", ""),
                    summary_json.get("line2", ""),
                    summary_json.get("line3", "")
                ]
                
                # 빈 줄 체크
                cleaned_lines = [line.strip() for line in cleaned_lines if line.strip()]
                
                # 3줄이 안 되어도 있는 만큼만 사용
                    
            except (json.JSONDecodeError, ValueError) as e:
                # JSON 파싱 실패 시 기존 방식으로 폴백
                logger.warning(f"JSON 파싱 실패, 기존 방식으로 폴백: {e}")
                
                # 기존 방식: 줄바꿈으로 분리
                lines = summary.split("\n")
                lines = [line.strip() for line in lines if line.strip()]
                
                # 불필요한 번호나 마커 제거
                cleaned_lines = []
                for line in lines:
                    line = re.sub(r"^[\d]+\.\s*", "", line)
                    line = re.sub(r"^[-•]\s*", "", line)
                    if line.strip():
                        cleaned_lines.append(line.strip())
                
                # 3줄이 안 되어도 있는 만큼만 사용
                if len(cleaned_lines) == 0:
                    return "<p>요약을 생성할 수 없습니다.</p>"

            # HTML 형식으로 변환
            html_summary = ""
            for i, line in enumerate(cleaned_lines[:3]):
                html_summary += f'<p style="margin: 8px 0;"><strong>{i+1}.</strong> {line}</p>\n'

            return html_summary

        except Exception as e:
            logger.error(f"3줄 요약 생성 실패: {e}")
            return None  # 요약 생성 실패 시 None 반환

    def _convert_markdown_to_html(self, text: str) -> str:
        """마크다운 텍스트를 HTML로 변환"""
        
        # Markdown 라이브러리 설정
        # extensions:
        # - extra: 테이블, 코드 블록, 각주, 약어, 속성 리스트 등 추가 기능
        # - nl2br: 줄바꿈을 <br> 태그로 변환
        # - sane_lists: 더 나은 리스트 처리
        # - smarty: 스마트 따옴표, 대시 등
        md = markdown.Markdown(extensions=['extra', 'nl2br', 'sane_lists', 'smarty'])
        
        # 기사 제목 처리를 위한 전처리
        # 첫 번째 # 제목을 찾아서 h2로 변환하고 스타일 적용
        lines = text.split('\n')
        processed_lines = []
        article_title_found = False
        
        for line in lines:
            if line.startswith('# ') and not article_title_found:
                # 첫 번째 h1 제목은 건너뛰기 (이미 header에 표시됨)
                article_title_found = True
                continue  # 이 줄을 건너뛰고 다음 줄로
            else:
                processed_lines.append(line)
        
        # 다시 합치기
        processed_text = '\n'.join(processed_lines)
        
        # Markdown을 HTML로 변환
        html = md.convert(processed_text)
        
        # 후처리: 외부 링크에만 target="_blank" 추가
        # 내부 링크: /, #, /index.html, /article_xxx.html 등으로 시작하는 경우
        # 외부 링크: http://, https://, //로 시작하는 경우
        def add_target_blank(match):
            href = match.group(1)
            # 외부 링크인 경우에만 target="_blank" 추가
            if href.startswith(('http://', 'https://', '//')):
                return f'<a href="{href}" target="_blank">'
            else:
                return f'<a href="{href}">'
        
        html = re.sub(r'<a href="([^"]+)">', add_target_blank, html)
        
        # 후처리: 모든 h2를 h3로 변경 (첫 번째 제목을 제거했으므로)
        html = html.replace('<h2>', '<h3>').replace('</h2>', '</h3>')
        
        return html

    def _generate_html(
        self, article_data: Dict, related_count: int, is_update: bool = False
    ) -> str:
        """
        HTML 출력 생성
        
        기사 데이터를 바탕으로 완전한 HTML 페이지를 생성합니다.
        
        Args:
            article_data: 기사 데이터 디텍셔너리
            related_count: 관련 기사 수
            is_update: 업데이트된 기사인지 여부
            
        Returns:
            완전한 HTML 문서
        """

        # 기본 템플릿
        current_time = get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
        version_info = f"(버전 {article_data.get('version', 1)})" if is_update else ""

        # comprehensive_article에서 제목 추출
        # 1. 먼저 generated_title이 있는지 확인 (가장 우선순위)
        comprehensive_title = article_data.get('generated_title', None)
        
        # 2. generated_title이 없으면 comprehensive_article 내용에서 찾기
        if not comprehensive_title:
            comprehensive_content = article_data.get('comprehensive_article', '')
            if comprehensive_content:
                # 마크다운 형식에서 첫 번째 # 제목 찾기
                import re
                title_match = re.search(r'^#\s+(.+?)$', comprehensive_content, re.MULTILINE)
                if title_match:
                    comprehensive_title = title_match.group(1).strip()
        
        # 3. 여전히 제목을 찾지 못했다면 main_article 제목 사용 (폴백)
        if not comprehensive_title:
            comprehensive_title = article_data["main_article"]["title"]
        
        # 제목에서 독점 보도 표현 제거
        clean_title = self.sanitize_exclusive_terms(comprehensive_title)
        
        # 태그 정보 추출
        tags = article_data.get("tags", {})
        category_tags = tags.get("category_tags", [])
        content_tags = tags.get("content_tags", [])
        all_tags = category_tags + content_tags

        html_template = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{clean_title} - {current_time}</title>
    <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
    <link rel="alternate icon" href="/static/favicon.svg">
    <meta name="article-tags" content="{','.join(all_tags)}">{f'''
    <meta name="article-category-tags" content="{','.join(category_tags)}">''' if category_tags else ''}{f'''
    <meta name="article-content-tags" content="{','.join(content_tags)}">''' if content_tags else ''}
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
            line-height: 1.8;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .header {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 30px;
        }}
        .version-badge {{
            background: #17a2b8;
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            display: inline-block;
            font-weight: bold;
            margin-bottom: 10px;
        }}
        .update-info {{
            background: #d4edda;
            border: 1px solid #c3e6cb;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }}
        .article-content {{
            margin: 30px 0;
            font-size: 17px;
            line-height: 1.9;
        }}
        .article-content h3 {{
            font-size: 1.4rem;
            color: #333;
            margin: 30px 0 15px 0;
            padding-bottom: 10px;
            border-bottom: 2px solid #e9ecef;
        }}
        .article-content p {{
            margin: 15px 0;
            text-align: justify;
        }}
        .meta {{
            margin: 20px 0;
            padding: 15px;
            background: #e9ecef;
            border-radius: 8px;
        }}
        .version-history {{
            margin: 30px 0;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            border: 1px solid #dee2e6;
        }}
        .version-history h3 {{
            margin-top: 0;
            color: #495057;
            cursor: pointer;
            user-select: none;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .version-history h3:hover {{
            color: #343a40;
        }}
        .version-toggle {{
            font-size: 0.9em;
            color: #6c757d;
            transition: transform 0.3s ease;
        }}
        .version-toggle.open {{
            transform: rotate(180deg);
        }}
        .version-list {{
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease;
        }}
        .version-list.open {{
            max-height: 500px;
            overflow-y: auto;
        }}
        .version-item {{
            margin: 10px 0;
            padding: 10px;
            background: white;
            border-radius: 4px;
            border-left: 3px solid #17a2b8;
        }}
        .version-item.current {{
            border-left-color: #28a745;
            font-weight: bold;
        }}
        .version-date {{
            font-size: 14px;
            color: #6c757d;
        }}
        .sources-section {{
            margin-top: 40px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            border: 1px solid #dee2e6;
        }}
        .sources-section h4 {{
            margin: 0 0 10px 0;
            font-size: 1.1rem;
            color: #495057;
        }}
        .source-list {{
            margin: 5px 0;
            font-size: 0.9rem;
        }}
        .source-list a {{
            color: #1a73e8;
            text-decoration: none;
            margin-right: 10px;
        }}
        .source-list a:hover {{
            text-decoration: underline;
        }}
        
        /* Floating Action Button */
        .fab {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 56px;
            height: 56px;
            background: #0066cc;
            color: white;
            border-radius: 28px;
            border: none;
            box-shadow: 0 2px 10px rgba(0,102,204,0.3);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            text-decoration: none;
            font-size: 24px;
            transition: transform 0.2s, box-shadow 0.2s;
            z-index: 1000;
        }}
        
        .fab:hover {{
            transform: scale(1.1);
            box-shadow: 0 4px 20px rgba(0,102,204,0.4);
        }}
        
        /* Related Articles Section */
        .related-articles {{
            margin-top: 50px;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            border: 1px solid #dee2e6;
        }}
        
        .related-articles h3 {{
            margin: 0 0 20px 0;
            color: #495057;
            font-size: 1.3rem;
        }}
        
        .related-article-item {{
            padding: 15px;
            margin-bottom: 10px;
            background: white;
            border-radius: 4px;
            border-left: 3px solid #0066cc;
            transition: transform 0.2s;
        }}
        
        .related-article-item:hover {{
            transform: translateX(5px);
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
        
        .related-article-item a {{
            color: #333;
            text-decoration: none;
            font-weight: 500;
        }}
        
        .related-article-item a:hover {{
            color: #0066cc;
        }}
        
        .related-article-meta {{
            font-size: 0.85rem;
            color: #6c757d;
            margin-top: 5px;
        }}
        
        .loading-message {{
            text-align: center;
            color: #6c757d;
            padding: 20px;
        }}
        
        /* Mobile responsiveness */
        @media (max-width: 768px) {{
            .fab {{
                bottom: 70px;
                right: 15px;
            }}
        }}
    </style>
    <script>
        function toggleVersionHistory() {{
            const versionList = document.querySelector('.version-list');
            const toggleIcon = document.querySelector('.version-toggle');
            
            if (versionList.classList.contains('open')) {{
                versionList.classList.remove('open');
                toggleIcon.classList.remove('open');
            }} else {{
                versionList.classList.add('open');
                toggleIcon.classList.add('open');
            }}
        }}
        
        // Load related articles based on current filter state
        async function loadRelatedArticles() {{
            const relatedSection = document.getElementById('related-articles-list');
            // current_time 형식: 2025-07-24 02:00:29
            const [datePart, timePart] = '{current_time}'.split(' ');
            const [year, month, day] = datePart.split('-');
            const [hour, minute, second] = timePart.split(':');
            const currentDate = new Date(year, month-1, day, hour, minute, second);
            
            // console.log('Loading related articles...');
            // console.log('Current date:', currentDate);
            
            try {{
                // Get the current filter state from URL hash
                const hash = window.location.hash.slice(1);
                const filters = hash ? hash.split(',').map(tag => decodeURIComponent(tag)) : [];
                // console.log('Active filters:', filters);
                
                // Fetch the main index page to get all articles
                const response = await fetch('/index.html');
                const html = await response.text();
                const parser = new DOMParser();
                const doc = parser.parseFromString(html, 'text/html');
                
                // Find all article items
                const articles = doc.querySelectorAll('.article-card');
                //console.log('Found articles:', articles.length);
                const filteredArticles = [];
                
                articles.forEach(article => {{
                    const titleElement = article.querySelector('h2');
                    const title = titleElement?.textContent;
                    const link = article.getAttribute('href');
                    const dateElement = article.querySelector('.article-meta span');
                    const dateText = dateElement?.textContent?.replace('📅 ', '');
                    
                    // console.log('Processing article:', title, 'Date text:', dateText);
                    
                    // Skip the current article
                    if (title && title.includes('{clean_title}')) {{
                        // console.log('Skipping current article:', title);
                        return;
                    }}
                    
                    // Parse the article date
                    let articleDate = null;
                    if (dateText) {{
                        // 날짜 형식: "2025년 07월 24일 01:03"
                        const match = dateText.match(/(\\d{{4}})년\\s+(\\d{{2}})월\\s+(\\d{{2}})일\\s+(\\d{{2}}):(\\d{{2}})/);
                        if (match) {{
                            articleDate = new Date(match[1], match[2]-1, match[3], match[4], match[5]);
                            // console.log('Parsed date:', articleDate);
                        }} else {{
                            // console.log('Date regex did not match for:', dateText);
                        }}
                    }}
                    
                    // Skip if no date found
                    if (!articleDate) {{
                        // console.log('Skipping article - no date found');
                        return;
                    }}
                    
                    // 현재 기사보다 오래된 기사만 표시
                    if (articleDate >= currentDate) {{
                        // console.log('Skipping newer or same-time article:', title);
                        return;
                    }}
                    
                    // If filters are applied, check if article matches
                    if (filters.length > 0) {{
                        const tagsData = article.getAttribute('data-tags');
                        if (!tagsData) return;
                        
                        const articleTags = tagsData.split('|').filter(tag => tag);
                        
                        const hasMatchingTag = filters.some(filter => articleTags.includes(filter));
                        if (!hasMatchingTag) return;
                    }}
                    
                    // Add the article to the list
                    if (title && link && dateText) {{
                        filteredArticles.push({{
                            title: title,
                            link: link,
                            date: dateText,
                            timestamp: articleDate
                        }});
                    }}
                }});
                
                // Sort by date (newest first among older articles)
                filteredArticles.sort((a, b) => b.timestamp - a.timestamp);
                
                // Display up to 10 articles
                if (filteredArticles.length > 0) {{
                    // Clear existing content
                    relatedSection.innerHTML = '';
                    
                    // Create articles using DOM methods to avoid CSP issues
                    filteredArticles.slice(0, 10).forEach(article => {{
                        const itemDiv = document.createElement('div');
                        itemDiv.className = 'related-article-item';
                        
                        const link = document.createElement('a');
                        link.href = article.link;
                        link.textContent = article.title;
                        
                        const metaDiv = document.createElement('div');
                        metaDiv.className = 'related-article-meta';
                        metaDiv.textContent = article.date;
                        
                        itemDiv.appendChild(link);
                        itemDiv.appendChild(metaDiv);
                        relatedSection.appendChild(itemDiv);
                    }});
                }} else {{
                    const message = document.createElement('p');
                    message.className = 'loading-message';
                    if (filters.length > 0) {{
                        message.textContent = '선택한 필터에 해당하는 이전 기사가 없습니다.';
                    }} else {{
                        message.textContent = '이전 기사가 없습니다.';
                    }}
                    relatedSection.innerHTML = '';
                    relatedSection.appendChild(message);
                }}
                
            }} catch (error) {{
                console.error('Error loading related articles:', error);
                const errorMessage = document.createElement('p');
                errorMessage.className = 'loading-message';
                errorMessage.textContent = '기사 목록을 불러올 수 없습니다.';
                relatedSection.innerHTML = '';
                relatedSection.appendChild(errorMessage);
            }}
        }}
        
        // Load related articles when page loads
        document.addEventListener('DOMContentLoaded', loadRelatedArticles);
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{clean_title}</h1>
            <p>
                분석 시간: {current_time}
                {f' <span style="font-size: 0.85rem; color: #17a2b8; margin-left: 15px;">✅ 버전 {article_data.get("version", 1)} (업데이트됨)</span>' if is_update else ''}
            </p>
        </div>
        
        {self._generate_summary_section(article_data)}
        
        {self._generate_ai_image_section(article_data)}
        
        <div class="article-content">
{self._convert_markdown_to_html(article_data.get('comprehensive_article', article_data.get('generated_article', '')))}
        </div>
        
        {self._generate_version_history_html(article_data.get('version_history', []))}
        
        {self._generate_sources_section(article_data)}
        
        <!-- Related Articles Section -->
        <div class="related-articles">
            <h3>📰 다른 기사</h3>
            <div id="related-articles-list">
                <p class="loading-message">기사 목록을 불러오는 중...</p>
            </div>
        </div>
        
        <hr>
        <p><small>이 기사는 AI가 자동으로 생성하고 관리하는 스마트 기사입니다.</small></p>
    </div>
    
    <!-- Floating Home Button -->
    <a href="/index.html" class="fab" title="홈으로">🏠</a>
</body>
</html>"""

        return html_template

    def _generate_version_history_html(self, version_history: List[Dict]) -> str:
        """버전 히스토리 HTML 생성"""
        if not version_history or len(version_history) <= 1:
            return ""  # 버전이 하나뿐이면 히스토리 표시 안 함

        html = """
        <div class="version-history">
            <h3 onclick="toggleVersionHistory()">
                <span>📚 기사 업데이트 히스토리</span>
                <span class="version-toggle">▼</span>
            </h3>
            <div class="version-list">
                <p style="font-size: 14px; color: #6c757d; margin: 15px 0;">
                    이 주제에 대한 기사가 시간에 따라 어떻게 업데이트되었는지 확인하세요.
                </p>
        """

        # 버전을 최신순으로 정렬
        sorted_history = sorted(version_history, key=lambda x: x["version"], reverse=True)

        for version_info in sorted_history:
            is_current = version_info.get("is_current", False)
            version_class = "version-item current" if is_current else "version-item"

            # 날짜 포맷팅
            created_at = version_info.get("created_at", "")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at)
                    formatted_date = dt.strftime("%Y년 %m월 %d일 %H:%M")
                except Exception as e:
                    logger.debug(f"Date formatting failed: {e}")
                    formatted_date = created_at
            else:
                formatted_date = "날짜 정보 없음"

            # 버전 파일 링크 생성
            article_id = version_info.get("article_id", "")
            version_num = version_info.get("version", "?")
            version_link = f"versions/article_{article_id}_v{version_num}.html"

            html += f"""
            <div class="{version_class}">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <a href="{version_link}" target="_blank" style="text-decoration: none; color: inherit;">
                            <strong>버전 {version_num}</strong>
                        </a>
                        {' (현재)' if is_current else ''}
                    </div>
                    <div class="version-date">{formatted_date}</div>
                </div>
                {f'<div style="margin-top: 5px; font-size: 14px;">{version_info.get("title", "")}</div>' if version_info.get('title') else ''}
                <div style="margin-top: 5px; font-size: 13px;">
                    <a href="{version_link}" target="_blank" style="color: #1a73e8; text-decoration: none;">
                        이 버전 보기 →
                    </a>
                </div>
            </div>
            """

        html += """
            </div>
        </div>
        """

        return html

    def _generate_ai_image_section(self, article_data: Dict) -> str:
        """AI 생성 이미지 섹션 생성"""
        # 생성된 이미지가 없으면 빈 문자열 반환
        image_path = article_data.get("generated_image_path")
        if not image_path:
            return ""
        
        # 이미지 경로를 웹 경로로 변환
        web_image_path = f"/{image_path}"
        
        article_title = article_data.get("main_article", {}).get("title", "뉴스 이미지")
        
        ai_image_section = f"""
        <div class="ai-image-section" style="margin: 30px 0;">
            <div style="position: relative; overflow: hidden; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <img src="{web_image_path}" 
                     alt="{article_title}" 
                     style="width: 100%; height: auto; display: block; max-height: 500px; object-fit: cover;"
                     loading="lazy">
                <div style="position: absolute; top: 10px; left: 10px; background: rgba(0,0,0,0.8); color: white; padding: 5px 10px; border-radius: 4px; font-size: 0.85rem;">
                    🎨 AI 생성 이미지
                </div>
            </div>
            <div style="margin-top: 10px; padding: 15px; background: #f8f9fa; border-radius: 8px;">
                <p style="margin: 0; font-size: 0.85rem; color: #666;">
                    ※ 이 이미지는 기사 내용을 바탕으로 AI가 생성한 이미지입니다.
                </p>
            </div>
        </div>
        """
        
        return ai_image_section

    def _generate_sources_section(self, article_data: Dict) -> str:
        """참조 소스 섹션 HTML 생성 (메타데이터 포함)"""
        sources_html = ""
        has_sources = False

        # 소스 섹션 시작
        sources_html += """
        <div class="sources-section">"""
        has_sources = True

        # YouTube 정보가 있는 경우
        if "youtube_videos" in article_data and article_data["youtube_videos"]:
            sources_html += """
            <h4>🎥 참조한 YouTube 영상</h4>
            <div class="source-list">"""

            for video in article_data["youtube_videos"][:5]:  # 최대 5개
                title = video.get("title", "")
                link = video.get("link", video.get("url", ""))  # link 또는 url 키 사용
                if title and link:
                    # 제목이 너무 길면 줄임
                    display_title = title[:30] + "..." if len(title) > 30 else title
                    sources_html += f'<a href="{link}" target="_blank">{display_title}</a>'

            sources_html += """
            </div>"""

        # 추가 참조 정보 (관련 기사 + Google 검색 정보 통합)
        all_references = []
        
        # 관련 기사 정보가 있는 경우
        if "related_articles" in article_data and article_data["related_articles"]:
            for article in article_data["related_articles"][:10]:  # 최대 10개
                title = article.get("title", "")
                link = article.get("link", article.get("url", ""))
                if title and link:
                    all_references.append({"title": title, "link": link})
        
        # Google 검색 정보가 있는 경우
        if "google_articles" in article_data and article_data["google_articles"]:
            for result in article_data["google_articles"][:5]:  # 최대 5개
                title = result.get("title", "")
                link = result.get("link", result.get("url", ""))  # link 또는 url 키 사용
                if title and link:
                    all_references.append({"title": title, "link": link})
        
        # 모든 참조 정보 출력
        if all_references:
            sources_html += """
            <h4 style="margin-top: 15px;">🔍 추가 참조 정보</h4>
            <div class="source-list">"""
            
            for ref in all_references:
                display_title = ref["title"][:30] + "..." if len(ref["title"]) > 30 else ref["title"]
                sources_html += f'<a href="{ref["link"]}" target="_blank">{display_title}</a>'
                
            sources_html += """
            </div>"""

        if has_sources:
            sources_html += """
        </div>"""

        return sources_html

    def get_cached_topics(self) -> List[Dict]:
        """캐시된 주제 목록 반환"""
        return self.cache_manager.get_topic_summary()


def test_smart_generator():
    """스마트 기사 생성 테스트"""

    generator = SmartArticleGenerator()

    # 1위 뉴스에 대한 기사 생성/업데이트
    result = generator.generate_or_update_article(rank=1)

    if result:
        print(f"\n결과: {result['status']}")
        print(f"메시지: {result['message']}")
        print(f"주제 ID: {result.get('topic_id')}")
        print(f"버전: {result.get('version')}")

        if result["status"] == "reused":
            print("→ 기존 기사를 재사용했습니다.")
        elif result["status"] == "updated":
            print("→ 새로운 정보로 기사를 업데이트했습니다.")
            print(f"   업데이트 내용: {result.get('updates')}")
        elif result["status"] == "created":
            print("→ 완전히 새로운 기사를 생성했습니다.")

    # 캐시된 주제 목록
    print("\n=== 캐시된 주제 목록 ===")
    topics = generator.get_cached_topics()
    for topic in topics[:5]:  # 상위 5개만
        print(f"- {topic['title']} (v{topic['version']})")


def regenerate_html_for_cached_articles():
    """캐시된 기사들의 HTML을 재생성 (버전별 파일 포함)"""

    generator = SmartArticleGenerator()
    cache_dir = "cache/articles"
    output_dir = "output/smart_articles"

    # 버전 디렉토리 생성
    os.makedirs(f"{output_dir}/versions", exist_ok=True)

    # 캐시 디렉토리의 모든 JSON 파일 읽기
    for filename in os.listdir(cache_dir):
        if filename.endswith(".json"):
            filepath = os.path.join(cache_dir, filename)

            # 캐시 파일 읽기
            with open(filepath, "r", encoding="utf-8") as f:
                article_data = json.load(f)

            # 메타데이터 추가 (analysis result에서 가져옴)
            if "analysis" in article_data and isinstance(article_data["analysis"], dict):
                # YouTube와 Google 정보 확인
                if "youtube_context" in article_data["analysis"]:
                    article_data["youtube_videos"] = article_data["analysis"]["youtube_context"]
                if "google_context" in article_data["analysis"]:
                    article_data["google_articles"] = article_data["analysis"]["google_context"]

            # 파일명 생성 (topic_id 기반)
            topic_id = article_data.get("topic_id", filename.replace(".json", ""))
            version = article_data.get("version", 1)

            # 버전 히스토리 확인
            version_history = article_data.get("version_history", [])
            if version_history:
                # 모든 버전에 대해 HTML 생성
                for version_info in version_history:
                    if version_info.get("article_id") == topic_id:
                        # 현재 버전
                        html_output = generator._generate_html(
                            article_data,
                            article_data.get("related_articles_count", 1),
                            is_update=version > 1,
                        )

                        # 버전별 파일 저장
                        version_filename = f"article_{topic_id}_v{version}.html"
                        version_path = f"{output_dir}/versions/{version_filename}"

                        with open(version_path, "w", encoding="utf-8") as f:
                            f.write(html_output)

                        print(f"버전 HTML 생성: {version_path}")
            else:
                # 버전 히스토리가 없는 경우 (구 버전)
                html_output = generator._generate_html(
                    article_data,
                    article_data.get("related_articles_count", 1),
                    is_update=version > 1,
                )

                # 현재 버전만 저장
                version_filename = f"article_{topic_id}_v{version}.html"
                version_path = f"{output_dir}/versions/{version_filename}"

                with open(version_path, "w", encoding="utf-8") as f:
                    f.write(html_output)

                print(f"버전 HTML 생성: {version_path}")


def generate_top_articles(start_rank: int = 1, end_rank: int = 5):
    """1~5위 기사 일괄 생성 (중복 방지)"""

    generator = SmartArticleGenerator()
    results = generator.generate_multiple_articles(start_rank=start_rank, end_rank=end_rank)

    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "--multiple" or sys.argv[1] == "all":
            # 1~5위 일괄 생성
            generate_top_articles(start_rank=1, end_rank=5)
        else:
            # 개별 순위 지정 (예: python smart_article_generator.py 1 3 5)
            try:
                ranks = [int(arg) for arg in sys.argv[1:]]
                generator = SmartArticleGenerator()
                
                logger.info(f"지정된 순위 기사 생성: {ranks}")
                
                for rank in ranks:
                    if 1 <= rank <= 10:  # 1~10위만 허용
                        logger.info(f"\n{'='*50}")
                        logger.info(f"{rank}위 기사 생성 시작")
                        logger.info(f"{'='*50}")
                        
                        result = generator.generate_or_update_article(rank=rank)
                        
                        if result:
                            logger.info(f"{rank}위 기사 생성 성공")
                        else:
                            logger.error(f"{rank}위 기사 생성 실패")
                    else:
                        logger.warning(f"잘못된 순위: {rank} (1~10 사이여야 함)")
                        
            except ValueError:
                logger.error("잘못된 입력: 순위는 숫자여야 합니다")
                print("사용법:")
                print("  python smart_article_generator.py         # 1위 기사만")
                print("  python smart_article_generator.py all  # 1~5위 모두")
                print("  python smart_article_generator.py 1 3 5    # 1, 3, 5위만")
    else:
        # 기본: 1위만 생성 (기존 동작)
        generate_top_articles(start_rank=1, end_rank=1)
