#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Track Namer — Padronização de Faixas MKV
Reordena e renomeia faixas de áudio e legenda conforme convenção de curadoria.

Quando a ordem desejada já é a do arquivo, edita in-place com mkvpropedit
(nome, flag forced, flag commentary) — sem remux. Se a ordem mudar, remuxa
com mkvmerge para a subpasta Remuxed/.

Uso: arraste arquivos .mkv ou pastas contendo .mkv sobre o track_namer.bat
"""

import subprocess
import sys
import json
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict

# ─── Executáveis ──────────────────────────────────────────────────────────────
MKVTOOLNIX = Path(r"C:\Program Files\MKVToolNix")
MKVMERGE = str(MKVTOOLNIX / "mkvmerge.exe")
MKVPROPEDIT = str(MKVTOOLNIX / "mkvpropedit.exe")

# ─── Ordem de prioridade canônica ─────────────────────────────────────────────
LANGUAGE_ORDER: List[str] = [
    "jpn",        #  1  Japanese
    "eng",        #  2  English
    "por_br",     #  3  Português Brasileiro
    "spa_lat",    #  4  Español Latino
    "spa_cast",   #  5  Español Castellano
    "fre",        #  6  Français
    "por_pt",     #  7  Português Europeu
    "ita",        #  8  Italiano
    "ger",        #  9  Deutsch
    "rus",        # 10  Русский
    "chi_s",      # 11  中文 (Simplified)
    "chi_t",      # 12  中文 (Traditional)
    "kor",        # 13  한국어
    "ara",        # 14  العربية
    "hin",        # 15  हिन्दी
    "dut",        # 16  Nederlands
    "pol",        # 17  Polski
    "tur",        # 18  Türkçe
    "swe",        # 19  Svenska
    "nor",        # 20  Norsk
    "dan",        # 21  Dansk
    "fin",        # 22  Suomi
    "cze",        # 23  Čeština
    "hun",        # 24  Magyar
    "gre",        # 25  Ελληνικά
    "ind",        # 26  Bahasa Indonesia
    "may",        # 27  Bahasa Melayu
    "tha",        # 28  ไทย
    "vie",        # 29  Tiếng Việt
    "bul",        # 30  Български
    "rum",        # 31  Română
    "heb",        # 32  עברית
    "est",        # 33  Eesti
    "lav",        # 34  Latviešu
    "lit",        # 35  Lietuvių
]

LANGUAGE_NAMES: Dict[str, str] = {
    "jpn":      "Japanese",
    "eng":      "English",
    "por_br":   "Português Brasileiro",
    "spa_lat":  "Español Latino",
    "spa_cast": "Español Castellano",
    "fre":      "Français",
    "ita":      "Italiano",
    "ger":      "Deutsch",
    "rus":      "Русский",
    "chi_s":    "中文 (Simplified)",
    "chi_t":    "中文 (Traditional)",
    "kor":      "한국어",
    "ara":      "العربية",
    "hin":      "हिन्दी",
    "dut":      "Nederlands",
    "por_pt":   "Português Europeu",
    "pol":      "Polski",
    "tur":      "Türkçe",
    "swe":      "Svenska",
    "nor":      "Norsk",
    "dan":      "Dansk",
    "fin":      "Suomi",
    "cze":      "Čeština",
    "hun":      "Magyar",
    "gre":      "Ελληνικά",
    "ind":      "Bahasa Indonesia",
    "may":      "Bahasa Melayu",
    "tha":      "ไทย",
    "vie":      "Tiếng Việt",
    "bul":      "Български",
    "rum":      "Română",
    "heb":      "עברית",
    "est":      "Eesti",
    "lav":      "Latviešu",
    "lit":      "Lietuvių",
}

# BCP-47 (IETF) → chave canônica
IETF_MAP: Dict[str, str] = {
    "ja": "jpn",
    "en": "eng", "en-us": "eng", "en-gb": "eng",
    "pt": "por_br", "pt-br": "por_br", "pt-pt": "por_pt",
    "es": "spa_lat", "es-419": "spa_lat", "es-la": "spa_lat",
    "es-mx": "spa_lat", "es-ar": "spa_lat", "es-co": "spa_lat",
    "es-cl": "spa_lat", "es-ve": "spa_lat", "es-pe": "spa_lat",
    "es-es": "spa_cast",
    "fr": "fre", "fr-fr": "fre",
    "it": "ita", "it-it": "ita",
    "de": "ger", "de-de": "ger", "de-at": "ger",
    "ru": "rus", "ru-ru": "rus",
    "zh": "chi_s", "zh-hans": "chi_s", "zh-cn": "chi_s", "zh-sg": "chi_s",
    "zh-hant": "chi_t", "zh-tw": "chi_t", "zh-hk": "chi_t",
    "ko": "kor", "ko-kr": "kor",
    "ar": "ara", "ar-sa": "ara",
    "hi": "hin", "hi-in": "hin",
    "nl": "dut", "nl-nl": "dut", "nl-be": "dut",
    "pl": "pol", "pl-pl": "pol",
    "tr": "tur", "tr-tr": "tur",
    "sv": "swe", "sv-se": "swe",
    "no": "nor", "nb": "nor", "nn": "nor", "no-no": "nor",
    "da": "dan", "da-dk": "dan",
    "fi": "fin", "fi-fi": "fin",
    "cs": "cze", "cs-cz": "cze",
    "hu": "hun", "hu-hu": "hun",
    "el": "gre", "el-gr": "gre",
    "id": "ind", "id-id": "ind",
    "ms": "may", "ms-my": "may",
    "th": "tha", "th-th": "tha",
    "vi": "vie", "vi-vn": "vie",
    "bg": "bul", "bg-bg": "bul",
    "ro": "rum", "ro-ro": "rum",
    "he": "heb", "he-il": "heb",
    "et": "est", "et-ee": "est",
    "lv": "lav", "lv-lv": "lav",
    "lt": "lit", "lt-lt": "lit",
}

# ISO 639-2 → chave canônica (fallback quando não há tag IETF)
ISO_MAP: Dict[str, str] = {
    "jpn": "jpn",
    "eng": "eng",
    "por": "por_br",
    "spa": "spa_lat",
    "fre": "fre", "fra": "fre",
    "ita": "ita",
    "ger": "ger", "deu": "ger",
    "rus": "rus",
    "chi": "chi_s", "zho": "chi_s", "cmn": "chi_s",
    "kor": "kor",
    "ara": "ara",
    "hin": "hin",
    "dut": "dut", "nld": "dut",
    "pol": "pol",
    "tur": "tur",
    "swe": "swe",
    "nor": "nor",
    "dan": "dan",
    "fin": "fin",
    "cze": "cze", "ces": "cze",
    "hun": "hun",
    "gre": "gre", "ell": "gre",
    "ind": "ind",
    "may": "may", "msa": "may",
    "tha": "tha",
    "vie": "vie",
    "bul": "bul",
    "rum": "rum", "ron": "rum",
    "heb": "heb",
    "est": "est",
    "lav": "lav",
    "lit": "lit",
}

# ISO codes que possuem variantes ambíguas (dois dialetos distintos)
AMBIGUOUS_ISO: Dict[str, Tuple[str, ...]] = {
    "por": ("por_br",  "por_pt"),
    "spa": ("spa_lat", "spa_cast"),
    "chi": ("chi_s",   "chi_t"),
    "zho": ("chi_s",   "chi_t"),
}

# Tags IETF "genéricas" (sem subtag regional) que não disambiguam variante
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
    r"\bfull\s*sub\b",
    r"\btitled\b",
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

COMMENTARY_HINTS: List[str] = [
    r"\bcommentary\b",
    r"\bcoment[aá]rios?\b",
    r"\bcomment\b",
    r"\bdirector(?:'?s)?\b",
    r"\bdiretor(?:es)?\b",
    r"\bcomm\b",
]

FORCED_HINTS: List[str] = [
    r"\bforced\b",
    r"\bfor[cç]ad[oa]s?\b",
    r"\bforce\b",
]

ROLE_TAGS = (
    ("signs_songs", "Signs & Songs"),
    ("commentary", "Commentary"),
    ("mark_forced", "Forced"),
)


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
    forced:        bool   # flag já presente no arquivo
    track_number:  int = 0          # TrackNumber do Matroska (mkvpropedit track:@N)
    commentary_flag: bool = False   # flag já presente no arquivo
    canonical:   Optional[str] = field(default=None, repr=False)
    signs_songs: bool = field(default=False, repr=False)
    commentary:  bool = field(default=False, repr=False)
    mark_forced: bool = field(default=False, repr=False)
    role_touched: bool = field(default=False, repr=False)

    def describe(self) -> str:
        """Representação legível para exibição no console."""
        ietf_str = f"/{self.language_ietf}" if self.language_ietf else ""
        name_str = f" | '{self.title}'" if self.title else ""
        flags = []
        if self.forced:
            flags.append("forced")
        if self.commentary_flag:
            flags.append("commentary")
        flag_str = f" {{{', '.join(flags)}}}" if flags else ""
        return f"ID={self.track_id} [{self.language}{ietf_str}] ({self.codec}){name_str}{flag_str}"

    def has_special_role(self) -> bool:
        return self.signs_songs or self.commentary or self.mark_forced


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
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            check=True,
        )
        raw = json.loads(result.stdout)
        tracks = []
        for t in raw.get('tracks', []):
            p = t['properties']
            tracks.append(TrackInfo(
                track_id        = t['id'],
                track_type      = t['type'],
                codec           = t['codec'],
                language        = p.get('language', 'und'),
                language_ietf   = p.get('language_ietf', '') or '',
                title           = p.get('track_name', '') or '',
                default         = bool(p.get('default_track', False)),
                forced          = bool(p.get('forced_track', False)),
                track_number    = int(p.get('number') or 0),
                commentary_flag = bool(p.get('commentary_track', False)),
            ))
        return tracks
    except subprocess.CalledProcessError as e:
        err = e.stderr or ""
        print(f"  [ERRO] mkvmerge falhou: {err[-300:]}")
        return []
    except json.JSONDecodeError as e:
        print(f"  [ERRO] JSON inválido: {e}")
        return []


def tool_available(path: str) -> bool:
    return Path(path).is_file()


def detect_merge_flag_opts() -> Dict[str, Optional[str]]:
    """
    Descobre os nomes das opções de flag do mkvmerge instalado.
    Versões novas usam --forced-display-flag / --commentary-flag;
    versões antigas usam --forced-track e podem não ter commentary.
    """
    forced = "--forced-track"
    commentary: Optional[str] = None
    try:
        result = subprocess.run(
            [MKVMERGE, "--help"],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
        )
        help_text = (result.stdout or "") + (result.stderr or "")
        if "--forced-display-flag" in help_text:
            forced = "--forced-display-flag"
        elif "--forced-track" in help_text:
            forced = "--forced-track"
        if "--commentary-flag" in help_text:
            commentary = "--commentary-flag"
    except OSError:
        pass
    return {"forced": forced, "commentary": commentary}


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
    if ietf in GENERIC_IETF.get(iso, set()):
        return False
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
    for t in tracks:
        t.canonical = detect_canonical_basic(t)

    by_iso: Dict[str, List[TrackInfo]] = defaultdict(list)
    for t in tracks:
        by_iso[t.language.lower()].append(t)

    for iso, group in by_iso.items():
        variants = AMBIGUOUS_ISO.get(iso)
        if not variants or len(group) < 2:
            continue

        default_can = ISO_MAP.get(iso)
        undecided = [
            t for t in group
            if t.canonical == default_can and not is_ietf_certain(t, iso)
        ]

        if len(undecided) < 2:
            continue

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

        leftover = [v for v in variants if v not in used_variants]
        if len(remaining) == 1 and len(leftover) == 1:
            remaining[0].canonical = leftover[0]
            remaining.clear()

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


def commentary_score(title: str) -> int:
    name_l = title.lower()
    return sum(1 for p in COMMENTARY_HINTS if re.search(p, name_l))


def forced_score(title: str) -> int:
    name_l = title.lower()
    return sum(1 for p in FORCED_HINTS if re.search(p, name_l))


def apply_role_hints(tracks: List[TrackInfo]) -> None:
    """Marca papéis a partir do título e das flags já gravadas no arquivo."""
    for t in tracks:
        ss = signs_songs_score(t.title)
        cc = commentary_score(t.title)
        ff = forced_score(t.title)
        if ss > 0:
            t.signs_songs = True
            t.role_touched = True
        if cc > 0 or t.commentary_flag:
            t.commentary = True
            t.role_touched = True
        if ff > 0 or t.forced:
            t.mark_forced = True
            t.role_touched = True


def parse_role_answer(raw: str, count: int) -> Optional[Dict[int, Set[str]]]:
    """
    Interpreta a resposta do usuário.
      vazio          → todas normais
      1,2            → legado: essas faixas são Signs & Songs
      1=s, 2=cf      → s signs, c commentary, f forced (combináveis)
      1=n            → normal explícito
    Retorna None se a entrada for inválida.
    """
    raw = raw.strip()
    result: Dict[int, Set[str]] = {i: set() for i in range(count)}
    if not raw:
        return result

    # Legado: "1,2" = signs & songs
    if re.fullmatch(r'\d+(\s*,\s*\d+)*', raw):
        indices = [int(p) - 1 for p in raw.split(',')]
        if not all(0 <= i < count for i in indices):
            return None
        for i in indices:
            result[i].add('s')
        return result

    parts = [p.strip() for p in re.split(r'[,;]+', raw) if p.strip()]
    if not parts:
        return None
    seen = set()
    for part in parts:
        m = re.fullmatch(r'(\d+)\s*=\s*([scfnSCFN]+)', part)
        if not m:
            return None
        idx = int(m.group(1)) - 1
        roles = set(m.group(2).lower())
        if not (0 <= idx < count) or idx in seen:
            return None
        if 'n' in roles and roles != {'n'}:
            return None
        seen.add(idx)
        result[idx] = set() if roles == {'n'} else (roles - {'n'})
    return result


def ask_roles(group: List[TrackInfo], track_type: str) -> None:
    """
    Pergunta Signs & Songs, Commentary e Forced para um grupo duplicado.
    Enter mantém o que os hints/flags já marcaram; resposta explícita substitui.
    """
    lang = LANGUAGE_NAMES.get(group[0].canonical or "", group[0].language)
    print(f"\n  [?] {len(group)} faixas de {track_type} com o mesmo idioma ({lang}):")
    for i, t in enumerate(group, 1):
        auto = []
        if t.signs_songs:
            auto.append("Signs & Songs")
        if t.commentary:
            auto.append("Commentary")
        if t.mark_forced:
            auto.append("Forced")
        auto_str = f"  → sugestão: {', '.join(auto)}" if auto else ""
        print(f"        {i}. {t.describe()}{auto_str}")
    print("      Classifique (Enter = aceitar sugestão / todas normais se não houver):")
    print("        s = Signs & Songs / Karaokê")
    print("        c = Commentary")
    print("        f = Forced")
    print("        n = Normal (diálogo)")
    print("      Formato: 1=s, 2=n   ou   1=sf, 2=c   (papéis combináveis)")
    print("      Legado: 1,2  = essas faixas são Signs & Songs")

    while True:
        r = input("      Opção: ").strip()
        parsed = parse_role_answer(r, len(group))
        if parsed is None:
            print("      Entrada inválida, tente novamente.")
            continue
        if r:
            for i, t in enumerate(group):
                roles = parsed[i]
                t.signs_songs = 's' in roles
                t.commentary = 'c' in roles
                t.mark_forced = 'f' in roles
                t.role_touched = True
        return


def resolve_roles(tracks: List[TrackInfo], track_type: str) -> None:
    """
    Marca Signs & Songs, Commentary e Forced.
    Hints de título e flags do arquivo são automáticos.
    Pergunta só quando há 2+ faixas do mesmo idioma ainda indistinguíveis.
    """
    apply_role_hints(tracks)

    by_can: Dict[Optional[str], List[TrackInfo]] = defaultdict(list)
    for t in tracks:
        by_can[t.canonical].append(t)

    for group in by_can.values():
        if len(group) < 2:
            continue
        plain = [t for t in group if not t.has_special_role()]
        # 2+ sem papel: não dá para saber qual é commentary/forced/signs
        if len(plain) >= 2:
            ask_roles(group, track_type)

        # Se todas ficaram como signs & songs, preserva uma como diálogo
        if len(group) >= 2 and all(t.signs_songs and not t.commentary for t in group):
            group[0].signs_songs = False


def desired_name(track: TrackInfo) -> Optional[str]:
    """Nome canônico + sufixos de papel. None se o idioma não for conhecido."""
    base = LANGUAGE_NAMES.get(track.canonical or "")
    if not base:
        return None
    tags = [label for attr, label in ROLE_TAGS if getattr(track, attr)]
    if not tags:
        return base
    return base + "".join(f" [{label}]" for label in tags)


def role_rank(track: TrackInfo) -> int:
    """Diálogo, depois signs, forced, commentary — dentro do mesmo idioma."""
    if track.commentary:
        return 3
    if track.mark_forced and not track.signs_songs:
        return 2
    if track.signs_songs:
        return 1
    return 0


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
        return LANGUAGE_ORDER.index(canonical)  # type: ignore[arg-type]
    except (ValueError, TypeError):
        return len(LANGUAGE_ORDER)


def propedit_selector(track: TrackInfo) -> str:
    """Seletor do mkvpropedit. track:@N usa o TrackNumber do Matroska."""
    if track.track_number:
        return f"track:@{track.track_number}"
    return f"track:{track.track_id + 1}"


def flags_differ(track: TrackInfo) -> bool:
    return track.mark_forced != track.forced or track.commentary != track.commentary_flag


def edit_inplace(mkv_path: Path, edits: List[TrackInfo], new_names: Dict[int, str]) -> bool:
    """Aplica nome e flags com mkvpropedit, sem remux. Altera o arquivo original."""
    if not tool_available(MKVPROPEDIT):
        print(f"  [ERRO] mkvpropedit não encontrado: {MKVPROPEDIT}")
        return False

    cmd = [MKVPROPEDIT, str(mkv_path)]
    for t in edits:
        cmd += ["--edit", propedit_selector(t)]
        if t.track_id in new_names:
            cmd += ["--set", f"name={new_names[t.track_id]}"]
        if t.role_touched or flags_differ(t):
            cmd += ["--set", f"flag-forced={'1' if t.mark_forced else '0'}"]
            cmd += ["--set", f"flag-commentary={'1' if t.commentary else '0'}"]

    print("\n  Editando in-place (sem remux)... ", end='', flush=True)
    try:
        subprocess.run(
            cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
            check=True,
        )
        print("✓")
        print(f"  → {mkv_path}  (original alterado)")
        return True
    except subprocess.CalledProcessError as e:
        print("✗")
        err_lines = [ln for ln in (e.stderr or "").splitlines() if ln.strip()]
        for line in err_lines[-5:]:
            print(f"  [ERRO] {line}")
        return False


def remux(mkv_path: Path, final_order: List[TrackInfo], new_names: Dict[int, str],
          flag_opts: Dict[str, Optional[str]]) -> bool:
    """Remuxa para Remuxed/ quando a ordem das faixas precisa mudar."""
    output_dir = mkv_path.parent / "Remuxed"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / mkv_path.name
    if output_path.exists():
        output_path.unlink()

    cmd = [MKVMERGE, "-o", str(output_path)]
    for track_id, name in new_names.items():
        cmd += ["--track-name", f"{track_id}:{name}"]

    forced_opt = flag_opts.get("forced") or "--forced-track"
    commentary_opt = flag_opts.get("commentary")
    for t in final_order:
        if t.track_type == 'video':
            continue
        if t.role_touched or flags_differ(t):
            cmd += [forced_opt, f"{t.track_id}:{1 if t.mark_forced else 0}"]
            if commentary_opt:
                cmd += [commentary_opt, f"{t.track_id}:{1 if t.commentary else 0}"]

    track_order_str = ",".join(f"0:{t.track_id}" for t in final_order)
    cmd += ["--track-order", track_order_str, str(mkv_path)]

    print("\n  Remuxando... ", end='', flush=True)
    try:
        subprocess.run(
            cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
            check=True,
        )
        print("✓")
        print(f"  → {output_path}")
    except subprocess.CalledProcessError as e:
        print("✗")
        err_lines = [ln for ln in (e.stderr or "").splitlines() if ln.strip()]
        for line in err_lines[-5:]:
            print(f"  [ERRO] {line}")
        return False

    # mkvmerge antigo não tem --commentary-flag: aplica a flag no arquivo novo
    if commentary_opt is None and tool_available(MKVPROPEDIT):
        pending = [t for t in final_order if t.track_type != 'video' and t.commentary]
        if pending:
            post = [MKVPROPEDIT, str(output_path)]
            for i, t in enumerate(final_order, 1):
                if t.track_type == 'video' or not t.commentary:
                    continue
                post += ["--edit", f"track:{i}", "--set", "flag-commentary=1"]
            subprocess.run(
                post, capture_output=True, text=True, encoding='utf-8', errors='replace',
            )
    return True


def process_file(mkv_path: Path, state: Dict) -> bool:
    """
    Analisa um MKV, classifica papéis e aplica nomes/flags.
    In-place se a ordem já estiver correta; remux só se a ordem mudar.

    state (compartilhado entre arquivos):
        'naming_mode': None | 'preencher' | 'sobrescrever'
        'confirm_all': bool — True = pular confirmação individual
        'order_mode': None | 'remux' | 'inplace' — escolha quando a ordem muda
        'flag_opts': opções de flag do mkvmerge
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

    assign_canonicals(audios, "áudio")
    assign_canonicals(subs, "legenda")

    resolve_roles(audios, "áudio")
    resolve_roles(subs, "legenda")

    named = [t for t in audios + subs if t.title.strip()]
    naming_mode = state.get('naming_mode')

    if named and naming_mode is None:
        naming_mode = ask_naming_mode(named)
        print("\n  Aplicar esta escolha a todos os próximos arquivos? ", end='')
        if input("(s/n): ").strip().lower() == 's':
            state['naming_mode'] = naming_mode
    elif naming_mode is None:
        naming_mode = 'preencher'

    sorted_audios = sorted(audios, key=lambda t: (canonical_order_key(t.canonical), role_rank(t)))
    sorted_subs   = sorted(subs,   key=lambda t: (canonical_order_key(t.canonical), role_rank(t)))
    final_order   = videos + sorted_audios + sorted_subs

    new_names: Dict[int, str] = {}
    for t in sorted_audios + sorted_subs:
        desired = desired_name(t)
        if not desired:
            continue
        if naming_mode == 'sobrescrever' or not t.title.strip():
            if desired != t.title:
                new_names[t.track_id] = desired

    order_same = [t.track_id for t in tracks] == [t.track_id for t in final_order]
    flag_edits = [
        t for t in sorted_audios + sorted_subs
        if (t.role_touched or t.track_id in new_names) and flags_differ(t)
    ]
    name_edits = [t for t in sorted_audios + sorted_subs if t.track_id in new_names]
    # União estável para o mkvpropedit
    edit_ids = []
    edits: List[TrackInfo] = []
    for t in name_edits + flag_edits:
        if t.track_id not in edit_ids:
            edit_ids.append(t.track_id)
            edits.append(t)

    if order_same and not edits:
        mode = 'noop'
    elif order_same:
        mode = 'inplace'
    else:
        mode = 'remux'

    tipo_map = {"video": "Vídeo", "audio": "Áudio", "subtitles": "Legenda"}
    print("\n  Plano:")
    if mode == 'inplace':
        print("  Modo: IN-PLACE (mkvpropedit, sem remux — altera o arquivo original)")
    elif mode == 'remux':
        print("  Modo: REMUX necessário (a ordem das faixas é diferente da desejada)")
    else:
        print("  Modo: nada a alterar (ordem e nomes/flags já estão corretos)")
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

        flag_bits = []
        if t.track_type != 'video' and (t.role_touched or t.track_id in new_names) and flags_differ(t):
            if t.mark_forced != t.forced:
                flag_bits.append(f"forced={'1' if t.mark_forced else '0'}")
            if t.commentary != t.commentary_flag:
                flag_bits.append(f"commentary={'1' if t.commentary else '0'}")
        if flag_bits:
            name_str += "  [" + ", ".join(flag_bits) + "]"

        print(f"  {i:>3}. [{tipo:<8}] {lang_str:<27} {name_str}")

    if mode == 'noop':
        print("  Arquivo já conforme. Pulando.")
        return True

    if mode == 'remux':
        choice = state.get('order_mode')
        if choice not in ('remux', 'inplace'):
            print("\n  Remux necessário, prosseguir com remux ou somente renomear "
                  "sem alterar ordem (inplace edit)?")
            print("    r = remux (reordena e salva em Remuxed/)")
            print("    i = inplace (só renomeia e flags, ordem atual)")
            print("    n = pular este arquivo")
            while True:
                r = input("  Opção [r/i/n]: ").strip().lower()
                if r in ('r', 'remux'):
                    choice = 'remux'
                    break
                if r in ('i', 'inplace', 'p'):
                    choice = 'inplace'
                    break
                if r in ('n', 'nao', 'não', 'pular'):
                    print("  Arquivo pulado.")
                    return False
                print("  Opção inválida.")
            print("  Aplicar esta escolha a todos os próximos arquivos que precisem de remux? ", end='')
            if input("(s/n): ").strip().lower() == 's':
                state['order_mode'] = choice
        if choice == 'inplace':
            if not edits:
                print("  Nada a renomear sem mudar a ordem. Pulando.")
                return True
            print("  Ordem mantida — só nomes e flags, no arquivo original.")
            return edit_inplace(mkv_path, edits, new_names)
        return remux(mkv_path, final_order, new_names, state.get('flag_opts') or {})

    if not state.get('confirm_all'):
        print("\n  Prosseguir com a edição in-place?  s = sim | n = pular | t = sim para todos")
        r = input("  Opção: ").strip().lower()
        if r == 't':
            state['confirm_all'] = True
        elif r != 's':
            print("  Arquivo pulado.")
            return False

    return edit_inplace(mkv_path, edits, new_names)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 64)
    print("  TRACK NAMER — Padronização de Faixas MKV")
    print("=" * 64)

    if not tool_available(MKVMERGE):
        print(f"\n[ERRO] mkvmerge não encontrado: {MKVMERGE}")
        input("\nEnter para sair...")
        sys.exit(1)
    if not tool_available(MKVPROPEDIT):
        print(f"\n[AVISO] mkvpropedit não encontrado: {MKVPROPEDIT}")
        print("        Edição in-place ficará indisponível; só remux.")

    if len(sys.argv) < 2:
        print("\n[ERRO] Nenhum arquivo ou pasta foi arrastado!")
        print("\nComo usar:")
        print("  • Arraste um ou mais arquivos .mkv sobre o track_namer.bat")
        print("  • Ou arraste pastas contendo arquivos .mkv")
        input("\nEnter para sair...")
        sys.exit(1)

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

    print("\nSe a ordem já estiver correta, o arquivo original é editado in-place.")
    print("Se a ordem mudar, o script pergunta: remux ou só renomear sem reordenar.")

    state: Dict = {
        'naming_mode': None,
        'confirm_all': False,
        'order_mode': None,   # None | 'remux' | 'inplace'
        'flag_opts': detect_merge_flag_opts(),
    }

    success = skipped = 0

    for mkv_path in mkv_files:
        result = process_file(mkv_path, state)
        if result is True:
            success += 1
        else:
            skipped += 1

    print(f"\n{'=' * 64}")
    print("  CONCLUÍDO")
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
