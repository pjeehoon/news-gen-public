#!/usr/bin/env python3
"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

"""
어드민 페이지 생성 스크립트 (버전 2)
- 버전 정보 표시
- 통합된 기사 처리
- 기사별 버전 히스토리
"""

import json
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import hashlib
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 환율 정보 가져오기 (기본값: 1400)
USD_TO_KRW_RATE = float(os.getenv('USD_TO_KRW_RATE', 1400))

# 모델명 가져오기
DEFAULT_MODEL = os.getenv('DETAIL_MODEL', 'gpt-4.1-nano')

def collect_article_metadata():
    """기사 메타데이터 수집 - 버전 정보 포함"""
    metadata = []
    
    # topic_index 로드
    topic_index_path = Path("cache/articles/topic_index.json")
    if topic_index_path.exists():
        with open(topic_index_path, 'r', encoding='utf-8') as f:
            topic_index = json.load(f)
    else:
        topic_index = {}
    
    # 각 기사별로 메타데이터 수집
    for article_id, info in topic_index.items():
        cache_file = Path(f"cache/articles/{article_id}.json")
        
        article_meta = {
            'id': article_id,
            'title': info.get('main_title', 'Unknown'),
            'created_at': info.get('created_at', ''),
            'last_updated': info.get('last_updated', ''),
            'version': info.get('version', 1),
            'parent_id': info.get('parent_id'),
            'model': DEFAULT_MODEL,  # 환경 변수에서 가져온 기본값
            'prompt_tokens': 0,
            'completion_tokens': 0,
            'total_tokens': 0,
            'cost_usd': 0,
            'tags': info.get('tags', {'category_tags': [], 'content_tags': []})  # 태그 정보 추가
        }
        
        # article_metadata 디렉토리에서 토큰 정보 찾기
        # article_metadata의 파일명: article_YYYYMMDD_HHMMSS_metadata.json
        # topic_index의 created_at 시간과 가장 가까운 metadata 파일 찾기
        metadata_found = False
        if info.get('created_at'):
            try:
                # ISO 형식 날짜를 파싱
                dt = datetime.fromisoformat(info['created_at'])
                target_timestamp = dt.timestamp()
                
                # article_metadata 디렉토리에서 모든 파일 검색
                metadata_dir = Path("article_metadata")
                if metadata_dir.exists():
                    best_match = None
                    min_time_diff = float('inf')
                    
                    for metadata_file in metadata_dir.glob("article_*_metadata.json"):
                        # 파일명에서 시간 추출
                        filename = metadata_file.stem  # article_20250722_152043_metadata -> article_20250722_152043
                        parts = filename.split('_')
                        if len(parts) >= 3:
                            try:
                                # YYYYMMDD_HHMMSS 추출
                                date_str = parts[1]
                                time_str = parts[2]
                                file_dt = datetime.strptime(f"{date_str}_{time_str}", "%Y%m%d_%H%M%S")
                                file_timestamp = file_dt.timestamp()
                                
                                # 시간 차이 계산 (초 단위)
                                time_diff = abs(file_timestamp - target_timestamp)
                                
                                # 5분(300초) 이내의 가장 가까운 파일 찾기
                                if time_diff < 300 and time_diff < min_time_diff:
                                    min_time_diff = time_diff
                                    best_match = metadata_file
                            except:
                                continue
                    
                    # 가장 가까운 매치가 있으면 사용
                    if best_match:
                        with open(best_match, 'r', encoding='utf-8') as f:
                            token_metadata = json.load(f)
                            article_meta['model'] = token_metadata.get('model', DEFAULT_MODEL)
                            article_meta['prompt_tokens'] = token_metadata.get('prompt_tokens', 0)
                            article_meta['completion_tokens'] = token_metadata.get('completion_tokens', 0)
                            article_meta['total_tokens'] = token_metadata.get('total_tokens', 0)
                            article_meta['cost_usd'] = token_metadata.get('cost_usd', 0)
                            article_meta['api_calls'] = token_metadata.get('api_calls', 1)
                            metadata_found = True
                            
            except Exception as e:
                print(f"Error processing metadata for {article_id}: {e}")
        
        # 메타데이터를 찾지 못한 경우 - 토큰 정보 없음으로 표시
        # (TokenTracker 도입 이전 기사들은 토큰 정보가 없음)
        
        # 버전 히스토리 수
        version_history = info.get('version_history', [])
        article_meta['version_count'] = len(version_history) + 1  # 현재 버전 포함
        
        metadata.append(article_meta)
    
    # 날짜순 정렬 (최신순)
    metadata.sort(key=lambda x: x.get('last_updated', x.get('created_at', '')), reverse=True)
    return metadata

