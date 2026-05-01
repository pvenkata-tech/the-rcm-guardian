"""
Generate watermarked synthetic billing-style PDFs + PNG rasters (no real PHI).

For each NN in 01–05, synthetic_eob_NN.pdf and synthetic_eob_NN.png are **different
documents** (not raster vs vector of the same page): distinct text, layout, and keys.

HIPAA note: fictional content for development and demos only.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

SAMPLES_DIR = Path(__file__).resolve().parent
GENERATED_DIR = SAMPLES_DIR / "generated"


@dataclass(frozen=True)
class Variant:
    """One rendered page (PDF or PNG only — not both from the same source)."""

    asset_key: str
    banner: str
    body: str
    page_size: tuple[float, float]
    banner_rect: tuple[float, float, float, float]
    text_rect: tuple[float, float, float, float]
    banner_stroke: tuple[float, float, float]
    banner_fill: tuple[float, float, float]
    body_fontsize: float


@dataclass(frozen=True)
class PdfPngPair:
    """Same ordinal NN; PDF and PNG hold different synthetic content."""

    suffix: str
    pdf: Variant
    png: Variant


PAIRS: tuple[PdfPngPair, ...] = (
    PdfPngPair(
        suffix="01",
        pdf=Variant(
            asset_key="RCM-SYNTH-01-PDF-9A2B47E1F0C8",
            banner="NOT REAL PHI — SYNTHETIC EOB (PDF) — outpatient / lab",
            body="""
=== SYNTHETIC EXPLANATION OF BENEFITS — PDF VARIANT 01 (NON-PHI) ===
Payer: FAUX HEALTH DEMO CARRIER
Group / plan: PLAN-SYNTH-001   Claim: CLM-A1-DEADBEEF

Member (fictional): SYNTHETIC PATIENT-ALPHA
Member ID: 999-ZZ-TEST-001     DOB (example): 1980-06-15

Service from / through: 2099-01-02 — 2099-01-02    POS: 11 (office)

Line items (fabricated):
  99213  Established visit      Billed 150.00   Allowed 98.00   You pay 20.00
  80053  Comprehensive panel     Billed 85.00    Allowed 62.00   You pay 10.00
  93000  Cardiography tracing   Billed 55.00    Allowed 44.00   You pay 5.00

Provider: DR. IMAGINE SAMPLE MD    NPI 1999999999
DX (example): Z00.00

Totals — Billed 290.00 | Allowed 204.00 | Your responsibility 35.00
This PDF variant is unique from the paired PNG for ordinal 01.
""".strip(),
            page_size=(612, 792),
            banner_rect=(36, 36, 576, 78),
            text_rect=(48, 92, 564, 756),
            banner_stroke=(0.75, 0.15, 0.15),
            banner_fill=(0.97, 0.88, 0.88),
            body_fontsize=8.8,
        ),
        png=Variant(
            asset_key="RCM-SYNTH-01-PNG-4D91E2A87B30",
            banner="NOT REAL PHI — SYNTHETIC PHARMACY REMITTANCE (PNG) — pair 01",
            body="""
SYNTHETIC PHARMACY REMITTANCE — PNG VARIANT 01 (NON-PHI)
========================================================
PBM (fictional): MOCK RX BENEFITS ADMIN

Member: SYNTHETIC PATIENT-ALPHA-B   Card: RX-TWIN-998877
Fill date: 2099-01-03   Store NPI 1777777771 (fake)

NDC / drug (invented):
  00093-7180  Generic metformin 500mg   Qty 90   Billed 42.00  Paid 8.40  Copay 5.00
  59762-5020  Lisinopril 10mg            Qty 30   Billed 18.00  Paid 3.20  Copay 1.00

Prescriber: DR. DOSE SAMPLE MD   NPI 1666666662
BIN/PCN (example): 610020 / MOCK1

This PNG variant differs from synthetic_eob_01.pdf (different service class).
""".strip(),
            page_size=(612, 792),
            banner_rect=(36, 34, 576, 76),
            text_rect=(46, 88, 566, 748),
            banner_stroke=(0.15, 0.45, 0.55),
            banner_fill=(0.88, 0.96, 0.98),
            body_fontsize=9.0,
        ),
    ),
    PdfPngPair(
        suffix="02",
        pdf=Variant(
            asset_key="RCM-SYNTH-02-PDF-3D8C1F6A4E90",
            banner="NOT REAL PHI — SYNTHETIC CLAIM SUMMARY (PDF) — urgent care",
            body="""
SYNTHETIC CLAIM SUMMARY — PDF VARIANT 02 (NON-PHI)
==================================================
Carrier: MOCK REGIONAL PAY ALLIANCE (fictional)
Claim control #: B2-88-CAFE-4242

