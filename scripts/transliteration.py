#!/usr/bin/env python3
"""
Bulgarian transliteration and brand alias resolution for cross-store matching.

Handles:
- Cyrillic ↔ Latin conversion (BGN/PCGN romanization)
- Brand alias dictionary (50+ common grocery brands)
- Product type synonyms (кисело мляко = йогурт, etc.)
"""

import re
from typing import Set, Optional

# =============================================================================
# CYRILLIC ↔ LATIN TRANSLITERATION
# =============================================================================

CYRILLIC_TO_LATIN = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ж': 'zh',
    'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
    'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f',
    'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sht', 'ъ': 'a',
    'ь': 'y', 'ю': 'yu', 'я': 'ya',
}

# Reverse mapping (multi-char sequences first for correct parsing)
_LATIN_DIGRAPHS = {
    'sht': 'щ', 'zh': 'ж', 'ch': 'ч', 'sh': 'ш', 'ts': 'ц',
    'yu': 'ю', 'ya': 'я',
}
_LATIN_SINGLE = {
    'a': 'а', 'b': 'б', 'v': 'в', 'g': 'г', 'd': 'д', 'e': 'е',
    'f': 'ф', 'h': 'х', 'i': 'и', 'j': 'дж', 'k': 'к', 'l': 'л',
    'm': 'м', 'n': 'н', 'o': 'о', 'p': 'п', 'r': 'р', 's': 'с',
    't': 'т', 'u': 'у', 'w': 'у', 'x': 'кс', 'y': 'и', 'z': 'з',
}


def cyrillic_to_latin(text: str) -> str:
    """Convert Cyrillic text to Latin using Bulgarian phonetic rules."""
    result = []
    for char in text.lower():
        result.append(CYRILLIC_TO_LATIN.get(char, char))
    return ''.join(result)


def latin_to_cyrillic(text: str) -> str:
    """Convert Latin text to Cyrillic (best effort, Bulgarian rules)."""
    text = text.lower()
    result = []
    i = 0
    while i < len(text):
        matched = False
        # Try 3-char, then 2-char digraphs first
        for length in (3, 2):
            if i + length <= len(text):
                chunk = text[i:i+length]
                if chunk in _LATIN_DIGRAPHS:
                    result.append(_LATIN_DIGRAPHS[chunk])
                    i += length
                    matched = True
                    break
        if not matched:
            char = text[i]
            result.append(_LATIN_SINGLE.get(char, char))
            i += 1
    return ''.join(result)


def has_cyrillic(text: str) -> bool:
    return bool(re.search(r'[а-яА-Я]', text))


def has_latin(text: str) -> bool:
    return bool(re.search(r'[a-zA-Z]', text))


# =============================================================================
# BRAND ALIAS DICTIONARY
# =============================================================================

