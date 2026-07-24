"""작성 가이드(브리핑) 규칙.

본문은 이 세션의 Claude(또는 사람)가 직접 작성한다. 이 패키지는 홈판/C-Rank/
DIA 최적화 '작성 규칙'을 제공해 브리핑에 주입한다. (자동 API 생성 없음)
"""
from nbpipe.generation.prompts import build_system_prompt

__all__ = ["build_system_prompt"]
