import sys
import os
from PIL import Image

MAX_SIZE_KB = 200
MIN_DIMENSION = 200
PRECISION = 0.001  # precisão da escala para parar a busca

def has_alpha(img: Image.Image) -> bool:
    return img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)

def save_png(img: Image.Image, dims, path):
    resized = img.resize(dims, Image.LANCZOS)
    resized.save(path, optimize=True)
    return os.path.getsize(path) / 1024  # KB

def base_out_path(path):
    base, _ = os.path.splitext(path)
    return base + "_twitter.png"

def progress_bar(current, total, prefix=""):
    width = 30
    filled = int(width * current / max(total, 1))
    bar = "█" * filled + "░" * (width - filled)
    print(f"\r{prefix} [{bar}] {int(100*current/max(total,1))}%", end="", flush=True)
    if current == total:
        print()

def binary_search_scale(img, orig_kb):
    width, height = img.size
    low = max(MIN_DIMENSION / width, MIN_DIMENSION / height)
    high = 1.0
    best_scale = low
    best_size = None
    best_dims = None
    iterations = 20  # max de tentativas para segurança
    for i in range(iterations):
        mid = (low + high) / 2
        new_w = max(int(width * mid), 1)
        new_h = max(int(height * mid), 1)
        size_kb = save_png(img, (new_w, new_h), "_temp.png")
        progress_bar(i+1, iterations, prefix="Buscando escala ideal")
        if size_kb <= MAX_SIZE_KB:
            best_scale = mid
            best_size = size_kb
            best_dims = (new_w, new_h)
            low = mid  # tentar aumentar para mais qualidade
        else:
            high = mid  # reduzir escala
        if high - low < PRECISION:
            break
    # remove temp file
    if os.path.exists("_temp.png"):
        os.remove("_temp.png")
    return best_dims, best_size

def optimize_png(path):
    img = Image.open(path)
    if not has_alpha(img):
        print(f"[!] Arquivo não tem transparência real: {path}")
        return

    print(f"[i] PNG com transparência detectado: {path}")
    width, height = img.size
    orig_kb = os.path.getsize(path) / 1024

    best_dims, best_size = binary_search_scale(img, orig_kb)
    out_path = base_out_path(path)
    save_png(img, best_dims, out_path)

    reduction = 100 - (best_size / orig_kb * 100)
    print(f"\n[✓] Exportado: {out_path}")
    print(f"    Original: {orig_kb:.1f} KB ({width}x{height})")
    print(f"    Final:    {best_size:.1f} KB ({best_dims[0]}x{best_dims[1]})")
    print(f"    Redução: {reduction:.1f}%")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Arraste um arquivo PNG em cima do .bat!")
        sys.exit(1)

    optimize_png(sys.argv[1])
    input("\n[✔] Processo concluído. Pressione ENTER para fechar...")
