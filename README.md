# nbpipe — 네이버 블로그 자동 초안 파이프라인

**경제 · 투자 · 부업 · 부동산** 니치에 특화된, **네이버 블로그 초안 파이프라인**입니다.
네이버 **홈판(홈피드)** 노출과 검색 상위노출 알고리즘(**C-Rank / D.I.A. / D.I.A.+**)을 학습해,
키워드 발굴 → **작성 브리핑** → (본문은 세션의 Claude/사람이 직접 작성) → SEO·컴플라이언스 자가검수 → 붙여넣기용 초안 출력까지 이어줍니다.

> 💡 **본문 작성에 LLM API 키가 필요 없습니다.**
> 파이프라인은 키워드·글감·작성 브리핑까지 만들고, **본문은 이 세션의 Claude(또는 사람)가 직접 씁니다.**
> 작성한 글을 `ingest` 하면 검수·출력이 됩니다. (레퍼런스 블로그 톤앤매너 학습 결과가 브리핑에 자동 주입됩니다.)

> ⚠️ **이 도구는 글을 자동으로 "발행"하지 않습니다.**
> 네이버 글쓰기 API는 2020년 종료됐고, 셀레니움/매크로 자동 발행은 ToS 위반 + 계정 정지·저품질 위험이 큽니다.
> 그래서 **생성(브리핑) → 작성 → 검수(사람) → 발행(사람)** 구조로 설계됐습니다.
> 완성된 초안을 검토·수정한 뒤 **직접 네이버 에디터에 붙여넣어** 발행하세요. (네이버 자격증명을 저장하지 않습니다.)

학습 정리: **[`knowledge/hompan.md`](knowledge/hompan.md)** (홈판/알고리즘) · **[`knowledge/style_reference.md`](knowledge/style_reference.md)** (레퍼런스 톤앤매너 가이드).

---

## 파이프라인 구조

```
1. 수집(collect)   시드주제 + 네이버 자동완성 (+선택: DataLab, 구글 트렌드)
        ↓
2. 선정(select)    소스 병합·스코어링 → 핵심/보조 키워드 & 글감(TopicPlan)
        ↓
3. 브리핑(brief)   홈판/C-Rank/DIA 규칙 + 레퍼런스 톤앤매너 + front-matter 템플릿
        ↓
   ✍️ 작성          이 세션의 Claude(또는 사람)가 브리핑대로 본문 작성
        ↓
4. 인제스트(ingest) 작성한 글 → SEO 자가진단 + 투자권유·과장광고 컴플라이언스 체크
        ↓
5. 출력(output)    Markdown(검토용) + HTML(붙여넣기용) 초안 파일
        ↓
6. 기록(store)     SQLite 실행 로그(중복 주제 회피·성과 추적)
```

핵심 설계 원칙(리서치 반영):
- **투트랙 intent**: `homefeed`(홈판, 기본) vs `search`(검색형) — 분량·제목·발행시간 규칙이 달라집니다.
- **고유성 우선**: 실경험·구체 수치·표/체크리스트를 강제해 "복붙 불가한" 문서로 만듭니다(D.I.A.+ 대응).
- **정직성**: 없는 통계를 만들지 않고, 최신 수치는 `[확인 필요]` 자리표시자로 남깁니다.
- **컴플라이언스**: 투자(자본시장법)·부동산(표시광고법)·부업(불법금융광고) 위반 문구를 자동 차단·경고합니다.

---

