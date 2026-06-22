# calculate_video_delay.py
import sys
import subprocess
import os
import json
import tempfile
import numpy as np
from scipy import signal
from pathlib import Path
from fractions import Fraction

try:
    import cv2
except ImportError:
    print("Erro: Instale 'opencv-python' com: pip install opencv-python")
    sys.exit(1)

try:
    import win32com.client
except ImportError:
    print("Erro: Instale 'pywin32' com: pip install pywin32")
    sys.exit(1)

# ─── Configurações ─────────────────────────────────────────────────────────────
FFMPEG_PATH  = r"C:\FFmpeg\bin\ffmpeg.exe"
FFPROBE_PATH = r"C:\FFmpeg\bin\ffprobe.exe"

# Pass 1 — varredura ampla
P1_FPS      = 2    # ±500ms
P1_DURATION = 30

# Pass 2 — refinamento
P2_FPS      = 25   # ±40ms
P2_DURATION = 8
P2_ANCHOR   = 12   # segundo de referência no BD

# Pass 3 — precisão sub-frame
P3_FPS      = 60   # ±16ms base; interpolação parabólica → ±2-3ms
P3_DURATION = 4
P3_ANCHOR   = 15   # ancoragem diferente do pass 2 para validação cruzada

FRAME_RESIZE = (320, 180)

sys.stdout.reconfigure(line_buffering=True)


# ─── Utilitários ───────────────────────────────────────────────────────────────

def resolve_lnk_path(file_path):
    try:
        if file_path.lower().endswith('.lnk'):
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(file_path)
            resolved = shortcut.TargetPath
            if not os.path.exists(resolved):
                print(f"Erro: Atalho aponta para arquivo inexistente: {resolved}")
                sys.exit(1)
            print(f"Atalho resolvido: {os.path.basename(resolved)}")
            return resolved
        return file_path
    except Exception as e:
        print(f"Erro ao resolver atalho: {e}")
        sys.exit(1)


def ffprobe_info(file_path):
    """Retorna (duration_s, native_fps) do arquivo."""
    try:
        cmd = [FFPROBE_PATH, "-v", "quiet", "-print_format", "json",
               "-show_streams", "-show_format", file_path]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))

        # Detecta FPS nativo da stream de vídeo
        native_fps = 24.0
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                rfr = s.get("r_frame_rate", "24/1")
                try:
                    native_fps = float(Fraction(rfr))
                except Exception:
                    pass
                break

        return duration, native_fps
    except Exception:
        return 0, 24.0


def extract_frames(file_path, fps, start_sec, duration, output_dir, label):
    pattern = os.path.join(output_dir, f"{label}_%05d.png")
    cmd = [
        FFMPEG_PATH, "-y",
        "-ss", f"{start_sec:.3f}",
        "-i", file_path,
        "-t", f"{duration:.3f}",
        "-vf", f"fps={fps},scale={FRAME_RESIZE[0]}:{FRAME_RESIZE[1]}",
        "-pix_fmt", "rgb24",
        "-vsync", "0",
        pattern
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    )
    if result.returncode != 0:
        print(f"Erro ao extrair frames: {result.stderr[-400:]}")
        sys.exit(1)
    frames = sorted(Path(output_dir).glob(f"{label}_*.png"))
    return [str(f) for f in frames]


# ─── Sinais visuais ────────────────────────────────────────────────────────────

def compute_histogram_signal(frame_paths):
    signals = []
    bins_h, bins_s, bins_v = 16, 8, 8
    for path in frame_paths:
        img = cv2.imread(path)
        if img is None:
            signals.append(np.zeros(bins_h + bins_s + bins_v))
            continue
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h = cv2.calcHist([hsv], [0], None, [bins_h], [0, 180]).flatten()
        s = cv2.calcHist([hsv], [1], None, [bins_s], [0, 256]).flatten()
        v = cv2.calcHist([hsv], [2], None, [bins_v], [0, 256]).flatten()
        combined = np.concatenate([h, s, v])
        signals.append(combined / (combined.sum() + 1e-9))
    return np.array(signals)


def compute_optflow_signal(frame_paths):
    magnitudes = []
    for i in range(len(frame_paths) - 1):
        prev = cv2.imread(frame_paths[i],     cv2.IMREAD_GRAYSCALE)
        curr = cv2.imread(frame_paths[i + 1], cv2.IMREAD_GRAYSCALE)
        if prev is None or curr is None:
            magnitudes.append(0.0)
            continue
        flow = cv2.calcOpticalFlowFarneback(
            prev, curr, None,
            pyr_scale=0.5, levels=2, winsize=15,
            iterations=2, poly_n=5, poly_sigma=1.1, flags=0
        )
        mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        magnitudes.append(float(mag.mean()))
    return np.array(magnitudes)


