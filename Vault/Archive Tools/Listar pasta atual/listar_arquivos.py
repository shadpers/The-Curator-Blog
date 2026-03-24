import os
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from tqdm import tqdm
import sys

def get_media_info(ffprobe_path, file_path):
    """Return duration (in seconds) and creation time of the media."""
    try:
        cmd = [
            ffprobe_path, "-v", "error", "-show_entries",
            "format=duration:format_tags=creation_time",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path)
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        lines = result.stdout.strip().split("\n")
        duration = float(lines[0]) if lines and lines[0] else 0.0
        creation_time = lines[1] if len(lines) > 1 else None
        return duration, creation_time
    except Exception:
        return 0.0, None

def format_duration(seconds: float) -> str:
    """Convert seconds to HH:MM:SS."""
    if not seconds or seconds <= 0:
        return "00:00:00"
    return str(timedelta(seconds=int(seconds)))

def format_creation_time(creation_time: str) -> str:
    """Format creation date to YYYY-MM-DD HH:MM:SS."""
    if not creation_time:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(creation_time.replace("Z", ""))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return creation_time

def safe_text(text: str) -> str:
    """Remove/replace invalid unicode characters."""
    return text.encode("utf-8", errors="replace").decode("utf-8")

def main():
    if len(sys.argv) < 2:
        print("Usage: python listar_arquivos.py <ffprobe_path>")
        return

    ffprobe_path = sys.argv[1]

    print("""
Choose how to sort the files:
1 - By size
2 - Alphabetically
3 - By duration (media)
4 - By creation date (media)
""")
    choice = input("Option: ").strip()

    folder = Path(__file__).parent
    files = [f for f in folder.iterdir() if f.is_file()]

    durations = {}
    creations = {}
    sizes = {}

    print("\nProcessing files...\n")
    for file in tqdm(files, desc="Reading files", unit="file"):
        dur, cri = get_media_info(ffprobe_path, file)
        durations[file] = dur
        creations[file] = cri
        if choice == "1":
            sizes[file] = file.stat().st_size

    if choice == "1":
        files.sort(key=lambda x: sizes[x], reverse=True)
    elif choice == "2":
        files.sort(key=lambda x: x.name.lower())
    elif choice == "3":
        files.sort(key=lambda x: durations[x], reverse=True)
    elif choice == "4":
        files.sort(key=lambda x: creations[x] or "", reverse=True)

    txt_path = folder / "file_list.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        for file in files:
            size_mb = file.stat().st_size / (1024 * 1024)
            dur = format_duration(durations.get(file, 0.0))
            cri = format_creation_time(creations.get(file, None))
            line = f"{file.name} | {size_mb:.2f} MB | {dur} | {cri}\n"
            f.write(safe_text(line))

    print(f"\nList generated at: {txt_path}")

if __name__ == "__main__":
    main()
