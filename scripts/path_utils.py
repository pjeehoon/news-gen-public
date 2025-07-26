"""
Copyright (c) 2025 pjeehoon and KONA Project Contributors
This file is part of KONA (Korean Open News by AI).
Unauthorized commercial use is prohibited.
See LICENSE file for details.
"""

"""
경로 관련 유틸리티 함수들
모든 스크립트가 프로젝트 루트에서 실행되도록 지원
"""

import os
from pathlib import Path

def get_project_root():
    """프로젝트 루트 디렉토리 경로를 반환"""
    # 이 파일이 scripts 폴더에 있으므로, 부모 디렉토리가 프로젝트 루트
    current_file = Path(__file__).resolve()
    return current_file.parent.parent

def get_output_dir():
    """output 디렉토리 경로를 반환"""
    return get_project_root() / "output"

def get_smart_articles_dir():
    """smart_articles 디렉토리 경로를 반환"""
    return get_output_dir() / "smart_articles"

def get_cache_dir():
    """cache 디렉토리 경로를 반환"""
    return get_project_root() / "cache"

def get_scripts_dir():
    """scripts 디렉토리 경로를 반환"""
    return get_project_root() / "scripts"

def ensure_output_dirs():
    """필요한 출력 디렉토리들을 생성"""
    dirs = [
        get_output_dir(),
        get_smart_articles_dir(),
        get_output_dir() / "trends",
        get_cache_dir() / "articles"
    ]
    for dir_path in dirs:
        dir_path.mkdir(parents=True, exist_ok=True)