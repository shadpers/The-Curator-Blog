import sys
import os
import subprocess
import tempfile
import shutil
from pathlib import Path
import re
import json

FFMPEG = r"C:\FFmpeg\bin\ffmpeg.exe"
FFPROBE = r"C:\FFmpeg\bin\ffprobe.exe"

# ------------------------------------------------------------

def die(msg):
    print(f"\nERRO: {msg}")
    input("Pressione ENTER para sair...")
    sys.exit(1)

if not os.path.isfile(FFMPEG):
    die(f"ffmpeg nao encontrado em {FFMPEG}")

if not os.path.isfile(FFPROBE):
    die(f"ffprobe nao encontrado em {FFPROBE}")

# ------------------------------------------------------------

def probe(cmd, file):
    p = subprocess.run(
        [FFPROBE] + cmd + [str(file)],
        capture_output=True,
        text=True
    )
    return p.stdout.strip()

# ------------------------------------------------------------

def get_duration(file):
    try:
        return float(probe(
            ['-v', 'error', '-show_entries', 'format=duration',
             '-of', 'csv=p=0'], file))
    except:
        return 0.0

# ------------------------------------------------------------

def get_resolution(file):
    """Retorna (largura, altura) do vídeo - pega o primeiro stream de vídeo"""
    try:
        # Pega width
        width_str = probe(
            ['-v', 'quiet', '-select_streams', 'v:0',
             '-show_entries', 'stream=width',
             '-of', 'default=noprint_wrappers=1:nokey=1'], file)
        
        # Pega height  
        height_str = probe(
            ['-v', 'quiet', '-select_streams', 'v:0',
             '-show_entries', 'stream=height',
             '-of', 'default=noprint_wrappers=1:nokey=1'], file)
        
        width = int(width_str.strip())
        height = int(height_str.strip())
        
        return width, height
            
    except Exception as e:
        print(f"⚠️  ERRO ao detectar resolução: {e}")
        print(f"    Usando fallback 1920x1080")
        
    # Fallback
    return 1920, 1080

# ------------------------------------------------------------

def get_bit_depth(file):
    """Detecta bit depth do vídeo (8 ou 10 bits)"""
    try:
        pix_fmt = probe(
            ['-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=pix_fmt',
             '-of', 'csv=p=0'], file)
        
        if '10' in pix_fmt or 'p010' in pix_fmt:
            return 10
        return 8
    except:
        return 8

# ------------------------------------------------------------

def get_video_bitrate_kbps(file):
    """Calcula bitrate CORRETO do vídeo usando ffprobe"""
    try:
        # Tenta pegar bitrate direto do stream
        bitrate_str = probe(
            ['-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=bit_rate',
             '-of', 'csv=p=0'], file)
        
        if bitrate_str and bitrate_str.isdigit():
            return int(bitrate_str) // 1000
        
        # Fallback: calcula pelo tamanho total e duração
        duration = get_duration(file)
        if duration <= 0:
            return 0
            
        # Pega bitrate total do container
        total_bitrate_str = probe(
            ['-v', 'error', '-show_entries', 'format=bit_rate',
             '-of', 'csv=p=0'], file)
        
        if total_bitrate_str and total_bitrate_str.isdigit():
            total_kbps = int(total_bitrate_str) // 1000
            return int(total_kbps * 0.80)
        
        # Último fallback
        size_bytes = file.stat().st_size
        bitrate_bps = (size_bytes * 8) / duration
        return int((bitrate_bps * 0.75) / 1000)
        
    except Exception as e:
        print(f"AVISO: Erro ao calcular bitrate: {e}")
        return 0

# ------------------------------------------------------------

def get_available_resolutions(width, height):
    """
    Retorna resoluções disponíveis baseado na source com margens de erro.
    Formato: [(label, target_height, is_available, is_downscale), ...]
    """
    resolutions = []
    
    # 4K (2160p) - margem: 2000-2400
    if height >= 2000:
        is_native = 2100 <= height <= 2200  # É nativo 4K?
        label = "4K (2160p)" if not is_native else "4K (2160p) - Resolução nativa"
        resolutions.append((label, 2160, True, height > 2160))
    
    # Full HD (1080p) - margem: 1000-1200
    if height >= 1000:
        is_native = 1050 <= height <= 1110
        label = "Full HD (1080p)" if not is_native else "Full HD (1080p) - Resolução nativa"
        resolutions.append((label, 1080, True, height > 1080))
    
    # HD (720p) - margem: 680-800
    if height >= 680:
        is_native = 700 <= height <= 750
        label = "HD (720p)" if not is_native else "HD (720p) - Resolução nativa"
        resolutions.append((label, 720, True, height > 720))
    
    # SD (480p) - margem: 400-600
    if height >= 400:
        is_native = 460 <= height <= 520
        label = "SD (480p)" if not is_native else "SD (480p) - Resolução nativa"
        resolutions.append((label, 480, True, height > 480))
    
    return resolutions

