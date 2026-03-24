#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Track Namer — Padronização de Faixas MKV
Reordena e renomeia faixas de áudio e legenda conforme convenção de curadoria.

Uso: arraste arquivos .mkv ou pastas contendo .mkv sobre o track_namer.bat
"""

import subprocess
import sys
import json
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict

# ─── Executável ───────────────────────────────────────────────────────────────
MKVMERGE = r"C:\Program Files\MKVToolNix\mkvmerge.exe"

# ─── Ordem de prioridade canônica ─────────────────────────────────────────────
# Top 15 idiomas mais comuns em releases de internet + variante europeia de PT
LANGUAGE_ORDER: List[str] = [
    "jpn",        #  1  Japanese
    "eng",        #  2  English
    "por_br",     #  3  Português Brasileiro
    "spa_lat",    #  4  Español Latino
    "spa_cast",   #  5  Español Castelhano
    "fre",        #  6  Français
    "ita",        #  7  Italiano
    "ger",        #  8  Deutsch
    "rus",        #  9  Русский
    "chi_s",      # 10  中文 (Simplificado)
    "chi_t",      # 11  中文 (Tradicional)
    "kor",        # 12  한국어
    "ara",        # 13  العربية
    "hin",        # 14  हिन्दी
    "dut",        # 15  Nederlands
    "por_pt",     #     Português (Europeu) — suportado mas fora do top-15
]

LANGUAGE_NAMES: Dict[str, str] = {
    "jpn":      "Japanese",
    "eng":      "English",
    "por_br":   "Português Brasileiro",
    "spa_lat":  "Español Latino",
    "spa_cast": "Español Castelhano",
    "fre":      "Français",
    "ita":      "Italiano",
    "ger":      "Deutsch",
    "rus":      "Русский",
    "chi_s":    "中文 (Simplificado)",
    "chi_t":    "中文 (Tradicional)",
    "kor":      "한국어",
    "ara":      "العربية",
    "hin":      "हिन्दी",
    "dut":      "Nederlands",
    "por_pt":   "Português (Europeu)",
}

# BCP-47 (IETF) → chave canônica
# Tags com subtag regional são consideradas "certas" (ex: "pt-BR", "es-419")
# Tags genéricas são "incertas" e podem precisar de desambiguação (ex: "pt", "es")
IETF_MAP: Dict[str, str] = {
    # Japonês
    "ja":       "jpn",
    # Inglês
    "en":       "eng",    "en-us":    "eng",    "en-gb":   "eng",
    # Português — "pt" genérico presume BR; "pt-pt" é certo para europeu
    "pt":       "por_br", "pt-br":    "por_br", "pt-pt":   "por_pt",
    # Espanhol — "es" genérico presume Latino; tags regionais são certas
    "es":       "spa_lat","es-419":   "spa_lat","es-la":   "spa_lat",
    "es-mx":    "spa_lat","es-ar":    "spa_lat","es-co":   "spa_lat",
    "es-cl":    "spa_lat","es-ve":    "spa_lat","es-pe":   "spa_lat",
    "es-es":    "spa_cast",
    # Francês
    "fr":       "fre",    "fr-fr":    "fre",
    # Italiano
    "it":       "ita",    "it-it":    "ita",
    # Alemão
    "de":       "ger",    "de-de":    "ger",    "de-at":   "ger",
    # Russo
    "ru":       "rus",    "ru-ru":    "rus",
    # Chinês — "zh" genérico presume Simplificado
    "zh":       "chi_s",  "zh-hans":  "chi_s",  "zh-cn":   "chi_s",  "zh-sg": "chi_s",
    "zh-hant":  "chi_t",  "zh-tw":    "chi_t",  "zh-hk":   "chi_t",
    # Coreano
    "ko":       "kor",    "ko-kr":    "kor",
    # Árabe
    "ar":       "ara",    "ar-sa":    "ara",
    # Hindi
    "hi":       "hin",    "hi-in":    "hin",
    # Holandês
    "nl":       "dut",    "nl-nl":    "dut",    "nl-be":   "dut",
}

# ISO 639-2 → chave canônica (fallback quando não há tag IETF)
# Presunções de variante padrão estão comentadas
ISO_MAP: Dict[str, str] = {
    "jpn": "jpn",
    "eng": "eng",
    "por": "por_br",    # presume Brasileiro
    "spa": "spa_lat",   # presume Latino
    "fre": "fre",  "fra": "fre",
    "ita": "ita",
    "ger": "ger",  "deu": "ger",
    "rus": "rus",
    "chi": "chi_s", "zho": "chi_s", "cmn": "chi_s",  # presume Simplificado
    "kor": "kor",
    "ara": "ara",
    "hin": "hin",
    "dut": "dut",  "nld": "dut",
}

# ISO codes que possuem variantes ambíguas (dois dialetos distintos)
AMBIGUOUS_ISO: Dict[str, Tuple[str, ...]] = {
    "por": ("por_br",  "por_pt"),
    "spa": ("spa_lat", "spa_cast"),
    "chi": ("chi_s",   "chi_t"),
    "zho": ("chi_s",   "chi_t"),
}

# Tags IETF "genéricas" (sem subtag regional) que não disambiguam variante
# Sua presença NÃO garante certeza na atribuição
GENERIC_IETF: Dict[str, set] = {
    "por": {"pt"},
    "spa": {"es"},
    "chi": {"zh"},
    "zho": {"zh"},
}

# Padrões regex no nome/título da faixa para detectar variante
VARIANT_HINTS: Dict[str, List[str]] = {
    "spa_lat":  [r"\blat(ino|am|in)?\b", r"\bes[-_]419\b", r"\blatam\b",
                 r"\bmex(icano)?\b", r"\barg(entino)?\b", r"\bcol(ombiano)?\b",
                 r"\bvene(zolano)?\b", r"\bchile(no)?\b"],
    "spa_cast": [r"\bcast(ellano|elhano)?\b", r"\bes[-_]es\b", r"\bspain\b",
                 r"\bcastile\b", r"\biberica?\b", r"\bpeninsul"],
    "por_br":   [r"\bbr(azil|asileiro)?\b", r"\bpt[-_]br\b"],
    "por_pt":   [r"\bpt[-_]pt\b", r"\bportugal\b", r"\beuropeu\b",
                 r"\beurope[ao]?\b"],
    "chi_s":    [r"\bsimp(lified)?\b", r"\bhans\b", r"\bchs\b",
                 r"\bcn\b", r"\bmainland\b"],
    "chi_t":    [r"\btrad(itional)?\b", r"\bhant\b", r"\bcht\b",
                 r"\btw\b", r"\btaiwan\b", r"\bhong\s*kong\b", r"\bhk\b"],
}

# Padrões para identificar faixas de karaokê / signs & songs em legendas
SIGNS_SONGS_HINTS: List[str] = [
    r"\bkara?oke?\b",
    r"\bkaraok[eê]\b",
    r"\bsigns?\b",
    r"\bsongs?\b",
    r"\bsigns?\s*[&e]\s*songs?\b",
    r"\bop/ed\b",
    r"\boped\b",
    r"\bopening\b",
    r"\bending\b",
    r"\binsert\s*song\b",
    r"\blyric[s]?\b",
    r"\bmusic\b",
    r"\bfull\s*sub\b",       # às vezes "full sub" indica a faixa SEM karaokê
    r"\btitled\b",            # "Titled" = só os títulos/signs
    r"\bsong[s]?\s*sub\b",
]

# Hints que NEGAM signs & songs (indicam faixa principal de diálogo)
DIALOGUE_HINTS: List[str] = [
    r"\bdialog(ue)?\b",
    r"\bdial\b",
    r"\bno\s*song\b",
    r"\bno\s*sign\b",
    r"\bno[-_\s]kara?oke?\b",
    r"\bsubs?\s*only\b",
]


# ─── Dataclass ────────────────────────────────────────────────────────────────

@dataclass
class TrackInfo:
    track_id:      int
    track_type:    str    # 'video' | 'audio' | 'subtitles'
    codec:         str
    language:      str    # ISO 639-2
    language_ietf: str    # BCP-47 ou ""
    title:         str    # nome da faixa (pode ser "")
    default:       bool
    forced:        bool
    canonical:   Optional[str] = field(default=None, repr=False)
    signs_songs: bool          = field(default=False, repr=False)

    def describe(self) -> str:
        """Representação legível para exibição no console."""
        ietf_str = f"/{self.language_ietf}" if self.language_ietf else ""
        name_str = f" | '{self.title}'" if self.title else ""
        return f"ID={self.track_id} [{self.language}{ietf_str}] ({self.codec}){name_str}"


# ─── Utilitários ──────────────────────────────────────────────────────────────

def natural_sort_key(text: str) -> list:
    """Ordenação natural: 'EP2' < 'EP10' (não alfabética)."""
    def conv(p): return int(p) if p.isdigit() else p.lower()
    return [conv(c) for c in re.split(r'(\d+)', text)]


def resolve_path(path_str: str) -> Path:
    """Resolve caminhos, incluindo atalhos .lnk do Windows."""
    path = Path(path_str)
    if path.suffix.lower() == '.lnk':
        try:
            import winshell
            return Path(winshell.shortcut(str(path)).path).resolve()
        except ImportError:
            pass
    return path.resolve()


def get_mkv_files(folder: Path) -> List[Path]:
    """Retorna arquivos MKV da pasta em ordem natural."""
    files = [f for f in folder.iterdir() if f.suffix.lower() == '.mkv']
    return sorted(files, key=lambda x: natural_sort_key(x.name))


def get_tracks(mkv_path: Path) -> List[TrackInfo]:
    """Extrai informações de todas as faixas do arquivo via mkvmerge -J."""
    try:
        result = subprocess.run(
            [MKVMERGE, "-J", str(mkv_path)],
            capture_output=True, text=True, encoding='utf-8', check=True
        )
        raw = json.loads(result.stdout)
        tracks = []
        for t in raw.get('tracks', []):
            p = t['properties']
            tracks.append(TrackInfo(
                track_id      = t['id'],
                track_type    = t['type'],
                codec         = t['codec'],
                language      = p.get('language', 'und'),
                language_ietf = p.get('language_ietf', ''),
                title         = p.get('track_name', ''),
                default       = p.get('default_track', False),
                forced        = p.get('forced_track', False),
            ))
        return tracks
    except subprocess.CalledProcessError as e:
        print(f"  [ERRO] mkvmerge falhou: {e.stderr[-300:]}")
        return []
    except json.JSONDecodeError as e:
        print(f"  [ERRO] JSON inválido: {e}")
        return []


# ─── Detecção de idioma ───────────────────────────────────────────────────────

def detect_canonical_basic(track: TrackInfo) -> Optional[str]:
    """
    Detecta o canônico básico via IETF → ISO 639-2.
    Não resolve ambiguidades de variantes (ex: spa_lat vs spa_cast).
    """
    ietf = track.language_ietf.lower().strip()
    if ietf:
        if ietf in IETF_MAP:
            return IETF_MAP[ietf]
        # Tenta só o prefixo base (ex: "es-419" → "es" caso não mapeado)
        prefix = ietf.split('-')[0]
        if prefix in IETF_MAP:
            return IETF_MAP[prefix]
    return ISO_MAP.get(track.language.lower().strip())


def is_ietf_certain(track: TrackInfo, iso: str) -> bool:
    """
    Retorna True se a tag IETF da faixa é específica o suficiente para
    disambiguar variantes sem ajuda extra.
    Ex: "pt-BR" é certa, "pt" genérica não é.
    """
    ietf = track.language_ietf.lower().strip()
    if not ietf:
        return False
    # Tag genérica (sem subtag regional) não desambigua
    if ietf in GENERIC_IETF.get(iso, set()):
        return False
    # Tag com subtag regional é considerada certa
    return '-' in ietf


def hint_score(name: str, variant: str) -> int:
    """Pontua quantos padrões de hint batem no título da faixa."""
    name_l = name.lower()
    return sum(1 for p in VARIANT_HINTS.get(variant, []) if re.search(p, name_l))


def ask_variant(track: TrackInfo, variants: Tuple[str, ...], track_type: str) -> str:
    """Pergunta ao usuário qual variante de idioma corresponde a esta faixa."""
    print(f"\n  [?] Faixa de {track_type} — {track.describe()}")
    print(f"      Idioma '{track.language}' tem variantes — qual é esta faixa?")
    for i, v in enumerate(variants, 1):
        print(f"        {i}. {LANGUAGE_NAMES.get(v, v)}")
    while True:
        r = input("      Opção: ").strip()
        if r.isdigit() and 1 <= int(r) <= len(variants):
            return variants[int(r) - 1]
        print("      Opção inválida, tente novamente.")


def assign_canonicals(tracks: List[TrackInfo], track_type: str) -> None:
    """
    Atribui a chave canônica a cada faixa da lista.
    Resolve ambiguidades de variantes (PT, ES, ZH) via:
      1. Tag IETF específica (ex: pt-BR, es-419)
      2. Hints no título/nome da faixa
      3. Pergunta ao usuário (último recurso)
    """
    # 1ª passagem: detecção básica para todas as faixas
    for t in tracks:
        t.canonical = detect_canonical_basic(t)

    # Agrupa faixas por ISO code para encontrar grupos ambíguos
    by_iso: Dict[str, List[TrackInfo]] = defaultdict(list)
    for t in tracks:
        by_iso[t.language.lower()].append(t)

    for iso, group in by_iso.items():
        variants = AMBIGUOUS_ISO.get(iso)
        if not variants or len(group) < 2:
            continue

        # Faixas sem certeza na atribuição (sem IETF específico ou com IETF genérico)
        default_can = ISO_MAP.get(iso)
        undecided = [
            t for t in group
            if t.canonical == default_can and not is_ietf_certain(t, iso)
        ]

        if len(undecided) < 2:
            continue  # Máximo uma incerta → tudo bem

        # ── Tentativa por hints de nome (greedy por maior score) ──────────────
        scores: Dict[int, Dict[str, int]] = {
            t.track_id: {v: hint_score(t.title, v) for v in variants}
            for t in undecided
        }

        used_variants: List[str] = []
        remaining = list(undecided)
        changed = True

        while changed and remaining:
            changed = False
            best_score, best_track, best_variant = -1, None, None

            for t in remaining:
                for v in variants:
                    # Se há mais faixas indecisas que variantes, permite reusar variante
                    if len(undecided) <= len(variants) and v in used_variants:
                        continue
                    s = scores[t.track_id][v]
                    if s > best_score:
                        best_score, best_track, best_variant = s, t, v

            if best_score > 0 and best_track and best_variant:
                best_track.canonical = best_variant
                used_variants.append(best_variant)
                remaining.remove(best_track)
                changed = True

        # ── Atribuição por eliminação (1 restante, 1 variante sobrando) ───────
        leftover = [v for v in variants if v not in used_variants]
        if len(remaining) == 1 and len(leftover) == 1:
            remaining[0].canonical = leftover[0]
            remaining.clear()

        # ── Último recurso: perguntar ao usuário ──────────────────────────────
        if remaining:
            print(f"\n  ⚠  {len(remaining)} faixa(s) de '{iso}' não puderam ser "
                  f"identificadas automaticamente.")
            for t in remaining:
                t.canonical = ask_variant(t, variants, track_type)


def signs_songs_score(title: str) -> int:
    """
    Pontua indícios de que uma legenda é de signs/songs/karaokê.
    Scores negativos indicam faixa de diálogo (nega signs & songs).
    """
    name_l = title.lower()
    score = sum(1 for p in SIGNS_SONGS_HINTS if re.search(p, name_l))
    score -= sum(2 for p in DIALOGUE_HINTS if re.search(p, name_l))
    return score


def ask_signs_songs(group: List[TrackInfo]) -> List[TrackInfo]:
    """
    Pergunta ao usuário quais faixas do grupo são signs & songs.
    Retorna a lista de faixas marcadas como signs_songs.
    """
    print(f"\n  [?] {len(group)} faixas de legenda com o mesmo idioma "
          f"({LANGUAGE_NAMES.get(group[0].canonical, group[0].language)}):")
    for i, t in enumerate(group, 1):
        print(f"        {i}. {t.describe()}")
    print(f"      Qual(is) é(são) a faixa de Signs & Songs / Karaokê?")
    print(f"      (números separados por vírgula; Enter = nenhuma)")

    while True:
        r = input("      Opção: ").strip()
        if not r:
            return []
        parts = [p.strip() for p in r.split(',')]
        try:
            indices = [int(p) - 1 for p in parts]
            if all(0 <= i < len(group) for i in indices):
                return [group[i] for i in indices]
        except ValueError:
            pass
        print("      Entrada inválida, tente novamente.")


def resolve_duplicate_subs(subs: List[TrackInfo]) -> None:
    """
    Detecta faixas de legenda duplicadas (mesmo canônico) e marca as que são
    Signs & Songs via hints de nome. Pergunta ao usuário somente se não houver
    nenhum hint em nenhuma faixa do grupo.
    """
    # Agrupa por canônico
    by_can: Dict[Optional[str], List[TrackInfo]] = defaultdict(list)
    for t in subs:
        by_can[t.canonical].append(t)

    for can, group in by_can.items():
        if len(group) < 2:
            continue  # sem duplicata — nada a fazer

        # Calcula score de signs & songs para cada faixa
        scored = [(t, signs_songs_score(t.title)) for t in group]

        max_score = max(s for _, s in scored)

        if max_score > 0:
            # ── Detecção automática ───────────────────────────────────────────
            # A(s) faixa(s) com maior score > 0 → signs & songs
            # Em caso de empate de score > 0, todas empatadas viram signs & songs
            # (a de menor score fica como principal)
            threshold = max_score
            for t, s in scored:
                if s >= threshold and s > 0:
                    t.signs_songs = True
            # Garante que pelo menos uma faixa fica como principal (signs_songs=False)
            # Se todas foram marcadas (scores iguais), desmarca a primeira
            if all(t.signs_songs for t in group):
                group[0].signs_songs = False
        else:
            # ── Nenhum hint encontrado → pergunta ao usuário ──────────────────
            marked = ask_signs_songs(group)
            for t in marked:
                t.signs_songs = True


# ─── Modo de nomenclatura ─────────────────────────────────────────────────────

def ask_naming_mode(named_tracks: List[TrackInfo]) -> str:
    """
    Exibe faixas já nomeadas e pergunta como proceder.
    Retorna 'preencher' ou 'sobrescrever'.
    """
    print("\n  Faixas com nome já definido:")
    for t in named_tracks:
        tipo = "áudio" if t.track_type == "audio" else "legenda"
        lang = LANGUAGE_NAMES.get(t.canonical, t.language) if t.canonical else t.language
        print(f"    ID={t.track_id} [{tipo}] {lang:25} → '{t.title}'")

    print("\n  Como tratar as faixas já nomeadas?")
    print("    1. preencher    — manter nomes existentes, preencher só as vazias")
    print("    2. sobrescrever — renomear TODAS (inclusive as já nomeadas)")
    while True:
        r = input("  Opção [1/2]: ").strip().lower()
        if r in ('1', 'p', 'preencher'):
            return 'preencher'
        if r in ('2', 's', 'sobrescrever'):
            return 'sobrescrever'
        print("  Opção inválida.")


# ─── Processamento do arquivo ─────────────────────────────────────────────────

def canonical_order_key(canonical: Optional[str]) -> int:
    """Retorna posição na ordem de prioridade; desconhecidos vão ao final."""
    try:
        return LANGUAGE_ORDER.index(canonical)
    except (ValueError, TypeError):
        return len(LANGUAGE_ORDER)


def process_file(mkv_path: Path, state: Dict) -> bool:
    """
    Analisa e remuxа um único arquivo MKV com faixas reordenadas e renomeadas.

    state (compartilhado entre arquivos):
        'naming_mode': None | 'preencher' | 'sobrescrever'
        'confirm_all': bool — True = pular confirmação individual
    """
    print(f"\n{'─' * 64}")
    print(f"  {mkv_path.name}")
    print(f"{'─' * 64}")

    tracks = get_tracks(mkv_path)
    if not tracks:
        print("  [AVISO] Sem faixas detectadas. Pulando.")
        return False

    videos = [t for t in tracks if t.track_type == 'video']
    audios = [t for t in tracks if t.track_type == 'audio']
    subs   = [t for t in tracks if t.track_type == 'subtitles']

    print(f"  Faixas: {len(videos)} vídeo | {len(audios)} áudio | {len(subs)} legenda")

    # Detectar idioma canônico (pode perguntar sobre variantes ambíguas)
    assign_canonicals(audios, "áudio")
    assign_canonicals(subs, "legenda")

    # Detectar faixas de legenda duplicadas (signs & songs / karaokê)
    resolve_duplicate_subs(subs)

    # ── Modo de nomenclatura ──────────────────────────────────────────────────
    named = [t for t in audios + subs if t.title.strip()]
    naming_mode = state.get('naming_mode')

    if named and naming_mode is None:
        naming_mode = ask_naming_mode(named)
        print(f"\n  Aplicar esta escolha a todos os próximos arquivos? ", end='')
        if input("(s/n): ").strip().lower() == 's':
            state['naming_mode'] = naming_mode
    elif naming_mode is None:
        naming_mode = 'preencher'

    # ── Ordenar faixas pela prioridade canônica ───────────────────────────────
    sorted_audios = sorted(audios, key=lambda t: canonical_order_key(t.canonical))
    sorted_subs   = sorted(subs,   key=lambda t: (canonical_order_key(t.canonical), int(not t.signs_songs)))
    final_order   = videos + sorted_audios + sorted_subs

    # ── Calcular novos nomes ──────────────────────────────────────────────────
    new_names: Dict[int, str] = {}
    for t in sorted_audios + sorted_subs:
        if not t.canonical:
            continue
        desired = LANGUAGE_NAMES.get(t.canonical)
        if not desired:
            continue
        if t.signs_songs:
            desired = f"{desired} [Signs & Songs]"
        if naming_mode == 'sobrescrever' or not t.title.strip():
            new_names[t.track_id] = desired

    # ── Exibir plano ──────────────────────────────────────────────────────────
    tipo_map = {"video": "Vídeo", "audio": "Áudio", "subtitles": "Legenda"}
    print("\n  Plano de remux:")
    print(f"  {'#':>3}  {'Tipo':<9} {'Idioma':<27} {'Nome'}")
    print(f"  {'─'*3}  {'─'*9} {'─'*27} {'─'*30}")

    for i, t in enumerate(final_order, 1):
        tipo = tipo_map.get(t.track_type, t.track_type)
        lang = LANGUAGE_NAMES.get(t.canonical) if t.canonical else None
        lang_str = lang if lang else f"[{t.language}]"

        new = new_names.get(t.track_id)
        if new:
            name_str = f"'{t.title}' → '{new}'" if t.title else f"→ '{new}'"
        elif t.title:
            name_str = f"'{t.title}' (mantido)"
        else:
            name_str = "(sem nome)"

        print(f"  {i:>3}. [{tipo:<8}] {lang_str:<27} {name_str}")

    # ── Confirmação ───────────────────────────────────────────────────────────
    if not state.get('confirm_all'):
        print(f"\n  Prosseguir com o remux?  s = sim | n = pular | t = sim para todos")
        r = input("  Opção: ").strip().lower()
        if r == 't':
            state['confirm_all'] = True
        elif r != 's':
            print("  Arquivo pulado.")
            return False

    # ── Executar mkvmerge ─────────────────────────────────────────────────────
    output_dir = mkv_path.parent / "Remuxed"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / mkv_path.name

    # Remove saída anterior se existir (mkvmerge pode travar em sobrescrever)
    if output_path.exists():
        output_path.unlink()

    # Montar comando
    cmd = [MKVMERGE, "-o", str(output_path)]

    # Nomes das faixas (devem vir ANTES do arquivo de entrada)
    for track_id, name in new_names.items():
        cmd += ["--track-name", f"{track_id}:{name}"]

    # Ordem das faixas no output (file_index:track_id — file_index sempre 0)
    track_order_str = ",".join(f"0:{t.track_id}" for t in final_order)
    cmd += ["--track-order", track_order_str]

    cmd.append(str(mkv_path))

    print(f"\n  Remuxando... ", end='', flush=True)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding='utf-8', check=True
        )
        print("✓")
        print(f"  → {output_path}")
        return True
    except subprocess.CalledProcessError as e:
        print("✗")
        # Exibe só a parte relevante do erro
        err_lines = [l for l in e.stderr.splitlines() if l.strip()]
        for line in err_lines[-5:]:
            print(f"  [ERRO] {line}")
        return False


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 64)
    print("  TRACK NAMER — Padronização de Faixas MKV")
    print("=" * 64)

    if len(sys.argv) < 2:
        print("\n[ERRO] Nenhum arquivo ou pasta foi arrastado!")
        print("\nComo usar:")
        print("  • Arraste um ou mais arquivos .mkv sobre o track_namer.bat")
        print("  • Ou arraste pastas contendo arquivos .mkv")
        input("\nEnter para sair...")
        sys.exit(1)

    # ── Coletar arquivos MKV dos argumentos ───────────────────────────────────
    mkv_files: List[Path] = []

    for arg in sys.argv[1:]:
        path = resolve_path(arg)

        if not path.exists():
            print(f"[AVISO] Caminho não encontrado: {arg}")
            continue

        if path.is_dir():
            found = get_mkv_files(path)
            if found:
                print(f"  📁 {path.name}: {len(found)} MKV(s)")
                mkv_files.extend(found)
            else:
                print(f"  [AVISO] Nenhum .mkv em: {path.name}")

        elif path.suffix.lower() == '.mkv':
            mkv_files.append(path)

        else:
            print(f"[AVISO] Ignorado (não é .mkv nem pasta): {path.name}")

    if not mkv_files:
        print("\n[ERRO] Nenhum arquivo MKV encontrado!")
        input("Enter para sair...")
        sys.exit(1)

    print(f"\n✓ {len(mkv_files)} arquivo(s) para processar:")
    for f in mkv_files:
        print(f"    • {f.name}")

    print(f"\nArquivos remuxados serão salvos em subpastas 'Remuxed/'")
    print(f"ao lado de cada arquivo original.")

    # ── Estado compartilhado entre arquivos ───────────────────────────────────
    state: Dict = {
        'naming_mode': None,   # None | 'preencher' | 'sobrescrever'
        'confirm_all': False,  # True = não pede confirmação por arquivo
    }

    # ── Processar arquivos em sequência ───────────────────────────────────────
    success = failed = skipped = 0

    for mkv_path in mkv_files:
        result = process_file(mkv_path, state)
        if result is True:
            success += 1
        elif result is False:
            # Distingue "pulado pelo usuário" de "erro" pelo contexto
            skipped += 1

    # ── Relatório final ───────────────────────────────────────────────────────
    print(f"\n{'=' * 64}")
    print(f"  CONCLUÍDO")
    print(f"  ✓ {success} processado(s)  |  ✗ {skipped} pulado(s)/erro(s)")
    print(f"{'=' * 64}")
    input("\nEnter para sair...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INFO] Cancelado pelo usuário.")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERRO CRÍTICO] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        input("\nEnter para sair...")
        sys.exit(1)
