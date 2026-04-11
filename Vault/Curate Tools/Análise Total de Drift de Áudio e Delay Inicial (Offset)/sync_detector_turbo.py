import sys
import subprocess
import os
import tempfile
import numpy as np
from scipy import signal
from scipy.io import wavfile

FFMPEG = r"C:\FFmpeg\bin\ffmpeg.exe"

SAMPLE_RATE = 22050
WINDOW_SEC = 20
STEP_SEC = 60
MIN_CONFIDENCE = 0.6


def extract_full_audio(src, stream_idx, out_wav):
    cmd = [
        FFMPEG, "-y",
        "-i", src,
        "-map", f"0:{stream_idx}",
        "-ac", "1",
        "-ar", str(SAMPLE_RATE),
        "-acodec", "pcm_s16le",
        out_wav
    ]
    
    print(f"  Processando: {os.path.basename(src)} (stream {stream_idx})...")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    if result.returncode != 0:
        print(f"\n❌ ERRO no FFmpeg!")
        print(f"Arquivo: {src}")
        print(f"Stream: {stream_idx}")
        print(f"\n--- Stderr do FFmpeg ---")
        print(result.stderr)
        print("------------------------\n")
        raise RuntimeError("FFmpeg falhou ao extrair áudio")
    
    if not os.path.exists(out_wav):
        raise FileNotFoundError(f"Arquivo WAV não foi criado: {out_wav}")
    
    print(f"  ✓ Áudio extraído com sucesso")


def load_audio(path):
    sr, audio = wavfile.read(path)
    audio = audio.astype(np.float32) / 32768.0
    return audio


def correlate(a, b):
    corr = signal.correlate(a, b, mode="full")
    lags = signal.correlation_lags(len(a), len(b), mode="full")
    idx = np.argmax(corr)
    lag = lags[idx]
    conf = corr[idx] / np.sqrt(np.sum(a*a) * np.sum(b*b))
    return lag, conf


def analyze_drift(bd_audio, web_audio):
    window = WINDOW_SEC * SAMPLE_RATE
    step = STEP_SEC * SAMPLE_RATE

    offsets = []
    times = []

    max_pos = min(len(bd_audio), len(web_audio)) - window

    for pos in range(0, max_pos, step):
        bd_seg = bd_audio[pos:pos+window]
        web_seg = web_audio[pos:pos+window]

        if np.max(np.abs(bd_seg)) < 0.01 or np.max(np.abs(web_seg)) < 0.01:
            continue

        lag, conf = correlate(bd_seg, web_seg)

        if conf < MIN_CONFIDENCE:
            continue

        offset_ms = (lag / SAMPLE_RATE) * 1000
        t_sec = pos / SAMPLE_RATE

        offsets.append(offset_ms)
        times.append(t_sec)

    return np.array(times), np.array(offsets)


def main(bd_path, web_path, bd_idx, web_idx):
    with tempfile.TemporaryDirectory() as tmp:
        bd_wav = os.path.join(tmp, "bd.wav")
        web_wav = os.path.join(tmp, "web.wav")

        print("\n⏳ Extraindo áudio completo...")
        try:
            extract_full_audio(bd_path, bd_idx, bd_wav)
            extract_full_audio(web_path, web_idx, web_wav)
        except Exception as e:
            print(f"\n❌ Falha na extração de áudio: {e}")
            return

        print("\n⏳ Carregando arquivos WAV...")
        bd_audio = load_audio(bd_wav)
        web_audio = load_audio(web_wav)
        
        print(f"  BD: {len(bd_audio)/SAMPLE_RATE:.1f} segundos")
        print(f"  WEB: {len(web_audio)/SAMPLE_RATE:.1f} segundos")

        print("\n⏳ Analisando drift ao longo do episódio...")
        t, off = analyze_drift(bd_audio, web_audio)

        if len(t) < 5:
            print("❌ Dados insuficientes para estimar drift.")
            print(f"   Pontos encontrados: {len(t)} (mínimo: 5)")
            return

        # Regressão linear simples
        A, B = np.polyfit(t, off, 1)

        stretch = 1 + (A / 1000)

        print("\n================ DRIFT ANALYSIS ================")
        print(f"Delay inicial (B): {B:.2f} ms")
        print(f"Drift: {A:.6f} ms / segundo")
        print(f"Fator de tempo sugerido: {stretch:.9f}")
        print("================================================")

        if abs(A) < 0.05:
            print("✅ Drift desprezível – apenas delay resolve.")
        elif abs(A) < 1:
            print("⚠ Drift leve – stretch único pode funcionar.")
        else:
            print("❌ Drift alto – edições incompatíveis (não-linear).")


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Uso:")
        print("python sync_detector_turbo.py BD.mkv WEB.mkv bd_stream_idx web_stream_idx")
        sys.exit(1)

    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))