# Maps canonical (lowercase, stripped) brand name → set of all known variants
# Both Latin and Cyrillic forms. Used for token expansion AND brand matching.
BRAND_ALIASES = {
    # Beverages
    'coca-cola': {'кока-кола', 'кока кола', 'кокакола', 'coca-cola', 'coca cola', 'cocacola'},
    'pepsi': {'пепси', 'pepsi'},
    'fanta': {'фанта', 'fanta'},
    'sprite': {'спрайт', 'sprite'},
    'schweppes': {'швепс', 'schweppes'},
    'red bull': {'ред бул', 'red bull', 'redbull'},
    'heineken': {'хайнекен', 'heineken'},
    'carlsberg': {'карлсберг', 'carlsberg'},
    'tuborg': {'туборг', 'tuborg'},
    'kamenitza': {'каменица', 'kamenitza', 'каменитца'},
    'zagorka': {'загорка', 'zagorka'},
    'shumensko': {'шуменско', 'shumensko'},
    'pirinsko': {'пиринско', 'pirinsko'},
    'devin': {'девин', 'devin'},
    'bankya': {'банкя', 'bankya', 'банкъя'},
    
    # Coffee
    'jacobs': {'якобс', 'джейкъбс', 'jacobs'},
    'nescafe': {'нескафе', 'nescafe', 'nescafé'},
    'lavazza': {'лаваца', 'лавацa', 'lavazza'},
    'tchibo': {'чибо', 'tchibo'},
    'illy': {'illy'},  # NOT "или" — that's Bulgarian for "or"!
    
    # Dairy
    'danone': {'данон', 'данън', 'danone'},
    'president': {'президент', 'president', 'président'},
    'vereia': {'верея', 'vereia', 'вереа'},
    'sayana': {'саяна', 'sayana'},
    'olympus': {'олимпус', 'olympus'},
    'elle & vire': {'ел е вир', 'elle vire', 'elle & vire'},
    
    # Chocolate & Sweets
    'milka': {'милка', 'milka'},
    'nutella': {'нутела', 'nutella'},
    'kinder': {'киндер', 'kinder'},
    'oreo': {'орео', 'oreo'},
    'ritter sport': {'ритер спорт', 'ritter sport', 'ritter'},
    'lindt': {'линдт', 'lindt'},
    'ferrero': {'фереро', 'ferrero'},
    'haribo': {'харибо', 'haribo'},
    'snickers': {'сникърс', 'snickers'},
    'mars': {'марс', 'mars'},
    'twix': {'туикс', 'twix'},
    'bounty': {'баунти', 'bounty'},
    'rafaello': {'рафаело', 'rafaello', 'raffaello'},
    
    # Personal Care
    'nivea': {'нивеа', 'нивея', 'nivea'},
    'dove': {'dove'},  # NOT дав/дов — too short, causes false matches in Bulgarian text
    'colgate': {'колгейт', 'colgate'},
    'oral-b': {'орал-б', 'oral-b', 'oral b', 'oralb'},
    'gillette': {'жилет', 'gillette', 'gilette'},
    'head & shoulders': {'хед енд шоулдърс', 'head shoulders', 'head & shoulders'},
    'pantene': {'пантене', 'pantene'},
    'garnier': {'гарние', 'garnier', 'гарниер'},
    'loreal': {'лореал', "l'oreal", 'loreal', "l'oréal"},
    'palmolive': {'палмолив', 'palmolive'},
    'rexona': {'рексона', 'rexona'},
    'old spice': {'олд спайс', 'old spice'},
    
    # Household
    'ariel': {'ариел', 'ariel'},
    'persil': {'персил', 'persil'},
    'lenor': {'ленор', 'lenor'},
    'finish': {'финиш', 'finish'},
    'fairy': {'фейри', 'fairy'},
    'domestos': {'доместос', 'domestos'},
    'calgon': {'калгон', 'calgon'},
    'vanish': {'ваниш', 'vanish'},
    'cif': {'сиф', 'cif'},
    'mr. proper': {'мистър пропър', 'mr proper', 'mr. proper'},
    
    # Snacks
    "lay's": {'лейс', "lay's", 'lays'},
    'pringles': {'принглс', 'pringles'},
    'chio': {'чио', 'chio'},
    'doritos': {'доритос', 'doritos'},
    
    # Food brands
    'nestle': {'нестле', 'nestle', 'nestlé'},
    'nesquik': {'нескуик', 'nesquik'},
    'maggi': {'маги', 'maggi'},
    'knorr': {'кнор', 'knorr'},
    'hellmanns': {'хелманс', "hellmann's", 'hellmanns'},
    'barilla': {'барила', 'barilla'},
    'bonduelle': {'бондюел', 'bonduelle'},
    
    # Spirits
    'absolut': {'абсолют', 'absolut'},
    'smirnoff': {'смирноф', 'smirnoff'},
    'jameson': {'джеймисън', 'jameson'},
    'johnnie walker': {'джони уокър', 'johnnie walker'},
    'jack daniels': {'джак даниелс', "jack daniel's", 'jack daniels'},
    
    # Bulgarian brands
    'tandem': {'тандем', 'tandem'},
    'perelik': {'перелик', 'perelik'},
    'kaliakra': {'калиакра', 'kaliakra'},
    'chipita': {'чипита', 'chipita'},
    'bella': {'бела', 'bella'},
    'deroni': {'дерони', 'deroni'},
    'cba': {'цба', 'cba'},
    'bor chvor': {'бор чвор', 'bor chvor'},
    'perunika': {'перуника', 'perunika'},
    'olineza': {'олинеза', 'olineza'},
    'zhiva voda': {'жива вода', 'zhiva voda'},
    'pestherska': {'пещерска', 'pestherska', 'peshterska'},
    
    # More brands found in DB across 2+ stores
    'heinz': {'хайнц', 'heinz'},
    'hochland': {'хохланд', 'hochland'},
    'jogobella': {'жогобела', 'jogobella'},
    'philadelphia': {'филаделфия', 'philadelphia'},
    'lindt': {'линдт', 'lindt'},
    'pampers': {'памперс', 'pampers'},
    'sensodyne': {'сенсодин', 'sensodyne'},
    'somat': {'сомат', 'somat'},
    'suchard': {'сушар', 'suchard'},
    'syoss': {'сиос', 'syoss'},
    'savex': {'савекс', 'savex'},
    'medix': {'медикс', 'medix'},
    'domestos': {'доместос', 'domestos'},
    'rexona': {'рексона', 'rexona'},
    'snickers': {'сникърс', 'snickers'},
    'alvina': {'алвина', 'alvina'},
    'brio': {'брио', 'brio'},
    'krina': {'крина', 'krina'},
    'teo': {'тео', 'teo'},
    'salza': {'салца', 'salza'},
    'prisun': {'присън', 'prisun'},
    'wet hankies': {'ует ханкис', 'wet hankies'},
    'jim beam': {'джим бийм', 'jim beam'},
    'nucrema': {'нукрема', 'nucrema'},
    
    # Bulgarian brands
    'orehite': {'орехите', 'orehite'},
    'vereia': {'верея', 'vereia'},
    'prestige': {'престиж', 'prestige', 'престиж'},
    'sladeia': {'сладея', 'sladeia'},
    'pastir': {'пастир', 'pastir'},
    'vita siluet': {'вита силует', 'vita siluet'},
    'delikatess zhitnitsa': {'деликатес житница'},
    'maistor tsvetko': {'майстор цветко'},
    'heli': {'хели', 'heli'},
    'kristal': {'кристал', 'kristal'},
    'roden': {'роден', 'roden'},
}