def calculate_statistics(metadata):
    """통계 계산"""
    daily_stats = defaultdict(lambda: {
        'articles': 0,
        'versions': 0,  # 버전 업데이트 수
        'total_tokens': 0,
        'prompt_tokens': 0,
        'completion_tokens': 0,
        'total_cost': 0
    })
    
    monthly_stats = defaultdict(lambda: {
        'articles': 0,
        'versions': 0,
        'total_tokens': 0,
        'prompt_tokens': 0,
        'completion_tokens': 0,
        'total_cost': 0
    })
    
    # 주제별 통계
    topic_stats = {}
    
    for article in metadata:
        date = article.get('created_at', '')[:10]  # YYYY-MM-DD
        month = article.get('created_at', '')[:7]   # YYYY-MM
        
        if date:
            daily_stats[date]['articles'] += 1
            if article.get('version', 1) > 1:
                daily_stats[date]['versions'] += 1
            daily_stats[date]['total_tokens'] += article.get('total_tokens', 0)
            daily_stats[date]['prompt_tokens'] += article.get('prompt_tokens', 0)
            daily_stats[date]['completion_tokens'] += article.get('completion_tokens', 0)
            daily_stats[date]['total_cost'] += article.get('cost_usd', 0)
        
        if month:
            monthly_stats[month]['articles'] += 1
            if article.get('version', 1) > 1:
                monthly_stats[month]['versions'] += 1
            monthly_stats[month]['total_tokens'] += article.get('total_tokens', 0)
            monthly_stats[month]['prompt_tokens'] += article.get('prompt_tokens', 0)
            monthly_stats[month]['completion_tokens'] += article.get('completion_tokens', 0)
            monthly_stats[month]['total_cost'] += article.get('cost_usd', 0)
        
        # 주제별 통계 (제목 기준)
        title = article.get('title', '')
        if title:
            if title not in topic_stats:
                topic_stats[title] = {
                    'count': 0,
                    'latest_version': 0,
                    'total_cost': 0
                }
            topic_stats[title]['count'] += 1
            topic_stats[title]['latest_version'] = max(
                topic_stats[title]['latest_version'],
                article.get('version', 1)
            )
            topic_stats[title]['total_cost'] += article.get('cost_usd', 0)
    
    return dict(daily_stats), dict(monthly_stats), topic_stats

