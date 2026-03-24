import subprocess
import os
import shutil
import re
import numpy as np
import torch
import torch.nn.functional as F
from torchvision import transforms
from PIL import Image
from concurrent.futures import ThreadPoolExecutor

FFPROBE = r"C:\FFmpeg\bin\ffprobe.exe"
FFMPEG = r"C:\FFmpeg\bin\ffmpeg.exe"

TEMP = "_temp_frames"
WINDOW = 60  # segundos extraídos
SAMPLE_RATE = 1  # Amostragem: 1 = todos frames; 2 = a cada 2, etc. (para acelerar mais)

# Detecta device (GPU se disponível)
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Usando device: {device}")

def load_image(path):
    img = Image.open(path).convert('RGB')
    transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
    ])
    return transform(img).unsqueeze(0).to(device)

def load_images_in_batch(dir_path, sample_rate=1):
    frames = sorted([f for f in os.listdir(dir_path) if f.endswith('.png')])
    images = []
    frame_nums = []
    with ThreadPoolExecutor() as executor:
        futures = []
        for i, frame in enumerate(frames):
            if i % sample_rate == 0:
                path = os.path.join(dir_path, frame)
                futures.append(executor.submit(load_image, path))
                frame_nums.append(i + 1)  # Frame number starting from 1
        images = [f.result() for f in futures]
    return torch.cat(images, dim=0), frame_nums  # Batch tensor [N, C, H, W]

def compute_mse_batch(img1, img2_batch):
    return torch.mean((img1 - img2_batch)**2, dim=[1,2,3])

def compute_ssim_batch(img1, img2_batch):
    mu1 = F.avg_pool2d(img1, 3, 1)
    mu2 = F.avg_pool2d(img2_batch, 3, 1)
    sigma1 = F.avg_pool2d(img1**2, 3, 1) - mu1**2
    sigma2 = F.avg_pool2d(img2_batch**2, 3, 1) - mu2**2
    sigma12 = F.avg_pool2d(img1 * img2_batch, 3, 1) - mu1 * mu2
    c1 = 0.01**2
    c2 = 0.03**2
    ssim = ((2 * mu1 * mu2 + c1) * (2 * sigma12 + c2)) / ((mu1**2 + mu2**2 + c1) * (sigma1 + sigma2 + c2))
    return ssim.mean(dim=[1,2,3])

def detect_cuts(frames_dir, threshold=0.5, sample_rate=1):
    print(f"Detectando cortes em {frames_dir}...")
    batch_imgs, frame_nums = load_images_in_batch(frames_dir, sample_rate)
    cuts = []
    prev_img = None
    for i, img in enumerate(batch_imgs):
        if prev_img is not None:
            diff = compute_mse_batch(prev_img, img.unsqueeze(0)).item()
            if diff > threshold:
                cuts.append(frame_nums[i])
        prev_img = img
    return cuts

def match_frames(bd_cuts, web_batch_imgs, web_frame_nums, bd_frames_dir, ssim_threshold=0.7):
    print("Matching frames...")
    pairs = []
    for bd_cut in bd_cuts:
        bd_frame_path = os.path.join(bd_frames_dir, f"frame_{bd_cut:06d}.png")
        bd_img = load_image(bd_frame_path)
        ssim_scores = compute_ssim_batch(bd_img, web_batch_imgs)
        best_idx = torch.argmax(ssim_scores).item()
        best_ssim = ssim_scores[best_idx].item()
        if best_ssim >= ssim_threshold:
            pairs.append((bd_cut, web_frame_nums[best_idx]))
    return pairs

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

def main(bd, web, auto=True):
    fps_bd, dur_bd = ffprobe_info(bd)
    fps_web, dur_web = ffprobe_info(web)

    if os.path.exists(TEMP):
        shutil.rmtree(TEMP)

    extract_frames(bd, f"{TEMP}/BD_start", 0)
    extract_frames(bd, f"{TEMP}/BD_end", dur_bd - WINDOW)
    extract_frames(web, f"{TEMP}/WEB_start", 0)
    extract_frames(web, f"{TEMP}/WEB_end", dur_web - WINDOW)

    times = []
    
    if auto:
        print("Executando detecção automática de cortes e matching...")
        
        # Start region
        bd_start_cuts = detect_cuts(f"{TEMP}/BD_start", threshold=0.5, sample_rate=SAMPLE_RATE)
        if bd_start_cuts:
            web_start_batch, web_start_nums = load_images_in_batch(f"{TEMP}/WEB_start", SAMPLE_RATE)
            start_pairs = match_frames(bd_start_cuts, web_start_batch, web_start_nums, f"{TEMP}/BD_start")
            times += pairs_to_times(start_pairs, fps_bd, fps_web, dur_bd, dur_web, "start")
        
        # End region
        bd_end_cuts = detect_cuts(f"{TEMP}/BD_end", threshold=0.5, sample_rate=SAMPLE_RATE)
        if bd_end_cuts:
            web_end_batch, web_end_nums = load_images_in_batch(f"{TEMP}/WEB_end", SAMPLE_RATE)
            end_pairs = match_frames(bd_end_cuts, web_end_batch, web_end_nums, f"{TEMP}/BD_end")
            times += pairs_to_times(end_pairs, fps_bd, fps_web, dur_bd, dur_web, "end")
        
        if not times:
            print("Nenhum match automático encontrado. Caindo para modo manual.")
            auto = False

    if not auto:
        os.startfile(TEMP)
        input("\nAnalise os frames e pressione ENTER...\n")
        start_txt = input("Pares START (BD:WEB): ").strip()
        end_txt = input("Pares END (BD:WEB): ").strip()
        start_pairs = parse_pairs(start_txt) if start_txt else []
        end_pairs = parse_pairs(end_txt) if end_txt else []
        times += pairs_to_times(start_pairs, fps_bd, fps_web, dur_bd, dur_web, "start")
        times += pairs_to_times(end_pairs, fps_bd, fps_web, dur_bd, dur_web, "end")

    if not times:
        print("Nenhum par fornecido. Abortando.")
        return

    stretch = compute_stretch(times)
    percent = stretch * 100

    print("\n=== RESULTADO ===")
    print(f"Stretch ideal: {percent:.6f}%")
    print(f"Fator FFmpeg: atempo={stretch:.8f}")

def parse_pairs(txt):
    pairs = []
    for p in txt.split(","):
        a, b = p.strip().split(":")
        pairs.append((int(a), int(b)))
    return pairs

if __name__ == "__main__":
    import sys
    main(sys.argv[1], sys.argv[2])