# Build reverse lookup: any variant → canonical name
_VARIANT_TO_CANONICAL = {}
for canonical, variants in BRAND_ALIASES.items():
    for v in variants:
        _VARIANT_TO_CANONICAL[v.lower().replace('-', '').replace(' ', '')] = canonical
    _VARIANT_TO_CANONICAL[canonical.lower().replace('-', '').replace(' ', '')] = canonical


def resolve_brand(brand_text: Optional[str]) -> Optional[str]:
    """Resolve a brand string to its canonical form using alias dictionary."""
    if not brand_text:
        return None
    key = brand_text.lower().strip().replace('-', '').replace(' ', '')
    if key in _VARIANT_TO_CANONICAL:
        return _VARIANT_TO_CANONICAL[key]
    # Try transliteration
    if has_cyrillic(key):
        latin = cyrillic_to_latin(key).replace(' ', '')
        if latin in _VARIANT_TO_CANONICAL:
            return _VARIANT_TO_CANONICAL[latin]
    elif has_latin(key):
        cyr = latin_to_cyrillic(key).replace(' ', '')
        if cyr in _VARIANT_TO_CANONICAL:
            return _VARIANT_TO_CANONICAL[cyr]
    return None


# =============================================================================
# PRODUCT TYPE SYNONYMS
# =============================================================================