## 설치

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt      # 핵심 + 선택 의존성
# 또는 개발 설치
pip install -e .
```

- 필수: `requests`, `PyYAML`, `python-dotenv`, `beautifulsoup4` (LLM API 의존성 없음)
- 선택: `pytrends`(구글 트렌드), `rich`(예쁜 출력)

## 설정

### 1) 비밀키 (`.env`) — 전부 선택
```bash
cp .env.example .env
```
본문은 세션에서 직접 쓰므로 LLM 키가 필요 없습니다. DataLab 을 쓰려면:
- `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` — 선택 (DataLab 검색어 트렌드)

### 2) 파이프라인 설정 (`config/config.yaml`)
```bash
cp config/config.example.yaml config/config.yaml
```
모델, 수집기 on/off, SEO 임계값, 출력 포맷 등을 조정합니다. (없으면 예시값으로 동작)

### 3) 니치별 주제 (`niches/*.yaml`)
`niches/economy.yaml`, `investing.yaml`, `sidejob.yaml`, `realestate.yaml` 의
`seed_topics` 를 **원하는 주제로 자유롭게 수정**하세요. 이게 키워드 발굴의 출발점입니다.

---

## 사용법

```bash
# 0) 상태 점검 (키/의존성/토글)
nbpipe doctor

# 1) 키워드 수집·선정 결과 확인 (실 네이버 자동완성)
nbpipe keywords 투자 --topic ETF --topic 배당주

# 2) 글감(키워드 기획안)만 확인
nbpipe plan 부동산 --topic 청약 --count 3

# 3) 작성 브리핑 생성 (수집→선정→브리핑 파일)
nbpipe brief 경제 --topic 기준금리 --count 2               # 홈판형(기본)
nbpipe brief 투자 --topic ETF --intent search             # 검색형
#   → output/briefs/*.md 생성. 파일의 가이드(홈판 규칙 + 톤앤매너)를 따라 본문을 채운다.

# 4) 작성한 글 인제스트 (검수→초안 출력)
nbpipe ingest output/briefs/economy_01_기준금리_brief.md

# 5) 실행 기록
nbpipe history
```

**작성 흐름 요약**: `brief` 로 템플릿 파일을 받고 → front-matter 의 빈 칸(title/tags/summary/image_prompts)과
`## 소제목` 아래 본문을 채운 뒤 → `ingest` 로 검수·출력. (브리핑 파일 자체가 `ingest` 입력이 됩니다.)

- 니치는 한글(`경제/투자/부업/부동산`) 또는 영문(`economy/investing/sidejob/realestate`) 모두 가능.
- `--intent homefeed`(기본, 홈판 겨냥) / `--intent search`(검색 상위노출 겨냥).
- 산출물은 `output/` 에 `YYYYMMDD_니치_슬러그.md` / `.html` 로 저장됩니다.
  - `.md` = 메타·SEO리포트·이미지가이드·발행 체크리스트가 포함된 **검토용 문서**
  - `.html` = 네이버 스마트에디터에 그대로 붙여넣을 **정갈한 본문**

### 작성 파일 포맷 (front-matter + 본문)
```markdown
---
niche: economy            # 경제|투자|부업|부동산
intent: homefeed          # homefeed|search
primary_keyword: 기준금리
secondary_keywords: [기준금리 인하, 대출 이자]
title: 기준금리 인하되면 내 대출이자 얼마나 줄까
tags: [기준금리, 금리, 대출, 예금, 경제]
summary: |
  도입부(첫 문단) 훅...
image_prompts:
  - position: 도입부 아래
    alt: 한국은행 기준금리 추이
    prompt: 기준금리 그래프 캡처
---
## 첫 소제목
본문...
```

> `PYTHONPATH=src python -m nbpipe.cli ...` 로도 실행할 수 있습니다(설치 전).

---

## SEO 자가진단 & 컴플라이언스

생성된 초안은 발행 전 자동으로 점수화됩니다(비공식 알고리즘 기반 **자가진단** 용도):

| 항목 | 기준(config로 조정 가능) |
|---|---|
| 제목 길이 / 키워드 앞쪽 배치 / 키워드 1회 | 12~30자, 앞 15자 내, 제목 반복 금지 |
| 본문 분량 | 홈피드형 2,000자+ / 검색형 1,700자+ |
| 소제목·이미지·태그 | 소제목 3+, 이미지 6+, 태그 5~10 |
| 핵심 키워드 반복 | 본문 3~6회 (6회 초과 스터핑 경고) |
| 고유성 요소 | 표/구체 수치/체크리스트 1개+ |
| 정형 서론·유사문서 위험 | AI 티 나는 서론·중복 문장 감지 |

컴플라이언스 체커는 니치별 규제 문구를 차단/경고합니다:
- **투자**: 수익/원금 보장, 확정·목표 수익률, 리딩, 직접 매수 권유 → 차단 + 면책문구 권장
- **부동산**: 확정 프리미엄, 시세차익 보장, 근거 없는 최저가/조망권 최고 → 차단
- **부업**: 수익 보장, 누구나 고수익, 돈 복사 → 차단
- **공통**: 제휴/쿠팡파트너스 링크 시 **광고/제휴 표시** 누락 차단(뒷광고 방지)

> ⚠️ 법률 자문이 아니며 완전한 규제 준수를 보장하지 않습니다. 발행 전 사람의 최종 확인이 필요합니다.

---

## 프로젝트 구조

```
Naver-Blog/
├── knowledge/
│   ├── hompan.md               # 홈판/알고리즘 학습 정리 (리서치 산출물)
│   └── style_reference.md      # 레퍼런스 블로그 톤앤매너 가이드 (학습 산출물)
├── config/config.example.yaml  # 파이프라인 설정
├── niches/*.yaml               # 니치별 시드주제·앵글·제외어
├── src/nbpipe/
│   ├── cli.py                  # CLI (doctor/keywords/plan/brief/ingest/history)
│   ├── pipeline.py             # 오케스트레이션
│   ├── authoring.py            # 작성 브리핑 생성 + 작성물 파싱(front-matter)
│   ├── config.py, models.py    # 설정·데이터 모델
│   ├── collectors/             # 자동완성·(연관검색어)·DataLab·구글트렌드·시드
│   ├── analysis/               # 키워드 병합·스코어링·글감 생성
│   ├── generation/             # 작성 규칙(브리핑용 프롬프트 조립)
│   ├── seo/                    # SEO 스코어러 + 컴플라이언스
│   ├── output/                 # Markdown/HTML 초안 출력
│   └── store/                  # SQLite 실행 로그
└── tests/                      # pytest
```

## 개발

```bash
python -m pytest -q          # 테스트 (네트워크/ API 불필요)
```

---

## 로드맵 (리서치가 제안한 다음 단계)

- 스마트블록 세부주제 크롤러(연관검색어 폐지 대체), 경쟁 상위글 벤치마킹(글자수·이미지 수 자동 목표화)
- 발행 직후 헬스체크(제목 전체검색 → 최상단 노출 확인), 유사문서/이미지 pHash 중복 검사
- 성과 지표(홈판 유입 비중·체류시간·공감/댓글) 수집 → A/B 개선 루프
- 클립(숏폼) 스크립트 동시 생성, AI 브리핑 인용형 Q&A 구조 강화

## 라이선스
MIT