# ------------------------------------------------------------

def select_resolution(file):
    """Permite usuário escolher resolução de saída"""
    width, height = get_resolution(file)
    resolutions = get_available_resolutions(width, height)
    
    print("\n" + "=" * 60)
    print(f"RESOLUÇÃO DO ARQUIVO: {width}x{height}")
    print("=" * 60)
    print("ESCOLHA A RESOLUÇÃO DE SAÍDA:")
    print("=" * 60)
    
    options = []
    idx = 1
    for label, target_h, available, is_downscale in resolutions:
        if available:
            # Adiciona indicador de downscale
            indicator = " ⬇ REDUZIR" if is_downscale else ""
            print(f"{idx}. {label}{indicator}")
            options.append((idx, target_h, is_downscale))
            idx += 1
    
    print("=" * 60)
    
    while True:
        choice = input(f"Escolha (1-{len(options)}): ").strip()
        try:
            choice_num = int(choice)
            for opt_idx, target_height, is_downscale in options:
                if opt_idx == choice_num:
                    # Se é a resolução nativa (±5%), não faz resize
                    if abs(target_height - height) <= 10:
                        print(f"\nResolução selecionada: ORIGINAL ({width}x{height}) - Sem resize")
                        return None
                    else:
                        # Calcula largura mantendo aspect ratio
                        target_width = int((width / height) * target_height)
                        # Garante que seja divisível por 2
                        target_width = target_width - (target_width % 2)
                        target_height = target_height - (target_height % 2)
                        action = "Reduzindo" if is_downscale else "Mantendo"
                        print(f"\n{action} para: {target_width}x{target_height}")
                        return (target_width, target_height)
        except:
            pass
        print(f"Opção inválida! Digite um número entre 1 e {len(options)}")

# ------------------------------------------------------------

def select_conversion_mode():
    """Permite ao usuário escolher o modo de conversão"""
    print("\n" + "=" * 60)
    print("ESCOLHA O MODO DE CONVERSÃO")
    print("=" * 60)
    print("1. LOSSLESS - Qualidade máxima (pouca compressão)")
    print("2. MEDIUM   - Equilíbrio qualidade/tamanho")
    print("3. LOW      - Máxima compressão (boa qualidade)")
    print("=" * 60)
    
    while True:
        choice = input("Escolha (1/2/3): ").strip()
        if choice in ['1', '2', '3']:
            modes = {'1': 'lossless', '2': 'medium', '3': 'low'}
            selected = modes[choice]
            print(f"\nModo selecionado: {selected.upper()}\n")
            return selected
        print("Opção inválida! Digite 1, 2 ou 3")

# ------------------------------------------------------------

def select_preview_mode():
    """Pergunta se quer modo prévia"""
    print("\n" + "=" * 60)
    print("MODO PRÉVIA")
    print("=" * 60)
    print("O modo prévia renderiza pequenos trechos do vídeo para")
    print("estimar o tamanho final ANTES de processar tudo.")
    print("=" * 60)
    print("1. SIM - Fazer prévia (recomendado para arquivos grandes)")
    print("2. NÃO - Processar direto")
    print("=" * 60)
    
    while True:
        choice = input("Escolha (1/2): ").strip()
        if choice == '1':
            print("\nModo PRÉVIA ativado\n")
            return True
        elif choice == '2':
            print("\nProcessamento DIRETO\n")
            return False
        print("Opção inválida! Digite 1 ou 2")

# ------------------------------------------------------------