def generate_admin_html():
    """어드민 페이지 HTML 생성 (버전 정보 포함)"""
    admin_password_hash = os.environ.get('ADMIN_PASSWORD_HASH')
    if not admin_password_hash:
        print("WARNING: ADMIN_PASSWORD_HASH not set. Admin page will not be accessible.")
        admin_password_hash = 'INVALID_HASH'  # This will prevent any login
    
    html_content = f"""<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KONA Admin Dashboard</title>
    <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
    <link rel="alternate icon" href="/static/favicon.svg">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans KR', sans-serif;
            background-color: #f5f5f5;
            color: #333;
        }}
        .login-container {{
            max-width: 400px;
            margin: 100px auto;
            padding: 40px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .login-container h1 {{
            margin-bottom: 30px;
            text-align: center;
            color: #1a73e8;
        }}
        .login-form input {{
            width: 100%;
            padding: 12px;
            margin-bottom: 20px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 16px;
        }}
        .login-form button {{
            width: 100%;
            padding: 12px;
            background: #1a73e8;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 16px;
            cursor: pointer;
        }}
        .login-form button:hover {{
            background: #1557b0;
        }}
        .admin-container {{
            display: none;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}
        .admin-header {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .admin-header h1 {{
            color: #1a73e8;
        }}
        .logout-btn {{
            padding: 8px 16px;
            background: #dc3545;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .stat-card h3 {{
            color: #666;
            font-size: 14px;
            margin-bottom: 10px;
        }}
        .stat-card .value {{
            font-size: 28px;
            font-weight: bold;
            color: #333;
        }}
        .stat-card .unit {{
            font-size: 14px;
            color: #666;
        }}
        .chart-container {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
            position: relative;
            height: 400px;
        }}
        .chart-container canvas {{
            max-height: 350px !important;
        }}
        .chart-container.donut-chart {{
            height: 450px;
        }}
        .chart-wrapper {{
            position: relative;
            height: 350px;
            margin: 0 auto;
            max-width: 350px;
        }}
        .chart-container h2 {{
            margin-bottom: 20px;
            color: #333;
        }}
        .articles-table {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .articles-table h2 {{
            margin-bottom: 20px;
            color: #333;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        th {{
            background: #f8f9fa;
            font-weight: 600;
        }}
        /* 열 너비 조정 */
        th:nth-child(1), td:nth-child(1) {{ width: 110px; }} /* 날짜 */
        th:nth-child(2), td:nth-child(2) {{ 
            width: 35%; 
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 0;
        }} /* 제목 */
        th:nth-child(3), td:nth-child(3) {{ width: 25%; }} /* 태그 */
        th:nth-child(4), td:nth-child(4) {{ width: 60px; }} /* 버전 */
        th:nth-child(5), td:nth-child(5) {{ width: 50px; }} /* 모델 */
        th:nth-child(6), td:nth-child(6) {{ width: 80px; }} /* P-T */
        th:nth-child(7), td:nth-child(7) {{ width: 80px; }} /* C-T */
        th:nth-child(8), td:nth-child(8) {{ width: 80px; }} /* 비용 */
        .version-badge {{
            background: #17a2b8;
            color: white;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
        }}
        .delete-btn {{
            padding: 4px 8px;
            background: #6c757d;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: not-allowed;
            font-size: 12px;
            opacity: 0.6;
        }}
        .cost {{
            color: #28a745;
            font-weight: 600;
        }}
        .error-message {{
            color: #dc3545;
            margin-bottom: 20px;
            text-align: center;
        }}
        .topic-stats {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        .topic-stats h2 {{
            margin-bottom: 20px;
            color: #333;
        }}
        .topic-item {{
            padding: 10px;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .topic-item:last-child {{
            border-bottom: none;
        }}
        .topic-name {{
            flex: 1;
            margin-right: 20px;
        }}
        .topic-meta {{
            display: flex;
            gap: 20px;
            font-size: 14px;
            color: #666;
        }}
        /* 태그 필터링 스타일 */
        .tag-filter-section {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        .tag-filter-section h3 {{
            margin-bottom: 15px;
            color: #333;
        }}
        .tag-buttons {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 15px;
        }}
        .tag-button {{
            padding: 6px 12px;
            border: 1px solid #ddd;
            border-radius: 20px;
            background: white;
            cursor: pointer;
            font-size: 14px;
            transition: all 0.3s;
        }}
        .tag-button:hover {{
            background: #f0f0f0;
        }}
        .tag-button.active {{
            background: #1a73e8;
            color: white;
            border-color: #1a73e8;
        }}
        .tag-reset-button {{
            padding: 6px 16px;
            background: #6c757d;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 14px;
            margin-left: 10px;
            display: none;
        }}
        .tag-reset-button:hover {{
            background: #5a6268;
        }}
        .tag-reset-button.visible {{
            display: inline-block;
        }}
        .tag-section-title {{
            font-weight: 600;
            color: #666;
            margin: 10px 0 5px 0;
            font-size: 14px;
        }}
        .tag-info {{
            display: inline-block;
            padding: 2px 8px;
            background: #e3f2fd;
            color: #1565c0;
            border-radius: 12px;
            font-size: 12px;
            margin-right: 4px;
        }}
        .tag-info.content-tag {{
            background: #f3e5f5;
            color: #7b1fa2;
        }}
    </style>
</head>
<body>
    <!-- 로그인 폼 -->
    <div class="login-container" id="loginContainer">
        <h1>KONA Admin</h1>
        <form class="login-form" onsubmit="return handleLogin(event)">
            <input type="password" id="password" placeholder="비밀번호 입력" required>
            <button type="submit">로그인</button>
            <div class="error-message" id="loginError"></div>
        </form>
    </div>

    <!-- 어드민 대시보드 -->
    <div class="admin-container" id="adminContainer">
        <div class="admin-header">
            <h1>KONA Admin Dashboard <span style="font-size: 0.5em; color: #666;">(지난 30일)</span></h1>
            <button class="logout-btn" onclick="handleLogout()">로그아웃</button>
        </div>

        <!-- 통계 카드 -->
        <div class="stats-grid">
            <div class="stat-card">
                <h3>총 기사 수</h3>
                <div class="value" id="totalArticles">0</div>
            </div>
            <div class="stat-card">
                <h3>고유 주제 수</h3>
                <div class="value" id="uniqueTopics">0</div>
            </div>
            <div class="stat-card">
                <h3>오늘 생성된 기사</h3>
                <div class="value" id="todayArticles">0</div>
            </div>
            <div class="stat-card">
                <h3>총 버전 업데이트</h3>
                <div class="value" id="totalVersions">0</div>
            </div>
            <div class="stat-card">
                <h3>총 토큰 사용량</h3>
                <div class="value" id="totalTokens">0</div>
            </div>
            <div class="stat-card">
                <h3>총 비용</h3>
                <div class="value"><span id="totalCost">₩0</span></div>
            </div>
        </div>

        <!-- 차트 -->
        <div class="chart-container">
            <h2>일별 비용 추이</h2>
            <canvas id="dailyCostChart"></canvas>
        </div>

        <div style="display: flex; gap: 20px; margin-bottom: 20px;">
            <div class="chart-container donut-chart" style="flex: 1;">
                <h2>토큰 사용량 기준</h2>
                <div class="chart-wrapper">
                    <canvas id="tokenChart"></canvas>
                </div>
            </div>
            <div class="chart-container donut-chart" style="flex: 1;">
                <h2>토큰 비용 기준</h2>
                <div class="chart-wrapper">
                    <canvas id="costChart"></canvas>
                </div>
            </div>
        </div>

        <!-- 태그 필터 섹션 -->
        <div class="tag-filter-section">
            <h3>태그 필터
                <button class="tag-reset-button" id="tagResetButton" onclick="resetTagFilter()">필터 초기화</button>
            </h3>
            
            <div class="tag-section-title">카테고리 태그</div>
            <div class="tag-buttons" id="categoryTagButtons">
                <!-- JavaScript로 채워짐 -->
            </div>
            
            <div class="tag-section-title">콘텐츠 태그 (상위 20개)</div>
            <div class="tag-buttons" id="contentTagButtons">
                <!-- JavaScript로 채워짐 -->
            </div>
        </div>

        <!-- 주제별 통계 -->
        <div class="topic-stats">
            <h2>주제별 버전 현황</h2>
            <div id="topicStatsContainer">
                <!-- JavaScript로 채워짐 -->
            </div>
        </div>

        <!-- 기사 목록 테이블 -->
        <div class="articles-table">
            <h2>최근 기사 목록</h2>
            <p style="font-size: 14px; color: #666; margin-bottom: 15px;">
                ※ M: Model (모델), P-T: Prompt Tokens (프롬프트 토큰), C-T: Completion Tokens (완성 토큰), n: {DEFAULT_MODEL}
            </p>
            <table>
                <thead>
                    <tr>
                        <th>날짜</th>
                        <th>제목</th>
                        <th>태그</th>
                        <th>버전</th>
                        <th>M</th>
                        <th>P-T</th>
                        <th>C-T</th>
                        <th>비용</th>
                    </tr>
                </thead>
                <tbody id="articlesTableBody">
                    <!-- JavaScript로 채워짐 -->
                </tbody>
            </table>
        </div>
    </div>

    <script>
        const ADMIN_PASSWORD_HASH = '{admin_password_hash}';
        let articlesData = [];
        let filteredArticlesData = [];
        let last30DaysArticles = []; // 30일 내 기사들
        let dailyStats = {{}};
        let monthlyStats = {{}};
        let topicStats = {{}};
        let selectedTags = new Set();
        let allTags = {{ category_tags: {{}}, content_tags: {{}} }};
        let USD_TO_KRW_RATE = 1400; // 기본값

        // SHA256 해시 함수
        async function sha256(message) {{
            const msgBuffer = new TextEncoder().encode(message);
            const hashBuffer = await crypto.subtle.digest('SHA-256', msgBuffer);
            const hashArray = Array.from(new Uint8Array(hashBuffer));
            return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
        }}

        // 로그인 처리
        async function handleLogin(event) {{
            event.preventDefault();
            const password = document.getElementById('password').value;
            const passwordHash = await sha256(password);
            
            if (passwordHash === ADMIN_PASSWORD_HASH) {{
                localStorage.setItem('adminAuth', 'true');
                document.getElementById('loginContainer').style.display = 'none';
                document.getElementById('adminContainer').style.display = 'block';
                loadData();
            }} else {{
                document.getElementById('loginError').textContent = '비밀번호가 올바르지 않습니다.';
            }}
        }}

        // 로그아웃 처리
        function handleLogout() {{
            localStorage.removeItem('adminAuth');
            location.reload();
        }}

        // 페이지 로드 시 인증 확인
        window.onload = function() {{
            if (localStorage.getItem('adminAuth') === 'true') {{
                document.getElementById('loginContainer').style.display = 'none';
                document.getElementById('adminContainer').style.display = 'block';
                loadData();
            }}
        }}

        // 데이터 로드
        async function loadData() {{
            try {{
                // 설정 로드
                const configResponse = await fetch('data/config.json');
                const config = await configResponse.json();
                USD_TO_KRW_RATE = config.USD_TO_KRW_RATE || 1400;
                
                // 메타데이터 로드
                const metadataResponse = await fetch('data/articles-metadata.json');
                articlesData = await metadataResponse.json();
                
                // 통계 로드
                const dailyResponse = await fetch('data/daily-stats.json');
                dailyStats = await dailyResponse.json();
                
                const monthlyResponse = await fetch('data/monthly-stats.json');
                monthlyStats = await monthlyResponse.json();
                
                const topicResponse = await fetch('data/topic-stats.json');
                topicStats = await topicResponse.json();
                
                updateDashboard();
            }} catch (error) {{
                console.error('데이터 로드 실패:', error);
            }}
        }}

        // 대시보드 업데이트
        function updateDashboard() {{
            // 30일 전 날짜 계산
            const today = new Date();
            const thirtyDaysAgo = new Date(today);
            thirtyDaysAgo.setDate(today.getDate() - 30);
            
            // 30일 내 기사만 필터링
            last30DaysArticles = articlesData.filter(article => {{
                const articleDate = new Date(article.created_at || article.last_updated);
                return articleDate >= thirtyDaysAgo;
            }});
            
            // 30일 내 고유 주제 수 계산
            const last30DaysTopics = new Set();
            last30DaysArticles.forEach(article => {{
                if (article.title) {{
                    last30DaysTopics.add(article.title);
                }}
            }});
            
            // 오늘 통계
            const todayStr = today.toISOString().split('T')[0];
            const todayData = dailyStats[todayStr] || {{}};
            
            // 30일 내 버전 업데이트된 기사 수
            const last30DaysVersions = last30DaysArticles.filter(a => a.version > 1).length;
            
            // 30일 내 총 토큰과 비용
            const last30DaysTokens = last30DaysArticles.reduce((sum, a) => sum + (a.total_tokens || 0), 0);
            const last30DaysCost = last30DaysArticles.reduce((sum, a) => sum + (a.cost_usd || 0), 0);
            
            // UI 업데이트
            document.getElementById('totalArticles').textContent = last30DaysArticles.length;
            document.getElementById('uniqueTopics').textContent = last30DaysTopics.size;
            document.getElementById('todayArticles').textContent = todayData.articles || 0;
            document.getElementById('totalVersions').textContent = last30DaysVersions;
            document.getElementById('totalTokens').textContent = last30DaysTokens.toLocaleString();
            document.getElementById('totalCost').textContent = 
                '₩' + (last30DaysCost * USD_TO_KRW_RATE).toFixed(1);
            
            // 태그 수집
            collectAllTags();
            
            // 태그 버튼 렌더링
            renderTagButtons();
            
            // 초기 필터링된 데이터 설정
            filteredArticlesData = [...articlesData];
            
            // 차트 그리기
            drawDailyCostChart();
            drawTokenChart();
            drawCostChart();
            
            // 주제별 통계 표시
            fillTopicStats();
            
            // 테이블 채우기
            fillArticlesTable();
        }}

        // 일별 비용 차트
        function drawDailyCostChart() {{
            const ctx = document.getElementById('dailyCostChart').getContext('2d');
            const dates = Object.keys(dailyStats).sort();
            const costs = dates.map(date => dailyStats[date].total_cost);
            
            // 동적으로 Y축 범위 계산
            const maxCost = Math.max(...costs);
            let stepSize;
            if (maxCost < 0.001) {{
                stepSize = 0.0001;
            }} else if (maxCost < 0.01) {{
                stepSize = 0.001;
            }} else if (maxCost < 0.1) {{
                stepSize = 0.01;
            }} else {{
                stepSize = 0.1;
            }}
            
            const yMax = maxCost * 1.2 || stepSize * 5;
            
            new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: dates,
                    datasets: [{{
                        label: '일별 비용 ($)',
                        data: costs,
                        borderColor: '#1a73e8',
                        backgroundColor: 'rgba(26, 115, 232, 0.1)',
                        borderWidth: 3,
                        pointRadius: 6,
                        pointBackgroundColor: '#1a73e8',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointHoverRadius: 8,
                        tension: 0.1,
                        fill: true
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{
                        y: {{
                            beginAtZero: true,
                            min: 0,
                            max: yMax,
                            ticks: {{
                                callback: function(value) {{
                                    if (value < 0.01) {{
                                        return '$' + value.toFixed(4);
                                    }} else if (value < 1) {{
                                        return '$' + value.toFixed(3);
                                    }} else {{
                                        return '$' + value.toFixed(2);
                                    }}
                                }},
                                stepSize: stepSize,
                                count: 6
                            }}
                        }},
                        x: {{
                            grid: {{
                                display: true,
                                color: 'rgba(0, 0, 0, 0.05)'
                            }}
                        }}
                    }},
                    plugins: {{
                        legend: {{
                            display: true,
                            position: 'top'
                        }},
                        tooltip: {{
                            callbacks: {{
                                label: function(context) {{
                                    return context.dataset.label + ': $' + context.parsed.y.toFixed(4);
                                }}
                            }}
                        }}
                    }}
                }}
            }});
        }}

        // 토큰 사용량 차트
        function drawTokenChart() {{
            const ctx = document.getElementById('tokenChart').getContext('2d');
            const totalPrompt = last30DaysArticles.reduce((sum, a) => sum + (a.prompt_tokens || 0), 0);
            const totalCompletion = last30DaysArticles.reduce((sum, a) => sum + (a.completion_tokens || 0), 0);
            
            new Chart(ctx, {{
                type: 'doughnut',
                data: {{
                    labels: ['Prompt Tokens', 'Completion Tokens'],
                    datasets: [{{
                        data: [totalPrompt, totalCompletion],
                        backgroundColor: ['#4285f4', '#34a853']
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        tooltip: {{
                            callbacks: {{
                                label: function(context) {{
                                    const label = context.label || '';
                                    const value = context.parsed;
                                    const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                    const percentage = ((value / total) * 100).toFixed(1);
                                    return `${{label}}: ${{value.toLocaleString()}} (${{percentage}}%)`;
                                }}
                            }}
                        }}
                    }}
                }}
            }});
        }}
        
        // 토큰 비용 차트
        function drawCostChart() {{
            const ctx = document.getElementById('costChart').getContext('2d');
            
            // 각 기사별로 prompt와 completion 비용 계산
            let totalPromptCost = 0;
            let totalCompletionCost = 0;
            
            last30DaysArticles.forEach(article => {{
                const promptTokens = article.prompt_tokens || 0;
                const completionTokens = article.completion_tokens || 0;
                const totalCost = article.cost_usd || 0;
                
                // 총 비용과 토큰 수를 이용해 단가 역산
                if (promptTokens + completionTokens > 0) {{
                    // 일반적으로 completion이 prompt보다 비싸므로 이를 고려한 비율 계산
                    // GPT-4.1-nano 기준: prompt $0.0001/1K, completion $0.0004/1K
                    const promptCost = (promptTokens / 1000) * 0.0001;
                    const completionCost = (completionTokens / 1000) * 0.0004;
                    
                    totalPromptCost += promptCost;
                    totalCompletionCost += completionCost;
                }}
            }});
            
            new Chart(ctx, {{
                type: 'doughnut',
                data: {{
                    labels: ['Prompt 비용', 'Completion 비용'],
                    datasets: [{{
                        data: [totalPromptCost, totalCompletionCost],
                        backgroundColor: ['#4285f4', '#34a853']
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        tooltip: {{
                            callbacks: {{
                                label: function(context) {{
                                    const label = context.label || '';
                                    const value = context.parsed;
                                    const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                    const percentage = ((value / total) * 100).toFixed(1);
                                    const krwValue = (value * USD_TO_KRW_RATE).toFixed(1);
                                    return `${{label}}: ₩${{krwValue}} (${{percentage}}%)`;
                                }}
                            }}
                        }}
                    }}
                }}
            }});
        }}

        // 주제별 통계 채우기
        function fillTopicStats() {{
            const container = document.getElementById('topicStatsContainer');
            container.innerHTML = '';
            
            // 30일 내 기사로부터 주제별 통계 재계산
            const last30DaysTopicStats = {{}};
            
            last30DaysArticles.forEach(article => {{
                const title = article.title;
                if (title) {{
                    if (!last30DaysTopicStats[title]) {{
                        last30DaysTopicStats[title] = {{
                            count: 0,
                            latest_version: 0,
                            total_cost: 0
                        }};
                    }}
                    last30DaysTopicStats[title].count += 1;
                    last30DaysTopicStats[title].latest_version = Math.max(
                        last30DaysTopicStats[title].latest_version,
                        article.version || 1
                    );
                    last30DaysTopicStats[title].total_cost += (article.cost_usd || 0);
                }}
            }});
            
            // 최신 버전이 높은 순으로 정렬
            const sortedTopics = Object.entries(last30DaysTopicStats)
                .sort((a, b) => b[1].latest_version - a[1].latest_version)
                .slice(0, 10);  // 상위 10개만
            
            sortedTopics.forEach(([title, stats]) => {{
                const div = document.createElement('div');
                div.className = 'topic-item';
                div.innerHTML = `
                    <div class="topic-name">${{title}}</div>
                    <div class="topic-meta">
                        <span>버전: <strong>v${{stats.latest_version}}</strong></span>
                        <span>총 ${{stats.count}}개</span>
                        <span>비용: ₩${{(stats.total_cost * USD_TO_KRW_RATE).toFixed(1)}}</span>
                    </div>
                `;
                container.appendChild(div);
            }});
        }}

        // 기사 테이블 채우기
        function fillArticlesTable() {{
            const tbody = document.getElementById('articlesTableBody');
            tbody.innerHTML = '';
            
            // 필터링된 데이터 사용
            const displayArticles = selectedTags.size > 0 ? filteredArticlesData : articlesData;
            
            displayArticles.slice(0, 20).forEach(article => {{
                const row = tbody.insertRow();
                const versionBadge = article.version > 1 ? 
                    `<span class="version-badge">v${{article.version}}</span>` : 'v1';
                
                // 태그 렌더링
                const tags = article.tags || {{category_tags: [], content_tags: []}};
                const categoryTags = tags.category_tags.map(tag => 
                    `<span class="tag-info">${{tag}}</span>`
                ).join('');
                const contentTags = tags.content_tags.slice(0, 3).map(tag => 
                    `<span class="tag-info content-tag">${{tag}}</span>`
                ).join('');
                const moreContentTags = tags.content_tags.length > 3 ? 
                    `<span class="tag-info content-tag">+${{tags.content_tags.length - 3}}</span>` : '';
                
                // 날짜와 시간 포맷팅 (년도 제거, 시:분 추가)
                let dateStr = '-';
                if (article.last_updated) {{
                    const [date, time] = article.last_updated.split('T');
                    const monthDay = date.substring(5); // MM-DD
                    const hourMin = time.substring(0, 5); // HH:MM
                    dateStr = `${{monthDay}} ${{hourMin}}`;
                }} else if (article.created_at) {{
                    const [date, time] = article.created_at.split('T');
                    const monthDay = date.substring(5); // MM-DD
                    const hourMin = time.substring(0, 5); // HH:MM
                    dateStr = `${{monthDay}} ${{hourMin}}`;
                }}
                
                // 비용을 원화로 변환
                const costInKRW = article.cost_usd ? (article.cost_usd * USD_TO_KRW_RATE).toFixed(1) : '-';
                
                // API 호출 횟수 포함한 completion tokens 표시
                let completionDisplay = article.completion_tokens ? article.completion_tokens.toLocaleString() : '-';
                if (article.api_calls && article.api_calls > 1) {{
                    completionDisplay += ` <small style="color: #666;">({{{{article.api_calls}}}}회)</small>`;
                }}
                
                row.innerHTML = `
                    <td>${{dateStr}}</td>
                    <td title="${{article.title || '제목 없음'}}">${{article.title || '제목 없음'}}</td>
                    <td>${{categoryTags}} ${{contentTags}} ${{moreContentTags}}</td>
                    <td>${{versionBadge}}</td>
                    <td>${{article.model === '{DEFAULT_MODEL}' ? 'n' : (article.model || 'GPT-4')}}</td>
                    <td>${{article.prompt_tokens ? article.prompt_tokens.toLocaleString() : '-'}}</td>
                    <td>${{completionDisplay}}</td>
                    <td class="cost">${{costInKRW !== '-' ? '₩' + costInKRW : '-'}}</td>
                `;
            }});
        }}
        
        // 모든 태그 수집
        function collectAllTags() {{
            allTags = {{ category_tags: {{}}, content_tags: {{}} }};
            
            last30DaysArticles.forEach(article => {{
                if (article.tags) {{
                    // 카테고리 태그 수집
                    article.tags.category_tags?.forEach(tag => {{
                        allTags.category_tags[tag] = (allTags.category_tags[tag] || 0) + 1;
                    }});
                    
                    // 콘텐츠 태그 수집
                    article.tags.content_tags?.forEach(tag => {{
                        allTags.content_tags[tag] = (allTags.content_tags[tag] || 0) + 1;
                    }});
                }}
            }});
        }}
        
        // 태그 버튼 렌더링
        function renderTagButtons() {{
            // 카테고리 태그 버튼
            const categoryContainer = document.getElementById('categoryTagButtons');
            categoryContainer.innerHTML = '';
            
            Object.entries(allTags.category_tags)
                .sort((a, b) => b[1] - a[1])  // 빈도순 정렬
                .forEach(([tag, count]) => {{
                    const button = document.createElement('button');
                    button.className = 'tag-button';
                    button.textContent = `${{tag}} (${{count}})`;
                    button.setAttribute('data-tag', tag);
                    button.onclick = () => toggleTag(button);
                    categoryContainer.appendChild(button);
                }});
            
            // 콘텐츠 태그 버튼 (상위 20개)
            const contentContainer = document.getElementById('contentTagButtons');
            contentContainer.innerHTML = '';
            
            Object.entries(allTags.content_tags)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 20)
                .forEach(([tag, count]) => {{
                    const button = document.createElement('button');
                    button.className = 'tag-button';
                    button.textContent = `${{tag}} (${{count}})`;
                    button.setAttribute('data-tag', tag);
                    button.onclick = () => toggleTag(button);
                    contentContainer.appendChild(button);
                }});
        }}
        
        // 태그 토글
        function toggleTag(button) {{
            const tag = button.getAttribute('data-tag');
            
            if (button.classList.contains('active')) {{
                button.classList.remove('active');
                selectedTags.delete(tag);
            }} else {{
                button.classList.add('active');
                selectedTags.add(tag);
            }}
            
            // 리셋 버튼 표시/숨김
            const resetButton = document.getElementById('tagResetButton');
            if (selectedTags.size > 0) {{
                resetButton.classList.add('visible');
            }} else {{
                resetButton.classList.remove('visible');
            }}
            
            // 필터링 수행
            applyTagFilter();
        }}
        
        // 태그 필터 적용
        function applyTagFilter() {{
            if (selectedTags.size === 0) {{
                filteredArticlesData = [...articlesData];
            }} else {{
                filteredArticlesData = articlesData.filter(article => {{
                    if (!article.tags) return false;
                    
                    // OR 연산 - 선택된 태그 중 하나라도 있으면 표시
                    const allArticleTags = [
                        ...(article.tags.category_tags || []),
                        ...(article.tags.content_tags || [])
                    ];
                    
                    return Array.from(selectedTags).some(tag => allArticleTags.includes(tag));
                }});
            }}
            
            // 테이블 다시 그리기
            fillArticlesTable();
            
            // 통계 업데이트
            updateFilteredStats();
        }}
        
        // 필터링된 통계 업데이트
        function updateFilteredStats() {{
            const displayArticles = selectedTags.size > 0 ? filteredArticlesData : articlesData;
            
            // 필터링된 기사 수 표시 (선택적)
            const totalArticlesElem = document.getElementById('totalArticles');
            if (selectedTags.size > 0) {{
                totalArticlesElem.textContent = `${{displayArticles.length}} / ${{articlesData.length}}`;
            }} else {{
                totalArticlesElem.textContent = articlesData.length;
            }}
        }}
        
        // 태그 필터 리셋
        function resetTagFilter() {{
            selectedTags.clear();
            
            // 모든 태그 버튼의 active 클래스 제거
            document.querySelectorAll('.tag-button.active').forEach(button => {{
                button.classList.remove('active');
            }});
            
            // 리셋 버튼 숨김
            document.getElementById('tagResetButton').classList.remove('visible');
            
            // 필터 초기화
            applyTagFilter();
        }}
    </script>
</body>
</html>"""
    
    return html_content