# Pruned to EXACT semantic equivalents only — no generic expansions
# (Sonnet+Kimi audit: aggressive synonyms cause false bridges between milk↔yogurt etc.)
PRODUCT_SYNONYMS = {
    'кисело мляко': {'йогурт', 'yoghurt', 'yogurt'},
    'йогурт': {'yoghurt', 'yogurt'},
    'кашкавал': {'kashkaval'},
    'сирене': {'sirene'},
    'шоколад': {'chocolate'},
    'чипс': {'чипсове', 'chips'},
    'шампоан': {'shampoo'},
    'дезодорант': {'deodorant'},
    'душ гел': {'душгел'},
}

# Build a flat synonym lookup: word → set of synonyms
_SYNONYM_LOOKUP = {}
for key, syns in PRODUCT_SYNONYMS.items():
    all_forms = {key} | syns
    for form in all_forms:
        if form not in _SYNONYM_LOOKUP:
            _SYNONYM_LOOKUP[form] = set()
        _SYNONYM_LOOKUP[form].update(all_forms - {form})


def get_synonyms(token: str) -> Set[str]:
    """Get product type synonyms for a token."""
    return _SYNONYM_LOOKUP.get(token.lower(), set())


# =============================================================================
# TOKEN EXPANSION
# =============================================================================

def expand_token(token: str) -> Set[str]:
    """
    Expand a single token with all transliteration variants and synonyms.
    Returns the original + all variants.
    """
    variants = {token}
    clean = re.sub(r'[^\w]', '', token.lower())
    if not clean:
        return variants
    
    # 1. Brand alias lookup (most reliable)
    canonical = resolve_brand(clean)
    if canonical and canonical in BRAND_ALIASES:
        # Add all variant forms of this brand
        for v in BRAND_ALIASES[canonical]:
            # Add as single tokens (split multi-word brands)
            for part in v.split():
                variants.add(part.lower())
    
    # 2. Transliteration (only for tokens >= 4 chars to avoid noise)
    if len(clean) >= 4:
        if has_cyrillic(clean):
            latin = cyrillic_to_latin(clean)
            if latin != clean:
                variants.add(latin)
        if has_latin(clean):
            cyr = latin_to_cyrillic(clean)
            if cyr != clean:
                variants.add(cyr)
    
    # 3. Product synonyms
    syns = get_synonyms(clean)
    for s in syns:
        for part in s.split():
            variants.add(part.lower())
    
    return {v for v in variants if len(v) > 1}


def expand_tokens(tokens: Set[str]) -> Set[str]:
    """Expand all tokens in a set with transliterations and synonyms."""
    expanded = set()
    for t in tokens:
        expanded.update(expand_token(t))
    return expanded


# =============================================================================
# CONCEPT JACCARD (fixes token expansion inflation)
# =============================================================================

def _normalize_to_concept(token: str) -> str:
    """Collapse a token to a single concept key (Latin base form)."""
    clean = re.sub(r'[^\w]', '', token.lower())
    if not clean:
        return token
    # If Cyrillic, convert to Latin as canonical form
    if has_cyrillic(clean):
        return cyrillic_to_latin(clean)
    return clean


def concept_jaccard(tokens_a: Set[str], tokens_b: Set[str], min_common: int = 1) -> float:
    """
    Jaccard on concept-collapsed tokens, not raw tokens.
    
    Fixes the inflation bug: "nivea" and "нивеа" collapse to same concept "nivea",
    so they count as 1 intersection / 1 union, not 2/3.
    """
    concepts_a = {_normalize_to_concept(t) for t in tokens_a}
    concepts_b = {_normalize_to_concept(t) for t in tokens_b}
    
    # Remove empty/tiny concepts
    concepts_a = {c for c in concepts_a if len(c) > 1}
    concepts_b = {c for c in concepts_b if len(c) > 1}
    
    if not concepts_a or not concepts_b:
        return 0.0
    
    common = concepts_a & concepts_b
    if len(common) < min_common:
        return 0.0
    
    return len(common) / len(concepts_a | concepts_b)


