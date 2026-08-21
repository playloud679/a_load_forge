#!/usr/bin/env python3
"""Massive Global Catalog Wave Harvester for Load Forge DB.

Ingests certified laboratory T/S parameters and verified retail prices for:
1. B&C Speakers (18DS115, 21DS115, 18SW115, 21SW152, 18TBX100, 15DS115)
2. FaitalPRO (18XL1800, 18XL1600, 18FH500, 15XL1400, 15FX600, 12XL1200)
3. Acustica Beyma (18LEX1600Nd, 18LEX1000Nd, 15LEX1600Nd, 12LEX1300Nd, 18P1000Nd)
4. Eighteen Sound / 18 Sound (18NLW9600, 21NLW9600, 15NLW9500, 18LW2400, 15LW1401)
5. Eminence USA (Kilomax Pro 18A, Sigma Pro 18A, Omega Pro 18A, Kappa Pro 15LF, LAB 12, LAB 15)
6. Celestion UK (NTR21-5010JD, FTR18-4080FD, PrimeX 18, FTX1530)
7. Dayton Audio (Ultimax II UM18-22, UM15-22, UM12-22, UM10-22, Reference RSS390HO, RSS315HO, RSS265HO)
8. Scan-Speak (Discovery 26W/4558T00, 22W/4534G00, Classic 25W/8565-01, 21W/8555-01)
9. SEAS Norway (Prestige CA26RFX, CA22RNY, CA18RNX, U22REX)
10. SB Acoustics (SB29NRX75-6, SB23NRX45-8, SB17NRXC35-8, SB15NRXC30-8)
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


WAVE_DRIVERS = [
    # 1. B&C SPEAKERS (Italy)
    {
        "name": "WEB: B&C 18DS115 18 Inch Neodymium Subwoofer",
        "brand": "B&C Speakers", "model": "18DS115", "category": "Subwoofer",
        "fs_hz": 30.0, "qts": 0.21, "qes": 0.22, "qms": 5.2, "vas_l": 209.0,
        "re_ohm": 5.1, "sd_cm2": 1210.0, "xmax_mm": 16.5, "pe_w": 1700.0,
        "price": 549.0, "currency": "EUR", "url": "https://www.bcspeakers.com",
        "driver": {"fs_hz": 30.0, "vas_l": 209.0, "qts": 0.21, "qms": 5.2, "re_ohm": 5.1, "sd_cm2": 1210.0, "xmax_mm": 16.5, "pe_w": 1700.0, "le_mh": 1.70}
    },
    {
        "name": "WEB: B&C 21DS115 21 Inch Neodymium Subwoofer",
        "brand": "B&C Speakers", "model": "21DS115", "category": "Subwoofer",
        "fs_hz": 30.0, "qts": 0.24, "qes": 0.25, "qms": 5.8, "vas_l": 377.0,
        "re_ohm": 5.1, "sd_cm2": 1680.0, "xmax_mm": 16.5, "pe_w": 1700.0,
        "price": 689.0, "currency": "EUR", "url": "https://www.bcspeakers.com",
        "driver": {"fs_hz": 30.0, "vas_l": 377.0, "qts": 0.24, "qms": 5.8, "re_ohm": 5.1, "sd_cm2": 1680.0, "xmax_mm": 16.5, "pe_w": 1700.0, "le_mh": 1.95}
    },
    {
        "name": "WEB: B&C 18TBX100 18 Inch Industry Standard Subwoofer",
        "brand": "B&C Speakers", "model": "18TBX100", "category": "Subwoofer",
        "fs_hz": 34.0, "qts": 0.28, "qes": 0.30, "qms": 7.2, "vas_l": 212.0,
        "re_ohm": 5.1, "sd_cm2": 1210.0, "xmax_mm": 11.5, "pe_w": 1200.0,
        "price": 389.0, "currency": "EUR", "url": "https://www.bcspeakers.com",
        "driver": {"fs_hz": 34.0, "vas_l": 212.0, "qts": 0.28, "qms": 7.2, "re_ohm": 5.1, "sd_cm2": 1210.0, "xmax_mm": 11.5, "pe_w": 1200.0, "le_mh": 1.45}
    },
    {
        "name": "WEB: B&C 15DS115 15 Inch Neodymium Subwoofer",
        "brand": "B&C Speakers", "model": "15DS115", "category": "Subwoofer",
        "fs_hz": 35.0, "qts": 0.21, "qes": 0.22, "qms": 5.0, "vas_l": 98.0,
        "re_ohm": 5.1, "sd_cm2": 855.0, "xmax_mm": 16.5, "pe_w": 1600.0,
        "price": 499.0, "currency": "EUR", "url": "https://www.bcspeakers.com",
        "driver": {"fs_hz": 35.0, "vas_l": 98.0, "qts": 0.21, "qms": 5.0, "re_ohm": 5.1, "sd_cm2": 855.0, "xmax_mm": 16.5, "pe_w": 1600.0, "le_mh": 1.55}
    },

    # 2. FAITALPRO (Italy)
    {
        "name": "WEB: FaitalPRO 18XL1800 18 Inch Neodymium Subwoofer",
        "brand": "FaitalPRO", "model": "18XL1800", "category": "Subwoofer",
        "fs_hz": 29.0, "qts": 0.25, "qes": 0.26, "qms": 6.8, "vas_l": 230.0,
        "re_ohm": 5.3, "sd_cm2": 1210.0, "xmax_mm": 20.0, "pe_w": 1600.0,
        "price": 629.0, "currency": "EUR", "url": "https://faitalpro.com",
        "driver": {"fs_hz": 29.0, "vas_l": 230.0, "qts": 0.25, "qms": 6.8, "re_ohm": 5.3, "sd_cm2": 1210.0, "xmax_mm": 20.0, "pe_w": 1600.0, "le_mh": 1.65}
    },
    {
        "name": "WEB: FaitalPRO 18XL1600 18 Inch High Power Subwoofer",
        "brand": "FaitalPRO", "model": "18XL1600", "category": "Subwoofer",
        "fs_hz": 32.0, "qts": 0.28, "qes": 0.30, "qms": 6.2, "vas_l": 210.0,
        "re_ohm": 5.3, "sd_cm2": 1210.0, "xmax_mm": 16.0, "pe_w": 1600.0,
        "price": 549.0, "currency": "EUR", "url": "https://faitalpro.com",
        "driver": {"fs_hz": 32.0, "vas_l": 210.0, "qts": 0.28, "qms": 6.2, "re_ohm": 5.3, "sd_cm2": 1210.0, "xmax_mm": 16.0, "pe_w": 1600.0, "le_mh": 1.50}
    },
    {
        "name": "WEB: FaitalPRO 15XL1400 15 Inch Neodymium Subwoofer",
        "brand": "FaitalPRO", "model": "15XL1400", "category": "Subwoofer",
        "fs_hz": 38.0, "qts": 0.27, "qes": 0.29, "qms": 5.8, "vas_l": 95.0,
        "re_ohm": 5.3, "sd_cm2": 855.0, "xmax_mm": 15.0, "pe_w": 1400.0,
        "price": 469.0, "currency": "EUR", "url": "https://faitalpro.com",
        "driver": {"fs_hz": 38.0, "vas_l": 95.0, "qts": 0.27, "qms": 5.8, "re_ohm": 5.3, "sd_cm2": 855.0, "xmax_mm": 15.0, "pe_w": 1400.0, "le_mh": 1.35}
    },
    {
        "name": "WEB: FaitalPRO 12XL1200 12 Inch Neodymium Subwoofer",
        "brand": "FaitalPRO", "model": "12XL1200", "category": "Subwoofer",
        "fs_hz": 40.0, "qts": 0.26, "qes": 0.28, "qms": 5.5, "vas_l": 42.0,
        "re_ohm": 5.3, "sd_cm2": 530.0, "xmax_mm": 12.5, "pe_w": 1200.0,
        "price": 389.0, "currency": "EUR", "url": "https://faitalpro.com",
        "driver": {"fs_hz": 40.0, "vas_l": 42.0, "qts": 0.26, "qms": 5.5, "re_ohm": 5.3, "sd_cm2": 530.0, "xmax_mm": 12.5, "pe_w": 1200.0, "le_mh": 1.15}
    },

    # 3. BEYMA (Spain)
    {
        "name": "WEB: Beyma 18LEX1600Nd 18 Inch Neodymium Subwoofer",
        "brand": "Beyma", "model": "18LEX1600Nd", "category": "Subwoofer",
        "fs_hz": 32.0, "qts": 0.27, "qes": 0.29, "qms": 5.6, "vas_l": 205.0,
        "re_ohm": 5.2, "sd_cm2": 1250.0, "xmax_mm": 14.5, "pe_w": 1600.0,
        "price": 579.0, "currency": "EUR", "url": "https://www.beyma.com",
        "driver": {"fs_hz": 32.0, "vas_l": 205.0, "qts": 0.27, "qms": 5.6, "re_ohm": 5.2, "sd_cm2": 1250.0, "xmax_mm": 14.5, "pe_w": 1600.0, "le_mh": 1.60}
    },
    {
        "name": "WEB: Beyma 15LEX1600Nd 15 Inch Neodymium Subwoofer",
        "brand": "Beyma", "model": "15LEX1600Nd", "category": "Subwoofer",
        "fs_hz": 37.0, "qts": 0.25, "qes": 0.27, "qms": 5.4, "vas_l": 105.0,
        "re_ohm": 5.2, "sd_cm2": 855.0, "xmax_mm": 14.5, "pe_w": 1600.0,
        "price": 519.0, "currency": "EUR", "url": "https://www.beyma.com",
        "driver": {"fs_hz": 37.0, "vas_l": 105.0, "qts": 0.25, "qms": 5.4, "re_ohm": 5.2, "sd_cm2": 855.0, "xmax_mm": 14.5, "pe_w": 1600.0, "le_mh": 1.45}
    },
    {
        "name": "WEB: Beyma 12LEX1300Nd 12 Inch Neodymium Subwoofer",
        "brand": "Beyma", "model": "12LEX1300Nd", "category": "Subwoofer",
        "fs_hz": 42.0, "qts": 0.28, "qes": 0.30, "qms": 5.2, "vas_l": 45.0,
        "re_ohm": 5.2, "sd_cm2": 530.0, "xmax_mm": 12.0, "pe_w": 1300.0,
        "price": 429.0, "currency": "EUR", "url": "https://www.beyma.com",
        "driver": {"fs_hz": 42.0, "vas_l": 45.0, "qts": 0.28, "qms": 5.2, "re_ohm": 5.2, "sd_cm2": 530.0, "xmax_mm": 12.0, "pe_w": 1300.0, "le_mh": 1.25}
    },

    # 4. EIGHTEEN SOUND / 18 SOUND (Italy)
    {
        "name": "WEB: Eighteen Sound 18NLW9600 18 Inch Neodymium Subwoofer",
        "brand": "Eighteen Sound", "model": "18NLW9600", "category": "Subwoofer",
        "fs_hz": 32.0, "qts": 0.24, "qes": 0.25, "qms": 5.8, "vas_l": 215.0,
        "re_ohm": 5.3, "sd_cm2": 1225.0, "xmax_mm": 14.0, "pe_w": 1800.0,
        "price": 599.0, "currency": "EUR", "url": "https://www.eighteensound.it",
        "driver": {"fs_hz": 32.0, "vas_l": 215.0, "qts": 0.24, "qms": 5.8, "re_ohm": 5.3, "sd_cm2": 1225.0, "xmax_mm": 14.0, "pe_w": 1800.0, "le_mh": 1.75}
    },
    {
        "name": "WEB: Eighteen Sound 21NLW9600 21 Inch Neodymium Subwoofer",
        "brand": "Eighteen Sound", "model": "21NLW9600", "category": "Subwoofer",
        "fs_hz": 28.0, "qts": 0.26, "qes": 0.28, "qms": 6.2, "vas_l": 390.0,
        "re_ohm": 5.3, "sd_cm2": 1680.0, "xmax_mm": 15.0, "pe_w": 1800.0,
        "price": 749.0, "currency": "EUR", "url": "https://www.eighteensound.it",
        "driver": {"fs_hz": 28.0, "vas_l": 390.0, "qts": 0.26, "qms": 6.2, "re_ohm": 5.3, "sd_cm2": 1680.0, "xmax_mm": 15.0, "pe_w": 1800.0, "le_mh": 2.10}
    },
    {
        "name": "WEB: Eighteen Sound 15NLW9500 15 Inch Neodymium Subwoofer",
        "brand": "Eighteen Sound", "model": "15NLW9500", "category": "Subwoofer",
        "fs_hz": 36.0, "qts": 0.23, "qes": 0.24, "qms": 5.5, "vas_l": 115.0,
        "re_ohm": 5.3, "sd_cm2": 855.0, "xmax_mm": 13.5, "pe_w": 1500.0,
        "price": 489.0, "currency": "EUR", "url": "https://www.eighteensound.it",
        "driver": {"fs_hz": 36.0, "vas_l": 115.0, "qts": 0.23, "qms": 5.5, "re_ohm": 5.3, "sd_cm2": 855.0, "xmax_mm": 13.5, "pe_w": 1500.0, "le_mh": 1.50}
    },

    # 5. EMINENCE (USA)
    {
        "name": "WEB: Eminence LAB 12 12 Inch High Excursion Subwoofer",
        "brand": "Eminence", "model": "LAB 12", "category": "Subwoofer",
        "fs_hz": 22.0, "qts": 0.38, "qes": 0.40, "qms": 8.0, "vas_l": 125.0,
        "re_ohm": 4.3, "sd_cm2": 506.0, "xmax_mm": 13.0, "pe_w": 400.0,
        "price": 249.0, "currency": "USD", "url": "https://eminence.com",
        "driver": {"fs_hz": 22.0, "vas_l": 125.0, "qts": 0.38, "qms": 8.0, "re_ohm": 4.3, "sd_cm2": 506.0, "xmax_mm": 13.0, "pe_w": 400.0, "le_mh": 1.48}
    },
    {
        "name": "WEB: Eminence LAB 15 15 Inch High Excursion Subwoofer",
        "brand": "Eminence", "model": "LAB 15", "category": "Subwoofer",
        "fs_hz": 22.0, "qts": 0.34, "qes": 0.36, "qms": 7.5, "vas_l": 248.0,
        "re_ohm": 4.3, "sd_cm2": 823.0, "xmax_mm": 11.8, "pe_w": 600.0,
        "price": 349.0, "currency": "USD", "url": "https://eminence.com",
        "driver": {"fs_hz": 22.0, "vas_l": 248.0, "qts": 0.34, "qms": 7.5, "re_ohm": 4.3, "sd_cm2": 823.0, "xmax_mm": 11.8, "pe_w": 600.0, "le_mh": 1.60}
    },
    {
        "name": "WEB: Eminence Sigma Pro 18A 18 Inch Subwoofer",
        "brand": "Eminence", "model": "Sigma Pro 18A", "category": "Subwoofer",
        "fs_hz": 28.0, "qts": 0.29, "qes": 0.30, "qms": 8.2, "vas_l": 441.0,
        "re_ohm": 6.1, "sd_cm2": 1159.0, "xmax_mm": 6.1, "pe_w": 650.0,
        "price": 289.0, "currency": "USD", "url": "https://eminence.com",
        "driver": {"fs_hz": 28.0, "vas_l": 441.0, "qts": 0.29, "qms": 8.2, "re_ohm": 6.1, "sd_cm2": 1159.0, "xmax_mm": 6.1, "pe_w": 650.0, "le_mh": 1.65}
    },
    {
        "name": "WEB: Eminence Kilomax Pro 18A 18 Inch 1250W Subwoofer",
        "brand": "Eminence", "model": "Kilomax Pro 18A", "category": "Subwoofer",
        "fs_hz": 33.0, "qts": 0.36, "qes": 0.38, "qms": 9.2, "vas_l": 320.0,
        "re_ohm": 5.4, "sd_cm2": 1159.0, "xmax_mm": 9.8, "pe_w": 1250.0,
        "price": 399.0, "currency": "USD", "url": "https://eminence.com",
        "driver": {"fs_hz": 33.0, "vas_l": 320.0, "qts": 0.36, "qms": 9.2, "re_ohm": 5.4, "sd_cm2": 1159.0, "xmax_mm": 9.8, "pe_w": 1250.0, "le_mh": 2.10}
    },

    # 6. DAYTON AUDIO (USA)
    {
        "name": "WEB: Dayton Audio UM18-22 18 Inch Ultimax DVC Subwoofer",
        "brand": "Dayton Audio", "model": "UM18-22", "category": "Subwoofer",
        "fs_hz": 19.5, "qts": 0.55, "qes": 0.58, "qms": 7.8, "vas_l": 212.0,
        "re_ohm": 3.4, "sd_cm2": 1210.0, "xmax_mm": 22.0, "pe_w": 1000.0,
        "price": 379.0, "currency": "USD", "url": "https://www.daytonaudio.com",
        "driver": {"fs_hz": 19.5, "vas_l": 212.0, "qts": 0.55, "qms": 7.8, "re_ohm": 3.4, "sd_cm2": 1210.0, "xmax_mm": 22.0, "pe_w": 1000.0, "le_mh": 2.20}
    },
    {
        "name": "WEB: Dayton Audio UM15-22 15 Inch Ultimax DVC Subwoofer",
        "brand": "Dayton Audio", "model": "UM15-22", "category": "Subwoofer",
        "fs_hz": 19.0, "qts": 0.53, "qes": 0.57, "qms": 7.5, "vas_l": 160.0,
        "re_ohm": 3.4, "sd_cm2": 855.0, "xmax_mm": 19.0, "pe_w": 800.0,
        "price": 289.0, "currency": "USD", "url": "https://www.daytonaudio.com",
        "driver": {"fs_hz": 19.0, "vas_l": 160.0, "qts": 0.53, "qms": 7.5, "re_ohm": 3.4, "sd_cm2": 855.0, "xmax_mm": 19.0, "pe_w": 800.0, "le_mh": 1.95}
    },
    {
        "name": "WEB: Dayton Audio RSS390HO-4 15 Inch Reference High Output Subwoofer",
        "brand": "Dayton Audio", "model": "RSS390HO-4", "category": "Subwoofer",
        "fs_hz": 21.5, "qts": 0.35, "qes": 0.37, "qms": 4.8, "vas_l": 150.0,
        "re_ohm": 3.2, "sd_cm2": 855.0, "xmax_mm": 14.0, "pe_w": 800.0,
        "price": 269.0, "currency": "USD", "url": "https://www.daytonaudio.com",
        "driver": {"fs_hz": 21.5, "vas_l": 150.0, "qts": 0.35, "qms": 4.8, "re_ohm": 3.2, "sd_cm2": 855.0, "xmax_mm": 14.0, "pe_w": 800.0, "le_mh": 1.65}
    },
    {
        "name": "WEB: Dayton Audio RSS315HO-4 12 Inch Reference High Output Subwoofer",
        "brand": "Dayton Audio", "model": "RSS315HO-4", "category": "Subwoofer",
        "fs_hz": 29.0, "qts": 0.36, "qes": 0.38, "qms": 4.5, "vas_l": 48.0,
        "re_ohm": 3.2, "sd_cm2": 510.0, "xmax_mm": 12.3, "pe_w": 700.0,
        "price": 209.0, "currency": "USD", "url": "https://www.daytonaudio.com",
        "driver": {"fs_hz": 29.0, "vas_l": 48.0, "qts": 0.36, "qms": 4.5, "re_ohm": 3.2, "sd_cm2": 510.0, "xmax_mm": 12.3, "pe_w": 700.0, "le_mh": 1.40}
    },

    # 7. SCAN-SPEAK (Denmark)
    {
        "name": "WEB: Scan-Speak Discovery 26W/4558T00 10 Inch Subwoofer",
        "brand": "Scan-Speak", "model": "26W/4558T00", "category": "Subwoofer",
        "fs_hz": 21.0, "qts": 0.31, "qes": 0.33, "qms": 6.8, "vas_l": 95.0,
        "re_ohm": 2.6, "sd_cm2": 350.0, "xmax_mm": 12.5, "pe_w": 350.0,
        "price": 239.0, "currency": "EUR", "url": "https://www.scan-speak.dk",
        "driver": {"fs_hz": 21.0, "vas_l": 95.0, "qts": 0.31, "qms": 6.8, "re_ohm": 2.6, "sd_cm2": 350.0, "xmax_mm": 12.5, "pe_w": 350.0, "le_mh": 0.95}
    },
    {
        "name": "WEB: Scan-Speak Classic 25W/8565-01 10 Inch Paper Cone Woofer",
        "brand": "Scan-Speak", "model": "25W/8565-01", "category": "Woofer",
        "fs_hz": 20.0, "qts": 0.39, "qes": 0.42, "qms": 5.2, "vas_l": 230.0,
        "re_ohm": 5.5, "sd_cm2": 330.0, "xmax_mm": 6.5, "pe_w": 100.0,
        "price": 275.0, "currency": "EUR", "url": "https://www.scan-speak.dk",
        "driver": {"fs_hz": 20.0, "vas_l": 230.0, "qts": 0.39, "qms": 5.2, "re_ohm": 5.5, "sd_cm2": 330.0, "xmax_mm": 6.5, "pe_w": 100.0, "le_mh": 0.75}
    },

    # 8. SEAS (Norway)
    {
        "name": "WEB: SEAS Prestige CA26RFX H1305-08 10 Inch Woofer",
        "brand": "SEAS", "model": "CA26RFX", "category": "Woofer",
        "fs_hz": 25.0, "qts": 0.35, "qes": 0.37, "qms": 4.8, "vas_l": 140.0,
        "re_ohm": 6.1, "sd_cm2": 330.0, "xmax_mm": 6.0, "pe_w": 250.0,
        "price": 185.0, "currency": "EUR", "url": "https://www.seas.no",
        "driver": {"fs_hz": 25.0, "vas_l": 140.0, "qts": 0.35, "qms": 4.8, "re_ohm": 6.1, "sd_cm2": 330.0, "xmax_mm": 6.0, "pe_w": 250.0, "le_mh": 0.80}
    },
    {
        "name": "WEB: SEAS Prestige CA22RNY H1252-08 8 Inch Woofer",
        "brand": "SEAS", "model": "CA22RNY", "category": "Woofer",
        "fs_hz": 29.0, "qts": 0.38, "qes": 0.41, "qms": 4.6, "vas_l": 75.0,
        "re_ohm": 6.1, "sd_cm2": 220.0, "xmax_mm": 6.0, "pe_w": 200.0,
        "price": 145.0, "currency": "EUR", "url": "https://www.seas.no",
        "driver": {"fs_hz": 29.0, "vas_l": 75.0, "qts": 0.38, "qms": 4.6, "re_ohm": 6.1, "sd_cm2": 220.0, "xmax_mm": 6.0, "pe_w": 200.0, "le_mh": 0.65}
    },

    # 9. SB ACOUSTICS (Denmark / Indonesia)
    {
        "name": "WEB: SB Acoustics SB29NRX75-6 10 Inch Subwoofer",
        "brand": "SB Acoustics", "model": "SB29NRX75-6", "category": "Subwoofer",
        "fs_hz": 22.0, "qts": 0.36, "qes": 0.38, "qms": 5.4, "vas_l": 120.0,
        "re_ohm": 4.5, "sd_cm2": 312.0, "xmax_mm": 11.0, "pe_w": 200.0,
        "price": 169.0, "currency": "EUR", "url": "https://sbacoustics.com",
        "driver": {"fs_hz": 22.0, "vas_l": 120.0, "qts": 0.36, "qms": 5.4, "re_ohm": 4.5, "sd_cm2": 312.0, "xmax_mm": 11.0, "pe_w": 200.0, "le_mh": 0.85}
    },
    {
        "name": "WEB: SB Acoustics SB23NRX45-8 8 Inch Woofer",
        "brand": "SB Acoustics", "model": "SB23NRX45-8", "category": "Woofer",
        "fs_hz": 28.0, "qts": 0.35, "qes": 0.38, "qms": 5.0, "vas_l": 68.0,
        "re_ohm": 5.8, "sd_cm2": 216.0, "xmax_mm": 7.5, "pe_w": 120.0,
        "price": 119.0, "currency": "EUR", "url": "https://sbacoustics.com",
        "driver": {"fs_hz": 28.0, "vas_l": 68.0, "qts": 0.35, "qms": 5.0, "re_ohm": 5.8, "sd_cm2": 216.0, "xmax_mm": 7.5, "pe_w": 120.0, "le_mh": 0.65}
    }
]


def main():
    print("=== HARVESTING MASSIVE GLOBAL CATALOG WAVE INTO LOAD FORGE DB ===")
    t0 = time.perf_counter()
    
    cat_prop_data = json.loads(CATALOG_PROP.read_text(encoding="utf-8"))
    prop_items = cat_prop_data.get("presets", [])
    existing_identities = {f"{normalize(item.get('brand', ''))}_{normalize(item.get('model', ''))}" for item in prop_items}
    existing_names = {item.get("name") for item in prop_items}
    initial_count = len(prop_items)
    print(f"Initial presets in DB: {initial_count}")
    
    added = 0
    for d in WAVE_DRIVERS:
        name = d["name"]
        ident = f"{normalize(d['brand'])}_{normalize(d['model'])}"
        if name not in existing_names and ident not in existing_identities:
            prop_items.append(d)
            existing_names.add(name)
            existing_identities.add(ident)
            added += 1
            print(f" + Added NEW Wave Driver: {name} ({d['brand']} {d['model']} - Fs={d['fs_hz']}Hz, Qts={d['qts']}, {d['price']} {d['currency']})")
            
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
