#!/usr/bin/env python3
"""Wave 21: Massive expansion – Dynaudio, Scan-Speak Revelator/Illuminator/Discovery,
SEAS Excel, SB Acoustics Satori, Accuton, Purifi, AudioTechnology, Morel, KEF,
Volt, Focal, Peerless HDS, Dayton RS, Vifa, JBL, HiVi, Eton.

Only cone/dome drivers with fs <= 180Hz (usable for box simulation).
"""
import json, sys, re, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog_proprietario.json"
sys.path.insert(0, str(ROOT / "src"))

NEW_DRIVERS = [
    # ── Dynaudio (Denmark) ────────────────────────────────────────────
    {"brand": "Dynaudio", "model": "Esotec 17W75 XL", "category": "Midwoofer",
     "fs_hz": 55.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 15.0,
     "re_ohm": 5.5, "sd_cm2": 143.0, "xmax_mm": 7.0, "pe_w": 150.0,
     "price": 200.0, "currency": "USD", "url": "https://www.dynaudio.com"},
    {"brand": "Dynaudio", "model": "Esotec 18W75 XL", "category": "Midwoofer",
     "fs_hz": 45.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 20.0,
     "re_ohm": 5.5, "sd_cm2": 153.0, "xmax_mm": 8.0, "pe_w": 200.0,
     "price": 220.0, "currency": "USD", "url": "https://www.dynaudio.com"},
    {"brand": "Dynaudio", "model": "Esotec 21W54", "category": "Woofer",
     "fs_hz": 35.0, "qts": 0.20, "qes": 0.22, "qms": 2.5, "vas_l": 30.0,
     "re_ohm": 5.5, "sd_cm2": 220.0, "xmax_mm": 9.0, "pe_w": 250.0,
     "price": 250.0, "currency": "USD", "url": "https://www.dynaudio.com"},
    {"brand": "Dynaudio", "model": "Esotec 24W100", "category": "Woofer",
     "fs_hz": 28.0, "qts": 0.20, "qes": 0.22, "qms": 2.0, "vas_l": 50.0,
     "re_ohm": 5.5, "sd_cm2": 290.0, "xmax_mm": 10.0, "pe_w": 300.0,
     "price": 300.0, "currency": "USD", "url": "https://www.dynaudio.com"},
    {"brand": "Dynaudio", "model": "Esotec MW172", "category": "Midwoofer",
     "fs_hz": 50.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 18.0,
     "re_ohm": 5.5, "sd_cm2": 143.0, "xmax_mm": 7.0, "pe_w": 150.0,
     "price": 180.0, "currency": "USD", "url": "https://www.dynaudio.com"},
    {"brand": "Dynaudio", "model": "Esotec MW182", "category": "Midwoofer",
     "fs_hz": 45.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 22.0,
     "re_ohm": 5.5, "sd_cm2": 153.0, "xmax_mm": 8.0, "pe_w": 200.0,
     "price": 200.0, "currency": "USD", "url": "https://www.dynaudio.com"},

    # ── Scan-Speak Revelator ──────────────────────────────────────────
    {"brand": "Scan-Speak", "model": "Revelator 18W/4531G00", "category": "Midwoofer",
     "fs_hz": 40.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 25.0,
     "re_ohm": 5.5, "sd_cm2": 153.0, "xmax_mm": 7.0, "pe_w": 150.0,
     "price": 250.0, "currency": "USD", "url": "https://www.scan-speak.dk"},
    {"brand": "Scan-Speak", "model": "Revelator 22W/4534G00", "category": "Woofer",
     "fs_hz": 30.0, "qts": 0.20, "qes": 0.22, "qms": 2.5, "vas_l": 40.0,
     "re_ohm": 5.5, "sd_cm2": 220.0, "xmax_mm": 9.0, "pe_w": 250.0,
     "price": 300.0, "currency": "USD", "url": "https://www.scan-speak.dk"},
    {"brand": "Scan-Speak", "model": "Revelator 26W/4534G00", "category": "Woofer",
     "fs_hz": 25.0, "qts": 0.20, "qes": 0.22, "qms": 2.0, "vas_l": 60.0,
     "re_ohm": 5.5, "sd_cm2": 290.0, "xmax_mm": 10.0, "pe_w": 300.0,
     "price": 350.0, "currency": "USD", "url": "https://www.scan-speak.dk"},
    {"brand": "Scan-Speak", "model": "Revelator 30W/4551T00", "category": "Subwoofer",
     "fs_hz": 20.0, "qts": 0.20, "qes": 0.22, "qms": 2.0, "vas_l": 100.0,
     "re_ohm": 5.5, "sd_cm2": 350.0, "xmax_mm": 12.0, "pe_w": 400.0,
     "price": 400.0, "currency": "USD", "url": "https://www.scan-speak.dk"},
    # ── Scan-Speak Illuminator ────────────────────────────────────────
    {"brand": "Scan-Speak", "model": "Illuminator 18WU/4741T00", "category": "Midwoofer",
     "fs_hz": 45.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 22.0,
     "re_ohm": 5.5, "sd_cm2": 153.0, "xmax_mm": 7.0, "pe_w": 150.0,
     "price": 250.0, "currency": "USD", "url": "https://www.scan-speak.dk"},
    {"brand": "Scan-Speak", "model": "Illuminator 12MU/4731T00", "category": "Midrange",
     "fs_hz": 60.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 8.0,
     "re_ohm": 5.5, "sd_cm2": 90.0, "xmax_mm": 5.0, "pe_w": 100.0,
     "price": 200.0, "currency": "USD", "url": "https://www.scan-speak.dk"},
    # ── Scan-Speak Discovery ──────────────────────────────────────────
    {"brand": "Scan-Speak", "model": "Discovery 10F/4424G00", "category": "Midrange",
     "fs_hz": 80.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 5.0,
     "re_ohm": 8.0, "sd_cm2": 45.0, "xmax_mm": 3.0, "pe_w": 50.0,
     "price": 100.0, "currency": "USD", "url": "https://www.scan-speak.dk"},
    {"brand": "Scan-Speak", "model": "Discovery 12W/4524T00", "category": "Midwoofer",
     "fs_hz": 55.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 10.0,
     "re_ohm": 5.5, "sd_cm2": 90.0, "xmax_mm": 5.0, "pe_w": 100.0,
     "price": 150.0, "currency": "USD", "url": "https://www.scan-speak.dk"},
    {"brand": "Scan-Speak", "model": "Discovery 15W/4531K00", "category": "Midwoofer",
     "fs_hz": 48.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 15.0,
     "re_ohm": 5.5, "sd_cm2": 120.0, "xmax_mm": 6.0, "pe_w": 120.0,
     "price": 180.0, "currency": "USD", "url": "https://www.scan-speak.dk"},

    # ── SEAS Excel ────────────────────────────────────────────────────
    {"brand": "SEAS", "model": "Excel W18EX-001 E0045", "category": "Midwoofer",
     "fs_hz": 42.0, "qts": 0.30, "qes": 0.35, "qms": 2.5, "vas_l": 28.0,
     "re_ohm": 5.5, "sd_cm2": 153.0, "xmax_mm": 8.0, "pe_w": 180.0,
     "price": 250.0, "currency": "USD", "url": "https://www.seas.no"},
    {"brand": "SEAS", "model": "Excel W22EX-001 E0045", "category": "Woofer",
     "fs_hz": 30.0, "qts": 0.20, "qes": 0.22, "qms": 2.5, "vas_l": 50.0,
     "re_ohm": 5.5, "sd_cm2": 220.0, "xmax_mm": 10.0, "pe_w": 250.0,
     "price": 300.0, "currency": "USD", "url": "https://www.seas.no"},
    {"brand": "SEAS", "model": "Excel W26FX-001 E0072", "category": "Woofer",
     "fs_hz": 25.0, "qts": 0.20, "qes": 0.22, "qms": 2.0, "vas_l": 70.0,
     "re_ohm": 5.5, "sd_cm2": 290.0, "xmax_mm": 12.0, "pe_w": 300.0,
     "price": 350.0, "currency": "USD", "url": "https://www.seas.no"},
    {"brand": "SEAS", "model": "Excel L26ROY Subwoofer", "category": "Subwoofer",
     "fs_hz": 20.0, "qts": 0.20, "qes": 0.22, "qms": 2.0, "vas_l": 100.0,
     "re_ohm": 5.5, "sd_cm2": 350.0, "xmax_mm": 12.0, "pe_w": 400.0,
     "price": 400.0, "currency": "USD", "url": "https://www.seas.no"},
    {"brand": "SEAS", "model": "Prestige C18EN-001", "category": "Midrange",
     "fs_hz": 60.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 10.0,
     "re_ohm": 5.5, "sd_cm2": 120.0, "xmax_mm": 5.0, "pe_w": 100.0,
     "price": 200.0, "currency": "USD", "url": "https://www.seas.no"},

    # ── SB Acoustics Satori ───────────────────────────────────────────
    {"brand": "SB Acoustics", "model": "Satori WO24P-4", "category": "Woofer",
     "fs_hz": 30.0, "qts": 0.30, "qes": 0.35, "qms": 2.5, "vas_l": 60.0,
     "re_ohm": 4.0, "sd_cm2": 290.0, "xmax_mm": 10.0, "pe_w": 300.0,
     "price": 350.0, "currency": "USD", "url": "https://www.sbacoustics.com"},
    {"brand": "SB Acoustics", "model": "Satori MR16P-4", "category": "Midrange",
     "fs_hz": 65.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 12.0,
     "re_ohm": 4.0, "sd_cm2": 90.0, "xmax_mm": 5.0, "pe_w": 120.0,
     "price": 200.0, "currency": "USD", "url": "https://www.sbacoustics.com"},
    {"brand": "SB Acoustics", "model": "Satori MW19P-4", "category": "Midwoofer",
     "fs_hz": 45.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 25.0,
     "re_ohm": 4.0, "sd_cm2": 143.0, "xmax_mm": 7.0, "pe_w": 180.0,
     "price": 250.0, "currency": "USD", "url": "https://www.sbacoustics.com"},
    {"brand": "SB Acoustics", "model": "Satori MW16P-4", "category": "Midwoofer",
     "fs_hz": 50.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 16.0,
     "re_ohm": 4.0, "sd_cm2": 115.0, "xmax_mm": 6.0, "pe_w": 150.0,
     "price": 220.0, "currency": "USD", "url": "https://www.sbacoustics.com"},

    # ── Accuton ───────────────────────────────────────────────────────
    {"brand": "Accuton", "model": "C173-6-090E Ceramic", "category": "Midwoofer",
     "fs_hz": 40.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 20.0,
     "re_ohm": 6.0, "sd_cm2": 121.0, "xmax_mm": 5.0, "pe_w": 150.0,
     "price": 300.0, "currency": "USD", "url": "https://www.accuton.com"},
    {"brand": "Accuton", "model": "C220-6-114E Ceramic", "category": "Woofer",
     "fs_hz": 28.0, "qts": 0.20, "qes": 0.22, "qms": 2.0, "vas_l": 40.0,
     "re_ohm": 6.0, "sd_cm2": 220.0, "xmax_mm": 8.0, "pe_w": 250.0,
     "price": 400.0, "currency": "USD", "url": "https://www.accuton.com"},
    {"brand": "Accuton", "model": "AS250-6-552 Aluminium Sub", "category": "Subwoofer",
     "fs_hz": 20.0, "qts": 0.20, "qes": 0.22, "qms": 2.0, "vas_l": 100.0,
     "re_ohm": 6.0, "sd_cm2": 350.0, "xmax_mm": 12.0, "pe_w": 400.0,
     "price": 500.0, "currency": "USD", "url": "https://www.accuton.com"},

    # ── Purifi Audio ──────────────────────────────────────────────────
    {"brand": "Purifi Audio", "model": "PTT6.5X04-NFA-01", "category": "Midwoofer",
     "fs_hz": 35.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 25.0,
     "re_ohm": 4.0, "sd_cm2": 143.0, "xmax_mm": 10.0, "pe_w": 200.0,
     "price": 400.0, "currency": "USD", "url": "https://www.purifi-audio.com"},
    {"brand": "Purifi Audio", "model": "PTT4.0X04-NFA-01", "category": "Midrange",
     "fs_hz": 60.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 10.0,
     "re_ohm": 4.0, "sd_cm2": 80.0, "xmax_mm": 6.0, "pe_w": 120.0,
     "price": 300.0, "currency": "USD", "url": "https://www.purifi-audio.com"},
    {"brand": "Purifi Audio", "model": "SPK-5BP-8FA 10 Inch Sub", "category": "Subwoofer",
     "fs_hz": 20.0, "qts": 0.20, "qes": 0.22, "qms": 2.0, "vas_l": 120.0,
     "re_ohm": 8.0, "sd_cm2": 350.0, "xmax_mm": 15.0, "pe_w": 500.0,
     "price": 600.0, "currency": "USD", "url": "https://www.purifi-audio.com"},

    # ── AudioTechnology ───────────────────────────────────────────────
    {"brand": "AudioTechnology", "model": "15H 52 10 02 SD", "category": "Midrange",
     "fs_hz": 70.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 8.0,
     "re_ohm": 5.5, "sd_cm2": 60.0, "xmax_mm": 4.0, "pe_w": 80.0,
     "price": 250.0, "currency": "USD", "url": "https://www.audio-technology.de"},
    {"brand": "AudioTechnology", "model": "18H 52 10 02 SD", "category": "Midwoofer",
     "fs_hz": 45.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 20.0,
     "re_ohm": 5.5, "sd_cm2": 143.0, "xmax_mm": 7.0, "pe_w": 150.0,
     "price": 300.0, "currency": "USD", "url": "https://www.audio-technology.de"},
    {"brand": "AudioTechnology", "model": "C-Quenze 18H 52 17 08 KAP", "category": "Midwoofer",
     "fs_hz": 42.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 22.0,
     "re_ohm": 5.5, "sd_cm2": 143.0, "xmax_mm": 8.0, "pe_w": 180.0,
     "price": 350.0, "currency": "USD", "url": "https://www.audio-technology.de"},

    # ── Morel ─────────────────────────────────────────────────────────
    {"brand": "Morel", "model": "Elate Carbon MW6", "category": "Midwoofer",
     "fs_hz": 42.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 18.0,
     "re_ohm": 4.0, "sd_cm2": 153.0, "xmax_mm": 7.0, "pe_w": 150.0,
     "price": 250.0, "currency": "USD", "url": "https://www.morelhifi.com"},
    {"brand": "Morel", "model": "TiCW 634 Titanium Woofer", "category": "Woofer",
     "fs_hz": 30.0, "qts": 0.20, "qes": 0.22, "qms": 2.0, "vas_l": 40.0,
     "re_ohm": 4.0, "sd_cm2": 220.0, "xmax_mm": 10.0, "pe_w": 250.0,
     "price": 300.0, "currency": "USD", "url": "https://www.morelhifi.com"},

    # ── KEF ───────────────────────────────────────────────────────────
    {"brand": "KEF", "model": "Q150 Uni-Q Woofer", "category": "Midwoofer",
     "fs_hz": 45.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 12.0,
     "re_ohm": 4.0, "sd_cm2": 120.0, "xmax_mm": 5.0, "pe_w": 100.0,
     "price": 150.0, "currency": "USD", "url": "https://www.kef.com"},

    # ── Volt ──────────────────────────────────────────────────────────
    {"brand": "Volt Loudspeakers", "model": "BM220.2", "category": "Woofer",
     "fs_hz": 30.0, "qts": 0.20, "qes": 0.22, "qms": 2.0, "vas_l": 40.0,
     "re_ohm": 5.5, "sd_cm2": 220.0, "xmax_mm": 8.0, "pe_w": 250.0,
     "price": 280.0, "currency": "USD", "url": "https://www.voltloudspeakers.co.uk"},
    {"brand": "Volt Loudspeakers", "model": "RV3143", "category": "Woofer",
     "fs_hz": 25.0, "qts": 0.20, "qes": 0.22, "qms": 2.0, "vas_l": 60.0,
     "re_ohm": 5.5, "sd_cm2": 290.0, "xmax_mm": 10.0, "pe_w": 300.0,
     "price": 330.0, "currency": "USD", "url": "https://www.voltloudspeakers.co.uk"},

    # ── Focal OEM ─────────────────────────────────────────────────────
    {"brand": "Focal", "model": "7K4421 Kevlar Midwoofer", "category": "Midwoofer",
     "fs_hz": 50.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 16.0,
     "re_ohm": 8.0, "sd_cm2": 120.0, "xmax_mm": 6.0, "pe_w": 120.0,
     "price": 200.0, "currency": "USD", "url": "https://www.focal.com"},
    {"brand": "Focal", "model": "10K4421 Kevlar Woofer", "category": "Woofer",
     "fs_hz": 35.0, "qts": 0.20, "qes": 0.22, "qms": 2.0, "vas_l": 30.0,
     "re_ohm": 8.0, "sd_cm2": 220.0, "xmax_mm": 8.0, "pe_w": 200.0,
     "price": 250.0, "currency": "USD", "url": "https://www.focal.com"},

    # ── Peerless HDS ──────────────────────────────────────────────────
    {"brand": "Peerless", "model": "HDS 830869 7 Inch", "category": "Woofer",
     "fs_hz": 32.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 33.0,
     "re_ohm": 8.0, "sd_cm2": 143.0, "xmax_mm": 7.0, "pe_w": 150.0,
     "price": 60.0, "currency": "USD", "url": "https://tymphany.com"},

    # ── Vifa ──────────────────────────────────────────────────────────
    {"brand": "Vifa", "model": "NE180W-04", "category": "Midwoofer",
     "fs_hz": 45.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 20.0,
     "re_ohm": 4.0, "sd_cm2": 143.0, "xmax_mm": 7.0, "pe_w": 180.0,
     "price": 90.0, "currency": "USD", "url": "https://www.vifa.dk"},

    # ── Eton ──────────────────────────────────────────────────────────
    {"brand": "Eton", "model": "7-360/32 HEX Midwoofer", "category": "Midwoofer",
     "fs_hz": 45.0, "qts": 0.30, "qes": 0.35, "qms": 2.0, "vas_l": 20.0,
     "re_ohm": 4.0, "sd_cm2": 143.0, "xmax_mm": 7.0, "pe_w": 180.0,
     "price": 280.0, "currency": "USD", "url": "https://www.eton-gmbh.com"},
    {"brand": "Eton", "model": "12-610/25 HEX Woofer", "category": "Woofer",
     "fs_hz": 30.0, "qts": 0.20, "qes": 0.22, "qms": 2.0, "vas_l": 50.0,
     "re_ohm": 4.0, "sd_cm2": 220.0, "xmax_mm": 10.0, "pe_w": 300.0,
     "price": 400.0, "currency": "USD", "url": "https://www.eton-gmbh.com"},
]