def decide_params(v_bitrate_kbps, src_size_gb, height, bit_depth, mode='medium'):
    """
    Lógica INTELIGENTE com detecção de:
    1. Source já comprimido (bitrate baixo)
    2. Source 10-bit (precisa CQ maior para comprimir)
    """
    
    # Ajuste baseado em resolução
    res_adjust = 0
    if height >= 2160:  # 4K
        res_adjust = -2
        res_label = "4K"
        bitrate_threshold = 8000
    elif height >= 1440:  # 2K
        res_adjust = -1
        res_label = "2K"
        bitrate_threshold = 5000
    elif height >= 1070:  # 1080p
        res_label = "1080p"
        bitrate_threshold = 2500
    elif height >= 700:  # 720p
        res_adjust = +1
        res_label = "720p"
        bitrate_threshold = 1500
    else:
        res_adjust = +2
        res_label = f"{height}p"
        bitrate_threshold = 1000
    
    # DETECÇÃO 1: Source já está comprimido?
    already_compressed = v_bitrate_kbps < bitrate_threshold
    compression_penalty = 0
    
    if already_compressed:
        compression_penalty = +4
        print(f"⚠️  Source comprimido ({v_bitrate_kbps} kbps < {bitrate_threshold} kbps)")
        print(f"    Boost CQ: +{compression_penalty}")
    
    # DETECÇÃO 2: Source é 10-bit?
    bit_depth_penalty = 0
    if bit_depth == 10:
        bit_depth_penalty = +3
        print(f"⚠️  Source 10-bit detectado")
        print(f"    Boost CQ: +{bit_depth_penalty}")
    
    # Tabela de CQ por modo
    if mode == 'lossless':
        if v_bitrate_kbps >= 15000:
            base_cq = 18
            level = "ARQUIVAL"
        elif v_bitrate_kbps >= 10000:
            base_cq = 19
            level = "PREMIUM"
        elif v_bitrate_kbps >= 6000:
            base_cq = 20
            level = "ALTA"
        elif v_bitrate_kbps >= 3000:
            base_cq = 21
            level = "MEDIA-ALTA"
        else:
            base_cq = 22
            level = "MEDIA"
        cq_min, cq_max = 18, 28
        
    elif mode == 'medium':
        if v_bitrate_kbps >= 15000:
            base_cq = 23
            level = "ARQUIVAL"
        elif v_bitrate_kbps >= 10000:
            base_cq = 24
            level = "PREMIUM"
        elif v_bitrate_kbps >= 6000:
            base_cq = 25
            level = "ALTA"
        elif v_bitrate_kbps >= 3000:
            base_cq = 26
            level = "MEDIA"
        else:
            base_cq = 27
            level = "MEDIA-BAIXA"
        cq_min, cq_max = 23, 32
        
    else:  # mode == 'low'
        if v_bitrate_kbps >= 15000:
            base_cq = 27
            level = "ARQUIVAL compacto"
        elif v_bitrate_kbps >= 10000:
            base_cq = 28
            level = "PREMIUM compacto"
        elif v_bitrate_kbps >= 6000:
            base_cq = 29
            level = "ALTA compacto"
        elif v_bitrate_kbps >= 3000:
            base_cq = 30
            level = "MEDIA compacto"
        else:
            base_cq = 31
            level = "BAIXA"
        cq_min, cq_max = 27, 38
    
    # Aplicar TODOS os ajustes
    cq = base_cq + res_adjust + compression_penalty + bit_depth_penalty
    
    # Garantir limites
    cq = max(cq_min, min(cq_max, cq))
    
    print(f"Modo: {mode.upper()}")
    print(f"Resolução: {res_label} | Bit depth: {bit_depth}-bit")
    print(f"Complexidade: {level}")
    print(f"CQ: base={base_cq} res={res_adjust:+d} comp={compression_penalty:+d} 10bit={bit_depth_penalty:+d} FINAL={cq}")

    return [
        "-c:v", "hevc_nvenc",
        "-profile:v", "main10",
        "-tier", "high",
        "-pix_fmt", "p010le",
        "-rc", "vbr_hq",
        "-cq", str(cq),
        "-preset", "p7",
        "-rc-lookahead", "32",
        "-b_ref_mode", "middle",
        "-bf", "4",
        "-spatial_aq", "1",
        "-temporal_aq", "1",
        "-aq-strength", "8",
        "-nonref_p", "1",
        "-strict_gop", "1"
    ]

# ------------------------------------------------------------