# ─── Cross-correlação ──────────────────────────────────────────────────────────

def signal_to_1d(matrix):
    if matrix.ndim == 1:
        return matrix
    centered = matrix - matrix.mean(axis=0)
    cov = np.cov(centered.T)
    _, eigvecs = np.linalg.eigh(cov)
    return centered @ eigvecs[:, -1]


def parabolic_interpolation(corr, peak_idx):
    """
    Ajusta uma parábola nos 3 pontos em torno do pico da correlação
    para encontrar o máximo sub-frame com precisão.
    Retorna offset fracionário em frames.
    """
    if peak_idx <= 0 or peak_idx >= len(corr) - 1:
        return 0.0  # pico na borda, sem interpolação possível

    y0 = corr[peak_idx - 1]
    y1 = corr[peak_idx]
    y2 = corr[peak_idx + 1]

    denom = 2 * (2 * y1 - y0 - y2)
    if abs(denom) < 1e-10:
        return 0.0

    delta = (y0 - y2) / denom  # offset fracionário em frames [-0.5, +0.5]
    return float(np.clip(delta, -0.5, 0.5))


def cross_correlate(sig1, sig2, max_lag_frames=None, interpolate=False):
    """
    Retorna (lag_frames_float, confidence).
    Se interpolate=True, aplica interpolação parabólica para precisão sub-frame.
    """
    s1 = (sig1 - sig1.mean()) / (sig1.std() + 1e-9)
    s2 = (sig2 - sig2.mean()) / (sig2.std() + 1e-9)

    corr = signal.correlate(s1, s2, mode='full')
    lags = signal.correlation_lags(len(s1), len(s2), mode='full')

    if max_lag_frames is not None:
        mask = np.abs(lags) <= max_lag_frames
        corr_search = np.where(mask, corr, -np.inf)
    else:
        corr_search = corr

    peak_idx   = int(np.argmax(corr_search))
    lag_int    = int(lags[peak_idx])
    confidence = float(corr[peak_idx] / (len(s1) + 1e-9))

    if interpolate:
        delta = parabolic_interpolation(corr, peak_idx)
        return lag_int + delta, confidence
    else:
        return float(lag_int), confidence


def frames_to_ms(lag_frames, fps):
    return (lag_frames / fps) * 1000.0


def safe_anchor(anchor, duration, window, offset_s=0.0):
    """Calcula start seguro para extração dado offset e limites do arquivo."""
    start = anchor - offset_s
    start = max(0.0, start)
    start = min(start, duration - window - 0.5)
    return start


# ─── Passes ────────────────────────────────────────────────────────────────────

def run_pass1(bd_path, web_path, analyze_dur, tmpdir):
    print("\n" + "=" * 70)
    print("ETAPA 1/6 — Extracao de Frames (Pass 1: varredura ampla, 2fps)")
    print("=" * 70)
    print(f"  Janela: {analyze_dur:.0f}s  |  Frames esperados: ~{int(analyze_dur * P1_FPS)} por source")

    bd_f  = extract_frames(bd_path,  P1_FPS, 0, analyze_dur, tmpdir, "p1_bd")
    web_f = extract_frames(web_path, P1_FPS, 0, analyze_dur, tmpdir, "p1_web")
    print(f"  BD: {len(bd_f)} frames  |  WEB: {len(web_f)} frames")

    if len(bd_f) < 4 or len(web_f) < 4:
        print("Erro: frames insuficientes no pass 1")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("ETAPA 2/6 — Sinais Visuais (Pass 1)")
    print("=" * 70)

    print("  Calculando histogramas HSV...")
    bd_hist  = signal_to_1d(compute_histogram_signal(bd_f))
    web_hist = signal_to_1d(compute_histogram_signal(web_f))

    print("  Calculando optical flow...")
    bd_flow  = compute_optflow_signal(bd_f)
    web_flow = compute_optflow_signal(web_f)

    lag_hist, conf_hist = cross_correlate(bd_hist, web_hist)
    ms_hist = frames_to_ms(lag_hist, P1_FPS)
    print(f"\n  Histograma:   lag={int(lag_hist):+d} frames -> {ms_hist:+.1f} ms  (confianca: {conf_hist:.3f})")

    has_flow = len(bd_flow) >= 3 and len(web_flow) >= 3
    ms_flow, conf_flow = ms_hist, conf_hist
    if has_flow:
        lag_flow, conf_flow = cross_correlate(bd_flow, web_flow)
        ms_flow = frames_to_ms(lag_flow, P1_FPS)
        print(f"  Optical Flow: lag={int(lag_flow):+d} frames -> {ms_flow:+.1f} ms  (confianca: {conf_flow:.3f})")

    if has_flow:
        total = conf_hist + conf_flow + 1e-9
        rough_ms   = ms_hist * (conf_hist / total) + ms_flow * (conf_flow / total)
        rough_conf = (conf_hist + conf_flow) / 2
    else:
        rough_ms, rough_conf = ms_hist, conf_hist

    frame_ms     = 1000.0 / P1_FPS
    rough_rounded = round(rough_ms / frame_ms) * frame_ms
    print(f"\n  >> Pass 1: {rough_rounded:+.1f} ms  (confianca: {rough_conf:.3f}  |  precisao: +-{frame_ms:.0f} ms)")
    return rough_rounded, rough_conf


