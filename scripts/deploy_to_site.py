#!/usr/bin/env python3
"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

"""
로컬에서 생성한 기사를 kona-news-site로 배포하는 스크립트
"""

import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

def run_command(cmd, cwd=None):
    """명령어 실행"""
    print(f"실행: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"에러: {result.stderr}")
        return False
    return True

def deploy_to_site():
    """로컬 기사를 사이트로 배포"""
    
    # DEPLOY_TOKEN 확인
    deploy_token = os.getenv('DEPLOY_TOKEN')
    if not deploy_token:
        print("ERROR: DEPLOY_TOKEN이 설정되지 않았습니다!")
        print("다음과 같이 설정하세요:")
        print("export DEPLOY_TOKEN=your_github_personal_access_token")
        return False
    
    # 임시 디렉토리 생성
    temp_dir = Path("/tmp/kona_deploy")
    temp_dir.mkdir(exist_ok=True)
    
    # Git 설정
    run_command('git config --global user.name "KONA News Bot"')
    run_command('git config --global user.email "actions@github.com"')
    
    # 기존 deploy 디렉토리 제거
    deploy_dir = temp_dir / "deploy_repo"
    if deploy_dir.exists():
        run_command(f"rm -rf {deploy_dir}")
    
    # 배포 리포지토리 클론
    print("\n1. 배포 리포지토리 클론...")
    if not run_command(f"git clone https://{deploy_token}@github.com/pjeehoon/kona-news-site.git deploy_repo", cwd=temp_dir):
        return False
    
    # 기존 기사 정보 출력
    print("\n2. 기존 기사 확인...")
    if (deploy_dir / "articles").exists():
        existing_articles = list((deploy_dir / "articles").glob("*.html"))
        print(f"   - 기존 배포 사이트에서 {len(existing_articles)}개의 기사 발견")
    
    # 특정 파일들만 삭제 (기사는 유지)
    print("\n3. 기존 파일 정리...")
    files_to_remove = ["index.html", "admin/index.html"]
    for file in files_to_remove:
        file_path = deploy_dir / file
        if file_path.exists():
            file_path.unlink()
    
    if (deploy_dir / "admin/data").exists():
        run_command(f"rm -rf {deploy_dir}/admin/data")
    
    # 새 파일 복사 (articles 폴더는 제외하고 복사)
    print("\n4. 새 파일 복사...")
    output_dir = Path("output")
    if output_dir.exists():
        # articles 폴더를 제외한 모든 파일/폴더 복사
        for item in output_dir.iterdir():
            if item.name != "articles":
                if item.is_file():
                    run_command(f"cp {item} {deploy_dir}/")
                else:
                    run_command(f"cp -r {item} {deploy_dir}/")
        
        # output/articles가 있으면 모든 기사 복사 (기존 + 새로운)
        output_articles_dir = output_dir / "articles"
        if output_articles_dir.exists():
            (deploy_dir / "articles").mkdir(exist_ok=True)
            article_files = list(output_articles_dir.glob("*.html"))
            print(f"   - output/articles에서 {len(article_files)}개의 기사 파일 발견")
            run_command(f"cp -r {output_articles_dir}/* {deploy_dir}/articles/")
        
        # smart_articles도 articles로 복사
        smart_articles_dir = output_dir / "smart_articles"
        if smart_articles_dir.exists():
            (deploy_dir / "articles").mkdir(exist_ok=True)
            article_files = list(smart_articles_dir.glob("*.html"))
            print(f"   - smart_articles에서 {len(article_files)}개의 기사 파일 발견")
            run_command(f"cp {smart_articles_dir}/*.html {deploy_dir}/articles/")
            
        # 최종 결과 확인
        final_articles = list((deploy_dir / "articles").glob("*.html"))
        print(f"   - 최종적으로 {len(final_articles)}개의 기사가 articles 폴더에 있음")
    
    # 추가 파일 복사
    print("\n5. 추가 파일 복사...")
    # topic_index.json 복사 (중복 제거를 위해 필요)
    if Path("cache/articles/topic_index.json").exists():
        run_command(f"cp cache/articles/topic_index.json {deploy_dir}/")
        print("   - topic_index.json 복사 완료")
    
    if Path("news_data/trends").exists():
        (deploy_dir / "trends").mkdir(exist_ok=True)
        run_command(f"cp news_data/trends/*.html {deploy_dir}/trends/ 2>/dev/null || true")
    
    if Path("multi_article_analysis").exists():
        (deploy_dir / "multi_article_analysis").mkdir(exist_ok=True)
        run_command(f"cp multi_article_analysis/*.json {deploy_dir}/multi_article_analysis/ 2>/dev/null || true")
    
    # static 파일 복사
    if Path("output/static").exists():
        run_command(f"cp -r output/static {deploy_dir}/")
        print("   - static 파일 복사 완료")
    
    # 배포 디렉토리에서 모든 기사를 포함한 index.html 재생성
    print("\n5.5. 모든 기사를 포함한 index.html 재생성...")
    current_dir = os.getcwd()
    os.chdir(deploy_dir)
    
    # generate_unified_index.py를 배포 디렉토리에서 실행
    generate_script = Path(current_dir) / "scripts" / "generate_unified_index.py"
    if generate_script.exists():
        # Python 스크립트를 직접 실행하여 모든 기사 포함
        result = run_command(f"python {generate_script}")
        
        # 생성된 index.html 확인
        index_file = deploy_dir / "index.html"
        if index_file.exists():
            # 파일 크기와 기사 수 확인
            file_size = index_file.stat().st_size
            with open(index_file, 'r', encoding='utf-8') as f:
                content = f.read()
                article_count = content.count('class="article-card"')
                print(f"   - index.html 생성 완료: {file_size:,} bytes, {article_count}개 기사 포함")
        else:
            print("   - ⚠️  index.html 생성 실패")
    
    os.chdir(current_dir)
    
    # Admin 페이지 생성
    print("\n5.6. Admin 페이지 생성...")
    admin_script = Path(current_dir) / "scripts" / "generate_admin_page.py"
    if admin_script.exists():
        # Admin 페이지 생성
        result = run_command(f"python {admin_script}")
        
        # 생성된 admin 페이지를 배포 디렉토리로 복사
        admin_output = Path(current_dir) / "output" / "admin"
        if admin_output.exists():
            deploy_admin_dir = deploy_dir / "admin"
            run_command(f"cp -r {admin_output} {deploy_dir}/")
            print("   - Admin 페이지 생성 및 복사 완료")
        else:
            print("   - ⚠️  Admin 페이지 생성 실패")
    
    os.chdir(current_dir)
    
    # Git commit & push
    print("\n6. Git commit & push...")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S KST")
    
    os.chdir(deploy_dir)
    run_command("git add .")
    
    # 변경사항 확인
    result = subprocess.run("git status --porcelain", shell=True, capture_output=True, text=True)
    if not result.stdout:
        print("변경사항이 없습니다.")
        return True
    
    # Commit and push
    run_command(f'git commit -m "로컬 업데이트 - {timestamp}"')
    
    if run_command("git push origin main"):
        print(f"\n✅ 배포 완료!")
        print(f"사이트 확인: https://kona-news-site.pages.dev/")
        return True
    else:
        print("\n❌ 배포 실패!")
        return False

if __name__ == "__main__":
    # 어드민 페이지 먼저 생성
    print("어드민 페이지 생성 중...")
    os.system("python scripts/generate_admin_page.py")
    
    # 배포 실행
    deploy_to_site()