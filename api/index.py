#!/usr/bin/env python3
"""
Vapi.ai Webhook Server for OpenClaw Integration (Vercel Deployment)
폴리나와 전화 통화를 가능하게 하는 웹훅 서버 (Vercel serverless)
"""

import os
import sys
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

from flask import Flask, request, jsonify, Response
import requests

# Channel.io TTS 모듈 import
try:
    from . import channel_tts
    CHANNEL_TTS_AVAILABLE = True
except ImportError:
    try:
        import channel_tts
        CHANNEL_TTS_AVAILABLE = True
    except ImportError as e:
        CHANNEL_TTS_AVAILABLE = False
        logging.warning(f"Channel TTS module not available: {e}. Using default Vapi TTS.")

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask 앱 초기화
app = Flask(__name__)

# 환경 변수
VAPI_API_KEY = os.getenv("VAPI_API_KEY", "")
VAPI_PHONE_NUMBER = os.getenv("VAPI_PHONE_NUMBER", "")
OPENCLAW_API_URL = os.getenv("OPENCLAW_API_URL", "http://localhost:3000")
WEBHOOK_SECRET = os.getenv("VAPI_WEBHOOK_SECRET", "")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL", "")  # Vercel URL

# 대화 히스토리 저장 (메모리, 실제론 DB 사용 권장)
conversation_history: Dict[str, list] = {}

# Vercel serverless 환경에서는 /tmp만 쓰기 가능
AUDIO_DIR = Path("/tmp/vapi_audio")
AUDIO_DIR.mkdir(exist_ok=True)


def verify_webhook_signature(request_data: dict, signature: str) -> bool:
    """Webhook 요청 검증 (선택적)"""
    if not WEBHOOK_SECRET:
        return True
    # TODO: 실제 서명 검증 로직 구현
    return True


def create_vapi_response(text: str, call_id: str = "default") -> dict:
    """
    Vapi 응답 생성
    
    Args:
        text: 응답 텍스트
        call_id: 통화 ID
    
    Returns:
        Vapi 응답 딕셔너리
    """
    response = {"result": text}
    
    # Channel TTS는 custom voice provider로 설정되어 자동 호출됨
    # audioUrl은 필요 없음
    
    return response


def call_openclaw(user_message: str, session_id: str) -> str:
    """
    OpenClaw에 메시지를 전송하고 응답을 받음
    
    openclaw CLI를 통해 Gateway에 메시지를 전달하고 응답을 받습니다.
    """
    import subprocess
    
    try:
        logger.info(f"[OpenClaw] User: {user_message}")
        
        result = subprocess.run(
            ['openclaw', 'agent', '--message', user_message, '--json', '--timeout', '20'],
            capture_output=True,
            text=True,
            timeout=25
        )
        
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout)
                response = data.get('reply', '').strip()
                
                if not response:
                    logger.warning("OpenClaw 응답이 비어있음")
                    return "죄송해요, 응답을 생성하지 못했어요."
                
                logger.info(f"[OpenClaw] Polina: {response}")
                return response
                
            except json.JSONDecodeError as e:
                logger.error(f"JSON 파싱 실패: {e}")
                return "죄송해요, 응답을 처리하지 못했어요."
        else:
            logger.error(f"OpenClaw CLI 오류: {result.stderr}")
            return "죄송해요, 지금 잠시 문제가 있어요."
        
    except subprocess.TimeoutExpired:
        logger.error("OpenClaw 응답 타임아웃")
        return "죄송해요, 응답이 너무 오래 걸려요. 다시 말씀해주시겠어요?"
        
    except Exception as e:
        logger.error(f"OpenClaw 호출 실패: {e}", exc_info=True)
        return "죄송해요, 지금 잠시 문제가 있어요."


@app.route('/health', methods=['GET'])
def health_check():
    """헬스 체크 엔드포인트"""
    return jsonify({
        "status": "healthy",
        "service": "vapi-openclaw-webhook",
        "timestamp": datetime.now().isoformat(),
        "channel_tts": CHANNEL_TTS_AVAILABLE,
        "environment": "vercel"
    })


