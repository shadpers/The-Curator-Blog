import subprocess
import os
import shutil
import re

FFPROBE = r"C:\FFmpeg\bin\ffprobe.exe"
FFMPEG = r"C:\FFmpeg\bin\ffmpeg.exe"

TEMP = "_temp_frames"
WINDOW = 60  # segundos extraídos

def ffprobe_info(path):
    cmd = [
        FFPROBE, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path
    ]
    out = subprocess.check_output(cmd, text=True).splitlines()
    num, den = map(int, out[0].split("/"))
    fps = num / den
    dur = float(out[1])
    return fps, dur

def extract_frames(video, outdir, start):
    os.makedirs(outdir, exist_ok=True)
    cmd = [
        FFMPEG, "-y",
        "-ss", str(start),
        "-t", str(WINDOW),
        "-i", video,
        os.path.join(outdir, "frame_%06d.png")
    ]
    subprocess.run(cmd, check=True)

def parse_pairs(txt):
    pairs = []
    for p in txt.split(","):
        a, b = p.strip().split(":")
        pairs.append((int(a), int(b)))
    return pairs

def pairs_to_times(pairs, fps_bd, fps_web, dur_bd, dur_web, region):
    times = []
    for f_bd, f_web in pairs:
        if region == "start":
            t_bd = f_bd / fps_bd
            t_web = f_web / fps_web
        else:
            t_bd = dur_bd - WINDOW + (f_bd / fps_bd)
            t_web = dur_web - WINDOW + (f_web / fps_web)
        times.append((t_bd, t_web))
    return times

def compute_stretch(times):
    num = den = 0.0
    for t_bd, t_web in times:
        num += t_bd * t_web
        den += t_bd * t_bd
    return num / den

def main(bd, web):
    fps_bd, dur_bd = ffprobe_info(bd)
    fps_web, dur_web = ffprobe_info(web)

    if os.path.exists(TEMP):
        shutil.rmtree(TEMP)

    extract_frames(bd, f"{TEMP}/BD_start", 0)
    extract_frames(bd, f"{TEMP}/BD_end", dur_bd - WINDOW)
    extract_frames(web, f"{TEMP}/WEB_start", 0)
    extract_frames(web, f"{TEMP}/WEB_end", dur_web - WINDOW)

    os.startfile(TEMP)
    input("\nAnalise os frames e pressione ENTER...\n")

    start_txt = input("Pares START (BD:WEB): ").strip()
    end_txt   = input("Pares END   (BD:WEB): ").strip()

    times = []
    if start_txt:
        times += pairs_to_times(
            parse_pairs(start_txt),
            fps_bd, fps_web, dur_bd, dur_web, "start"
        )
    if end_txt:
        times += pairs_to_times(
            parse_pairs(end_txt),
            fps_bd, fps_web, dur_bd, dur_web, "end"
        )

    stretch = compute_stretch(times)
    percent = stretch * 100

    print("\n=== RESULTADO ===")
    print(f"Stretch ideal: {percent:.6f}%")
    print(f"Fator FFmpeg: atempo={stretch:.8f}")

if __name__ == "__main__":
    import sys
    main(sys.argv[1], sys.argv[2])
