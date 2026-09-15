# 칭찬고래

> AI 감정 재구성과 친구 응원을 결합한 자기칭찬 기반 소셜 플랫폼

### 1. 프로젝트 소개

칭찬고래는 사용자가 하루의 작은 성취를 기록하고, 친구와 서로 응원하며 자기칭찬 습관을 만들어 가는 iOS·Android 모바일 서비스입니다.

청년층은 높은 성취 기준 때문에 자신의 노력을 과소평가하거나 자기비판에 빠지기 쉽습니다. 칭찬고래는 “세 시간밖에 못했다”를 “세 시간이나 해냈다”로 바라볼 수 있도록 돕고, 이 긍정적인 시선이 친구 간의 응원으로 이어지는 선순환을 만드는 것을 목표로 합니다.

AI는 사용자의 글을 대신 완성하지 않습니다. 일기 원문과 의미적으로 비슷한 과거 기록을 참고해 2~4문장의 짧은 칭찬·코칭 한마디를 제공하고, 사용자가 직접 자신의 표현으로 글을 완성하도록 돕습니다.

주요 기능은 다음과 같습니다.

- Google·Kakao·Apple 소셜 로그인
- 400자 이내 자기칭찬 기록, 사진 첨부 및 공개 범위 설정
- 과거 기록을 반영한 AI 칭찬 코칭과 최대 3회의 재생성
- 친구의 글을 확인하고 댓글·좋아요로 응원하는 소셜 피드
- 캘린더형 보관함, 작성 스트릭 및 기록 통계
- 친구 활동과 반응에 대한 푸시 알림
- 개인정보 마스킹, 유해·위기 표현 감지 및 안전 응답
- PostHog 기반 사용자 행동 분석

### 2. 팀소개

| 이름 | 학번 | 연락처 | 담당 |
| --- | --- | --- | --- |
| 서혜민 | 202355544 | gp4077@pusan.ac.kr | PM·기획·프론트엔드 |
| 김태란 | 202355529 | taeran4767@pusan.ac.kr | 서비스 개발·인프라 |
| 오지현 | 202355640 | zeehy78@pusan.ac.kr | AI 파이프라인·AI 서버 |

### 3. 시스템 구성도

![칭찬고래 시스템 구성도](docs/architecture_diagram.png)

칭찬고래는 React Native/Expo 모바일 앱, Supabase 서비스 백엔드, FastAPI AI 서버의 세 계층으로 구성됩니다.

- 모바일 앱은 Supabase Auth를 통한 인증과 PostgreSQL·Storage 기반의 게시글, 댓글, 친구, 알림 및 이미지 데이터를 사용합니다.
- 서버 처리가 필요한 신고, 계정 삭제, 푸시 알림은 Supabase Edge Functions와 DB Trigger가 담당합니다.
- AI 요청은 AWS ECS Fargate에서 실행되는 FastAPI 서버로 전달되며, 서버는 Supabase JWT를 검증한 뒤 개인정보를 마스킹하고 정책 위반 여부를 확인합니다.
- `text-embedding-3-small`과 pgvector로 관련 과거 기록 및 few-shot 예시를 검색하고, `gpt-4o-mini`로 칭찬 코칭 문장을 생성합니다.
- 생성 결과는 말투, 문장 수, 금칙 표현 규칙을 검증하며 실패하면 최대 1회 자동 보정합니다.
- Docker 이미지는 Amazon ECR에 저장하고, GitHub Actions와 AWS OIDC로 배포합니다. 비밀값은 AWS Secrets Manager로 관리합니다.

#### 사용 기술

| 구분 | 기술 |
| --- | --- |
| Mobile | React Native 0.81.5, React 19.1.0, Expo SDK 54, Expo Router 6 |
| Service Backend | Supabase PostgreSQL, Auth, RLS, Storage, Edge Functions, pgvector |
| AI Server | Python 3.11, FastAPI, Uvicorn |
| AI | OpenAI API (`gpt-4o-mini`, `text-embedding-3-small`, Moderation API) |
| Infrastructure | Docker, Amazon ECR, AWS ECS Fargate, AWS Secrets Manager, Cloudflare |
| CI/CD | GitHub Actions, AWS OIDC, EAS Build, TestFlight |
| Monitoring & Analytics | Amazon CloudWatch, Server-Timing, PostHog |
| Notification & Email | Expo Push Notifications, Resend |

### 4. 소개 및 시연 영상


[![부산대학교 정보컴퓨터공학부 소개](http://img.youtube.com/vi/zh_gQ_lmLqE/0.jpg)](https://youtu.be/zh_gQ_lmLqE)


### 5. 설치 및 사용법

#### 5.1. 사전 준비

- Node.js 20 이상과 npm
- Python 3.11
- Expo Go 또는 iOS·Android 개발 환경
- Supabase 프로젝트
- AI 기능 사용 시 OpenAI API 키
- Docker(선택 사항)

#### 5.2. 모바일 앱 실행

```bash
cd whale-app
npm install
```

`whale-app/.env` 파일에 다음 값을 설정합니다.

```env
EXPO_PUBLIC_SUPABASE_URL=your_supabase_url
EXPO_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
```

개발 서버를 실행합니다.

```bash
npm run start
```

터미널에 표시되는 QR 코드를 Expo Go로 스캔하거나, 아래 명령으로 에뮬레이터·시뮬레이터에서 실행할 수 있습니다.

```bash
npm run android
npm run ios
```

#### 5.3. AI 서버 실행

```bash
cd whale-AI
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

`whale-AI/.env` 파일에 다음 값을 설정합니다. 실제 키가 포함된 `.env` 파일은 저장소에 커밋하지 않습니다.

```env
OPENAI_API_KEY=your_openai_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_service_role_key
```

Supabase SQL Editor에서 `whale-AI/schema.sql`을 한 번 실행한 뒤 서버를 시작합니다.

```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

- 상태 확인: <http://127.0.0.1:8000/health>
- API 문서: <http://127.0.0.1:8000/docs>

Docker를 사용할 경우 다음과 같이 실행할 수 있습니다.

```bash
docker build -t whale-ai ./whale-AI
docker run --rm -p 8000:8000 --env-file ./whale-AI/.env whale-ai
```