Subscriber: DEMO SUBSCRIBER-BRUNO (fabricated)
ID: BRK-TEST-7700-K

DOS 2099-02-14    Facility: IMAGINARY URGENT CARE WEST

Charges:
  99204  New patient detailed visit … Billed 285.00 Allowed 210.00 Coins 42.00
  87635  Infectious agent RNA …       Billed 125.00 Allowed 98.00  Coins 19.60

Attending: NP PATTERN SAMPLE        NPI 1888888888

Remark codes (example): CO-45, PR-2
Unique PDF stub 02 — PNG partner uses PT narrative.
""".strip(),
            page_size=(612, 792),
            banner_rect=(40, 32, 572, 70),
            text_rect=(52, 82, 560, 740),
            banner_stroke=(0.12, 0.35, 0.72),
            banner_fill=(0.88, 0.93, 0.99),
            body_fontsize=8.4,
        ),
        png=Variant(
            asset_key="RCM-SYNTH-02-PNG-82ACF0D15E44",
            banner="NOT REAL PHI — SYNTHETIC PT PLAN OF CARE (PNG) — pair 02",
            body="""
SYNTHETIC PHYSICAL THERAPY NOTICE — PNG VARIANT 02 (NON-PHI)
============================================================
Clinic (fictional): IMAGINARY REHAB EAST
Auth session ref: PT-AUTH-2200-ZZ

Patient: SYNTHETIC PATIENT-BRUNO-RX
Visits auth: 12   Used: 3   Remaining: 9

Per-visit charge (fabricated):
  97110  Therapeutic exercise   Billed 95.00  Allowed 72.00  Coins 14.40
  97140  Manual therapy       Billed 85.00  Allowed 65.00  Coins 13.00
  G0283  E-stim unattended    Billed 22.00  Allowed 15.00  Coins 3.00

PT: LICENSE STUB PT   NPI 1555555510
Goal codes (example): reduced LBP, improved ROM.

PNG-only content — not a raster of PDF 02.
""".strip(),
            page_size=(612, 792),
            banner_rect=(34, 38, 578, 80),
            text_rect=(48, 90, 564, 750),
            banner_stroke=(0.35, 0.5, 0.12),
            banner_fill=(0.93, 0.98, 0.9),
            body_fontsize=8.6,
        ),
    ),
    PdfPngPair(
        suffix="03",
        pdf=Variant(
            asset_key="RCM-SYNTH-03-PDF-7E41B2D9C5A3",
            banner="NOT REAL PHI — SYNTHETIC ASC STATEMENT (PDF) — surgery",
            body="""
=== SYNTHETIC AMBULATORY SURGERY — PDF VARIANT 03 (NON-PHI) ===
Plan: ILLUSTRATION PPO GOLD (not a real product)
Claim ID: ASC-C3-00FE-00DC

Patient (fabricated): SYNTHETIC PATIENT-GAMMA

Surgical lines:
  66984  Cataract w/ IOL           Billed 3200.00  Allowed 2100.00  Patient 315.00
  00142  Anesthesia cataract       Billed 650.00   Allowed 520.00   Patient 78.00

Surgeon: DR. MOCK SURGEON         NPI 1777777777
DX: H25.11

PDF ambulatory bundle — paired PNG is lab requisition style.
""".strip(),
            page_size=(612, 792),
            banner_rect=(36, 40, 576, 86),
            text_rect=(48, 98, 564, 748),
            banner_stroke=(0.1, 0.55, 0.25),
            banner_fill=(0.9, 0.98, 0.92),
            body_fontsize=8.8,
        ),
        png=Variant(
            asset_key="RCM-SYNTH-03-PNG-19FE66AA7301",
            banner="NOT REAL PHI — SYNTHETIC MOLECULAR LAB REQ (PNG) — pair 03",
            body="""
SYNTHETIC MOLECULAR LAB REQUISITION — PNG VARIANT 03 (NON-PHI)
==============================================================
Lab network (fictional): MOCK GENOMICS REF LAB
Requisition: LAB-REQ-C3-41414141

Patient: SYNTHETIC PATIENT-GAMMA-LAB
Specimen: blood     Collection: 2099-03-05

Test codes (invented):
  81479  Unlisted molecular procedure    Billed 2400.00  Not covered example
  81265  Gene variant panel stub         Billed 980.00   Allowed 720.00 Patient 144.00

Ordering MD: DR. HELIX SAMPLE    NPI 1444444403
ICD-10 pointers: R68.89 (example only)

