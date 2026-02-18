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
    'illy': {'или', 'illy'},
    
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
    'dove': {'дав', 'дов', 'dove'},
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

PRODUCT_SYNONYMS = {
    'кисело мляко': {'йогурт', 'yoghurt', 'yogurt'},
    'йогурт': {'кисело мляко', 'yoghurt', 'yogurt'},
    'прясно мляко': {'мляко', 'milk', 'fresh milk'},
    'кашкавал': {'yellow cheese', 'kashkaval'},
    'сирене': {'white cheese', 'sirene', 'feta'},
    'масло': {'butter', 'масло краве'},
    'хляб': {'bread', 'хлеб'},
    'кафе': {'coffee', 'cafe'},
    'чай': {'tea', 'чаи'},
    'бира': {'beer'},
    'вино': {'wine'},
    'ракия': {'rakia', 'rakiya'},
    'водка': {'vodka'},
    'уиски': {'whisky', 'whiskey'},
    'сок': {'juice'},
    'вода': {'water'},
    'шоколад': {'chocolate', 'чоколад'},
    'бисквити': {'biscuits', 'cookies'},
    'чипс': {'chips', 'чипсове', 'crisps'},
    'сапун': {'soap'},
    'шампоан': {'shampoo'},
    'паста за зъби': {'toothpaste'},
    'дезодорант': {'deodorant', 'дез'},
    'душ гел': {'shower gel', 'душгел'},
    'прах за пране': {'washing powder', 'detergent'},
    'гел за пране': {'liquid detergent', 'washing gel'},
    'омекотител': {'fabric softener'},
    'препарат': {'detergent', 'cleaner'},
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
    
    # 2. Transliteration
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