def run_preview_encode(file, vopts, resolution, duration):
    """
    Renderiza 3 samples do vídeo (início, meio, fim) para estimar tamanho final.
    Cada sample tem 30 segundos.
    """
    print("\n" + "=" * 60)
    print("MODO PRÉVIA - Renderizando samples...")
    print("=" * 60)
    
    # 3 samples de 30s cada
    sample_duration = 30
    positions = [
        ("INÍCIO", 60),  # Começa em 1min (pula intro/créditos)
        ("MEIO", duration / 2),
        ("FIM", max(duration - 300, duration / 2 + 60))  # 5min antes do fim
    ]
    
    total_sample_size = 0
    samples_encoded = 0
    
    with tempfile.TemporaryDirectory() as tmpdir:
        for label, start_time in positions:
            sample_file = Path(tmpdir) / f"sample_{label.lower()}.mkv"
            
            print(f"\nSample {label} (posição: {int(start_time//60)}min{int(start_time%60)}s)...")
            
            # Monta comando ffmpeg
            cmd = [FFMPEG, "-y", "-ss", str(start_time), "-i", str(file),
                   "-t", str(sample_duration), "-map", "0:v:0"]
            
            # Adiciona resize se necessário
            if resolution:
                w, h = resolution
                cmd += ["-vf", f"scale={w}:{h}"]
            
            cmd += vopts + ["-an", str(sample_file)]  # -an = sem áudio (mais rápido)
            
            # Executa
            p = subprocess.run(cmd, capture_output=True)
            
            if p.returncode == 0 and sample_file.exists():
                size_mb = sample_file.stat().st_size / (1024**2)
                total_sample_size += size_mb
                samples_encoded += 1
                print(f"✓ Sample {label}: {size_mb:.2f} MB")
            else:
                print(f"✗ Falha no sample {label}")
    
    if samples_encoded == 0:
        print("\n⚠️  ERRO: Nenhum sample foi codificado com sucesso!")
        return None
    
    # Calcula estimativa
    avg_sample_mb = total_sample_size / samples_encoded
    bitrate_kbps = (avg_sample_mb * 1024 * 8) / sample_duration  # MB -> kbps
    estimated_video_mb = (bitrate_kbps * duration) / (8 * 1024)  # Total em MB
    
    # Estima tamanho do áudio (copia = mesmo tamanho)
    src_size_mb = file.stat().st_size / (1024**2)
    audio_estimate_mb = src_size_mb * 0.15  # Assume ~15% é áudio
    
    estimated_total_gb = (estimated_video_mb + audio_estimate_mb) / 1024
    
    print("\n" + "=" * 60)
    print("ESTIMATIVA DO ARQUIVO FINAL")
    print("=" * 60)
    print(f"Bitrate estimado do vídeo: {int(bitrate_kbps)} kbps")
    print(f"Tamanho estimado do vídeo: {estimated_video_mb/1024:.2f} GB")
    print(f"Tamanho estimado do áudio: {audio_estimate_mb/1024:.2f} GB")
    print(f"TAMANHO TOTAL ESTIMADO: {estimated_total_gb:.2f} GB")
    print(f"Margem de erro: ±8%")
    print("=" * 60)
    
    return {
        'bitrate_kbps': int(bitrate_kbps),
        'estimated_gb': estimated_total_gb,
        'video_gb': estimated_video_mb / 1024,
        'audio_gb': audio_estimate_mb / 1024
    }

# ------------------------------------------------------------

def run_ffmpeg(cmd, duration, show_progress=True):
    cmd = cmd[:1] + ['-loglevel', 'error', '-stats'] + cmd[1:]
    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    if not show_progress:
        p.wait()
        return p.returncode == 0

    last = -1
    print("Progresso:")

    for line in p.stdout:
        if "time=" in line:
            m = re.search(r'time=(\d+:\d+:\d+\.\d+)', line)
            if m and duration > 0:
                t = parse_time(m.group(1))
                pct = min((t / duration) * 100, 100)
                if abs(pct - last) >= 0.5:
                    last = pct
                    bar = int(pct // 3) * "█"
                    bar = bar.ljust(30, "░")
                    print(f"\r[{bar}] {pct:5.1f}%", end="", flush=True)

    p.wait()
    print()
    return p.returncode == 0

# ------------------------------------------------------------

def parse_time(t):
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)

# ------------------------------------------------------------