def run_pass2(bd_path, web_path, rough_ms, bd_dur, web_dur, tmpdir):
    rough_s = rough_ms / 1000.0
    bd_start  = float(P2_ANCHOR)
    web_start = bd_start - rough_s
    # Ajusta se web_start for inválido
    if web_start < 0:
        delta = -web_start; bd_start += delta; web_start = 0.0
    bd_start  = min(bd_start,  bd_dur  - P2_DURATION - 0.5)
    web_start = min(web_start, web_dur - P2_DURATION - 0.5)

    print("\n" + "=" * 70)
    print("ETAPA 3/6 — Extracao de Frames (Pass 2: refinamento, 25fps)")
    print("=" * 70)
    print(f"  BD  t={bd_start:.2f}s  +{P2_DURATION}s  |  WEB t={web_start:.2f}s  +{P2_DURATION}s")

    bd_f  = extract_frames(bd_path,  P2_FPS, bd_start,  P2_DURATION, tmpdir, "p2_bd")
    web_f = extract_frames(web_path, P2_FPS, web_start, P2_DURATION, tmpdir, "p2_web")
    print(f"  BD: {len(bd_f)} frames  |  WEB: {len(web_f)} frames")

    if len(bd_f) < 10 or len(web_f) < 10:
        print("  Aviso: frames insuficientes — mantendo Pass 1")
        return rough_ms, 0.0

    print("\n" + "=" * 70)
    print("ETAPA 4/6 — Sinais Visuais e Correlacao (Pass 2)")
    print("=" * 70)

    print("  Calculando histogramas HSV...")
    bd_hist  = signal_to_1d(compute_histogram_signal(bd_f))
    web_hist = signal_to_1d(compute_histogram_signal(web_f))

    print("  Calculando optical flow...")
    bd_flow  = compute_optflow_signal(bd_f)
    web_flow = compute_optflow_signal(web_f)

    max_lag = int((1000.0 / P1_FPS) / (1000.0 / P2_FPS)) + 2

    lag_hist, conf_hist = cross_correlate(bd_hist, web_hist, max_lag_frames=max_lag)
    ms_hist = frames_to_ms(lag_hist, P2_FPS)
    print(f"\n  Histograma:   lag={lag_hist:+.2f} frames -> {ms_hist:+.1f} ms  (confianca: {conf_hist:.3f})")

    has_flow = len(bd_flow) >= 5 and len(web_flow) >= 5
    ms_flow, conf_flow = ms_hist, conf_hist
    if has_flow:
        lag_flow, conf_flow = cross_correlate(bd_flow, web_flow, max_lag_frames=max_lag)
        ms_flow = frames_to_ms(lag_flow, P2_FPS)
        print(f"  Optical Flow: lag={lag_flow:+.2f} frames -> {ms_flow:+.1f} ms  (confianca: {conf_flow:.3f})")

    if has_flow:
        total = conf_hist + conf_flow + 1e-9
        delta = ms_hist * (conf_hist / total) + ms_flow * (conf_flow / total)
        p2_conf = (conf_hist + conf_flow) / 2
    else:
        delta, p2_conf = ms_hist, conf_hist

    final_ms = rough_ms + delta
    print(f"\n  >> Delta: {delta:+.1f} ms  |  Pass 2: {final_ms:+.1f} ms  (confianca: {p2_conf:.3f}  |  precisao: +-{1000/P2_FPS:.0f} ms)")
    return final_ms, p2_conf


