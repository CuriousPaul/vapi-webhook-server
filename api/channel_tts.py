#!/usr/bin/env python3
"""
Channel.io TTS Integration for Vapi
채널톡의 고품질 한국어 TTS API를 Vapi와 통합
"""

import os
import io
import logging
import requests
import struct
import subprocess
from typing import Optional, Iterator

logger = logging.getLogger(__name__)

# Channel.io TTS API 설정
CHANNELTTS_API_BASE = "https://ch-tts-streaming-demo.channel.io"
CHANNELTTS_VOICE_ID = "hana"  # 고정 voice ID
DEFAULT_LATENCY_LEVEL = 3  # 0-4, 3 = 빠른 응답 (권장)


def generate_speech_stream(
    text: str,
    latency_level: int = DEFAULT_LATENCY_LEVEL,
    output_format: str = "pcm_24000"
) -> Iterator[bytes]:
    """
    Channel.io TTS API로 음성 생성 (스트리밍)
    
    Args:
        text: 한국어 텍스트
        latency_level: 지연시간 최적화 수준 (0-4, 3 권장)
        output_format: 출력 형식 (기본: pcm_24000)
    
    Yields:
        오디오 청크 (bytes)
    
    Raises:
        requests.RequestException: API 호출 실패
    """
    url = f"{CHANNELTTS_API_BASE}/v1/text-to-speech/{CHANNELTTS_VOICE_ID}/stream"
    
    params = {
        "optimize_streaming_latency": latency_level
    }
    
    payload = {
        "text": text,
        "model_id": "default",
        "voice_settings": {},
        "output_format": output_format
    }
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "audio/pcm"  # PCM 형식 요청
    }
    
    try:
        logger.info(f"[ChannelTTS] Generating speech for: {text[:50]}...")
        
        with requests.post(
            url,
            params=params,
            json=payload,
            headers=headers,
            stream=True,
            timeout=30
        ) as response:
            response.raise_for_status()
            
            chunk_count = 0
            for chunk in response.iter_content(chunk_size=4096):
                if chunk:
                    chunk_count += 1
                    if chunk_count == 1:
                        logger.info("[ChannelTTS] First chunk received!")
                    yield chunk
            
            logger.info(f"[ChannelTTS] Streaming complete ({chunk_count} chunks)")
    
    except requests.RequestException as e:
        logger.error(f"[ChannelTTS] API request failed: {e}")
        raise