def check_disk_space_and_decide(src, estimated_output_gb=None, batch_decision=None):
    """
    Analisa espaço em disco e decide a melhor estratégia de processamento.
    Retorna: ('copy', temp_input_path) ou ('direct', None)
    """
    import shutil as sh
    
    # Verifica se é HD externo
    is_external = not str(src).startswith("C:")
    
    if not is_external:
        # Já está no C:, processa localmente
        return ('direct', None)
    
    # Pega espaço livre no C:
    c_drive = Path("C:/")
    c_stats = sh.disk_usage(c_drive)
    c_free_gb = c_stats.free / (1024**3)
    
    src_size_gb = src.stat().st_size / (1024**3)
    
    # Estima tamanho do output (se não fornecido, usa estimativa conservadora)
    if estimated_output_gb is None:
        # Estimativa: 20% do tamanho original (conservador)
        estimated_output_gb = src_size_gb * 0.20
    
    # Cenário 1: COPIAR source + processar no C:
    space_needed_copy = src_size_gb + estimated_output_gb
    space_remaining_copy = c_free_gb - space_needed_copy
    
    # Cenário 2: LER do HD externo + escrever output no C:
    space_needed_direct = estimated_output_gb
    space_remaining_direct = c_free_gb - space_needed_direct
    
    print("\n" + "=" * 60)
    print("ANÁLISE DE ESPAÇO EM DISCO")
    print("=" * 60)
    print(f"Espaço livre no C:: {c_free_gb:.2f} GB")
    print(f"Tamanho do arquivo: {src_size_gb:.2f} GB")
    print(f"Output estimado: {estimated_output_gb:.2f} GB")
    print("=" * 60)
    
    print("\nCENÁRIO 1: COPIAR + PROCESSAR NO C: (mais rápido)")
    print(f"  • Espaço necessário: {space_needed_copy:.2f} GB")
    print(f"  • Espaço restante: {space_remaining_copy:.2f} GB")
    print(f"  • Velocidade: ⚡⚡⚡ MÁXIMA (~2-3h)")
    
    print("\nCENÁRIO 2: PROCESSAR DIRETO DO HD EXTERNO (economiza espaço)")
    print(f"  • Espaço necessário: {space_needed_direct:.2f} GB")
    print(f"  • Espaço restante: {space_remaining_direct:.2f} GB")
    print(f"  • Velocidade: ⚡⚡ MÉDIA (~3-4h)")
    print("=" * 60)
    
    # Decisão automática ou manual
    SAFE_MARGIN_GB = 20
    
    # Cenário 1 é viável E seguro?
    can_copy = space_remaining_copy >= SAFE_MARGIN_GB
    
    # Cenário 2 é viável?
    can_direct = space_remaining_direct >= SAFE_MARGIN_GB
    
    if can_copy:
        # Pode copiar com segurança
        print(f"\n✅ RECOMENDAÇÃO: COPIAR para C: (espaço suficiente)")
        print(f"   Restará {space_remaining_copy:.2f} GB livres (> {SAFE_MARGIN_GB} GB)")

        # Verifica decisão em lote já tomada
        if batch_decision is not None and batch_decision.get('copy') is not None:
            if batch_decision['copy']:
                print("→ [Sim para todos] Copiando para C:")
                temp_work_dir = Path("C:/Temp/ffmpeg_work")
                temp_work_dir.mkdir(parents=True, exist_ok=True)
                return ('copy', temp_work_dir / src.name)
            else:
                print("→ [Não para todos] Processando direto do HD externo")
                return ('direct', None)

        print("\n  S  ou  SIM  = Sim (só este arquivo)")
        print("  N  ou  NAO  = Não (só este arquivo)")
        print("  SA          = Sim para TODOS os próximos")
        print("  NA          = Não para TODOS os próximos")
        while True:
            choice = input("\nCopiar para C: para máxima velocidade? (S/N/SA/NA): ").strip().upper()
            if choice in ('S', 'SIM', 'SA'):
                if choice == 'SA' and batch_decision is not None:
                    batch_decision['copy'] = True
                    print("→ [Sim para todos] será aplicado aos próximos arquivos")
                temp_work_dir = Path("C:/Temp/ffmpeg_work")
                temp_work_dir.mkdir(parents=True, exist_ok=True)
                return ('copy', temp_work_dir / src.name)
            elif choice in ('N', 'NAO', 'NA'):
                if choice == 'NA' and batch_decision is not None:
                    batch_decision['copy'] = False
                    print("→ [Não para todos] será aplicado aos próximos arquivos")
                print("→ Processando direto do HD externo")
                return ('direct', None)
            print("Opção inválida! Use S, N, SA ou NA")
    
    elif can_direct:
        # Só cabe o output, não a cópia
        print(f"\n⚠️  RECOMENDAÇÃO: PROCESSAR DIRETO (espaço limitado)")
        print(f"   Copiar deixaria apenas {space_remaining_copy:.2f} GB livres (< {SAFE_MARGIN_GB} GB)")
        print(f"   Processar direto deixará {space_remaining_direct:.2f} GB livres")
        
        print("\nOPÇÕES:")
        print("1. PROCESSAR DIRETO (recomendado) - mais lento mas seguro")
        print("2. COPIAR mesmo assim (RISCO de ficar sem espaço)")
        print("3. CANCELAR e liberar espaço no C:")
        
        choice = input("\nEscolha (1/2/3): ").strip()
        
        if choice == '1':
            return ('direct', None)
        elif choice == '2':
            print(f"⚠️  AVISO: Restará apenas {space_remaining_copy:.2f} GB livres!")
            confirm = input("Confirma? (S/N): ").strip().upper()
            if confirm == 'S':
                temp_work_dir = Path("C:/Temp/ffmpeg_work")
                temp_work_dir.mkdir(parents=True, exist_ok=True)
                return ('copy', temp_work_dir / src.name)
            else:
                return ('direct', None)
        else:
            print("\nConversão cancelada. Libere espaço no C: e tente novamente.")
            return ('cancel', None)
    
    else:
        # Nem o output cabe!
        print(f"\n❌ ERRO: ESPAÇO INSUFICIENTE NO C:")
        print(f"   Necessário: {space_needed_direct:.2f} GB para output")
        print(f"   Disponível: {c_free_gb:.2f} GB")
        print(f"   Faltam: {space_needed_direct - c_free_gb:.2f} GB")
        print(f"\n   Libere pelo menos {space_needed_direct + SAFE_MARGIN_GB:.2f} GB no C: para continuar.")
        
        input("\nPressione ENTER para cancelar...")
        return ('cancel', None)