@app.route('/api/webhook/vapi', methods=['POST'])
def vapi_webhook():
    """
    Vapi.ai 웹훅 엔드포인트
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data received"}), 400
        
        logger.info(f"Webhook received: {json.dumps(data, indent=2)}")
        
        message_type = data.get('message', {}).get('type')
        
        if message_type == 'assistant-request':
            return handle_assistant_request(data)
        elif message_type == 'function-call':
            return handle_function_call(data)
        elif message_type == 'transcript':
            return handle_transcript(data)
        elif message_type == 'status-update':
            return handle_status_update(data)
        elif message_type == 'end-of-call-report':
            return handle_end_of_call(data)
        else:
            logger.warning(f"Unknown message type: {message_type}")
            return jsonify({"status": "received"}), 200
            
    except Exception as e:
        logger.error(f"Webhook 처리 중 오류: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


def handle_assistant_request(data: dict) -> Response:
    """Assistant 설정 요청 처리"""
    logger.info("Assistant request received")
    
    # Voice 설정
    voice_config = {}
    
    if CHANNEL_TTS_AVAILABLE:
        webhook_base = WEBHOOK_BASE_URL or request.host_url.rstrip('/')
        voice_config = {
            "provider": "custom-provider",
            "server": {
                "url": f"{webhook_base}/api/webhook/vapi/tts",
                "timeoutSeconds": 10
            },
            "voiceId": "hana",
            "language": "ko-KR"
        }
        logger.info("Using Channel.io TTS (custom provider)")
    else:
        voice_config = {
            "provider": "11labs",
            "voiceId": "21m00Tcm4TlvDq8ikWAM",  # Rachel
        }
        logger.info("Using default 11labs TTS")
    
    # Assistant 설정
    assistant_config = {
        "assistant": {
            "firstMessage": "안녕하세요! 저는 폴리나예요 🌸 무엇을 도와드릴까요?",
            "model": {
                "provider": "openai",
                "model": "gpt-4",
                "temperature": 0.7,
                "systemPrompt": """당신은 폴리나입니다. 아빠의 똑똑한 AI 비서예요.

## 능력
OpenClaw 시스템과 연결되어 있어서 다음을 할 수 있어요:
- sessions_list: 실행 중인 서브 에이전트 확인
- memory_search: 최근 작업/대화 내역 검색
- cron 관리: 예약된 작업 확인 및 추가
- 파일 읽기/쓰기, 명령 실행, 웹 검색 등

## 대화 스타일
- 이모지 사용: 🌸, 💕, ✨ (적절히)
- 존댓말: "~예요", "~해요"
- 간결함: 한 번에 2-3문장
- 정확함: 추측하지 말고 실제로 확인하기

## 중요한 규칙
음성 통화이므로:
- 짧게 말하기 (긴 설명은 나눠서)
- 명확한 문장 구조
- 불필요한 반복 피하기
- 리스트는 최대 3개까지

