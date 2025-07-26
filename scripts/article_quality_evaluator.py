"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

"""
기사 품질 평가 시스템
betterNews 스타일의 품질 평가 기준을 적용하여
생성된 기사의 품질을 High/Medium/Low로 평가
"""

import logging
import re
from typing import Dict, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class ArticleQualityEvaluator:
    """기사 품질 평가기"""
    
    def __init__(self):
        # 평가 기준 정의
        self.quality_criteria = {
            "High": {
                "description": "단순한 정보 전달 뿐만 아니라, 해당 정보에 대한 평가를 제공하며, 그 평가가 도출된 근거를 제시",
                "emoji": "😊",
                "min_score": 0.7
            },
            "Medium": {
                "description": "단순한 정보를 전달한 뿐, 해당 정보에 대한 평가가 없거나, 평가가 있어도 그 평가가 도출된 근거가 부족",
                "emoji": "😐",
                "min_score": 0.4
            },
            "Low": {
                "description": "정보 전달에 있어서도 출처가 불명확하여 해당 정보의 사실 여부를 확인하기 어렵거나, 해당 정보를 잘못된 방법으로 해석",
                "emoji": "☹️",
                "min_score": 0.0
            }
        }
        
        # 모호한 출처 표현 패턴
        self.vague_source_patterns = [
            r"한\s*관계자",
            r"정통한\s*소식통",
            r"익명의?\s*관계자",
            r"소식통",
            r"관계자",
            r"알려진\s*바에?\s*따르면",
            r"전해진다",
            r"알려졌다",
            r"~것으로\s*보인다",
            r"~것으로\s*추정된다"
        ]
        
        # 구체적 출처 표현 패턴
        self.specific_source_patterns = [
            r"\[.+\]\(.+\)",  # 마크다운 링크
            r"에\s*따르면",
            r"발표",
            r"보도",
            r"밝혔다",
            r"전했다",
            r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일",  # 구체적 날짜
            r"공식",
            r"성명",
            r"인터뷰"
        ]
    
    def evaluate_article(self, article: Dict[str, any]) -> Tuple[str, str, Dict]:
        """
        기사 품질 평가
        
        Args:
            article: 평가할 기사 데이터
            
        Returns:
            (품질 등급, 이모지, 상세 평가 결과)
        """
        scores = {
            "evidence_quality": self._check_evidence_quality(article),
            "source_transparency": self._check_source_transparency(article),
            "balance_and_objectivity": self._check_balance(article),
            "fact_verification": self._check_fact_verification(article),
            "analysis_depth": self._check_analysis_depth(article)
        }
        
        # 전체 점수 계산 (가중평균)
        weights = {
            "evidence_quality": 0.25,
            "source_transparency": 0.25,
            "balance_and_objectivity": 0.20,
            "fact_verification": 0.20,
            "analysis_depth": 0.10
        }
        
        total_score = sum(scores[key] * weights[key] for key in scores)
        
        # 품질 등급 결정
        quality_rating = self._determine_quality_rating(total_score)
        emoji = self.quality_criteria[quality_rating]["emoji"]
        
        # 상세 평가 결과
        evaluation_details = {
            "quality_rating": quality_rating,
            "emoji": emoji,
            "total_score": round(total_score, 2),
            "scores": scores,
            "strengths": self._identify_strengths(scores),
            "weaknesses": self._identify_weaknesses(scores),
            "recommendations": self._generate_recommendations(scores)
        }
        
        return quality_rating, emoji, evaluation_details
    
    def _check_evidence_quality(self, article: Dict) -> float:
        """증거 품질 평가"""
        content = article.get("comprehensive_article", article.get("generated_article", ""))
        if not content:
            return 0.0
        
        score = 0.0
        
        # 구체적 증거 확인
        evidence_indicators = [
            (r"\d+[%％]", 0.1),  # 백분율
            (r"\d+[명억만천]", 0.1),  # 수치
            (r"조사\s*결과", 0.15),  # 조사 결과
            (r"보고서", 0.15),  # 보고서
            (r"통계", 0.1),  # 통계
            (r"연구", 0.1),  # 연구
            (r"발표", 0.1),  # 발표
            (r"공식", 0.1),  # 공식
            (r"문서", 0.1),  # 문서
        ]
        
        for pattern, weight in evidence_indicators:
            if re.search(pattern, content):
                score += weight
        
        return min(score, 1.0)
    
    def _check_source_transparency(self, article: Dict) -> float:
        """출처 투명성 평가"""
        content = article.get("comprehensive_article", article.get("generated_article", ""))
        if not content:
            return 0.0
        
        # 모호한 출처 카운트
        vague_count = sum(1 for pattern in self.vague_source_patterns 
                         if re.search(pattern, content))
        
        # 구체적 출처 카운트
        specific_count = sum(1 for pattern in self.specific_source_patterns 
                           if re.search(pattern, content))
        
        # 마크다운 링크 개수
        link_count = len(re.findall(r"\[.+?\]\(.+?\)", content))
        
        # 점수 계산
        if specific_count + link_count == 0:
            return 0.0
        
        transparency_ratio = (specific_count + link_count * 2) / (specific_count + link_count + vague_count)
        return min(transparency_ratio, 1.0)
    
    def _check_balance(self, article: Dict) -> float:
        """균형성과 객관성 평가"""
        content = article.get("comprehensive_article", article.get("generated_article", ""))
        if not content:
            return 0.0
        
        score = 0.0
        
        # 다양한 관점 표현 확인
        balance_indicators = [
            (r"한편", 0.15),
            (r"반면", 0.15),
            (r"그러나", 0.1),
            (r"다만", 0.1),
            (r"찬성", 0.1),
            (r"반대", 0.1),
            (r"긍정", 0.1),
            (r"부정", 0.1),
            (r"전문가", 0.1),
        ]
        
        for pattern, weight in balance_indicators:
            if re.search(pattern, content):
                score += weight
        
        return min(score, 1.0)
    
    def _check_fact_verification(self, article: Dict) -> float:
        """사실 검증 가능성 평가"""
        content = article.get("comprehensive_article", article.get("generated_article", ""))
        if not content:
            return 0.0
        
        score = 0.0
        
        # 검증 가능한 사실 표현
        verification_indicators = [
            (r"확인됐다", 0.2),
            (r"검증", 0.2),
            (r"사실", 0.1),
            (r"공식\s*확인", 0.2),
            (r"증명", 0.1),
            (r"입증", 0.1),
            (r"밝혀졌다", 0.1),
        ]
        
        for pattern, weight in verification_indicators:
            if re.search(pattern, content):
                score += weight
        
        # 링크가 있으면 추가 점수
        link_count = len(re.findall(r"\[.+?\]\(.+?\)", content))
        score += min(link_count * 0.05, 0.3)
        
        return min(score, 1.0)
    
    def _check_analysis_depth(self, article: Dict) -> float:
        """분석 깊이 평가"""
        content = article.get("comprehensive_article", article.get("generated_article", ""))
        if not content:
            return 0.0
        
        # 기사 길이 (분석 깊이의 기본 지표)
        word_count = len(content.split())
        length_score = min(word_count / 1000, 0.5)  # 1000단어 기준
        
        # 분석적 표현
        analysis_indicators = [
            (r"분석", 0.1),
            (r"평가", 0.1),
            (r"의미", 0.1),
            (r"영향", 0.1),
            (r"전망", 0.1),
            (r"시사점", 0.1),
            (r"배경", 0.1),
            (r"원인", 0.1),
            (r"결과", 0.1),
        ]
        
        analysis_score = 0.0
        for pattern, weight in analysis_indicators:
            if re.search(pattern, content):
                analysis_score += weight
        
        return min(length_score + analysis_score * 0.5, 1.0)
    
    def _determine_quality_rating(self, score: float) -> str:
        """점수에 따른 품질 등급 결정"""
        if score >= self.quality_criteria["High"]["min_score"]:
            return "High"
        elif score >= self.quality_criteria["Medium"]["min_score"]:
            return "Medium"
        else:
            return "Low"
    
    def _identify_strengths(self, scores: Dict[str, float]) -> List[str]:
        """강점 식별"""
        strengths = []
        
        if scores["evidence_quality"] >= 0.7:
            strengths.append("구체적인 증거와 수치 제시")
        if scores["source_transparency"] >= 0.7:
            strengths.append("명확한 출처 표시")
        if scores["balance_and_objectivity"] >= 0.7:
            strengths.append("균형잡힌 관점 제시")
        if scores["fact_verification"] >= 0.7:
            strengths.append("검증 가능한 사실 위주")
        if scores["analysis_depth"] >= 0.7:
            strengths.append("심층적인 분석 포함")
        
        return strengths
    
    def _identify_weaknesses(self, scores: Dict[str, float]) -> List[str]:
        """약점 식별"""
        weaknesses = []
        
        if scores["evidence_quality"] < 0.4:
            weaknesses.append("구체적 증거 부족")
        if scores["source_transparency"] < 0.4:
            weaknesses.append("모호한 출처 표현 과다")
        if scores["balance_and_objectivity"] < 0.4:
            weaknesses.append("편향된 시각")
        if scores["fact_verification"] < 0.4:
            weaknesses.append("검증되지 않은 주장 포함")
        if scores["analysis_depth"] < 0.4:
            weaknesses.append("피상적인 정보 전달")
        
        return weaknesses
    
    def _generate_recommendations(self, scores: Dict[str, float]) -> List[str]:
        """개선 권고사항 생성"""
        recommendations = []
        
        if scores["evidence_quality"] < 0.6:
            recommendations.append("더 많은 통계, 연구 결과, 공식 발표 인용 필요")
        if scores["source_transparency"] < 0.6:
            recommendations.append("익명 출처보다 실명 출처 활용 권장")
        if scores["balance_and_objectivity"] < 0.6:
            recommendations.append("다양한 이해관계자의 입장 포함 필요")
        if scores["fact_verification"] < 0.6:
            recommendations.append("주장에 대한 근거 자료 링크 추가 필요")
        if scores["analysis_depth"] < 0.6:
            recommendations.append("단순 사실 전달을 넘어 의미와 영향 분석 필요")
        
        return recommendations