def generate_admin_page():
    """어드민 페이지 및 관련 데이터 생성 (버전 2)"""
    output_dir = Path("output/admin")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    data_dir = output_dir / "data"
    data_dir.mkdir(exist_ok=True)
    
    # 메타데이터 수집
    metadata = collect_article_metadata()
    
    # 통계 계산
    daily_stats, monthly_stats, topic_stats = calculate_statistics(metadata)
    
    # JSON 파일 저장
    with open(data_dir / "articles-metadata.json", 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    with open(data_dir / "daily-stats.json", 'w', encoding='utf-8') as f:
        json.dump(daily_stats, f, ensure_ascii=False, indent=2)
    
    with open(data_dir / "monthly-stats.json", 'w', encoding='utf-8') as f:
        json.dump(monthly_stats, f, ensure_ascii=False, indent=2)
    
    with open(data_dir / "topic-stats.json", 'w', encoding='utf-8') as f:
        json.dump(topic_stats, f, ensure_ascii=False, indent=2)
    
    # 환율 정보 저장
    with open(data_dir / "config.json", 'w', encoding='utf-8') as f:
        json.dump({'USD_TO_KRW_RATE': USD_TO_KRW_RATE}, f)
    
    # HTML 생성
    html_content = generate_admin_html()
    with open(output_dir / "index.html", 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Admin page generated with {len(metadata)} articles")
    print(f"Unique topics: {len(topic_stats)}")
    print(f"Daily stats: {len(daily_stats)} days")
    print(f"Monthly stats: {len(monthly_stats)} months")

if __name__ == "__main__":
    generate_admin_page()