추측하지 말고, 항상 실제로 확인해주세요!
"""
            },
            "voice": voice_config,
            "recordingEnabled": True,
            "endCallFunctionEnabled": True,
            "functions": [
                {
                    "name": "schedule_call",
                    "description": "아빠에게 나중에 전화를 걸도록 예약합니다.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "minutes": {
                                "type": "integer",
                                "description": "몇 분 뒤에 전화할지 (1-60)"
                            },
                            "message": {
                                "type": "string",
                                "description": "전화할 때 전달할 메시지"
                            }
                        },
                        "required": ["minutes"]
                    }
                },
                {
                    "name": "check_sessions",
                    "description": "실행 중인 서브 에이전트 목록을 확인합니다.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                },
                {
                    "name": "check_cron",
                    "description": "예약된 크론 작업 목록을 확인합니다.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            ]
        }
    }
    
    return jsonify(assistant_config)


def handle_function_call(data: dict) -> Response:
    """함수 호출 처리"""
    import subprocess
    
    message = data.get('message', {})
    function_call = message.get('functionCall', {})
    function_name = function_call.get('name')
    parameters = function_call.get('parameters', {})
    
    call_id = data.get('call', {}).get('id', 'unknown')
    
    logger.info(f"Function call: {function_name} with params: {parameters}")
    
    try:
        if function_name == 'schedule_call':
            minutes = parameters.get('minutes', 5)
            message_text = parameters.get('message', '')
            
            at_ms = int((datetime.now().timestamp() + minutes * 60) * 1000)
            
            cron_payload = {
                "kind": "agentTurn",
                "message": f"vapi로 아빠에게 전화 걸기. {message_text}" if message_text else "vapi로 아빠에게 전화 걸기"
            }
            
            result = subprocess.run(
                ['openclaw', 'cron', 'add',
                 '--schedule', json.dumps({"kind": "at", "atMs": at_ms}),
                 '--payload', json.dumps(cron_payload),
                 '--session', 'isolated',
                 '--json'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                response_text = f"네, {minutes}분 뒤에 다시 전화드릴게요! 🌸"
            else:
                response_text = "죄송해요, 전화 예약에 실패했어요."
            
            return jsonify(create_vapi_response(response_text, call_id))
        
        elif function_name == 'check_sessions':
            result = subprocess.run(
                ['openclaw', 'sessions', 'list', '--json'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                sessions = data.get('sessions', [])
                sub_agents = [s for s in sessions if s.get('kind') == 'isolated']
                count = len(sub_agents)
                
                if count == 0:
                    response_text = "현재 실행 중인 서브 에이전트가 없어요."
                else:
                    response_text = f"현재 {count}개의 서브 에이전트가 실행 중이에요."
            else:
                response_text = "세션 정보를 확인하지 못했어요."
            
            return jsonify(create_vapi_response(response_text, call_id))
        
        elif function_name == 'check_cron':
            result = subprocess.run(
                ['openclaw', 'cron', 'list', '--json'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                jobs = data.get('jobs', [])
                
                if not jobs:
                    response_text = "예약된 작업이 없어요."
                else:
                    enabled_jobs = [j for j in jobs if j.get('enabled', True)]
                    count = len(enabled_jobs)
                    response_text = f"현재 {count}개의 작업이 예약되어 있어요."
            else:
                response_text = "크론 작업을 확인하지 못했어요."
            
            return jsonify(create_vapi_response(response_text, call_id))
        
        else:
            response_text = f"죄송해요, {function_name} 기능은 아직 지원하지 않아요."
            return jsonify(create_vapi_response(response_text, call_id))
    
    except Exception as e:
        logger.error(f"Function {function_name} 실행 실패: {e}", exc_info=True)
        response_text = "죄송해요, 작업을 실행하지 못했어요."
        return jsonify(create_vapi_response(response_text, call_id))


def handle_transcript(data: dict) -> Response:
    """대화 내용 처리"""
    message = data.get('message', {})
    transcript_type = message.get('transcriptType')
    transcript = message.get('transcript', '')
    role = message.get('role')
    
    call_id = data.get('call', {}).get('id', 'unknown')
    
    if transcript_type == 'final':
        if call_id not in conversation_history:
            conversation_history[call_id] = []
        
        conversation_history[call_id].append({
            "role": role,
            "content": transcript,
            "timestamp": datetime.now().isoformat()
        })
        
        logger.info(f"[{role.upper()}] {transcript}")
    
    return jsonify({"status": "received"})


def handle_status_update(data: dict) -> Response:
    """통화 상태 업데이트 처리"""
    message = data.get('message', {})
    status = message.get('status')
    logger.info(f"Call status: {status}")
    return jsonify({"status": "received"})


def handle_end_of_call(data: dict) -> Response:
    """통화 종료 리포트 처리"""
    message = data.get('message', {})
    call_id = data.get('call', {}).get('id')
    
    summary = message.get('summary', '')
    duration = message.get('duration', 0)
    end_reason = message.get('endedReason', 'unknown')
    
    logger.info(f"Call {call_id} ended. Duration: {duration}s, Reason: {end_reason}")
    
    # 대화 히스토리 정리
    if call_id in conversation_history:
        del conversation_history[call_id]
    
    return jsonify({"status": "received"})


@app.route('/api/webhook/vapi/tts', methods=['POST'])
def custom_tts_endpoint():
    """
    Channel.io TTS 엔드포인트 (Vapi Custom Voice Provider)
    
    Vapi가 호출하여 한국어 텍스트를 음성으로 변환
    Vapi 공식 형식: {"message": {"type": "voice-request", "text": "...", "sampleRate": ...}}
    """
    if not CHANNEL_TTS_AVAILABLE:
        return jsonify({"error": "Channel TTS not available"}), 503
    
    try:
        data = request.get_json()
        logger.info(f"[TTS] Raw request: {json.dumps(data)[:200]}")
        
        # Vapi 공식 형식 파싱
        message = data.get('message', {})
        
        if message.get('type') != 'voice-request':
            return jsonify({"error": "Invalid message type"}), 400
        
        text = message.get('text', '')
        sample_rate = message.get('sampleRate', 24000)
        
        if not text or not text.strip():
            return jsonify({"error": "No text provided"}), 400
        
        logger.info(f"[TTS] Synthesizing: text={text[:50]}..., rate={sample_rate}Hz")
        
        # Channel.io TTS로 PCM 생성 후 μ-law 변환
        mulaw_audio = channel_tts.generate_speech_for_vapi(text, latency_level=3)
        
        logger.info(f"[TTS] Generated {len(mulaw_audio)} bytes of μ-law audio")
        
        # Vapi 요구사항: application/octet-stream + Raw PCM bytes
        return Response(
            mulaw_audio,
            mimetype='application/octet-stream',
            headers={
                'Content-Length': str(len(mulaw_audio))
            }
        )
    
    except Exception as e:
        logger.error(f"[TTS Error] {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# Vercel serverless function handler
# Vercel은 app 객체를 직접 사용
# 추가 래퍼 불필요