Distinct from ASC PDF 03 — different financial narrative.
""".strip(),
            page_size=(612, 792),
            banner_rect=(30, 36, 582, 74),
            text_rect=(42, 84, 570, 752),
            banner_stroke=(0.55, 0.25, 0.1),
            banner_fill=(0.98, 0.93, 0.88),
            body_fontsize=8.5,
        ),
    ),
    PdfPngPair(
        suffix="04",
        pdf=Variant(
            asset_key="RCM-SYNTH-04-PDF-F1A6C8E042BD",
            banner="NOT REAL PHI — SYNTHETIC DME SUMMARY (PDF) — rental",
            body="""
SYNTHETIC DME EXPLANATION — PDF VARIANT 04 (NON-PHI)
=====================================================
Payer: FAUX DURABLE MED BENEFITS (fictional plan)
Beneficiary: SYNTHETIC PATIENT-DELTA   Policy DME-TEST-44012

Equipment:
  E0601  CPAP rental month 1     Billed 180.00   Allowed 135.00   You 27.00
  A7030  CPAP mask               Billed 95.00    Allowed 72.00    You 14.40

Supplier: SAMPLE MEDICAL SUPPLY LLC (fabricated)

DME PDF — partner PNG is home-health authorization.
""".strip(),
            page_size=(612, 792),
            banner_rect=(32, 36, 580, 74),
            text_rect=(44, 86, 568, 752),
            banner_stroke=(0.45, 0.2, 0.65),
            banner_fill=(0.94, 0.9, 0.98),
            body_fontsize=9.0,
        ),
        png=Variant(
            asset_key="RCM-SYNTH-04-PNG-C0B8132D9A7E",
            banner="NOT REAL PHI — SYNTHETIC HOME HEALTH AUTH (PNG) — pair 04",
            body="""
SYNTHETIC HOME HEALTH AUTHORIZATION — PNG VARIANT 04 (NON-PHI)
==============================================================
Agency (fictional): IMAGINARY HOME CARE CO
Auth #: HH-AUTH-D4-55667788

Patient: SYNTHETIC PATIENT-DELTA-HH
Cert period (example): 2099-04-01 — 2099-06-30   Skilled nursing hours: 8/wk

Visit types (fabricated):
  G0299  SN visit               Billed 175.00  Allowed 135.00  Patient 27.00
  G0300  SN RN eval             Billed 220.00  Allowed 180.00  Patient 36.00
  T1023  Care coordination      Billed 95.00   Allowed 72.00   Patient 14.40

RN case manager: R.N. STUB CASE   NPI 1333333304

Not the DME PDF — separate benefit category for testing.
""".strip(),
            page_size=(612, 792),
            banner_rect=(36, 32, 576, 72),
            text_rect=(48, 82, 564, 748),
            banner_stroke=(0.25, 0.35, 0.65),
            banner_fill=(0.92, 0.94, 1.0),
            body_fontsize=8.4,
        ),
    ),
    PdfPngPair(
        suffix="05",
        pdf=Variant(
            asset_key="RCM-SYNTH-05-PDF-55AB901E7F22",
            banner="NOT REAL PHI — SYNTHETIC RADIOLOGY EOB (PDF) — landscape",
            body="""
SYNTHETIC RADIOLOGY BENEFITS — PDF VARIANT 05 (NON-PHI) — landscape sheet
========================================================================
Payer: MOCK IMAGING PREFERRED (fictional)     Auth: RAD-AUTH-774411
Patient: SYNTHETIC PATIENT-EPSILON

CT / contrast lines:
  71250  CT thorax w/o       Billed 890.00   Allowed 620.00  Patient 124.00
  74177  CT abd/pelvis w     Billed 1120.00  Allowed 780.00  Patient 156.00

Radiologist: DR. PICTURE PLACEHOLDER   NPI 1444444444

Landscape PDF 05 — paired PNG is portrait mammography-style.
""".strip(),
            page_size=(792, 612),
            banner_rect=(28, 28, 764, 62),
            text_rect=(40, 72, 752, 580),
            banner_stroke=(0.72, 0.45, 0.1),
            banner_fill=(0.99, 0.94, 0.86),
            body_fontsize=8.0,
        ),
        png=Variant(
            asset_key="RCM-SYNTH-05-PNG-EF44901B62AA",
            banner="NOT REAL PHI — SYNTHETIC MAMMO SCREENING (PNG) — pair 05 portrait",
            body="""
SYNTHETIC MAMMOGRAPHY SCREENING SUMMARY — PNG VARIANT 05 (NON-PHI)
=================================================================
Breast center (fictional): MOCK WOMENS IMAGING NORTH
Accession: MAM-ACC-05-ABCDEF

