#!/usr/bin/env python3
"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

"""
HTML 렌더링 모듈
- 통합 자율 취재 시스템의 결과를 HTML로 변환
- Jinja2 템플릿 사용
"""

import os
import json
import sys
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from scripts.utils import setup_logging, get_kst_now

logger = setup_logging("render_html")

def load_articles_from_investigations(investigations_dir="integrated_results"):
    """통합 조사 결과에서 기사 로드"""
    articles = []
    investigations_path = Path(investigations_dir)
    
    if not investigations_path.exists():
        logger.warning(f"Investigations directory '{investigations_dir}' not found.")
        return articles
    
    for json_file in investigations_path.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                investigation = json.load(f)
            
            # 기사 데이터 추출
            article_data = investigation.get('phases', {}).get('autonomous_investigation', {}).get('stages', {}).get('article')
            
            if article_data:
                # 추가 메타데이터
                article_data['id'] = json_file.stem
                article_data['topic'] = investigation.get('topic', 'unknown')
                article_data['sources_count'] = investigation.get('phases', {}).get('multi_source_collection', {}).get('total_sources', 0)
                article_data['coverage_gaps'] = len(investigation.get('phases', {}).get('topic_analysis', {}).get('coverage_gaps', {}).get('unasked_questions', []))
                
                # 날짜 포맷 조정
                if 'generated_at' not in article_data:
                    article_data['generated_at'] = investigation.get('timestamp', get_kst_now().isoformat())
                
                articles.append(article_data)
                
        except Exception as e:
            logger.error(f"Error loading {json_file}: {e}")
    
    # 날짜순 정렬 (최신순)
    articles.sort(key=lambda x: x.get('generated_at', ''), reverse=True)
    return articles

def setup_jinja_env():
    """Set up Jinja2 environment with templates directory."""
    templates_dir = Path("templates")
    if not templates_dir.exists():
        templates_dir.mkdir(parents=True)
        create_default_templates(templates_dir)
    
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(['html', 'xml'])
    )
    return env

def create_default_templates(templates_dir):
    """Create default templates if they don't exist."""
    # Create base template
    base_template = '''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}KONA - Korean Open News by AI{% endblock %}</title>
    <link rel="stylesheet" href="../static/style.css">
</head>
<body>
    <header>
        <h1>KONA</h1>
        <p>AI 자율 취재 시스템 - 언론이 놓친 진실을 찾아서</p>
    </header>
    
    <main>
        {% block content %}{% endblock %}
    </main>
    
    <footer>
        <p>&copy; 2024 KONA. Open source AI-powered autonomous journalism.</p>
    </footer>
</body>
</html>'''
    
    # Create index template
    index_template = '''{% extends "base.html" %}

{% block title %}KONA - AI 자율 취재 시스템{% endblock %}

{% block content %}
<h2>AI가 발견한 심층 기사</h2>
<div class="articles">
    {% for article in articles %}
    <article>
        <h3><a href="articles/{{ article.id }}.html">{{ article.title }}</a></h3>
        <p class="meta">
            {{ article.generated_at[:10] }} | 
            주제: {{ article.topic }} | 
            취재 깊이: {{ article.investigation_depth }}
        </p>
        <p class="lead">{{ article.lead }}</p>
        <div class="article-stats">
            <span>📊 발견된 취재 공백: {{ article.coverage_gaps }}개</span>
            <span>📚 활용된 소스: {{ article.sources_count }}개</span>
        </div>
    </article>
    {% endfor %}
</div>
{% endblock %}'''
    
    # Create article template
    article_template = '''{% extends "base.html" %}

{% block title %}{{ article.title }} - KONA{% endblock %}

{% block content %}
<article class="full-article">
    <h2>{{ article.title }}</h2>
    <p class="meta">
        {{ article.generated_at[:10] }} | 
        주제: {{ article.topic }} | 
        취재 유형: {{ article.investigation_type }}
    </p>
    
    <div class="lead">
        <p>{{ article.lead }}</p>
    </div>
    
    {% if article.body %}
    <div class="content">
        {% if article.body.introduction %}
        <section class="introduction">
            <p>{{ article.body.introduction }}</p>
        </section>
        {% endif %}
        
        {% if article.body.analysis %}
        <section class="analysis">
            {% for point in article.body.analysis %}
            <div class="analysis-point">
                <h3>{{ point.point }}</h3>
                <p>{{ point.description }}</p>
            </div>
            {% endfor %}
        </section>
        {% endif %}
        
        {% if article.body.data_evidence %}
        <section class="data-evidence">
            <h3>데이터 근거</h3>
            <p>{{ article.body.data_evidence }}</p>
        </section>
        {% endif %}
    </div>
    {% endif %}
    
    {% if article.conclusion %}
    <div class="conclusion">
        <h3>결론</h3>
        <p><strong>의미:</strong> {{ article.conclusion.meaning }}</p>
        <p><strong>전망:</strong> {{ article.conclusion.prospect }}</p>
    </div>
    {% endif %}
    
    {% if article.visualization %}
    <div class="visualization-note">
        <p><em>제안된 시각화: {{ article.visualization.suggestion }}</em></p>
    </div>
    {% endif %}
    
    <div class="article-metadata">
        <p>취재 깊이: {{ article.investigation_depth }}</p>
        <p>검증 점수: {{ article.verification_score }}</p>
        <p>활용된 소스: {{ article.sources_count }}개</p>
    </div>
</article>

<a href="../index.html">← 목록으로 돌아가기</a>
{% endblock %}'''
    
    # Write templates
    (templates_dir / "base.html").write_text(base_template, encoding='utf-8')
    (templates_dir / "index.html").write_text(index_template, encoding='utf-8')
    (templates_dir / "article.html").write_text(article_template, encoding='utf-8')
    print("Created default templates")

