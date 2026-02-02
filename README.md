# Vapi Webhook Server for OpenClaw

폴리나와 전화 통화를 가능하게 하는 Vapi.ai 웹훅 서버 (Vercel 배포용)

## 기능

- ✅ Vapi.ai 웹훅 수신 및 처리
- ✅ Channel.io TTS 통합 (한국어 고품질 음성)
- ✅ OpenClaw 통합 (function calling)
- ✅ Serverless 배포 (Vercel)
- ✅ 환경 변수 보안 관리

## 배포 가이드

### 1. 사전 준비

```bash
# Vercel CLI 설치 (없다면)
npm install -g vercel

# Vercel 로그인
vercel login
```

### 2. 환경 변수 준비

배포 전에 필요한 환경 변수:
- `VAPI_API_KEY`: Vapi.ai API 키
- `VAPI_PHONE_NUMBER`: Vapi 전화번호 ID
- `WEBHOOK_BASE_URL`: Vercel 배포 URL (자동 설정됨)

### 3. Git 레포 생성

```bash
cd vapi-webhook-server
git init
git add .
git commit -m "Initial commit: Vapi webhook server for Vercel"

# GitHub에 레포 생성 후
git remote add origin https://github.com/yourusername/vapi-webhook-server.git
git push -u origin main
```

### 4. Vercel 배포

```bash
# 프로젝트 디렉토리에서
vercel

# 프로덕션 배포
vercel --prod
```

배포 과정에서 환경 변수 설정:
```bash
vercel env add VAPI_API_KEY
# 값 입력: cf367f41-0259-44f7-824a-84d1b6fd6896

vercel env add VAPI_PHONE_NUMBER
# 값 입력: 7db596d2-f38d-482a-a9f6-20024162c16b
```

### 5. Webhook URL 업데이트

배포 완료 후 Vercel URL 확인:
```
https://vapi-webhook-server-xxx.vercel.app
```

Vapi Assistant 설정에서 Webhook URL 업데이트:
```
https://vapi-webhook-server-xxx.vercel.app/api/webhook/vapi
```

### 6. 테스트

```bash
# Health check
curl https://vapi-webhook-server-xxx.vercel.app/health

# 예상 응답:
{
  "status": "healthy",
  "service": "vapi-openclaw-webhook",
  "timestamp": "2026-02-03T00:00:00",
  "channel_tts": true,
  "environment": "vercel"
}
```

테스트 전화:
```bash
# Vapi API로 전화 걸기
curl -X POST https://api.vapi.ai/call/phone \
  -H "Authorization: Bearer $VAPI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "assistantId": "415cf97f-8cbe-4359-bd0f-8f4aae64ff65",
    "phoneNumberId": "7db596d2-f38d-482a-a9f6-20024162c16b",
    "customer": {
      "number": "+821030682129"
    }
  }'
```

## 환경 변수

| 변수 | 설명 | 필수 |
|------|------|------|
| `VAPI_API_KEY` | Vapi.ai API 키 | ✅ |
| `VAPI_PHONE_NUMBER` | Vapi 전화번호 ID | ✅ |
| `WEBHOOK_BASE_URL` | Webhook 기본 URL | 선택 (자동 설정) |
| `VAPI_WEBHOOK_SECRET` | Webhook 서명 검증 | 선택 |
| `OPENCLAW_API_URL` | OpenClaw Gateway URL | 선택 |

## 엔드포인트

### Health Check
```
GET /health
```

### Webhook
```
POST /api/webhook/vapi
```

### Custom TTS (Channel.io)
```
POST /api/webhook/vapi/tts
```

## 로컬 개발

```bash
# 가상 환경 생성
python3 -m venv venv
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
cp .env.example .env
# .env 파일 수정

# Vercel 로컬 실행
vercel dev
```

로컬 서버: http://localhost:3000

## 문제 해결

### Channel TTS 실패 시
- ffmpeg 설치 확인: `which ffmpeg`
- Vercel 환경에서 ffmpeg는 기본 제공됨

### OpenClaw 연결 실패 시
- `openclaw` CLI가 PATH에 있는지 확인
- Vercel serverless 환경에서는 로컬 CLI 접근 불가
- 대안: OpenClaw Gateway HTTP API 사용

### 타임아웃 오류 시
- Vercel Hobby plan: 10초 제한
- Pro plan: 60초까지 가능
- `vercel.json`에서 `maxDuration` 조정

## 라이선스

MIT

## 작성자

폴리나 (Polina) - OpenClaw AI Assistant
# Auto-deploy trigger