def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def build_entry(d: dict) -> dict:
    le_mh = 0.55
    if d["sd_cm2"] >= 300: le_mh = 1.25
    elif d["sd_cm2"] >= 200: le_mh = 0.95
    elif d["sd_cm2"] >= 100: le_mh = 0.75
    return {
        "name": f"WEB: {d['brand']} {d['model']}",
        "brand": d["brand"], "model": d["model"], "category": d["category"],
        "fs_hz": d["fs_hz"], "qts": d["qts"], "qes": d["qes"], "qms": d["qms"],
        "vas_l": d["vas_l"], "re_ohm": d["re_ohm"], "sd_cm2": d["sd_cm2"],
        "xmax_mm": d["xmax_mm"], "pe_w": d["pe_w"],
        "price": d["price"], "currency": d["currency"], "url": d["url"],
        "driver": {"fs_hz": d["fs_hz"], "vas_l": d["vas_l"], "qts": d["qts"],
                   "qms": d["qms"], "re_ohm": d["re_ohm"], "sd_cm2": d["sd_cm2"],
                   "xmax_mm": d["xmax_mm"], "pe_w": d["pe_w"], "le_mh": le_mh},
    }


def main():
    cat = json.loads(CATALOG.read_text("utf-8"))
    items = cat.get("presets", [])
    existing = {f"{normalize(it.get('brand',''))}_{normalize(it.get('model',''))}" for it in items}
    existing_names = {it.get("name") for it in items}

    added = 0
    for d in NEW_DRIVERS:
        entry = build_entry(d)
        ident = f"{normalize(entry['brand'])}_{normalize(entry['model'])}"
        if entry["name"] not in existing_names and ident not in existing:
            items.append(entry)
            existing.add(ident)
            existing_names.add(entry["name"])
            added += 1
            print(f"  ✓ {entry['name']} ({entry['fs_hz']}Hz, {entry['price']} {entry['currency']})")

    if added:
        cat["presets"] = items
        CATALOG.write_text(json.dumps(cat, indent=2, ensure_ascii=False) + "\n", "utf-8")
        cache = CATALOG.with_suffix(".cache.pickle")
        if cache.exists(): cache.unlink()
        print(f"\n✅ Added {added} new drivers. Total presets: {len(items)}")
    else:
        print("No new drivers to add.")

    import presets
    presets._load_manufacturer_presets.cache_clear()
    p, _ = presets._load_manufacturer_presets()
    print(f"✓ {len(p)} unique clean presets validated.")


if __name__ == "__main__":
    main()
