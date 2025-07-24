#!/usr/bin/env python3
"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

"""
통합 index.html 생성 스크립트 (버전 2)
- topic_index를 활용하여 최신 버전만 표시
- 버전 관리 시스템과 통합
"""

import os
import re
import json
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup

def extract_article_info_from_html(html_path):
    """HTML 파일에서 기사 정보 추출"""
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        
        # 제목 추출
        title = soup.find('title')
        if title:
            title_text = title.text.strip()
            # "스마트 기사 - 날짜" 형식에서 실제 제목 추출
            if " - " in title_text:
                title_text = title_text.split(" - ")[0].strip()
        else:
            title_text = "제목 없음"
        
        # 시간 추출 (파일명에서)
        filename = os.path.basename(html_path)
        time_match = re.search(r'(\d{8}_\d{6})', filename)
        if time_match:
            time_str = time_match.group(1)
            dt = datetime.strptime(time_str, "%Y%m%d_%H%M%S")
            formatted_time = dt.strftime("%Y년 %m월 %d일 %H:%M")
        else:
            formatted_time = "시간 정보 없음"
        
        # 세 줄 요약 추출
        summary_lines = []
        html_text = str(soup)
        summary_match = re.search(r'<h3>📝 (?:세 줄 )?요약</h3>\s*(.+?)(?=</div>|<h)', html_text, re.DOTALL)
        if summary_match:
            summary_text = summary_match.group(1)
            # HTML 태그와 번호 제거하고 내용만 추출
            lines = re.findall(r'<strong>\d+\.</strong>\s*(.+?)</p>', summary_text)
            if lines:
                summary = " / ".join(lines[:3])  # 최대 3줄
            else:
                summary = "요약을 찾을 수 없습니다."
        else:
            # 대체: 첫 번째 단락 추출
            article_content = soup.find(class_='article-content')
            if article_content:
                # 텍스트만 추출하고 처음 200자
                summary = article_content.get_text(strip=True)[:200] + "..."
            else:
                summary = "요약을 찾을 수 없습니다."
        
        return {
            'filename': os.path.basename(html_path),
            'title': title_text,
            'time': formatted_time,
            'summary': summary,
            'source': 'html',
            'path': str(html_path)
        }
    except Exception as e:
        print(f"Error processing {html_path}: {e}")
        return None