def create_default_css():
    """Create default CSS file."""
    css_content = '''/* KONA AI 자율 취재 시스템 스타일 */
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", sans-serif;
    line-height: 1.8;
    color: #333;
    max-width: 900px;
    margin: 0 auto;
    padding: 20px;
    background-color: #f8f9fa;
}

header {
    text-align: center;
    margin-bottom: 40px;
    padding: 30px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    border-radius: 12px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}

header h1 {
    font-size: 2.5em;
    margin: 0;
    font-weight: 700;
}

header p {
    margin: 10px 0 0 0;
    font-size: 1.1em;
    opacity: 0.9;
}

main {
    background-color: white;
    padding: 40px;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

/* 기사 목록 스타일 */
.articles article {
    margin-bottom: 35px;
    padding-bottom: 30px;
    border-bottom: 2px solid #f0f0f0;
}

.articles article:last-child {
    border-bottom: none;
}

.articles h3 {
    margin-bottom: 10px;
    font-size: 1.4em;
}

.articles h3 a {
    color: #2d3748;
    font-weight: 600;
    transition: color 0.2s;
}

.articles h3 a:hover {
    color: #667eea;
}

.lead {
    font-size: 1.1em;
    color: #4a5568;
    margin: 15px 0;
    font-style: italic;
}

.article-stats {
    display: flex;
    gap: 20px;
    margin-top: 10px;
    font-size: 0.9em;
    color: #718096;
}

.article-stats span {
    display: flex;
    align-items: center;
    gap: 5px;
}

/* 개별 기사 스타일 */
.full-article h2 {
    font-size: 2.2em;
    margin-bottom: 20px;
    color: #1a202c;
    line-height: 1.3;
}

.meta {
    color: #718096;
    font-size: 0.95em;
    margin-bottom: 20px;
    padding-bottom: 20px;
    border-bottom: 1px solid #e2e8f0;
}

.content section {
    margin: 30px 0;
}

.introduction {
    font-size: 1.15em;
    color: #2d3748;
    background-color: #f7fafc;
    padding: 20px;
    border-radius: 8px;
    border-left: 4px solid #667eea;
}

.analysis-point {
    margin: 25px 0;
    padding: 20px;
    background-color: #fafafa;
    border-radius: 8px;
}

.analysis-point h3 {
    color: #4a5568;
    margin-bottom: 10px;
    font-size: 1.2em;
}

.data-evidence {
    background-color: #edf2f7;
    padding: 25px;
    border-radius: 8px;
    margin: 30px 0;
}

.data-evidence h3 {
    color: #2b6cb0;
    margin-bottom: 15px;
}

.conclusion {
    margin-top: 40px;
    padding: 25px;
    background-color: #f0f4f8;
    border-radius: 8px;
    border: 1px solid #cbd5e0;
}

.conclusion h3 {
    color: #2d3748;
    margin-bottom: 15px;
}

.conclusion p {
    margin: 10px 0;
}

.visualization-note {
    margin: 20px 0;
    padding: 15px;
    background-color: #fffaf0;
    border-radius: 8px;
    border: 1px solid #feb2b2;
    color: #742a2a;
}

.article-metadata {
    margin-top: 40px;
    padding: 20px;
    background-color: #f7fafc;
    border-radius: 8px;
    font-size: 0.9em;
    color: #4a5568;
}

a {
    color: #667eea;
    text-decoration: none;
    transition: color 0.2s;
}

a:hover {
    color: #5a67d8;
    text-decoration: underline;
}

footer {
    text-align: center;
    margin-top: 50px;
    padding-top: 30px;
    border-top: 1px solid #e2e8f0;
    color: #718096;
    font-size: 0.9em;
}

.no-articles {
    text-align: center;
    padding: 60px 20px;
    color: #718096;
}

.no-articles h3 {
    color: #2d3748;
    margin-bottom: 15px;
    font-size: 1.5em;
}

.no-articles p {
    margin: 10px 0;
}'''
    
    static_dir = Path("static")
    static_dir.mkdir(exist_ok=True)
    (static_dir / "style.css").write_text(css_content, encoding='utf-8')
    print("Created default CSS")

