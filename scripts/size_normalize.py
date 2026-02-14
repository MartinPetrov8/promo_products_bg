"""
Size normalization for product matching.
Normalizes Bulgarian size expressions to Latin equivalents for better matching.
"""
import re


def normalize_size_for_matching(text: str) -> str:
    """
    Normalize Bulgarian size expressions to standard Latin format.
    Used BEFORE matching to improve hit rate.
    
    Examples:
        "Мляко 500г" → "Мляко 500g"
        "Олио 1л" → "Олио 1l"
        "Кафе 200 гр" → "Кафе 200g"
    """
    if not text:
        return text
    
    # Replace comma with dot in decimals (1,5 → 1.5)
    text = re.sub(r'(\d),(\d)', r'\1.\2', text)
    
    # Kilograms: кг, КГ → kg
    text = re.sub(r'(\d+(?:\.\d+)?)\s*[кКkK][гГgG]', r'\1kg', text)
    
    # Grams: г, гр, ГР, Г → g
    text = re.sub(r'(\d+(?:\.\d+)?)\s*[гГgG][рРrR]?(?![гГgGрРrRаА])', r'\1g', text)
    
    # Liters: л, Л → l
    text = re.sub(r'(\d+(?:\.\d+)?)\s*[лЛlL](?![иІ])', r'\1l', text)
    
    # Milliliters: мл, МЛ → ml
    text = re.sub(r'(\d+(?:\.\d+)?)\s*[мМmM][лЛlL]', r'\1ml', text)
    
    return text


if __name__ == "__main__":
    tests = [
        ("Прясно мляко 3.6% 1л", "Прясно мляко 3.6% 1l"),
        ("Краве сирене 400 гр", "Краве сирене 400g"),
        ("Захар 1 кг", "Захар 1kg"),
        ("Бира Каменица 500 мл", "Бира Каменица 500ml"),
        ("Олио Слънчогледово 1,5 Л", "Олио Слънчогледово 1.5l"),
        ("Кисело мляко БДС 2%", "Кисело мляко БДС 2%"),  # no size
        ("Вода 500МЛ", "Вода 500ml"),
        ("Ориз 2 КГ", "Ориз 2kg"),
    ]
    
    print("=== Size Normalization Tests ===\n")
    passed = 0
    for input_text, expected in tests:
        result = normalize_size_for_matching(input_text)
        status = "✅" if result == expected else "❌"
        if result == expected:
            passed += 1
        print(f"{status} '{input_text}'")
        print(f"   → '{result}'")
        if result != expected:
            print(f"   Expected: '{expected}'")
        print()
    
    print(f"Passed: {passed}/{len(tests)}")