def run_pass3(bd_path, web_path, p2_ms, bd_dur, web_dur, tmpdir):
    """
    Extrai 4s a 60fps em torno de P3_ANCHOR,
    aplica interpolação parabólica no pico da correlação → ±2-3ms.
    """
    p2_s = p2_ms / 1000.0
    bd_start  = float(P3_ANCHOR)
    web_start = bd_start - p2_s
    if web_start < 0:
        delta = -web_start; bd_start += delta; web_start = 0.0
    bd_start  = min(bd_start,  bd_dur  - P3_DURATION - 0.5)
    web_start = min(web_start, web_dur - P3_DURATION - 0.5)

    print("\n" + "=" * 70)
    print("ETAPA 5/6 — Extracao de Frames (Pass 3: precisao sub-frame, 60fps)")
    print("=" * 70)
    print(f"  BD  t={bd_start:.2f}s  +{P3_DURATION}s  |  WEB t={web_start:.2f}s  +{P3_DURATION}s")

    bd_f  = extract_frames(bd_path,  P3_FPS, bd_start,  P3_DURATION, tmpdir, "p3_bd")
    web_f = extract_frames(web_path, P3_FPS, web_start, P3_DURATION, tmpdir, "p3_web")
    print(f"  BD: {len(bd_f)} frames  |  WEB: {len(web_f)} frames")

    if len(bd_f) < 20 or len(web_f) < 20:
        print("  Aviso: frames insuficientes — mantendo Pass 2")
        return p2_ms, 0.0

    print("\n" + "=" * 70)
    print("ETAPA 6/6 — Correlacao com Interpolacao Parabolica (Pass 3)")
    print("=" * 70)

    print("  Calculando histogramas HSV...")
    bd_hist  = signal_to_1d(compute_histogram_signal(bd_f))
    web_hist = signal_to_1d(compute_histogram_signal(web_f))

    print("  Calculando optical flow...")
    bd_flow  = compute_optflow_signal(bd_f)
    web_flow = compute_optflow_signal(web_f)

    # Busca limitada a ±1 frame do P2 = ±(1000/P2_FPS) ms / (1000/P3_FPS) frames
    max_lag = int((1000.0 / P2_FPS) / (1000.0 / P3_FPS)) + 3

    lag_hist, conf_hist = cross_correlate(bd_hist, web_hist, max_lag_frames=max_lag, interpolate=True)
    ms_hist = frames_to_ms(lag_hist, P3_FPS)
    print(f"\n  Histograma:   lag={lag_hist:+.4f} frames -> {ms_hist:+.2f} ms  (confianca: {conf_hist:.3f})")

    has_flow = len(bd_flow) >= 10 and len(web_flow) >= 10
    ms_flow, conf_flow = ms_hist, conf_hist
    if has_flow:
        lag_flow, conf_flow = cross_correlate(bd_flow, web_flow, max_lag_frames=max_lag, interpolate=True)
        ms_flow = frames_to_ms(lag_flow, P3_FPS)
        print(f"  Optical Flow: lag={lag_flow:+.4f} frames -> {ms_flow:+.2f} ms  (confianca: {conf_flow:.3f})")

    if has_flow:
        total = conf_hist + conf_flow + 1e-9
        delta = ms_hist * (conf_hist / total) + ms_flow * (conf_flow / total)
        p3_conf = (conf_hist + conf_flow) / 2
    else:
        delta, p3_conf = ms_hist, conf_hist

    final_ms = p2_ms + delta
    print(f"\n  >> Delta sub-frame: {delta:+.2f} ms  |  Pass 3: {final_ms:+.2f} ms  (confianca: {p3_conf:.3f}  |  precisao: ~+-2 ms)")
    return final_ms, p3_conf


# ─── Análise principal ─────────────────────────────────────────────────────────