def generate_speech(
    text: str,
    latency_level: int = DEFAULT_LATENCY_LEVEL,
    output_format: str = "pcm_24000"
) -> bytes:
    """
    Channel.io TTS API로 음성 생성 (전체 바이너리 반환)
    
    Args:
        text: 한국어 텍스트
        latency_level: 지연시간 최적화 수준 (0-4, 3 권장)
        output_format: 출력 형식 (기본: pcm_24000)
    
    Returns:
        PCM 오디오 데이터 (bytes)
    
    Raises:
        requests.RequestException: API 호출 실패
    """
    url = f"{CHANNELTTS_API_BASE}/v1/text-to-speech/{CHANNELTTS_VOICE_ID}/stream"
    
    params = {
        "optimize_streaming_latency": latency_level
    }
    
    payload = {
        "text": text,
        "model_id": "default",
        "voice_settings": {},
        "output_format": output_format
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        logger.info(f"[ChannelTTS] Generating speech for: {text[:50]}...")
        
        # stream=False로 한 번에 받기
        response = requests.post(
            url,
            params=params,
            json=payload,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        
        audio_data = response.content
        logger.info(f"[ChannelTTS] Generated {len(audio_data)} bytes of audio")
        
        return audio_data
    
    except requests.RequestException as e:
        logger.error(f"[ChannelTTS] API request failed: {e}")
        raise


def linear_to_mulaw(sample: int) -> int:
    """
    16-bit linear PCM → μ-law 변환 (단일 샘플)
    표준 G.711 μ-law 알고리즘 (ITU-T G.711)
    """
    BIAS = 0x84  # 132
    CLIP = 32635
    
    # Get sign
    sign = 0x80 if sample < 0 else 0x00
    
    # Get magnitude
    if sample < 0:
        sample = -sample
    
    if sample > CLIP:
        sample = CLIP
    
    sample = sample + BIAS
    
    # Find exponent
    exponent = 7
    for exp_lut in [0x4000, 0x2000, 0x1000, 0x800, 0x400, 0x200, 0x100, 0x80]:
        if sample >= exp_lut:
            break
        exponent -= 1
    
    # Get mantissa
    mantissa = (sample >> (exponent + 3)) & 0x0F
    
    # Combine and invert
    mulaw_byte = ~(sign | (exponent << 4) | mantissa)
    
    return mulaw_byte & 0xFF


def resample_pcm(pcm_data: bytes, from_rate: int, to_rate: int) -> bytes:
    """
    Simple PCM resampling (nearest neighbor)
    """
    import array
    
    # Convert bytes to int16 array
    samples = array.array('h', pcm_data)  # 'h' = signed short (16-bit)
    
    # Calculate resampling ratio
    ratio = from_rate / to_rate
    output_length = int(len(samples) / ratio)
    
    # Resample
    resampled = array.array('h')
    for i in range(output_length):
        src_index = int(i * ratio)
        if src_index < len(samples):
            resampled.append(samples[src_index])
    
    return resampled.tobytes()


def convert_pcm_to_mulaw(pcm_data: bytes, sample_rate: int = 24000) -> bytes:
    """
    PCM 오디오를 μ-law (G.711) 형식으로 변환
    Vapi는 전화 통화에 μ-law를 사용
    
    Pure Python 구현 (Python 3.13+ 호환, audioop 불필요):
    - PCM s16le (16-bit signed little-endian) → μ-law
    - 24kHz → 8kHz 리샘플링 (전화 통화 표준)
    
    Args:
        pcm_data: PCM 오디오 데이터 (16-bit, mono)
        sample_rate: 입력 샘플레이트 (기본: 24000)
    
    Returns:
        μ-law 오디오 데이터 (bytes, 8kHz, mono)
    """
    try:
        import array
        
        # 1. Resample: 24kHz → 8kHz (전화 통화 표준)
        if sample_rate != 8000:
            resampled_data = resample_pcm(pcm_data, sample_rate, 8000)
            logger.info(f"[ChannelTTS] Resampled: {len(pcm_data)} → {len(resampled_data)} bytes ({sample_rate}Hz → 8kHz)")
        else:
            resampled_data = pcm_data
        
        # 2. PCM (16-bit) → μ-law
        samples = array.array('h', resampled_data)  # 'h' = signed short
        mulaw_bytes = bytearray()
        
        for sample in samples:
            mulaw_bytes.append(linear_to_mulaw(sample))
        
        mulaw_data = bytes(mulaw_bytes)
        
        logger.info(f"[ChannelTTS] PCM → μ-law: {len(pcm_data)} → {len(mulaw_data)} bytes")
        
        return mulaw_data
    
    except Exception as e:
        logger.error(f"[ChannelTTS] PCM → μ-law conversion failed: {e}")
        raise


def generate_speech_for_vapi(text: str, latency_level: int = DEFAULT_LATENCY_LEVEL) -> bytes:
    """
    Vapi 통화용 음성 생성 (PCM → μ-law 변환 포함)
    
    Args:
        text: 한국어 텍스트
        latency_level: 지연시간 최적화 수준 (0-4, 3 권장)
    
    Returns:
        μ-law 오디오 데이터 (Vapi 통화용)
    
    Raises:
        Exception: 음성 생성 또는 변환 실패
    """
    # 1. Channel.io TTS로 PCM 생성
    pcm_data = generate_speech(text, latency_level, output_format="pcm_24000")
    
    # 2. PCM → μ-law 변환
    mulaw_data = convert_pcm_to_mulaw(pcm_data, sample_rate=24000)
    
    logger.info(f"[ChannelTTS] Vapi-ready audio: {len(mulaw_data)} bytes (μ-law)")
    
    return mulaw_data


def test_tts(text: str = "안녕하세요! 폴리나예요 🌸"):
    """
    TTS 기능 테스트
    
    Args:
        text: 테스트할 텍스트 (기본: 폴리나 인사)
    """
    import time
    
    print(f"Testing Channel.io TTS with text: {text}")
    
    # 1. 스트리밍 테스트
    print("\n[1] Streaming test...")
    start_time = time.time()
    
    chunks = []
    first_chunk_time = None
    
    for chunk in generate_speech_stream(text):
        if first_chunk_time is None:
            first_chunk_time = time.time() - start_time
            print(f"✅ First chunk received in {first_chunk_time:.3f}s")
        
        chunks.append(chunk)
    
    total_time = time.time() - start_time
    total_bytes = sum(len(c) for c in chunks)
    
    print(f"✅ Streaming complete: {total_bytes} bytes in {total_time:.3f}s")
    print(f"   First chunk latency: {first_chunk_time:.3f}s")
    print(f"   Total chunks: {len(chunks)}")
    
    # 2. 전체 바이너리 생성 테스트
    print("\n[2] Full binary test...")
    start_time = time.time()
    
    audio_data = generate_speech(text)
    
    total_time = time.time() - start_time
    print(f"✅ Generated {len(audio_data)} bytes in {total_time:.3f}s")
    
    # 3. Vapi용 변환 테스트
    print("\n[3] Vapi μ-law conversion test...")
    start_time = time.time()
    
    mulaw_data = generate_speech_for_vapi(text)
    
    total_time = time.time() - start_time
    print(f"✅ Vapi-ready audio: {len(mulaw_data)} bytes in {total_time:.3f}s")
    
    # 4. 파일 저장 (선택)
    output_dir = os.path.expanduser("~/.openclaw/skills/vapi/test_output")
    os.makedirs(output_dir, exist_ok=True)
    
    # PCM 저장
    pcm_path = os.path.join(output_dir, "test_pcm.raw")
    with open(pcm_path, "wb") as f:
        f.write(audio_data)
    print(f"\n📁 PCM audio saved: {pcm_path}")
    
    # μ-law 저장
    mulaw_path = os.path.join(output_dir, "test_mulaw.raw")
    with open(mulaw_path, "wb") as f:
        f.write(mulaw_data)
    print(f"📁 μ-law audio saved: {mulaw_path}")
    
    print("\n✅ All tests passed!")
    print("\nTo play PCM audio:")
    print(f"  ffplay -f s16le -ar 24000 -ac 1 {pcm_path}")
    print("\nTo play μ-law audio:")
    print(f"  ffplay -f mulaw -ar 8000 -ac 1 {mulaw_path}")


if __name__ == "__main__":
    import sys
    
    # CLI 인터페이스
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        test_tts(text)
    else:
        test_tts()
