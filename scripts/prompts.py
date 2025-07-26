#!/usr/bin/env python3
"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

"""
AI prompts for Korean news article generation
"""

# System prompts for different AI models
SYSTEM_PROMPTS = {
    "claude": """당신은 한국의 전문 뉴스 기자입니다. 한국 독자를 위해 정확하고 공정하며 읽기 쉬운 한국어 뉴스 기사를 작성합니다.

다음 원칙을 따라주세요:
1. 사실에 기반한 정확한 보도
2. 중립적이고 균형잡힌 시각
3. 명확하고 간결한 한국어 문장
4. 출처를 명확히 표시
5. 한국 독자의 관심사와 문화적 맥락 고려""",
    
    "gpt4": """You are a professional Korean news journalist. Write accurate, fair, and easy-to-read Korean news articles for Korean readers.

Follow these principles:
1. Fact-based accurate reporting
2. Neutral and balanced perspective
3. Clear and concise Korean sentences
4. Clearly indicate sources
5. Consider Korean readers' interests and cultural context"""
}

# Article generation prompt template
ARTICLE_GENERATION_PROMPT = """다음 뉴스 정보를 바탕으로 한국 독자를 위한 뉴스 기사를 작성해주세요.

## 주요 뉴스 정보:
{news_summary}

## 관련 소스:
{sources}

## 작성 지침:
1. 제목: 독자의 관심을 끄는 명확한 제목 (30자 이내)
2. 리드문: 핵심 내용을 요약한 첫 문단
3. 본문: 5W1H를 포함한 상세 내용 (500-800자)
4. 결론: 사건의 의미나 향후 전망
5. 출처 표시: 각 정보의 출처를 명시

## 추가 요구사항:
- 한국 독자가 이해하기 쉬운 문체 사용
- 전문 용어는 쉽게 설명
- 한국의 상황과 연관지어 설명
- 객관적이고 중립적인 톤 유지

## 출력 형식:
```json
{{
  "title": "기사 제목",
  "subtitle": "부제목 (선택사항)",
  "lead": "리드문",
  "body": "본문 내용",
  "conclusion": "결론",
  "sources": ["출처1", "출처2"],
  "category": "카테고리",
  "tags": ["태그1", "태그2"]
}}
```"""

# Fact-checking prompt
FACT_CHECK_PROMPT = """다음 뉴스 기사의 사실을 검증해주세요.

## 기사 내용:
{article_content}

## 원본 소스:
{original_sources}

## 검증 항목:
1. 주요 사실의 정확성
2. 인용문의 정확성
3. 숫자와 통계의 정확성
4. 시간과 장소의 정확성
5. 교차 검증 가능한 정보 확인

## 출력 형식:
```json
{{
  "accuracy_score": 0-100,
  "verified_facts": ["검증된 사실1", "검증된 사실2"],
  "unverified_claims": ["미검증 주장1", "미검증 주장2"],
  "corrections_needed": ["수정 필요 사항1", "수정 필요 사항2"],
  "additional_sources_needed": ["추가 확인 필요 소스1"]
}}
```"""

# Title optimization prompt
TITLE_OPTIMIZATION_PROMPT = """다음 기사에 대해 한국 독자의 관심을 끄는 제목을 만들어주세요.

## 기사 요약:
{article_summary}

## 제목 요구사항:
1. 30자 이내
2. 핵심 내용 포함
3. 클릭을 유도하되 선정적이지 않게
4. 명확하고 구체적
5. 한국어 제목 작성 관례 준수

## 출력:
5개의 제목 후보를 제시해주세요."""

# Summary generation prompt
SUMMARY_GENERATION_PROMPT = """다음 뉴스 기사를 한국 독자를 위해 요약해주세요.

## 원문:
{article_text}

## 요약 지침:
1. 3-5문장으로 요약
2. 핵심 정보만 포함
3. 시간 순서대로 정리
4. 중요한 인물, 장소, 숫자 포함

## 출력:
간결하고 명확한 요약문을 작성해주세요."""

# Cross-validation prompt
CROSS_VALIDATION_PROMPT = """다음 여러 출처의 뉴스를 비교 분석해주세요.

## 뉴스 소스들:
{news_sources}

## 분석 항목:
1. 공통된 핵심 사실
2. 출처별 차이점
3. 상충되는 정보
4. 가장 신뢰할 수 있는 정보
5. 추가 확인이 필요한 사항

## 출력 형식:
```json
{
  "common_facts": ["공통 사실1", "공통 사실2"],
  "discrepancies": [
    {"topic": "주제", "source1": "출처1 주장", "source2": "출처2 주장"}
  ],
  "reliability_assessment": {"most_reliable": "출처명", "reason": "이유"},
  "needs_verification": ["확인 필요 사항1"]
}
```"""


def get_prompt(prompt_type: str, **kwargs) -> str:
    """Get formatted prompt based on type and parameters"""
    prompts = {
        "article_generation": ARTICLE_GENERATION_PROMPT,
        "fact_check": FACT_CHECK_PROMPT,
        "title_optimization": TITLE_OPTIMIZATION_PROMPT,
        "summary": SUMMARY_GENERATION_PROMPT,
        "cross_validation": CROSS_VALIDATION_PROMPT
    }
    
    prompt_template = prompts.get(prompt_type)
    if not prompt_template:
        raise ValueError(f"Unknown prompt type: {prompt_type}")
    
    return prompt_template.format(**kwargs)