Patient: SYNTHETIC PATIENT-EPSILON-IMG
Study: 8099-02-13   Bilateral screening digital mammo

Procedure (fabricated):
  77067  Screening mammo bilat   Billed 310.00   Allowed 0.00  Preventive bucket
  77065  DX mammo additional     Billed 125.00   Allowed 98.00 Patient 19.60

Radiologist: DR. MAMMO STUB MD   NPI 1222222205
BI-RADS (example): 1 — negative

Portrait PNG — content and geometry differ from landscape PDF 05.
""".strip(),
            page_size=(612, 792),
            banner_rect=(36, 36, 576, 76),
            text_rect=(48, 92, 564, 754),
            banner_stroke=(0.65, 0.2, 0.45),
            banner_fill=(0.99, 0.9, 0.94),
            body_fontsize=8.7,
        ),
    ),
)


def _resolve_unicode_sans_font() -> str:
    candidates: list[Path] = []
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windir:
        fdir = Path(windir) / "Fonts"
        candidates.extend(
            [
                fdir / "arial.ttf",
                fdir / "segoeui.ttf",
                fdir / "calibri.ttf",
            ]
        )
    candidates.extend(
        [
            Path("/Library/Fonts/Arial.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        ]
    )
    for p in candidates:
        if p.is_file():
            return str(p.resolve())
    raise SystemExit(
        "No Unicode .ttf found. Install a system sans font or set FONT_SANS_TTF.\n"
        "Linux: sudo apt install fonts-dejavu-core"
    )


def _render_pdf(font_path: str, variant: Variant, out_path: Path) -> None:
    doc = fitz.open()
    w, h = variant.page_size
    page = doc.new_page(width=w, height=h)
    _draw_page(font_path, page, variant)
    doc.save(out_path, garbage=4, clean=True, deflate=True)
    doc.close()


def _render_png(font_path: str, variant: Variant, out_path: Path) -> None:
    doc = fitz.open()
    w, h = variant.page_size
    page = doc.new_page(width=w, height=h)
    _draw_page(font_path, page, variant)
    pix = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72), alpha=False)
    pix.save(out_path)
    doc.close()


def _draw_page(font_path: str, page: fitz.Page, variant: Variant) -> None:
    w = page.rect.width
    br = fitz.Rect(variant.banner_rect)
    page.draw_rect(br, color=variant.banner_stroke, fill=variant.banner_fill)
    page.insert_textbox(
        br,
        variant.banner,
        fontsize=11 if w > 700 else 12,
        fontfile=font_path,
        color=(0.25, 0.12, 0.08),
        align=fitz.TEXT_ALIGN_CENTER,
    )
    tr = fitz.Rect(variant.text_rect)
    body_with_key = f"{variant.body}\n\nUnique asset key (non-PHI test id): {variant.asset_key}"
    rc = page.insert_textbox(
        tr,
        body_with_key,
        fontsize=variant.body_fontsize,
        fontfile=font_path,
        color=(0, 0, 0),
        align=fitz.TEXT_ALIGN_LEFT,
    )
    if rc < 0:
        raise SystemExit("Text overflow — shorten copy or rects for this variant.")


def _assert_pairwise_unique_contents(paths: list[Path]) -> None:
    seen: dict[str, Path] = {}
    for p in paths:
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if digest in seen:
            raise SystemExit(
                f"Generated duplicate bytes: {p.name} == {seen[digest].name} (sha256 {digest[:16]}…)"
            )
        seen[digest] = p


def main() -> None:
    env_font = os.environ.get("FONT_SANS_TTF")
    font_path = env_font if env_font and Path(env_font).is_file() else _resolve_unicode_sans_font()

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    for legacy in ("synthetic_eob.pdf", "synthetic_eob.png"):
        p = GENERATED_DIR / legacy
        if p.is_file():
            p.unlink()

    written: list[Path] = []
    for pair in PAIRS:
        stem = f"synthetic_eob_{pair.suffix}"
        pdf_path = GENERATED_DIR / f"{stem}.pdf"
        png_path = GENERATED_DIR / f"{stem}.png"
        _render_pdf(font_path, pair.pdf, pdf_path)
        _render_png(font_path, pair.png, png_path)
        written.extend([pdf_path, png_path])

    _assert_pairwise_unique_contents(written)

    print(f"Using font: {font_path}")
    for p in written:
        print(f"Wrote {p}")
    print(
        f"Verified {len(written)} files: SHA-256 all distinct; "
        "each .pdf/.png pair uses different synthetic copy (not raster-of-PDF)."
    )


if __name__ == "__main__":
    main()