def render_pages(articles):
    """Render HTML pages from articles."""
    env = setup_jinja_env()
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    
    # Create static directory in output
    output_static = output_dir / "static"
    output_static.mkdir(exist_ok=True)
    
    # Copy CSS file
    if not Path("static/style.css").exists():
        create_default_css()
    
    css_source = Path("static/style.css")
    if css_source.exists():
        (output_static / "style.css").write_text(
            css_source.read_text(encoding='utf-8'),
            encoding='utf-8'
        )
    
    # Render index page with articles (even if empty list)
    index_template = env.get_template("index.html")
    index_html = index_template.render(articles=articles)
    (output_dir / "index.html").write_text(index_html, encoding='utf-8')
    print(f"Generated index.html with {len(articles)} articles")
    
    # Create articles directory
    articles_dir = output_dir / "articles"
    articles_dir.mkdir(exist_ok=True)
    
    # Render individual article pages
    if articles:
        article_template = env.get_template("article.html")
        for article in articles:
            if 'id' in article:
                article_html = article_template.render(article=article)
                article_file = articles_dir / f"{article['id']}.html"
                article_file.write_text(article_html, encoding='utf-8')
                print(f"Generated {article['id']}.html")
    
    print(f"\nSuccessfully rendered {len(articles)} articles to {output_dir}")

def main():
    """Main function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Render HTML from autonomous investigation results')
    parser.add_argument('--investigation-dir', default='integrated_results', 
                        help='Directory containing investigation JSON files')
    args = parser.parse_args()
    
    print("🎨 KONA HTML 렌더링 시작...")
    
    # Load articles from investigation results
    articles = load_articles_from_investigations(args.investigation_dir)
    
    if not articles:
        print("⚠️  렌더링할 기사가 없습니다.")
        return 0
    
    print(f"📚 {len(articles)}개의 기사를 발견했습니다.")
    
    # Render pages
    try:
        render_pages(articles)
        print("✅ HTML 렌더링 완료!")
        return 0
    except Exception as e:
        logger.error(f"Error during rendering: {e}")
        print(f"❌ 렌더링 중 오류 발생: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())