def analyze_video_sync(bd_path, web_path):
    try:
        print("\n" + "=" * 70)
        print("SYNC DETECTOR VISUAL — Analise de Delay por Frame (Three-Pass)")
        print("=" * 70)

        bd_path  = resolve_lnk_path(bd_path)
        web_path = resolve_lnk_path(web_path)

        print(f"\n  BD:  {os.path.basename(bd_path)}")
        print(f"  WEB: {os.path.basename(web_path)}")

        bd_dur,  bd_fps  = ffprobe_info(bd_path)
        web_dur, web_fps = ffprobe_info(web_path)
        analyze_dur = min(P1_DURATION, bd_dur, web_dur)

        print(f"  BD  FPS nativo: {bd_fps:.3f}  |  Duracao: {bd_dur:.1f}s")
        print(f"  WEB FPS nativo: {web_fps:.3f}  |  Duracao: {web_dur:.1f}s")

        if analyze_dur < 5:
            print(f"\nErro: duracao insuficiente ({analyze_dur:.1f}s)")
            sys.exit(1)

        with tempfile.TemporaryDirectory() as tmpdir:

            rough_ms, rough_conf = run_pass1(bd_path, web_path, analyze_dur, tmpdir)

            min_dur_p2 = max(P2_ANCHOR, P3_ANCHOR) + max(P2_DURATION, P3_DURATION) + 1.0
            if bd_dur >= min_dur_p2 and web_dur >= min_dur_p2:
                p2_ms, p2_conf = run_pass2(bd_path, web_path, rough_ms, bd_dur, web_dur, tmpdir)
                p3_ms, p3_conf = run_pass3(bd_path, web_path, p2_ms,    bd_dur, web_dur, tmpdir)
                final_ms   = p3_ms
                final_conf = p3_conf
                used_passes = 3
            else:
                print("\nAviso: video curto demais para Pass 2/3 — usando apenas Pass 1")
                p2_ms = p2_conf = None
                final_ms, final_conf = rough_ms, rough_conf
                used_passes = 1

        # ── Resultado ─────────────────────────────────────────────────────
        print("\n" + "=" * 70)
        print("RESULTADO FINAL")
        print("=" * 70)
        print(f"\n  Pass 1  (2fps  varredura):       {rough_ms:+9.1f} ms   confianca: {rough_conf:.3f}   precisao: +-500 ms")
        if used_passes >= 2:
            print(f"  Pass 2  (25fps refinamento):     {p2_ms:+9.1f} ms   confianca: {p2_conf:.3f}   precisao: +-40 ms")
            print(f"  Pass 3  (60fps + interp. par.):  {p3_ms:+9.2f} ms   confianca: {p3_conf:.3f}   precisao: ~+-2 ms")

        print(f"\n  Offset final:  {final_ms:+.2f} ms")
        print(f"  Precisao:      ~+-2 ms")

        if rough_conf < 0.2:
            print("\n  AVISO: Confianca baixa no Pass 1!")
            print("    - Creditos/intro muito diferentes entre BD e WEB")
            print("    - Tela preta prolongada no inicio")
            print("    - Cortes editoriais diferentes nos primeiros 30s")

        print("\n" + "-" * 70)

        if abs(final_ms) < 5:
            print("  Videos praticamente SINCRONIZADOS (< 5ms)")
            print("  Nenhum ajuste necessario!")
        elif final_ms > 0:
            print(f"  BD comeca {final_ms:.2f} ms DEPOIS do WEB")
            print(f"\n  Para sincronizar no MKVToolNix:")
            print(f"  -> Adicione -{final_ms:.2f} ms de delay no video/audio do BD")
            print(f"  -> OU adicione +{final_ms:.2f} ms no video/audio do WEB")
        else:
            abs_ms = abs(final_ms)
            print(f"  WEB comeca {abs_ms:.2f} ms DEPOIS do BD")
            print(f"\n  Para sincronizar no MKVToolNix:")
            print(f"  -> Adicione +{abs_ms:.2f} ms de delay no video/audio do WEB")
            print(f"  -> OU adicione -{abs_ms:.2f} ms no video/audio do BD")

        print("\n" + "=" * 70)
        print("  Analise concluida!")
        print("=" * 70 + "\n")

    except KeyboardInterrupt:
        print("\n\nOperacao cancelada pelo usuario.")
        sys.exit(0)
    except Exception as e:
        print(f"\nErro na analise: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    try:
        if len(sys.argv) < 3:
            print("\n" + "=" * 70)
            print("SYNC DETECTOR VISUAL — Detector de Delay por Frame")
            print("=" * 70)
            print("\nUso: python calculate_video_delay.py <arquivo_BD> <arquivo_WEB>")
            print("\nDependencias:")
            print("  pip install opencv-python pywin32 scipy numpy")
            print("=" * 70 + "\n")
            sys.exit(1)

        analyze_video_sync(sys.argv[1].strip('"'), sys.argv[2].strip('"'))

    except KeyboardInterrupt:
        print("\n\nOperacao cancelada.")
        sys.exit(0)
    except Exception as e:
        print(f"\nErro fatal: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