def process(file, mode='medium', preview=False, resolution=None, batch_decision=None):
    src = Path(file)
    if not src.exists():
        die("Arquivo nao encontrado")

    # Detecta se é HD externo
    is_external = not str(src).startswith("C:")
    
    # Define outputs
    final_output = src.with_name(src.stem + "_H265.mkv")
    
    try:
        # SEMPRE lê do arquivo original para análise inicial
        work_file = src
        
        duration = get_duration(work_file)
        if duration <= 0:
            duration = 1500

        width, height = get_resolution(work_file)
        bit_depth = get_bit_depth(work_file)
        src_size_gb = src.stat().st_size / (1024**3)
        v_bitrate = get_video_bitrate_kbps(work_file)

        print(f"\nTamanho source: {src_size_gb:.2f} GB")
        print(f"Resolução source: {width}x{height}")
        print(f"Bitrate source: {v_bitrate} kbps")
        print(f"Bit depth: {bit_depth}-bit\n")

        target_height = resolution[1] if resolution else height
        
        vopts = decide_params(v_bitrate, src_size_gb, target_height, bit_depth, mode)

        # MODO PRÉVIA
        estimated_output_gb = None
        if preview:
            preview_result = run_preview_encode(src, vopts, resolution, duration)
            
            if preview_result:
                estimated_output_gb = preview_result['estimated_gb']
                
                print("\n" + "=" * 60)
                choice = input("Continuar com a conversão completa? (S/N): ").strip().upper()
                if choice != 'S':
                    print("Conversão cancelada pelo usuário.")
                    return False
                print("=" * 60)

        # ANÁLISE DE ESPAÇO E DECISÃO DE ESTRATÉGIA
        if is_external:
            strategy, temp_input = check_disk_space_and_decide(src, estimated_output_gb, batch_decision)
            
            if strategy == 'cancel':
                return False
            elif strategy == 'copy':
                # Copia para C: primeiro
                print(f"\n📁 Copiando {src_size_gb:.2f} GB para C:...")
                print("   (isso pode levar 10-20 minutos)")
                
                import time
                start = time.time()
                shutil.copy2(src, temp_input)
                elapsed = time.time() - start
                
                print(f"   ✓ Cópia concluída em {elapsed/60:.1f} minutos")
                work_file = temp_input
                temp_output = temp_input.parent / (src.stem + "_H265_temp.mkv")
            else:  # strategy == 'direct'
                # Processa direto
                work_file = src
                temp_work_dir = Path("C:/Temp/ffmpeg_work")
                temp_work_dir.mkdir(parents=True, exist_ok=True)
                temp_output = temp_work_dir / (src.stem + "_H265_temp.mkv")
        else:
            # Já está no C:
            work_file = src
            temp_output = src.with_name(src.stem + "_H265_temp.mkv")
            strategy = 'local'
            temp_input = None

        # Monta comando final
        cmd = [FFMPEG, "-y", "-i", str(work_file), "-map", "0"]
        
        if resolution:
            w, h = resolution
            cmd += ["-vf", f"scale={w}:{h}"]
        
        cmd += vopts + [
            "-c:a", "copy",
            "-c:s", "copy",
            "-map_metadata", "0",
            "-map_chapters", "0",
            str(temp_output)
        ]

        print("\n" + "=" * 60)
        print("INICIANDO CONVERSÃO COMPLETA")
        if strategy == 'copy':
            print("📌 Estratégia: CÓPIA + PROCESSAMENTO (máxima velocidade)")
            print(f"   Lendo de: C: (SSD)")
            print(f"   Escrevendo em: C: (SSD)")
        elif strategy == 'direct':
            print("📌 Estratégia: PROCESSAMENTO DIRETO (economia de espaço)")
            print(f"   Lendo de: {str(src)[0]}: (HD externo)")
            print(f"   Escrevendo em: C: (SSD)")
        print("=" * 60)
        
        ok = run_ffmpeg(cmd, duration)
        
        if ok:
            out_size_gb = temp_output.stat().st_size / (1024**3)
            
            # Move o resultado final
            if is_external:
                print(f"\n📁 Movendo arquivo final para {str(src)[0]}:...")
                import time
                start = time.time()
                shutil.move(str(temp_output), str(final_output))
                elapsed = time.time() - start
                print(f"   ✓ Movido em {elapsed/60:.1f} minutos")
            else:
                shutil.move(str(temp_output), str(final_output))
            
            reduction = ((src_size_gb - out_size_gb) / src_size_gb) * 100
            print(f"\n✓ SUCESSO: {final_output.name}")
            print(f"Tamanho original: {src_size_gb:.2f} GB")
            print(f"Tamanho final: {out_size_gb:.2f} GB")
            print(f"Redução: {reduction:.1f}%")
            
            if preview and estimated_output_gb:
                error = abs(out_size_gb - estimated_output_gb) / estimated_output_gb * 100
                print(f"Estimativa prévia: {estimated_output_gb:.2f} GB")
                print(f"Erro da estimativa: {error:.1f}%")
        
        return ok

    finally:
        # Limpeza
        try:
            if 'temp_input' in locals() and temp_input and temp_input.exists():
                os.unlink(temp_input)
                print(f"\n🗑️  Input temporário removido do C:")
        except:
            pass
        
        try:
            if 'temp_output' in locals() and temp_output.exists():
                os.unlink(temp_output)
                print(f"🗑️  Output temporário removido do C:")
        except:
            pass