def extract_article_info_from_cache(json_path, topic_id=None):
    """캐시 JSON에서 기사 정보 추출"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 제목 - AI 생성 제목 우선 사용
        title = data.get('generated_title') or data.get('main_article', {}).get('title', '제목 없음')
        
        # 시간 (last_updated 우선, 없으면 created_at)
        time_str = data.get('last_updated') or data.get('created_at', '')
        if time_str:
            dt = datetime.fromisoformat(time_str)
            formatted_time = dt.strftime("%Y년 %m월 %d일 %H:%M")
        else:
            formatted_time = "시간 정보 없음"
        
        # article_id와 version 정보 가져오기
        article_id = topic_id or data.get('topic_id', os.path.basename(json_path).replace('.json', ''))
        latest_version = data.get('version', 1)
        
        # HTML 파일에서 세 줄 요약 추출
        html_path = Path("output") / f"smart_articles/versions/article_{article_id}_v{latest_version}.html"
        summary_lines = []
        
        if html_path.exists():
            try:
                with open(html_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                    # 세 줄 요약 부분 추출
                    import re
                    summary_match = re.search(r'<h3>📝 (?:세 줄 )?요약</h3>\s*(.+?)(?=</div>|<h)', html_content, re.DOTALL)
                    if summary_match:
                        summary_text = summary_match.group(1)
                        # HTML 태그와 번호 제거하고 내용만 추출
                        lines = re.findall(r'<strong>\d+\.</strong>\s*(.+?)</p>', summary_text)
                        summary_lines = lines[:3]  # 최대 3줄
                        
                if summary_lines:
                    summary = " / ".join(summary_lines)
                else:
                    # 대체 방법: comprehensive_article에서 첫 문장 추출
                    generated_article = data.get('comprehensive_article', '')
                    if generated_article:
                        # 첫 번째 단락 찾기 (제목 다음의 첫 문장)
                        first_para_match = re.search(r'^[^#\n].+?[.!?]', generated_article, re.MULTILINE)
                        if first_para_match:
                            summary = first_para_match.group(0)
                        else:
                            summary = "요약을 찾을 수 없습니다."
                    else:
                        summary = "요약을 찾을 수 없습니다."
            except Exception as e:
                print(f"Warning: Could not extract summary from HTML for {article_id}: {e}")
                summary = "요약을 찾을 수 없습니다."
        else:
            summary = "요약을 찾을 수 없습니다."
        
        # 대응하는 HTML 파일 찾기
        if not topic_id:
            topic_id = data.get('topic_id', os.path.basename(json_path).replace('.json', ''))
        smart_articles_dir = Path("output/smart_articles")
        
        # 가장 가까운 시간의 HTML 파일 찾기
        matching_html = None
        if smart_articles_dir.exists() and time_str:
            target_time = datetime.fromisoformat(time_str)
            min_diff = float('inf')
            
            for html_file in smart_articles_dir.glob("article_*.html"):
                time_match = re.search(r'(\d{8}_\d{6})', html_file.name)
                if time_match:
                    file_time = datetime.strptime(time_match.group(1), "%Y%m%d_%H%M%S")
                    diff = abs((file_time - target_time).total_seconds())
                    if diff < min_diff and diff < (3600 * 24):  # 24시간 이내
                        min_diff = diff
                        matching_html = html_file.name
        
        # 버전 정보
        version = data.get('version', 1)
        
        return {
            'filename': matching_html or f"article_{topic_id}.html",
            'title': title,
            'time': formatted_time,
            'summary': summary,
            'source': 'cache',
            'path': f"smart_articles/{matching_html}" if matching_html else None,
            'cache_path': str(json_path),
            'topic_id': topic_id,
            'version': version
        }
    except Exception as e:
        print(f"Error processing {json_path}: {e}")
        return None

def generate_unified_index():
    """통합 index.html 생성 (최신 버전만 표시)"""
    # GitHub Actions 환경에서는 output 디렉토리가 없을 수 있음
    # 현재 디렉토리에 articles가 있으면 현재 디렉토리를 사용
    if Path("articles").exists() or Path("smart_articles").exists():
        output_dir = Path(".")
    else:
        output_dir = Path("output")
    
    # topic_index 로드 (여러 위치에서 시도)
    topic_index = {}
    possible_paths = [
        Path("topic_index.json"),  # 배포 디렉토리 루트
        Path("cache/articles/topic_index.json"),
        Path("../cache/articles/topic_index.json"),
        output_dir / "topic_index.json"
    ]
    
    for topic_index_path in possible_paths:
        if topic_index_path.exists():
            print(f"Found topic_index.json at: {topic_index_path}")
            with open(topic_index_path, 'r', encoding='utf-8') as f:
                topic_index = json.load(f)
            break
    else:
        print("Warning: topic_index.json not found in any location")
        print("Will scan HTML files directly (may include duplicates)")
    
    # 최신 버전만 필터링 (parent_id가 없는 것들 = 최상위 버전)
    latest_articles = []
    
    # 각 주제의 최신 버전 찾기
    # 버전 체인을 따라가서 각 체인의 최신 버전만 선택
    processed_chains = set()
    
    for article_id, info in topic_index.items():
        # 이미 처리된 체인의 일부인 경우 스킵
        if article_id in processed_chains:
            continue
            
        # 이 기사가 속한 체인의 최신 버전 찾기
        chain_articles = []
        
        # 같은 주제의 모든 기사 찾기 (제목 기준)
        base_title = info['main_title']
        for aid, ainfo in topic_index.items():
            if ainfo['main_title'] == base_title or aid == article_id:
                chain_articles.append((aid, ainfo))
                processed_chains.add(aid)
        
        # 버전 번호로 정렬하여 최신 버전 찾기
        if chain_articles:
            chain_articles.sort(key=lambda x: x[1].get('version', 1), reverse=True)
            latest_id, latest_info = chain_articles[0]
            
            # 캐시 파일 확인 (없어도 topic_index 정보로 기사 생성)
            cache_path = Path(f"cache/articles/{latest_id}.json")
            if cache_path.exists():
                article_info = extract_article_info_from_cache(cache_path, latest_id)
            else:
                # 캐시가 없으면 topic_index 정보로 기사 정보 생성
                # 하지만 HTML 파일에서 세 줄 요약을 찾아보기
                summary = latest_info.get('main_title', '제목 없음') + '...'  # 기본값
                
                # HTML 파일에서 세 줄 요약 추출 시도
                version = latest_info.get('version', 1)
                html_path = Path("output") / f"smart_articles/versions/article_{latest_id}_v{version}.html"
                if not html_path.exists():
                    # 버전 파일이 없으면 일반 파일 경로 시도
                    if latest_info.get('created_at'):
                        try:
                            dt = datetime.fromisoformat(latest_info['created_at'])
                            file_pattern = dt.strftime("article_%Y%m%d_%H%M")
                            for search_dir in [Path("output/smart_articles"), Path("smart_articles")]:
                                if search_dir.exists():
                                    matching_files = list(search_dir.glob(f"{file_pattern}*.html"))
                                    if matching_files:
                                        html_path = matching_files[0]
                                        break
                        except:
                            pass
                
                if html_path.exists():
                    try:
                        with open(html_path, 'r', encoding='utf-8') as f:
                            html_content = f.read()
                            # 세 줄 요약 부분 추출
                            import re
                            summary_match = re.search(r'<h3>📝 (?:세 줄 )?요약</h3>\s*(.+?)(?=</div>|<h)', html_content, re.DOTALL)
                            if summary_match:
                                summary_text = summary_match.group(1)
                                # HTML 태그와 번호 제거하고 내용만 추출
                                lines = re.findall(r'<strong>\d+\.</strong>\s*(.+?)</p>', summary_text)
                                if lines:
                                    summary = " / ".join(lines[:3])  # 최대 3줄
                    except Exception as e:
                        print(f"Warning: Could not extract summary from HTML for {latest_id}: {e}")
                
                article_info = {
                    'filename': f"article_{latest_id}.html",
                    'title': latest_info.get('generated_title') or latest_info.get('main_title', '제목 없음'),
                    'time': datetime.fromisoformat(latest_info.get('last_updated', latest_info.get('created_at', ''))).strftime("%Y년 %m월 %d일 %H:%M") if latest_info.get('last_updated') or latest_info.get('created_at') else '시간 정보 없음',
                    'summary': summary,
                    'source': 'topic_index',
                    'path': None,  # 경로는 나중에 찾기
                    'topic_id': latest_id,
                    'version': latest_info.get('version', 1)
                }
            
            # topic_index의 generated_title 또는 main_title로 제목을 덮어쓰기
            if article_info:
                if latest_info.get('generated_title'):
                    article_info['title'] = latest_info['generated_title']
                elif latest_info.get('main_title'):
                    article_info['title'] = latest_info['main_title']
            
            # HTML 파일 경로 찾기
            if article_info and not article_info.get('path'):
                # created_at 날짜로 파일명 추정
                if latest_info.get('created_at'):
                    try:
                        dt = datetime.fromisoformat(latest_info['created_at'])
                        file_pattern = dt.strftime("article_%Y%m%d_%H%M")
                        
                        # 가능한 파일 경로들 검색
                        for search_dir in [Path("articles"), Path("smart_articles")]:
                            if search_dir.exists():
                                matching_files = list(search_dir.glob(f"{file_pattern}*.html"))
                                if matching_files:
                                    article_info['path'] = f"{search_dir.name}/{matching_files[0].name}"
                                    break
                    except:
                        pass
            
            # 경로를 찾지 못해도 topic_index에 있으면 포함
            if article_info:
                # 경로가 없으면 기본 경로 생성
                if not article_info.get('path'):
                    # topic_id나 날짜 기반으로 기본 경로 설정
                    if latest_info.get('created_at'):
                        try:
                            dt = datetime.fromisoformat(latest_info['created_at'])
                            filename = dt.strftime("article_%Y%m%d_%H%M%S.html")
                            article_info['path'] = f"smart_articles/{filename}"
                        except:
                            article_info['path'] = f"smart_articles/article_{latest_id}.html"
                    else:
                        article_info['path'] = f"smart_articles/article_{latest_id}.html"
                
                article_info['version_info'] = f"v{latest_info.get('version', 1)}"
                article_info['tags'] = latest_info.get('tags', {'category_tags': [], 'content_tags': []})
                latest_articles.append(article_info)
    
    # topic_index에 기사가 없으면 기존 방식으로 HTML 파일 직접 스캔
    if not latest_articles:
        print("No articles found in topic_index, scanning HTML files directly...")
        print("WARNING: This may include duplicate articles!")
        
        # 중복 체크를 위한 제목 세트
        seen_titles = set()
        all_scanned_articles = []
        
        # 여러 위치에서 기사 파일 검색
        search_locations = [
            (Path("articles"), "articles"),  # 배포 디렉토리 우선
            (output_dir / "articles", "articles"),
            (output_dir / "smart_articles", "smart_articles"),
            (Path("smart_articles"), "smart_articles"),
        ]
        
        for search_dir, path_prefix in search_locations:
            if search_dir.exists():
                print(f"Scanning {search_dir}...")
                article_files = list(search_dir.glob("article_*.html"))
                print(f"Found {len(article_files)} files in {search_dir}")
                
                for article_file in article_files:
                    if article_file.stem.endswith('_backup'):
                        continue
                        
                    article_info = extract_article_info_from_html(article_file)
                    if article_info:
                        # 경로 조정
                        article_info['path'] = f"{path_prefix}/{article_file.name}"
                        article_info['tags'] = {'category_tags': [], 'content_tags': []}
                        all_scanned_articles.append(article_info)
        
        # 시간순 정렬 후 제목 기반 중복 제거
        all_scanned_articles.sort(key=lambda x: x['time'], reverse=True)
        
        for article in all_scanned_articles:
            title = article['title']
            if title not in seen_titles:
                seen_titles.add(title)
                latest_articles.append(article)
        
        print(f"After deduplication: {len(latest_articles)} unique articles")
    
    # 시간순 정렬 (최신순)
    latest_articles.sort(key=lambda x: x['time'], reverse=True)
    
    # 모든 태그 수집
    # 미리 정의된 카테고리 태그 (순서 유지)
    predefined_categories = ['정치', '경제', '사회', '생활/문화', 'IT/과학', '국제']
    used_category_tags = set()  # 실제 사용된 카테고리만 수집
    all_content_tags = set()
    
    # 최신 10개 기사의 대표 태그 수집
    recent_tags = []
    tag_count = {}
    
    for i, article in enumerate(latest_articles):
        tags = article.get('tags', {'category_tags': [], 'content_tags': []})
        used_category_tags.update(tags.get('category_tags', []))  # 실제 사용된 카테고리만
        content_tags = tags.get('content_tags', [])
        all_content_tags.update(content_tags)
        
        # 태그 빈도 계산
        for tag in content_tags:
            tag_count[tag] = tag_count.get(tag, 0) + 1
        
        # 최신 10개 기사의 첫 번째 태그 저장
        if i < 10 and content_tags:
            recent_tags.append(content_tags[0])
    
    # 태그 정렬 - 실제 사용된 카테고리만, 미리 정의된 순서대로
    sorted_category_tags = [cat for cat in predefined_categories if cat in used_category_tags]
    
    # 주요 키워드 정렬: 최신 기사 대표 태그 + 나머지 랜덤
    import random
    remaining_tags = list(all_content_tags - set(recent_tags))
    random.shuffle(remaining_tags)
    sorted_content_tags = recent_tags + remaining_tags
    
    # HTML 생성
    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KONA - Korean Open News by AI</title>
    <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
    <link rel="alternate icon" href="/static/favicon.svg">
    <style>
        :root {{
            --primary-color: #1a73e8;
            --text-color: #202124;
            --bg-color: #f8f9fa;
            --card-bg: #ffffff;
            --border-color: #dadce0;
        }}
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif;
            color: var(--text-color);
            background-color: var(--bg-color);
            line-height: 1.6;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 20px;
        }}
        header {{
            background-color: var(--card-bg);
            border-bottom: 1px solid var(--border-color);
            padding: 15px 0;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            position: sticky;
            top: 0;
            z-index: 1000;
        }}
        h1 {{
            font-size: 2.2rem;
            color: var(--primary-color);
            margin: 0;
        }}
        h1 a {{
            color: inherit;
            text-decoration: none;
            transition: opacity 0.2s ease;
        }}
        h1 a:hover {{
            opacity: 0.8;
        }}
        .header-content {{
            display: flex;
            flex-direction: row;
            align-items: baseline;
            gap: 20px;
        }}
        .tagline {{
            color: #5f6368;
            font-size: 1.1rem;
            margin: 0;
        }}
        .update-info {{
            background: #e8f0fe;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
            display: flex;
            align-items: center;
            gap: 15px;
        }}
        .update-info .badge {{
            background: var(--primary-color);
            color: white;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 500;
        }}
        .articles-count {{
            background: #28a745;
            color: white;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 500;
        }}
        .tag-filter-section {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .tag-filter-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 15px;
        }}
        .tag-filter-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-color);
        }}
        .tag-reset-btn {{
            display: none;
            padding: 6px 16px;
            background: #dc3545;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: all 0.3s ease;
        }}
        .tag-reset-btn.active {{
            display: block;
        }}
        .tag-reset-btn:hover {{
            background: #c82333;
        }}
        .tag-groups {{
            display: flex;
            flex-direction: column;
            gap: 15px;
        }}
        .tag-group {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            align-items: center;
        }}
        .tag-group-label {{
            font-size: 0.9rem;
            color: #666;
            margin-right: 10px;
            min-width: 80px;
        }}
        .tag-btn {{
            padding: 5px 12px;
            background: #f0f0f0;
            border: 1px solid #ddd;
            border-radius: 20px;
            cursor: pointer;
            font-size: 0.85rem;
            transition: all 0.2s ease;
            user-select: none;
        }}
        .tag-btn:hover {{
            background: #e0e0e0;
            border-color: #bbb;
        }}
        .tag-btn.active {{
            background: var(--primary-color);
            color: white;
            border-color: var(--primary-color);
        }}
        .no-results {{
            text-align: center;
            padding: 60px 20px;
            color: #666;
        }}
        .articles-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
            gap: 25px;
            margin-bottom: 50px;
        }}
        .article-card {{
            background: var(--card-bg);
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            transition: all 0.3s ease;
            border: 1px solid var(--border-color);
            cursor: pointer;
            text-decoration: none;
            color: inherit;
            display: block;
            position: relative;
        }}
        .article-card:hover {{
            transform: translateY(-3px);
            box-shadow: 0 4px 16px rgba(0,0,0,0.12);
        }}
        .article-card h2 {{
            font-size: 1.4rem;
            margin-bottom: 10px;
            line-height: 1.4;
            color: var(--text-color);
        }}
        .article-meta {{
            display: flex;
            gap: 15px;
            margin-bottom: 15px;
            font-size: 0.9rem;
            color: #5f6368;
        }}
        .article-summary {{
            color: #5f6368;
            line-height: 1.6;
            font-size: 0.95rem;
        }}
        .version-badge {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: #17a2b8;
            color: white;
            padding: 3px 8px;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 500;
        }}
        .no-articles {{
            text-align: center;
            padding: 60px 20px;
            color: #5f6368;
        }}
        .no-articles h2 {{
            color: var(--text-color);
            margin-bottom: 10px;
        }}
        footer {{
            background: var(--card-bg);
            border-top: 1px solid var(--border-color);
            padding: 30px 0;
            margin-top: 60px;
            text-align: center;
            color: #5f6368;
        }}
        footer a {{
            color: var(--primary-color);
            text-decoration: none;
        }}
        footer a:hover {{
            text-decoration: underline;
        }}
        .admin-link {{
            margin-top: 20px;
        }}
        .admin-link a {{
            background: var(--primary-color);
            color: white;
            padding: 10px 20px;
            border-radius: 5px;
            text-decoration: none;
            display: inline-block;
        }}
        .admin-link a:hover {{
            background: #1557b0;
        }}
        /* 키워드 섹션 스타일 */
        .keywords-section {{
            cursor: pointer;
            position: relative;
        }}
        .keywords-container {{
            position: relative;
        }}
        .keywords-collapsed {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            align-items: center;
            max-height: 40px;
            overflow: hidden;
        }}
        .expand-indicator {{
            color: var(--primary-color);
            font-weight: 500;
            margin-left: 8px;
            white-space: nowrap;
        }}
        .keywords-expanded {{
            margin-top: 15px;
        }}
        .keyword-search {{
            width: 100%;
            max-width: 300px;
            padding: 8px 12px;
            border: 1px solid var(--border-color);
            border-radius: 20px;
            margin-bottom: 15px;
            font-size: 0.9rem;
            outline: none;
        }}
        .keyword-search:focus {{
            border-color: var(--primary-color);
        }}
        .selected-keywords {{
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid var(--border-color);
            min-height: 20px;
        }}
        .selected-keywords:empty {{
            display: none;
        }}
        .selected-keywords .tag-btn {{
            background: var(--primary-color);
            color: white;
        }}
        .all-keywords {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            max-height: 120px;
            overflow-y: auto;
            padding-right: 10px;
        }}
        .all-keywords .tag-btn.hidden {{
            display: none;
        }}
        
        /* 하단 네비게이션 바 */
        .bottom-nav {{
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: white;
            display: none;
            justify-content: space-around;
            padding: 8px 0;
            box-shadow: 0 -2px 4px rgba(0,0,0,0.1);
            z-index: 999;
            border-top: 1px solid var(--border-color);
        }}
        .bottom-nav-item {{
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 5px 15px;
            text-decoration: none;
            color: #666;
            transition: color 0.2s ease;
            cursor: pointer;
            background: none;
            border: none;
            font-family: inherit;
        }}
        .bottom-nav-item:hover {{
            color: var(--primary-color);
        }}
        .bottom-nav-item.active {{
            color: var(--primary-color);
        }}
        .bottom-nav-item .icon {{
            font-size: 1.5rem;
            margin-bottom: 3px;
        }}
        .bottom-nav-item .label {{
            font-size: 0.75rem;
        }}
        
        /* 태그 드로어 */
        .tag-drawer {{
            position: fixed;
            top: 0;
            right: -300px;
            width: 300px;
            max-width: 80%;
            height: 100%;
            background: white;
            box-shadow: -2px 0 8px rgba(0,0,0,0.2);
            transition: right 0.3s ease;
            overflow-y: auto;
            z-index: 1001;
            padding: 20px;
        }}
        .tag-drawer.open {{
            right: 0;
        }}
        .drawer-overlay {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.5);
            display: none;
            z-index: 1000;
        }}
        .drawer-overlay.active {{
            display: block;
        }}
        .drawer-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid var(--border-color);
        }}
        .drawer-title {{
            font-size: 1.2rem;
            font-weight: 600;
        }}
        .drawer-close {{
            background: none;
            border: none;
            font-size: 1.5rem;
            cursor: pointer;
            color: #666;
        }}
        
        /* 모바일 최적화 */
        @media (max-width: 768px) {{
            header {{
                padding: 10px 0;
                margin-bottom: 15px;
            }}
            .header-content {{
                flex-direction: row;
                gap: 10px;
                align-items: center; /* 수직 가운데 정렬 */
            }}
            h1 {{
                font-size: 1.3rem;
                margin-bottom: 0;
            }}
            .tagline {{
                font-size: 0.75rem;
                color: #8e8e93;
                margin: 0;
            }}
            .update-info {{
                padding: 10px;
                margin-bottom: 15px;
                flex-wrap: wrap;
                font-size: 0.85rem;
            }}
            .update-info .badge {{
                padding: 4px 10px;
                font-size: 0.8rem;
            }}
            .articles-grid {{
                grid-template-columns: 1fr;
                padding-bottom: 80px; /* 하단 네비게이션 공간 */
            }}
            .tag-groups {{
                gap: 10px;
            }}
            .tag-chip {{
                font-size: 0.85rem;
                padding: 6px 10px;
            }}
            .bottom-nav {{
                display: flex;
            }}
            .tag-filter-section {{
                display: none; /* 모바일에서는 태그 필터 숨김 */
            }}
            /* 모바일 태그 드로어 내부 스타일 */
            .tag-drawer .all-keywords {{
                max-height: calc(100vh - 200px); /* 화면 높이에서 헤더와 여백을 뺀 높이 */
                overflow-y: auto;
                -webkit-overflow-scrolling: touch;
            }}
            .tag-drawer .keywords-expanded {{
                display: block !important; /* 모바일에서는 항상 확장 상태 */
            }}
            .tag-drawer .keywords-collapsed {{
                display: none !important; /* 모바일에서는 축소 상태 숨김 */
            }}
            .tag-drawer .keyword-search {{
                margin-bottom: 15px;
            }}
        }}
    </style>
</head>
<body>
    <header>
        <div class="container">
            <div class="header-content">
                <h1><a href="/">KONA</a></h1>
                <p class="tagline">Korean Open News by AI - AI가 만드는 투명한 한국 뉴스</p>
            </div>
        </div>
    </header>
    
    <main class="container">
        <div class="update-info">
            <span class="badge">LIVE</span>
            <span>최신 AI 생성 뉴스 - {datetime.now().strftime('%Y년 %m월 %d일 %H:%M')} 업데이트</span>
            <span class="articles-count">총 {len(latest_articles)}개 기사</span>
        </div>
        
        <div class="tag-filter-section">
            <div class="tag-filter-header">
                <h3 class="tag-filter-title">🏷️ 태그로 필터링</h3>
                <button class="tag-reset-btn" onclick="resetAllTags()">모든 태그 해제</button>
            </div>
            <div class="tag-groups">
"""

    # 카테고리 태그 추가
    if sorted_category_tags:
        html_content += '                <div class="tag-group">\n'
        html_content += '                    <span class="tag-group-label">카테고리:</span>\n'
        for tag in sorted_category_tags:
            html_content += f'                    <button class="tag-btn category-tag" data-tag="{tag}" onclick="toggleTag(this, event)">{tag}</button>\n'
        html_content += '                </div>\n'
    
    # 콘텐츠 태그 추가
    if sorted_content_tags:
        html_content += '                <div class="tag-group keywords-section" onclick="toggleKeywordsExpansion(event)">\n'
        html_content += '                    <span class="tag-group-label">주요 키워드:</span>\n'
        html_content += '                    <div class="keywords-container">\n'
        html_content += '                        <div class="keywords-collapsed">\n'
        # 첫 줄에 표시할 태그들 (약 10개 정도)
        for i, tag in enumerate(sorted_content_tags[:10]):
            html_content += f'                            <button class="tag-btn content-tag" data-tag="{tag}" onclick="toggleTag(this, event)">{tag}</button>\n'
        html_content += '                            <span class="expand-indicator">... 더보기</span>\n'
        html_content += '                        </div>\n'
        html_content += '                        <div class="keywords-expanded" style="display: none;">\n'
        html_content += '                            <input type="text" class="keyword-search" placeholder="키워드 검색..." oninput="searchKeywords(this)">\n'
        html_content += '                            <div class="selected-keywords"></div>\n'
        html_content += '                            <div class="all-keywords">\n'
        for tag in sorted_content_tags:
            html_content += f'                                <button class="tag-btn content-tag" data-tag="{tag}" onclick="toggleTag(this, event)">{tag}</button>\n'
        html_content += '                            </div>\n'
        html_content += '                        </div>\n'
        html_content += '                    </div>\n'
        html_content += '                </div>\n'
    
    html_content += '            </div>\n'
    html_content += '        </div>\n'
    
    html_content += '''        <div class="no-results" style="display: none;"></div>
'''
    
    if latest_articles:
        html_content += '        <div class="articles-grid">\n'
        for article in latest_articles:
            if article.get('path'):
                version_badge = f'<span class="version-badge">v{article.get("version", 1)}</span>' if article.get('version', 1) > 1 else ''
                tags = article.get('tags', {'category_tags': [], 'content_tags': []})
                all_tags = tags.get('category_tags', []) + tags.get('content_tags', [])
                # 태그를 파이프(|) 문자로 구분하여 저장
                tags_data = '|'.join(all_tags)
                
                html_content += f'''            <a href="/{article['path']}" class="article-card" data-tags="{tags_data}" onclick="this.href = '/{article['path']}#' + Array.from(selectedTags).join(',')">
                {version_badge}
                <h2>{article['title']}</h2>
                <div class="article-meta">
                    <span>📅 {article['time']}</span>
                    <span>🤖 AI 생성</span>
                </div>
                <p class="article-summary">{article['summary']}</p>
            </a>
'''
        html_content += '        </div>\n'
    else:
        html_content += '''        <div class="no-articles">
            <h2>아직 생성된 뉴스가 없습니다</h2>
            <p>KONA 시스템이 새로운 뉴스를 생성 중입니다.</p>
        </div>
'''

    html_content += f'''    </main>
    
    <footer>
        <div class="container">
            <p>© 2025 KONA Project | 
            <a href="https://github.com/pjeehoon/kona-news" target="_blank">GitHub</a> | 
            <a href="https://github.com/pjeehoon/kona-news/blob/main/LICENSE" target="_blank">License</a>
            </p>
            <p style="margin-top: 10px; font-size: 0.85rem;">
                생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S KST')}
            </p>
        </div>
    </footer>
    
    <script>
        let selectedTags = new Set();
        
        function toggleTag(button, event) {{
            if (event) {{
                event.stopPropagation();
            }}
            
            const tag = button.getAttribute('data-tag');
            
            if (button.classList.contains('active')) {{
                button.classList.remove('active');
                selectedTags.delete(tag);
            }} else {{
                button.classList.add('active');
                selectedTags.add(tag);
            }}
            
            // 선택된 태그 업데이트
            updateSelectedKeywords();
            
            // 태그 해제 버튼 표시/숨김
            const resetBtn = document.querySelector('.tag-reset-btn');
            if (selectedTags.size > 0) {{
                resetBtn.classList.add('active');
            }} else {{
                resetBtn.classList.remove('active');
            }}
            
            filterArticles();
        }}
        
        function toggleKeywordsExpansion(event) {{
            // 태그 버튼 클릭은 무시
            if (event.target.classList.contains('tag-btn')) {{
                return;
            }}
            
            const section = event.currentTarget;
            const collapsed = section.querySelector('.keywords-collapsed');
            const expanded = section.querySelector('.keywords-expanded');
            
            if (collapsed.style.display === 'none') {{
                collapsed.style.display = 'flex';
                expanded.style.display = 'none';
            }} else {{
                collapsed.style.display = 'none';
                expanded.style.display = 'block';
                // 검색창에 포커스
                expanded.querySelector('.keyword-search').focus();
            }}
        }}
        
        function searchKeywords(input) {{
            const searchText = input.value.toLowerCase();
            const allKeywords = document.querySelectorAll('.all-keywords .tag-btn');
            
            allKeywords.forEach(btn => {{
                const tagText = btn.textContent.toLowerCase();
                if (tagText.includes(searchText)) {{
                    btn.classList.remove('hidden');
                }} else {{
                    btn.classList.add('hidden');
                }}
            }});
        }}
        
        function updateSelectedKeywords() {{
            const selectedContainer = document.querySelector('.selected-keywords');
            const allButtons = document.querySelectorAll('.tag-btn.content-tag');
            
            // 선택된 태그들을 상단에 표시
            selectedContainer.innerHTML = '';
            allButtons.forEach(btn => {{
                if (btn.classList.contains('active')) {{
                    const clone = btn.cloneNode(true);
                    clone.onclick = (e) => toggleTag(btn, e);
                    selectedContainer.appendChild(clone);
                }}
            }});
        }}
        
        function resetAllTags() {{
            // 모든 태그 버튼의 active 클래스 제거
            document.querySelectorAll('.tag-btn').forEach(btn => {{
                btn.classList.remove('active');
            }});
            
            // 선택된 태그 초기화
            selectedTags.clear();
            
            // 태그 해제 버튼 숨김
            document.querySelector('.tag-reset-btn').classList.remove('active');
            
            // 모든 기사 표시
            filterArticles();
        }}
        
        function filterArticles() {{
            const articles = document.querySelectorAll('.article-card');
            let visibleCount = 0;
            
            articles.forEach(article => {{
                if (selectedTags.size === 0) {{
                    // 태그가 선택되지 않은 경우 모든 기사 표시
                    article.style.display = 'block';
                    visibleCount++;
                }} else {{
                    // 기사의 태그 가져오기 (파이프로 구분)
                    const articleTags = article.getAttribute('data-tags').split('|').filter(tag => tag);
                    
                    // OR 조건: 선택된 태그 중 하나라도 있으면 표시
                    const hasSelectedTag = Array.from(selectedTags).some(tag => articleTags.includes(tag));
                    
                    if (hasSelectedTag) {{
                        article.style.display = 'block';
                        visibleCount++;
                    }} else {{
                        article.style.display = 'none';
                    }}
                }}
            }});
            
            // 결과가 없을 때 메시지 표시
            const articlesGrid = document.querySelector('.articles-grid');
            const existingNoResults = document.querySelector('.no-results');
            
            if (visibleCount === 0 && selectedTags.size > 0) {{
                if (!existingNoResults) {{
                    const noResultsDiv = document.createElement('div');
                    noResultsDiv.className = 'no-results';
                    noResultsDiv.innerHTML = '<h3>선택한 태그와 일치하는 기사가 없습니다.</h3>';
                    articlesGrid.parentNode.insertBefore(noResultsDiv, articlesGrid.nextSibling);
                }}
                articlesGrid.style.display = 'none';
            }} else {{
                if (existingNoResults) {{
                    existingNoResults.remove();
                }}
                articlesGrid.style.display = 'grid';
            }}
        }}
    </script>
    
    <!-- 하단 네비게이션 바 -->
    <nav class="bottom-nav">
        <a href="/" class="bottom-nav-item">
            <span class="icon">🏠</span>
            <span class="label">홈</span>
        </a>
        <button class="bottom-nav-item" onclick="toggleTagDrawer()">
            <span class="icon">🏷️</span>
            <span class="label">태그</span>
        </button>
    </nav>
    
    <!-- 태그 드로어 -->
    <div class="drawer-overlay" onclick="toggleTagDrawer()"></div>
    <div class="tag-drawer">
        <div class="drawer-header">
            <h3 class="drawer-title">태그로 필터링</h3>
            <button class="drawer-close" onclick="toggleTagDrawer()">✕</button>
        </div>
        <div class="drawer-content">
            <!-- 태그 내용이 여기에 복사됩니다 -->
        </div>
    </div>
    
    <script>
        // 태그 드로어 토글
        function toggleTagDrawer() {{
            const drawer = document.querySelector('.tag-drawer');
            const overlay = document.querySelector('.drawer-overlay');
            const isOpen = drawer.classList.contains('open');
            
            if (!isOpen) {{
                // 태그 필터 내용 복사
                const tagFilterSection = document.querySelector('.tag-filter-section');
                const drawerContent = document.querySelector('.drawer-content');
                if (tagFilterSection && drawerContent) {{
                    drawerContent.innerHTML = tagFilterSection.innerHTML;
                    // 이벤트 리스너 다시 연결
                    initializeDrawerTags();
                }}
            }}
            
            drawer.classList.toggle('open');
            overlay.classList.toggle('active');
        }}
        
        // 드로어 내 태그 초기화
        function initializeDrawerTags() {{
            const drawerContent = document.querySelector('.drawer-content');
            if (!drawerContent) return;
            
            // 태그 버튼 이벤트 리스너
            drawerContent.querySelectorAll('.tag-btn').forEach(btn => {{
                btn.addEventListener('click', function() {{
                    const tag = this.dataset.tag;
                    filterByTag(tag);
                    toggleTagDrawer(); // 선택 후 드로어 닫기
                }});
            }});
            
            // 초기화 버튼
            const resetBtn = drawerContent.querySelector('.tag-reset-btn');
            if (resetBtn) {{
                resetBtn.addEventListener('click', function() {{
                    resetTagFilter();
                    toggleTagDrawer(); // 초기화 후 드로어 닫기
                }});
            }}
        }}
    </script>
</body>
</html>'''

    # 파일 저장
    output_path = output_dir / "index.html"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Generated unified index.html with {len(latest_articles)} articles (latest versions only)")
    print(f"Total topics in index: {len(topic_index)}")
    return len(latest_articles)

if __name__ == "__main__":
    generate_unified_index()