#!/usr/bin/env python3
"""Test Ollama for edge case extraction."""

import json
import subprocess

# Test cases - the ones rules failed on
test_cases = [
    {"sku": "test1", "text": "Bingo Гел за пране 3л=50пр"},
    {"sku": "test2", "text": "LIV&BO Одеяло 150 x 200 см"},
    {"sku": "test3", "text": "Osram LED Star лампа 4,9 W"},
    {"sku": "test4", "text": "Bonuss Тоалетна хартия 32+8 бр."},
    {"sku": "test5", "text": "FAMILIA Collection Сладолед различни вкусове"},
    {"sku": "test6", "text": "Nivea Men Крем за бръснене"},
    {"sku": "test7", "text": "COCA-COLA 8 x 0,33 л кен промопакет"},
    {"sku": "test8", "text": "Свински врат без кост около 1,5 кг"},
]

PROMPT = """Extract from Bulgarian product text:
- brand (or null)
- category (Месо, Млечни, Напитки, Хигиена, Дом, Други)
- quantity_value (number, calculate totals for packs)
- quantity_unit

Return JSON only. Example:
{"brand": "Coca-Cola", "category": "Напитки", "quantity_value": 2640, "quantity_unit": "ml"}

Product: """

print("Testing Ollama (Llama 3.1 8B)...\n")

for tc in test_cases:
    payload = {
        "model": "llama3.1:8b-instruct-q4_K_M",
        "prompt": PROMPT + tc['text'],
        "stream": False,
        "format": "json"
    }
    
    result = subprocess.run(
        ['curl', '-s', 'http://172.17.0.1:11434/api/generate', '-d', json.dumps(payload)],
        capture_output=True, text=True, timeout=30
    )
    
    try:
        resp = json.loads(result.stdout)
        answer = resp.get('response', '')
        parsed = json.loads(answer) if answer.strip().startswith('{') else answer
        print(f"Input: {tc['text'][:50]}")
        print(f"Output: {parsed}")
        print()
    except Exception as e:
        print(f"Input: {tc['text'][:50]}")
        print(f"Error: {e}")
        print(f"Raw: {result.stdout[:200]}")
        print()