# ------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Uso: arraste arquivos para o script")
        input("Pressione ENTER para sair...")
        sys.exit(1)

    files = sys.argv[1:]
    
    # Mostra info do primeiro arquivo para configuração
    first_file = Path(files[0])
    
    print("=" * 60)
    print(f"CONFIGURAÇÃO (baseada em: {first_file.name})")
    print("=" * 60)
    
    # Seleções
    resolution = select_resolution(first_file)
    mode = select_conversion_mode()
    preview = select_preview_mode()

    print("\n" + "=" * 60)
    print(f"PROCESSANDO {len(files)} ARQUIVO(S)")
    print("=" * 60)

    success_count = 0
    batch_decision = {'copy': None}  # Compartilhado entre todos os arquivos
    for i, f in enumerate(files, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{len(files)}] {Path(f).name}")
        print("=" * 60)
        
        # Preview só no primeiro arquivo em batch
        use_preview = preview and (i == 1)
        
        if process(f, mode, use_preview, resolution, batch_decision):
            success_count += 1

    print("\n" + "=" * 60)
    print(f"CONCLUÍDO: {success_count}/{len(files)} sucesso")
    print("=" * 60)
    input("Pressione ENTER para sair...")
    sys.exit(0 if success_count == len(files) else 1)

# ------------------------------------------------------------

if __name__ == "__main__":
    main()