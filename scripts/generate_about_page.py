#!/usr/bin/env python3
"""
KONA 소개 페이지 생성 스크립트
"""

import os
from datetime import datetime
from pathlib import Path

def generate_about_page():
    """KONA 소개 페이지 생성"""
    
    html_content = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KONA란? - Korean News by AI</title>
    <link rel="icon" type="image/svg+xml" href="static/favicon.svg">
    <style>
        :root {
            --primary-color: #1a73e8;
            --text-color: #202124;
            --bg-color: #f8f9fa;
            --card-bg: #ffffff;
            --border-color: #dadce0;
            --accent-color: #ea4335;
        }
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, sans-serif;
            line-height: 1.6;
            color: var(--text-color);
            background: var(--bg-color);
        }
        .container {
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        header {
            background: var(--card-bg);
            border-bottom: 1px solid var(--border-color);
            padding: 20px 0;
            margin-bottom: 40px;
        }
        h1 {
            color: var(--primary-color);
            font-size: 2.5rem;
            margin: 0;
        }
        h1 a {
            color: inherit;
            text-decoration: none;
        }
        .header-content {
            display: flex;
            align-items: center;
            gap: 20px;
        }
        .tagline {
            margin: 0;
            line-height: 1.3;
        }
        .tagline div:first-child {
            color: #5f6368;
            font-size: 1.1rem;
        }
        .tagline div:last-child {
            color: #5f6368;
            font-size: 0.95rem;
            margin-top: 2px;
        }
        .back-btn {
            display: inline-block;
            padding: 8px 16px;
            background: var(--primary-color);
            color: white;
            text-decoration: none;
            border-radius: 20px;
            font-size: 14px;
            margin-bottom: 30px;
            transition: background 0.3s;
        }
        .back-btn:hover {
            background: #1557b0;
        }
        .section {
            background: var(--card-bg);
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 30px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        h2 {
            color: var(--primary-color);
            font-size: 1.8rem;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid var(--border-color);
        }
        h3 {
            color: var(--text-color);
            font-size: 1.3rem;
            margin: 20px 0 10px 0;
        }
        p {
            margin-bottom: 15px;
            line-height: 1.8;
        }
        ul {
            margin: 15px 0;
            padding-left: 30px;
        }
        li {
            margin-bottom: 10px;
            line-height: 1.8;
        }
        .highlight {
            background: #e8f0fe;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid var(--primary-color);
        }
        .problem-box {
            background: #fce8e6;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid var(--accent-color);
        }
        .solution-box {
            background: #e6f4ea;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid #34a853;
        }
        .feature-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }
        .feature-card {
            background: var(--bg-color);
            padding: 20px;
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }
        .feature-card h4 {
            color: var(--primary-color);
            margin-bottom: 10px;
        }
        .icon {
            font-size: 2rem;
            margin-bottom: 10px;
        }
        footer {
            text-align: center;
            padding: 40px 20px;
            color: #5f6368;
            border-top: 1px solid var(--border-color);
            margin-top: 60px;
        }
    </style>
</head>
<body>
    <header>
        <div class="container">
            <div class="header-content">
                <h1><a href="index.html">KONA</a></h1>
                <div class="tagline">
                    <div>Korean News by AI</div>
                    <div>AI가 만드는 투명한 한국 뉴스</div>
                </div>
            </div>
        </div>
    </header>

    <div class="container">
        <a href="index.html" class="back-btn">← 메인으로 돌아가기</a>

        <section class="section">
            <h2>KONA란 무엇인가요?</h2>
            <p>KONA(Korean News by AI)는 인공지능 기술을 활용하여 보다 투명하고 객관적인 한국 뉴스를 제공하는 프로젝트입니다. 우리는 AI의 힘을 빌려 한국 언론의 고질적인 문제들을 해결하고, 독자들에게 더 나은 뉴스 경험을 제공하고자 합니다.</p>
            
            <div class="highlight">
                <p><strong>우리의 미션:</strong> AI 기술을 통해 사실 중심의 투명한 뉴스를 제공하여, 독자들이 편향되지 않은 정보를 바탕으로 올바른 판단을 내릴 수 있도록 돕습니다.</p>
            </div>
        </section>

        <section class="section">
            <h2>1. 현재 한국 언론의 문제점</h2>
            
            <div class="problem-box">
                <h3>🚨 클릭베이트와 선정주의</h3>
                <p>많은 언론사들이 클릭 수를 늘리기 위해 자극적이고 선정적인 제목을 사용합니다. 실제 기사 내용과 동떨어진 제목으로 독자를 현혹시키는 일이 빈번합니다.</p>
            </div>

            <div class="problem-box">
                <h3>📰 정치적 편향과 진영 논리</h3>
                <p>대부분의 주요 언론사들이 특정 정치 성향을 띠고 있어, 같은 사건도 언론사에 따라 전혀 다르게 보도됩니다. 독자들은 객관적인 사실보다는 편향된 시각에 노출됩니다.</p>
            </div>

            <div class="problem-box">
                <h3>💰 광고주 영향과 상업주의</h3>
                <p>광고 수익에 의존하는 구조로 인해, 광고주의 이익에 반하는 내용은 보도되지 않거나 축소됩니다. 진실보다 수익이 우선시되는 경우가 많습니다.</p>
            </div>

            <div class="problem-box">
                <h3>📋 보도자료 의존과 검증 부족</h3>
                <p>시간과 인력 부족으로 인해 기업이나 정부의 보도자료를 그대로 옮겨 적는 '받아쓰기 저널리즘'이 만연합니다. 심층 취재와 팩트체크가 부족합니다.</p>
            </div>
        </section>

        <section class="section">
            <h2>2. AI가 어떻게 개선할 수 있을까요?</h2>
            
            <div class="solution-box">
                <h3>🤖 편향 없는 데이터 분석</h3>
                <p>AI는 다양한 소스의 데이터를 종합적으로 분석하여, 특정 시각에 치우치지 않은 균형잡힌 관점을 제공할 수 있습니다. 여러 언론사의 보도를 교차 검증하여 사실을 추출합니다.</p>
            </div>

            <div class="solution-box">
                <h3>📊 팩트 기반 보도</h3>
                <p>AI는 감정이나 이해관계에 좌우되지 않고, 오직 데이터와 사실에 기반한 보도를 합니다. 숫자, 날짜, 인물 등 검증 가능한 정보를 중심으로 기사를 구성합니다.</p>
            </div>

            <div class="solution-box">
                <h3>🔍 광범위한 정보 수집</h3>
                <p>인간 기자가 제한된 시간 내에 확인할 수 없는 방대한 양의 정보를 AI는 순식간에 수집하고 분석할 수 있습니다. Wikipedia, YouTube, Google 검색 등 다양한 소스를 활용합니다.</p>
            </div>

            <div class="solution-box">
                <h3>⏱️ 24시간 실시간 모니터링</h3>
                <p>AI는 쉬지 않고 뉴스를 모니터링하며, 중요한 이슈를 놓치지 않습니다. 트렌드 변화를 실시간으로 감지하고 신속하게 보도할 수 있습니다.</p>
            </div>
        </section>

        <section class="section">
            <h2>3. KONA의 특징</h2>
            
            <div class="feature-grid">
                <div class="feature-card">
                    <div class="icon">🚫</div>
                    <h4>제목 낚시질 않음</h4>
                    <p>자극적인 제목으로 클릭을 유도하지 않습니다. 기사 내용을 정확히 반영하는 솔직한 제목을 사용합니다.</p>
                </div>

                <div class="feature-card">
                    <div class="icon">⚖️</div>
                    <h4>객관적 시각</h4>
                    <p>정치적 성향이나 이해관계에 좌우되지 않는 중립적이고 균형잡힌 보도를 추구합니다.</p>
                </div>

                <div class="feature-card">
                    <div class="icon">📊</div>
                    <h4>사실 중심 작성</h4>
                    <p>추측이나 의견보다는 검증 가능한 사실과 데이터를 중심으로 기사를 작성합니다.</p>
                </div>

                <div class="feature-card">
                    <div class="icon">🌐</div>
                    <h4>다양한 소스 활용</h4>
                    <p>네이버, 구글, 위키피디아, 유튜브 등 신뢰할 수 있는 다양한 소스에서 정보를 수집합니다.</p>
                </div>

                <div class="feature-card">
                    <div class="icon">🔍</div>
                    <h4>교차 검증</h4>
                    <p>여러 출처의 정보를 교차 검증하여 정확성을 높이고, 단일 소스 의존을 방지합니다.</p>
                </div>

            </div>

        </section>

        <section class="section">
            <h2>우리의 비전</h2>
            <p>우리는 AI가 인간 기자를 대체하는 것이 아니라, 더 나은 저널리즘을 위한 도구가 될 수 있다고 믿습니다. KONA를 통해 한국의 뉴스 환경이 조금 더 건강해지기를 희망합니다.</p>
        </section>
    </div>

    <footer>
        <a href="index.html" class="back-btn" style="margin-bottom: 30px;">← 메인으로 돌아가기</a>
        <p>&copy; 2025 KONA Project. AI로 만드는 투명한 한국 뉴스.</p>
    </footer>
</body>
</html>"""

    # output 디렉토리 생성
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    
    # about.html 파일 저장
    output_file = output_dir / "about.html"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✅ KONA 소개 페이지가 생성되었습니다: {output_file}")

if __name__ == "__main__":
    generate_about_page()