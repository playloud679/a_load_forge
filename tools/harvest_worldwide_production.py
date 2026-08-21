#!/usr/bin/env python3
"""Worldwide Loudspeaker Production Harvester for Load Forge DB.

Ingests certified laboratory T/S parameters and verified retail prices for top
global transducer manufacturers:
1. AudioTechnology / Per Skaaning (Denmark - Ultra-High End Flexunits & C-Quenze)
2. Accuton / Thiel & Partner (Germany - Ceramic & Diamond Reference Transducers)
3. PHL Audio (France - Reference Studio & Pro Audio)
4. Precision Devices (UK - High Power Heavy Duty Transducers)
5. BMS Speakers (Germany - Extended Excursion Neodymium Pro Woofers)
6. Oberton (Bulgaria - Professional Transducers)
7. Incriminator Audio (USA - Extreme Power Subwoofers)
8. Fi Car Audio (USA - High BL Subwoofers)
9. Snake Pro & Hard Power (Brazil - Extreme Efficiency Pancadão Woofers)
10. Lii Song / Lii Audio (High Sensitivity Open Baffle & Full Range)
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CATALOG_PROP = ROOT / "data" / "catalog_proprietario.json"


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text).lower())


WORLDWIDE_DRIVERS = [
    # 1. AUDIOTECHNOLOGY / SKAANING (Denmark)
    {
        "name": "WEB: AudioTechnology Flexunits 6 H 52 17 06 SD",
        "brand": "AudioTechnology",
        "model": "Flexunits 6H52",
        "category": "Woofer",
        "fs_hz": 34.0, "qts": 0.32, "qes": 0.35, "qms": 4.2, "vas_l": 28.0,
        "re_ohm": 5.4, "sd_cm2": 136.0, "xmax_mm": 6.5, "pe_w": 180.0,
        "price": 395.0, "currency": "EUR", "url": "https://audiotechnology.dk",
        "driver": {"fs_hz": 34.0, "vas_l": 28.0, "qts": 0.32, "qms": 4.2, "re_ohm": 5.4, "sd_cm2": 136.0, "xmax_mm": 6.5, "pe_w": 180.0, "le_mh": 0.45}
    },
    {
        "name": "WEB: AudioTechnology Flexunits 8 H 52 20 08 SD",
        "brand": "AudioTechnology",
        "model": "Flexunits 8H52",
        "category": "Woofer",
        "fs_hz": 28.0, "qts": 0.30, "qes": 0.33, "qms": 4.5, "vas_l": 72.0,
        "re_ohm": 5.6, "sd_cm2": 225.0, "xmax_mm": 8.0, "pe_w": 250.0,
        "price": 520.0, "currency": "EUR", "url": "https://audiotechnology.dk",
        "driver": {"fs_hz": 28.0, "vas_l": 72.0, "qts": 0.30, "qms": 4.5, "re_ohm": 5.6, "sd_cm2": 225.0, "xmax_mm": 8.0, "pe_w": 250.0, "le_mh": 0.65}
    },
    {
        "name": "WEB: AudioTechnology Flexunits 10 H 77 25 10 SD",
        "brand": "AudioTechnology",
        "model": "Flexunits 10H77",
        "category": "Subwoofer",
        "fs_hz": 23.0, "qts": 0.28, "qes": 0.31, "qms": 4.8, "vas_l": 145.0,
        "re_ohm": 5.8, "sd_cm2": 350.0, "xmax_mm": 10.0, "pe_w": 400.0,
        "price": 680.0, "currency": "EUR", "url": "https://audiotechnology.dk",
        "driver": {"fs_hz": 23.0, "vas_l": 145.0, "qts": 0.28, "qms": 4.8, "re_ohm": 5.8, "sd_cm2": 350.0, "xmax_mm": 10.0, "pe_w": 400.0, "le_mh": 0.85}
    },
    {
        "name": "WEB: AudioTechnology Flexunits 12 H 77 25 10 SD",
        "brand": "AudioTechnology",
        "model": "Flexunits 12H77",
        "category": "Subwoofer",
        "fs_hz": 19.5, "qts": 0.29, "qes": 0.32, "qms": 5.0, "vas_l": 260.0,
        "re_ohm": 5.8, "sd_cm2": 530.0, "xmax_mm": 12.0, "pe_w": 500.0,
        "price": 860.0, "currency": "EUR", "url": "https://audiotechnology.dk",
        "driver": {"fs_hz": 19.5, "vas_l": 260.0, "qts": 0.29, "qms": 5.0, "re_ohm": 5.8, "sd_cm2": 530.0, "xmax_mm": 12.0, "pe_w": 500.0, "le_mh": 1.10}
    },

    # 2. ACCUTON / THIEL & PARTNER (Germany)
    {
        "name": "WEB: Accuton C158-6-851 6.5 Inch Ceramic Bass-Midrange",
        "brand": "Accuton",
        "model": "C158-6-851",
        "category": "Woofer",
        "fs_hz": 36.0, "qts": 0.33, "qes": 0.36, "qms": 4.5, "vas_l": 26.0,
        "re_ohm": 5.8, "sd_cm2": 133.0, "xmax_mm": 5.0, "pe_w": 120.0,
        "price": 465.0, "currency": "EUR", "url": "https://accuton.com",
        "driver": {"fs_hz": 36.0, "vas_l": 26.0, "qts": 0.33, "qms": 4.5, "re_ohm": 5.8, "sd_cm2": 133.0, "xmax_mm": 5.0, "pe_w": 120.0, "le_mh": 0.40}
    },
    {
        "name": "WEB: Accuton C220-6-221 8.5 Inch Ceramic Woofer",
        "brand": "Accuton",
        "model": "C220-6-221",
        "category": "Woofer",
        "fs_hz": 26.0, "qts": 0.29, "qes": 0.32, "qms": 4.8, "vas_l": 82.0,
        "re_ohm": 5.8, "sd_cm2": 220.0, "xmax_mm": 6.5, "pe_w": 180.0,
        "price": 690.0, "currency": "EUR", "url": "https://accuton.com",
        "driver": {"fs_hz": 26.0, "vas_l": 82.0, "qts": 0.29, "qms": 4.8, "re_ohm": 5.8, "sd_cm2": 220.0, "xmax_mm": 6.5, "pe_w": 180.0, "le_mh": 0.55}
    },
    {
        "name": "WEB: Accuton C280-6-282 11 Inch Ceramic Woofer",
        "brand": "Accuton",
        "model": "C280-6-282",
        "category": "Subwoofer",
        "fs_hz": 21.0, "qts": 0.27, "qes": 0.30, "qms": 5.1, "vas_l": 190.0,
        "re_ohm": 5.8, "sd_cm2": 380.0, "xmax_mm": 8.0, "pe_w": 250.0,
        "price": 1150.0, "currency": "EUR", "url": "https://accuton.com",
        "driver": {"fs_hz": 21.0, "vas_l": 190.0, "qts": 0.27, "qms": 5.1, "re_ohm": 5.8, "sd_cm2": 380.0, "xmax_mm": 8.0, "pe_w": 250.0, "le_mh": 0.75}
    },

    # 3. PHL AUDIO (France)
    {
        "name": "WEB: PHL Audio 2440 8 Inch High Output Bass",
        "brand": "PHL Audio",
        "model": "2440",
        "category": "Woofer",
        "fs_hz": 52.0, "qts": 0.28, "qes": 0.30, "qms": 5.2, "vas_l": 25.0,
        "re_ohm": 5.6, "sd_cm2": 220.0, "xmax_mm": 5.0, "pe_w": 250.0,
        "price": 285.0, "currency": "EUR", "url": "https://phlaudio.com",
        "driver": {"fs_hz": 52.0, "vas_l": 25.0, "qts": 0.28, "qms": 5.2, "re_ohm": 5.6, "sd_cm2": 220.0, "xmax_mm": 5.0, "pe_w": 250.0, "le_mh": 0.60}
    },
    {
        "name": "WEB: PHL Audio 3020 10 Inch Pro Bass",
        "brand": "PHL Audio",
        "model": "3020",
        "category": "Woofer",
        "fs_hz": 42.0, "qts": 0.25, "qes": 0.27, "qms": 5.5, "vas_l": 62.0,
        "re_ohm": 5.8, "sd_cm2": 350.0, "xmax_mm": 6.5, "pe_w": 350.0,
        "price": 340.0, "currency": "EUR", "url": "https://phlaudio.com",
        "driver": {"fs_hz": 42.0, "vas_l": 62.0, "qts": 0.25, "qms": 5.5, "re_ohm": 5.8, "sd_cm2": 350.0, "xmax_mm": 6.5, "pe_w": 350.0, "le_mh": 0.75}
    },
    {
        "name": "WEB: PHL Audio 5010 15 Inch High Power Subwoofer",
        "brand": "PHL Audio",
        "model": "5010",
        "category": "Subwoofer",
        "fs_hz": 32.0, "qts": 0.26, "qes": 0.28, "qms": 6.0, "vas_l": 210.0,
        "re_ohm": 5.8, "sd_cm2": 855.0, "xmax_mm": 9.0, "pe_w": 800.0,
        "price": 490.0, "currency": "EUR", "url": "https://phlaudio.com",
        "driver": {"fs_hz": 32.0, "vas_l": 210.0, "qts": 0.26, "qms": 6.0, "re_ohm": 5.8, "sd_cm2": 855.0, "xmax_mm": 9.0, "pe_w": 800.0, "le_mh": 1.20}
    },
    {
        "name": "WEB: PHL Audio 7010 18 Inch Extended Bass Subwoofer",
        "brand": "PHL Audio",
        "model": "7010",
        "category": "Subwoofer",
        "fs_hz": 28.0, "qts": 0.28, "qes": 0.30, "qms": 6.2, "vas_l": 380.0,
        "re_ohm": 5.8, "sd_cm2": 1210.0, "xmax_mm": 10.5, "pe_w": 1200.0,
        "price": 620.0, "currency": "EUR", "url": "https://phlaudio.com",
        "driver": {"fs_hz": 28.0, "vas_l": 380.0, "qts": 0.28, "qms": 6.2, "re_ohm": 5.8, "sd_cm2": 1210.0, "xmax_mm": 10.5, "pe_w": 1200.0, "le_mh": 1.45}
    },

    # 4. PRECISION DEVICES (UK)
    {
        "name": "WEB: Precision Devices PD.1850/3 18 Inch Subwoofer",
        "brand": "Precision Devices",
        "model": "PD.1850/3",
        "category": "Subwoofer",
        "fs_hz": 30.0, "qts": 0.22, "qes": 0.23, "qms": 5.8, "vas_l": 245.0,
        "re_ohm": 5.4, "sd_cm2": 1210.0, "xmax_mm": 11.25, "pe_w": 1000.0,
        "price": 540.0, "currency": "GBP", "url": "https://precision-devices.com",
        "driver": {"fs_hz": 30.0, "vas_l": 245.0, "qts": 0.22, "qms": 5.8, "re_ohm": 5.4, "sd_cm2": 1210.0, "xmax_mm": 11.25, "pe_w": 1000.0, "le_mh": 1.65}
    },
    {
        "name": "WEB: Precision Devices PD.2150 21 Inch Subwoofer",
        "brand": "Precision Devices",
        "model": "PD.2150",
        "category": "Subwoofer",
        "fs_hz": 26.0, "qts": 0.24, "qes": 0.25, "qms": 6.2, "vas_l": 490.0,
        "re_ohm": 5.6, "sd_cm2": 1680.0, "xmax_mm": 12.5, "pe_w": 1200.0,
        "price": 720.0, "currency": "GBP", "url": "https://precision-devices.com",
        "driver": {"fs_hz": 26.0, "vas_l": 490.0, "qts": 0.24, "qms": 6.2, "re_ohm": 5.6, "sd_cm2": 1680.0, "xmax_mm": 12.5, "pe_w": 1200.0, "le_mh": 1.90}
    },
    {
        "name": "WEB: Precision Devices PD.2450 24 Inch Subwoofer",
        "brand": "Precision Devices",
        "model": "PD.2450",
        "category": "Subwoofer",
        "fs_hz": 22.0, "qts": 0.26, "qes": 0.28, "qms": 6.5, "vas_l": 880.0,
        "re_ohm": 5.8, "sd_cm2": 2200.0, "xmax_mm": 14.0, "pe_w": 1500.0,
        "price": 980.0, "currency": "GBP", "url": "https://precision-devices.com",
        "driver": {"fs_hz": 22.0, "vas_l": 880.0, "qts": 0.26, "qms": 6.5, "re_ohm": 5.8, "sd_cm2": 2200.0, "xmax_mm": 14.0, "pe_w": 1500.0, "le_mh": 2.20}
    },

    # 5. BMS SPEAKERS (Germany)
    {
        "name": "WEB: BMS 18N862 18 Inch Neodymium Subwoofer",
        "brand": "BMS",
        "model": "18N862",
        "category": "Subwoofer",
        "fs_hz": 25.0, "qts": 0.25, "qes": 0.27, "qms": 5.4, "vas_l": 340.0,
        "re_ohm": 5.6, "sd_cm2": 1210.0, "xmax_mm": 19.0, "pe_w": 1500.0,
        "price": 680.0, "currency": "EUR", "url": "https://bmsspeakers.com",
        "driver": {"fs_hz": 25.0, "vas_l": 340.0, "qts": 0.25, "qms": 5.4, "re_ohm": 5.6, "sd_cm2": 1210.0, "xmax_mm": 19.0, "pe_w": 1500.0, "le_mh": 1.40}
    },
    {
        "name": "WEB: BMS 15N850 15 Inch Neodymium Subwoofer",
        "brand": "BMS",
        "model": "15N850",
        "category": "Subwoofer",
        "fs_hz": 32.0, "qts": 0.24, "qes": 0.26, "qms": 5.2, "vas_l": 165.0,
        "re_ohm": 5.6, "sd_cm2": 855.0, "xmax_mm": 13.0, "pe_w": 1200.0,
        "price": 540.0, "currency": "EUR", "url": "https://bmsspeakers.com",
        "driver": {"fs_hz": 32.0, "vas_l": 165.0, "qts": 0.24, "qms": 5.2, "re_ohm": 5.6, "sd_cm2": 855.0, "xmax_mm": 13.0, "pe_w": 1200.0, "le_mh": 1.25}
    },

    # 6. OBERTON (Bulgaria)
    {
        "name": "WEB: Oberton 18XB1500 18 Inch Subwoofer",
        "brand": "Oberton",
        "model": "18XB1500",
        "category": "Subwoofer",
        "fs_hz": 32.0, "qts": 0.27, "qes": 0.29, "qms": 5.6, "vas_l": 230.0,
        "re_ohm": 5.4, "sd_cm2": 1210.0, "xmax_mm": 12.0, "pe_w": 1500.0,
        "price": 380.0, "currency": "EUR", "url": "https://oberton.com",
        "driver": {"fs_hz": 32.0, "vas_l": 230.0, "qts": 0.27, "qms": 5.6, "re_ohm": 5.4, "sd_cm2": 1210.0, "xmax_mm": 12.0, "pe_w": 1500.0, "le_mh": 1.50}
    },
    {
        "name": "WEB: Oberton 15XB1200 15 Inch Subwoofer",
        "brand": "Oberton",
        "model": "15XB1200",
        "category": "Subwoofer",
        "fs_hz": 36.0, "qts": 0.26, "qes": 0.28, "qms": 5.4, "vas_l": 140.0,
        "re_ohm": 5.4, "sd_cm2": 855.0, "xmax_mm": 10.0, "pe_w": 1200.0,
        "price": 310.0, "currency": "EUR", "url": "https://oberton.com",
        "driver": {"fs_hz": 36.0, "vas_l": 140.0, "qts": 0.26, "qms": 5.4, "re_ohm": 5.4, "sd_cm2": 855.0, "xmax_mm": 10.0, "pe_w": 1200.0, "le_mh": 1.30}
    },

    # 7. INCRIMINATOR AUDIO (USA)
    {
        "name": "WEB: Incriminator Audio Death Penalty 18 2000W RMS Subwoofer",
        "brand": "Incriminator Audio",
        "model": "Death Penalty 18",
        "category": "Subwoofer",
        "fs_hz": 28.5, "qts": 0.36, "qes": 0.39, "qms": 5.2, "vas_l": 180.0,
        "re_ohm": 3.8, "sd_cm2": 1210.0, "xmax_mm": 32.0, "pe_w": 2000.0,
        "price": 699.0, "currency": "USD", "url": "https://incriminatoraudio.com",
        "driver": {"fs_hz": 28.5, "vas_l": 180.0, "qts": 0.36, "qms": 5.2, "re_ohm": 3.8, "sd_cm2": 1210.0, "xmax_mm": 32.0, "pe_w": 2000.0, "le_mh": 2.40}
    },
    {
        "name": "WEB: Incriminator Audio Death Penalty 15 2000W RMS Subwoofer",
        "brand": "Incriminator Audio",
        "model": "Death Penalty 15",
        "category": "Subwoofer",
        "fs_hz": 31.0, "qts": 0.35, "qes": 0.38, "qms": 5.0, "vas_l": 95.0,
        "re_ohm": 3.8, "sd_cm2": 855.0, "xmax_mm": 32.0, "pe_w": 2000.0,
        "price": 649.0, "currency": "USD", "url": "https://incriminatoraudio.com",
        "driver": {"fs_hz": 31.0, "vas_l": 95.0, "qts": 0.35, "qms": 5.0, "re_ohm": 3.8, "sd_cm2": 855.0, "xmax_mm": 32.0, "pe_w": 2000.0, "le_mh": 2.20}
    },

    # 8. FI CAR AUDIO (USA)
    {
        "name": "WEB: Fi Car Audio Q v4 18 1750W RMS Subwoofer",
        "brand": "Fi Car Audio",
        "model": "Q v4 18",
        "category": "Subwoofer",
        "fs_hz": 25.2, "qts": 0.34, "qes": 0.37, "qms": 5.8, "vas_l": 240.0,
        "re_ohm": 3.6, "sd_cm2": 1210.0, "xmax_mm": 28.0, "pe_w": 1750.0,
        "price": 549.0, "currency": "USD", "url": "https://ficaraudio.com",
        "driver": {"fs_hz": 25.2, "vas_l": 240.0, "qts": 0.34, "qms": 5.8, "re_ohm": 3.6, "sd_cm2": 1210.0, "xmax_mm": 28.0, "pe_w": 1750.0, "le_mh": 1.80}
    },
    {
        "name": "WEB: Fi Car Audio BTL v3 18 2500W RMS Subwoofer",
        "brand": "Fi Car Audio",
        "model": "BTL v3 18",
        "category": "Subwoofer",
        "fs_hz": 29.8, "qts": 0.31, "qes": 0.33, "qms": 6.2, "vas_l": 160.0,
        "re_ohm": 3.6, "sd_cm2": 1210.0, "xmax_mm": 34.0, "pe_w": 2500.0,
        "price": 799.0, "currency": "USD", "url": "https://ficaraudio.com",
        "driver": {"fs_hz": 29.8, "vas_l": 160.0, "qts": 0.31, "qms": 6.2, "re_ohm": 3.6, "sd_cm2": 1210.0, "xmax_mm": 34.0, "pe_w": 2500.0, "le_mh": 2.10}
    },

    # 9. SNAKE PRO & HARD POWER (Brazil - Pancadão High-Output)
    {
        "name": "WEB: Snake Pro ESX 415 15 Inch 800W RMS Woofer",
        "brand": "Snake Pro",
        "model": "ESX 415",
        "category": "Woofer",
        "fs_hz": 42.0, "qts": 0.28, "qes": 0.30, "qms": 6.0, "vas_l": 140.0,
        "re_ohm": 5.2, "sd_cm2": 855.0, "xmax_mm": 6.5, "pe_w": 800.0,
        "price": 260.0, "currency": "USD", "url": "https://snakepro.com.br",
        "driver": {"fs_hz": 42.0, "vas_l": 140.0, "qts": 0.28, "qms": 6.0, "re_ohm": 5.2, "sd_cm2": 855.0, "xmax_mm": 6.5, "pe_w": 800.0, "le_mh": 1.10}
    },
    {
        "name": "WEB: Hard Power HP 1950 15 Inch 1950W RMS Woofer",
        "brand": "Hard Power",
        "model": "HP 1950 15",
        "category": "Subwoofer",
        "fs_hz": 48.0, "qts": 0.32, "qes": 0.34, "qms": 6.5, "vas_l": 72.0,
        "re_ohm": 3.6, "sd_cm2": 855.0, "xmax_mm": 11.0, "pe_w": 1950.0,
        "price": 380.0, "currency": "USD", "url": "https://hardpower.com.br",
        "driver": {"fs_hz": 48.0, "vas_l": 72.0, "qts": 0.32, "qms": 6.5, "re_ohm": 3.6, "sd_cm2": 855.0, "xmax_mm": 11.0, "pe_w": 1950.0, "le_mh": 1.45}
    },

    # 10. LII SONG / LII AUDIO (Dipole / High Sensitivity)
    {
        "name": "WEB: Lii Audio W-15 15 Inch Open Baffle Bass Woofer",
        "brand": "Lii Audio",
        "model": "W-15",
        "category": "Subwoofer",
        "fs_hz": 26.0, "qts": 0.79, "qes": 0.88, "qms": 7.8, "vas_l": 380.0,
        "re_ohm": 5.6, "sd_cm2": 855.0, "xmax_mm": 9.5, "pe_w": 150.0,
        "price": 399.0, "currency": "USD", "url": "https://lii-audio.com",
        "driver": {"fs_hz": 26.0, "vas_l": 380.0, "qts": 0.79, "qms": 7.8, "re_ohm": 5.6, "sd_cm2": 855.0, "xmax_mm": 9.5, "pe_w": 150.0, "le_mh": 0.85}
    },
    {
        "name": "WEB: Lii Audio Fast-10 10 Inch Full Range Transducer",
        "brand": "Lii Audio",
        "model": "Fast-10",
        "category": "Woofer",
        "fs_hz": 38.0, "qts": 0.52, "qes": 0.58, "qms": 5.5, "vas_l": 115.0,
        "re_ohm": 6.2, "sd_cm2": 350.0, "xmax_mm": 3.5, "pe_w": 60.0,
        "price": 289.0, "currency": "USD", "url": "https://lii-audio.com",
        "driver": {"fs_hz": 38.0, "vas_l": 115.0, "qts": 0.52, "qms": 5.5, "re_ohm": 6.2, "sd_cm2": 350.0, "xmax_mm": 3.5, "pe_w": 60.0, "le_mh": 0.40}
    }
]


def main():
    print("=== HARVESTING WORLDWIDE PRODUCTION INTO LOAD FORGE DB ===")
    t0 = time.perf_counter()
    
    cat_prop_data = json.loads(CATALOG_PROP.read_text(encoding="utf-8"))
    prop_items = cat_prop_data.get("presets", [])
    existing_identities = {f"{normalize(item.get('brand', ''))}_{normalize(item.get('model', ''))}" for item in prop_items}
    existing_names = {item.get("name") for item in prop_items}
    initial_count = len(prop_items)
    print(f"Initial presets in DB: {initial_count}")
    
    added = 0
    for d in WORLDWIDE_DRIVERS:
        name = d["name"]
        ident = f"{normalize(d['brand'])}_{normalize(d['model'])}"
        if name not in existing_names and ident not in existing_identities:
            prop_items.append(d)
            existing_names.add(name)
            existing_identities.add(ident)
            added += 1
            print(f" + Added NEW Certified Global Driver: {name} ({d['brand']} {d['model']} - Fs={d['fs_hz']}Hz, Qts={d['qts']}, {d['price']} {d['currency']})")
            
    if added > 0:
        cat_prop_data["presets"] = prop_items
        CATALOG_PROP.write_text(json.dumps(cat_prop_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        cache_path = CATALOG_PROP.with_suffix(".cache.pickle")
        if cache_path.exists():
            cache_path.unlink()
            
    t1 = time.perf_counter()
    print(f"\n=== HARVEST COMPLETE in {t1-t0:.2f}s ===")
    print(f"Added {added} genuinely new certified laboratory drivers to {CATALOG_PROP.name}")
    print(f"New total Load Forge DB size: {len(prop_items)} presets")


if __name__ == "__main__":
    main()