# =============================================================================
# BRAND EXTRACTION FROM PRODUCT NAME
# =============================================================================

def extract_brand_from_name(name: str) -> Optional[str]:
    """
    Extract brand from product name when DB brand is missing/NO_BRAND.
    Uses word-boundary matching to avoid false positives.
    Requires brand to be >= 3 chars to avoid matching short Bulgarian words.
    """
    if not name:
        return None
    name_lower = name.lower()
    name_clean = name_lower.replace('-', ' ').replace('  ', ' ')
    
    best_match = None
    best_len = 0
    for canonical, variants in BRAND_ALIASES.items():
        all_forms = variants | {canonical}
        for variant in all_forms:
            v_lower = variant.lower()
            # Skip very short variants (high false positive risk)
            if len(v_lower) < 3:
                continue
            # Use word boundary matching
            pattern = r'(?:^|[\s,;(])' + re.escape(v_lower) + r'(?:[\s,;)]|$)'
            if re.search(pattern, name_clean) or re.search(pattern, name_lower):
                if len(v_lower) > best_len:
                    best_match = canonical
                    best_len = len(v_lower)
    
    return best_match


# =============================================================================
# PRODUCT TYPE CONFLICT DETECTION (Parkside false positive fix)
# =============================================================================

TYPE_INDICATORS = {
    'power_tools': {'бормашина', 'шлайф', 'ексцентършлайф', 'трион', 'фреза', 'полираща', 'винтоверт'},
    'hand_tools': {'чук', 'отвертка', 'ключ', 'клещи', 'кусачки'},
    'garden': {'листосъбирач', 'косачка', 'ножица', 'градински'},
    'clothing': {'блуза', 'тениска', 'тениски', 'панталон', 'чорапи', 'чорап', 'термочорапи', 'яке', 'колан'},
    'camping': {'палатка', 'спален', 'чанта', 'фенер'},
    'storage': {'стелаж', 'кутия', 'органайзер'},
    'fasteners': {'уплътнители', 'битове', 'винтове', 'скоби', 'свредла'},
    'battery': {'батерия', 'зарядно'},
    # CPG product types (prevents shower gel matching soap, shampoo matching dye)
    'shower_gel': {'душ'},
    'soap': {'сапун'},
    'shampoo': {'шампоан', 'балсам'},
    'hair_dye': {'боя', 'боядисване'},
    'deodorant': {'дезодорант', 'антиперспирант'},
    'face_care': {'мицеларна', 'мицеларен', 'лице'},
    'shaving': {'бръснене'},
    'cream_cpg': {'крем'},
    # Food product types  
    'biscuit': {'бисквити'},
    'wafer': {'вафли', 'вафла'},
    'pasta_dry': {'паста'},
}


def detect_type_conflict(tokens_a: Set[str], tokens_b: Set[str]) -> bool:
    """
    Returns True if products have CONFLICTING type indicators.
    Used to reject same-brand matches like Parkside tent vs Parkside belt.
    Uses both exact token match AND substring match for compound words.
    """
    def find_types(tokens):
        types = set()
        tokens_lower = {t.lower() for t in tokens}
        joined = ' '.join(tokens_lower)  # For substring matching
        for ptype, keywords in TYPE_INDICATORS.items():
            # Exact token match
            if tokens_lower & keywords:
                types.add(ptype)
            else:
                # Substring match (catches "ексцентършлайф" containing "шлайф")
                for kw in keywords:
                    if kw in joined:
                        types.add(ptype)
                        break
        return types
    
    types_a = find_types(tokens_a)
    types_b = find_types(tokens_b)
    
    # Conflict = both have type indicators but NO overlap
    if types_a and types_b and not (types_a & types_b):
        return True
    
    return False
