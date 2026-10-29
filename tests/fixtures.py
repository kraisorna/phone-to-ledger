"""Golden seed fixture S1: clean ABB slip, inclusive VAT."""
import copy

S1_GOLDEN = {
    "schema_version": "1.0",
    "document_type": "receipt",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "document_number": "ABB-0001",
    "status": "paid",
    "dates": {
        "issue_date": "2026-08-27",
        "raw_date_string": "27/08/2569",
        "era_resolution": {"detected_era": "BE", "year_digits": 4,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "Test Shop Co., Ltd.",
        "brand_name": "Test Shop",
        "branch_code": "00001",
        "tax_id": "1234567890121",
        "vat_registered": True,
        "address": "1 Test Rd, Bangkok",
        "phone": "[PHONE]",
        "email": None,
    },
    "line_items": [
        {"line_number": 1, "description": "Noodles", "line_total": 8000,
         "quantity": 2, "quantity_source": "column", "unit_price": 4000,
         "supply_type": "goods", "vat_flag": "V"},
        {"line_number": 2, "description": "Extra egg", "line_total": 0,
         "quantity": 1, "quantity_source": "column", "supply_type": "goods",
         "vat_flag": "V", "is_modifier": True, "parent_line_number": 1},
        {"line_number": 3, "description": "Drink X2", "line_total": 2700,
         "quantity": 2, "quantity_source": "embedded_in_name", "supply_type": "goods",
         "vat_flag": "V"},
    ],
    "payments": [
        {"amount": 7200, "method": "cash", "method_raw": "CASH"},
        {"amount": 3500, "method": "promptpay", "method_raw": "PromptPay"},
    ],
    "totals": {
        "grand_total": 10700, "subtotal": 10700, "discount_total": 0,
        "total": 10700, "vatable_amount": 10000, "vat_amount": 700,
        "vat_amount_computed": 700, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": "E123456789012",
    "field_confidence": {"totals.grand_total": 0.99, "totals.vat_amount": 0.98,
                         "dates.issue_date": 0.97, "issuer.tax_id": 0.99,
                         "document_number": 0.95},
    "source": {"kind": "ocr", "image_uri": "s1.jpg",
               "image_hash": "aaa", "model": "test",
               "image_quality": {"blur_score": 0.9, "contrast_score": 0.8,
                                 "skew_degrees": 1.0,
                                 "passed_gate": True}},
}


def fresh():
    return copy.deepcopy(S1_GOLDEN)


# ---------------------------------------------------------------------------
# S1-S6: faithful seed fixtures from 02-ocr-edge-cases.md / 05-ocr-pipeline-plan.md
#
# Documented values (merchant, totals, dates, VAT figures, POS ids, masks,
# emails, QR purpose) are verbatim from the edge-case catalogue. S1-S6 were
# additionally transcribed from the real sample images in
# ../rapee/docs/samples/ (real tax IDs, branch codes, receipt numbers, line
# names — checksums verified). S2 keeps document_number absent (no labelled
# receipt number on the slip; the bottom-line "16811002 3499" is a store /
# terminal / sequence stamp, and the R10 fuzzy-key pin depends on this).
# S1_GOLDEN above is an older synthetic fixture kept for the original tests.
# S7-S11 cannot be fixtured: the docs say "Details still to be written up".
# ---------------------------------------------------------------------------

# S1: Cafe Amazon (PTT OR), 45.00. BE 4-digit year; split payment (QR 35.00
# + AIS discount voucher 10.00 — tender, NOT a totals discount); 0.00
# modifier; printed "VATable: 45.00" is NOT trusted (recomputed 42.06);
# leading card mask on slip; POS ID label; queue number.
S1_CAFE_AMAZON = {
    "schema_version": "1.0",
    "document_type": "combined",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "document_number": "2083RC082569/005087",
    "status": "paid",
    "dates": {
        "issue_date": "2026-08-27",
        "raw_date_string": "27/08/2569 15:14",
        "era_resolution": {"detected_era": "BE", "year_digits": 4,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "บมจ.ปตท. น้ำมันและการค้าปลีก",
        "brand_name": "Cafe Amazon",
        "branch_name": "สน.สุทธิสาร",
        "branch_code": "00031",  # slip also shows store code 2083 (no field)
        "tax_id": "0107561000013",  # real, checksum-verified
        "vat_registered": True,
    },
    "line_items": [
        {"line_number": 1, "description": "TW น้ำลิ้นจี่ เย็น",
         "description_raw": "TW น้ำลิ้นจี่ เย็น",
         "line_total": 4500, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "V"},
        {"line_number": 2, "description": "- TW หวานน้อย 50%",
         "description_raw": "- TW หวานน้อย 50%",
         "line_total": 0, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "V",
         "is_modifier": True, "parent_line_number": 1},
    ],
    "payments": [
        {"amount": 3500, "method": "qr_promptpay",
         "method_raw": "QRPayment(API)",
         # middle digits creased on the slip; best read:
         "external_ref": "promptpay\\APIC1787318440425NZX"},
        {"amount": 1000, "method": "voucher_discount",
         "method_raw": "ส่วนลด 10 บาท AIS"},
    ],
    "totals": {
        "grand_total": 4500, "subtotal": 4500, "discount_total": 0,
        "total": 4500,
        # Slip prints "VATable: 45.00" — arithmetically impossible next to
        # VAT 2.94, so the label carries the recomputed 42.06.
        "vatable_amount": 4206, "vat_amount": 294,
        "vat_amount_computed": 294, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": "E020100002A2158",
    # Slip also shows leading-mask card "XXXX XXXX 3423 1665", a WiFi
    # password and a cashier name: unattributed/untranscribed/PII, omitted.
    "discarded_text": ["คิวที่ 71"],
    "field_confidence": {"totals.grand_total": 0.98, "totals.vat_amount": 0.97,
                         "dates.issue_date": 0.99, "issuer.tax_id": 0.99,
                         "document_number": 0.95},
    "source": {"kind": "ocr", "image_uri": "s1.jpg",
               "image_hash": "placeholder-hash-s1", "model": "hand-label"},
}

# S2: CP Axtra / Lotus's, 89.00. No VAT line at all; qty embedded in the
# name; trailing V flag; middle card mask; RID. label; doc label at bottom.
S2_LOTUS = {
    "schema_version": "1.0",
    "document_type": "combined",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "status": "paid",
    "dates": {
        "issue_date": "2026-08-27",
        "raw_date_string": "27/08/2026",
        "era_resolution": {"detected_era": "AD", "year_digits": 4,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "CP AXTRA",
        "brand_name": "Lotus's",
        "branch_name": "ประชาราษฎร์บำเพ็ญ",
        "branch_code": "1681",
        "tax_id": "0107567000414",  # real, checksum-verified
        "vat_registered": True,
    },
    "line_items": [
        {"line_number": 1, "description": "ดัชชี่ผลไม้รวม125ก.",
         "description_raw": "ดัชชี่ผลไม้รวม125ก.X4",
         "line_total": 4900, "quantity": 4, "quantity_source": "embedded_in_name",
         "supply_type": "goods", "vat_flag": "V"},  # printed "49.00V"
        {"line_number": 2, "description": "โลตัส ไอศกรีม ช็อกโกชิพ",
         "description_raw": "โลตัส ไอศกรีม ช็อกโกชิพ",
         "line_total": 4000, "quantity": 1, "quantity_source": "assumed",
         "supply_type": "goods", "vat_flag": "V"},  # printed "40.00V"
    ],
    "payments": [
        {"amount": 8900, "method": "credit_card",
         "method_raw": "LOTUSS MC",
         "card_mask": "559233XXXXXX3717", "card_mask_position": "middle"},
    ],
    "totals": {
        "grand_total": 8900, "subtotal": 8900, "discount_total": 0,
        "total": 8900, "vatable_amount": None, "vat_amount": None,  # absent on slip
        "vat_amount_computed": 582, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": "E020100002A2259",
    "field_confidence": {"totals.grand_total": 0.97,
                         "dates.issue_date": 0.99, "issuer.tax_id": 0.99},
    "source": {"kind": "ocr", "image_uri": "s2.jpg",
               "image_hash": "placeholder-hash-s2", "model": "hand-label"},
}

# S3: Jones Salad, 208.00. Tax Summary table; item count in the SUBTOTAL row
# (not a quantity); section header; "-" discount means zero; two timestamps;
# placeholder email; feedback QR.
S3_JONES = {
    "schema_version": "1.0",
    "document_type": "combined",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "document_number": "JS001/ESP014867",
    "status": "paid",
    "dates": {
        "issue_date": "2026-08-28",
        "raw_date_string": "28/08/2026",
        "printed_at": "2026-08-28T14:59:00",  # PRN ON; issue was 14:28
        "era_resolution": {"detected_era": "AD", "year_digits": 4,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "Jones Salad",
        "brand_name": "Jones Salad",
        "branch_name": "Esplanade",
        "branch_code": "00001",
        "tax_id": "0105559141754",  # real, checksum-verified
        "vat_registered": True,
        "email": "U1346493@noemail.longdo.com",
        "email_is_placeholder": True,
    },
    "line_items": [
        {"line_number": 1, "description": "** Dine In **", "line_total": 0,
         "is_section_header": True},
        {"line_number": 2, "description": "สลัดสวนคุณพ่อ (L)",
         "description_raw": "สลัดสวนคุณพ่อ (L)",
         "line_total": 9900, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 3, "description": "แรปทูน่าคอร์น",
         "description_raw": "แรปทูน่าคอร์น",
         "line_total": 10900, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
    ],
    "payments": [
        {"amount": 20800, "method": "bank_qr",
         "method_raw": "QR Payment Bangkok Bank"},
    ],
    "totals": {
        "grand_total": 20800, "subtotal": 20800,
        "discount_total": 0,  # slip shows "-": zero, not an error
        "total": 20800, "vatable_amount": 19439, "vat_amount": 1361,
        "vat_amount_computed": 1361, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "qr_codes": [{"purpose": "feedback", "raw_payload": ""}],  # survey QR;
    # payload not transcribed; purpose is the documented finding
    "discarded_text": ["ORDER NUMBER 12575"],
    "field_confidence": {"totals.grand_total": 0.98, "totals.vat_amount": 0.95,
                         "dates.issue_date": 0.99, "issuer.tax_id": 0.99},
    "source": {"kind": "ocr", "image_uri": "s3.jpg",
               "image_hash": "placeholder-hash-s3", "model": "hand-label"},
}

# S4: Starbucks, 75.00. Misaligned VAT line (still reconciles: 4.91/70.09);
# alpha date with 2-digit year and NO anchor -> era stays ambiguous;
# loyalty expiry dates are fake dates; trailing card mask; POS# label.
S4_STARBUCKS = {
    "schema_version": "1.0",
    "document_type": "combined",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "document_number": "260828-01-07563",
    "status": "paid",
    "dates": {
        "issue_date": None,  # unresolved: no anchor for the 2-digit year
        "raw_date_string": "Aug28 26 4:44PM",
        "era_resolution": {"detected_era": "ambiguous", "year_digits": 2,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "Starbucks Coffee",
        "brand_name": "Starbucks",
        "branch_name": "Siam Future Esplanade",
        "branch_code": "14098",
        "tax_id": "0105541008688",  # real, checksum-verified
        "vat_registered": True,
    },
    "line_items": [
        {"line_number": 1, "description": "NEW SBUX WATER",
         "description_raw": "NEW SBUX WATER",
         "line_total": 2500, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 2, "description": "CHOC DONUT 60G",
         "description_raw": "CHOC DONUT 60G",  # 60G weight, not GOG
         "line_total": 5000, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
    ],
    "payments": [
        {"amount": 7500, "method": "stored_value_redeem",
         "method_raw": "Starbucks stored-value redeem"},
    ],
    "totals": {
        "grand_total": 7500, "subtotal": 7500, "discount_total": 0,
        "total": 7500, "vatable_amount": 7009, "vat_amount": 491,
        "vat_amount_computed": 491, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": "E020110002A1570",
    "discarded_text": ["21Aug27", "31Dec26"],  # loyalty expiry, not doc dates
    "field_confidence": {"totals.grand_total": 0.96, "totals.vat_amount": 0.9,
                         "issuer.tax_id": 0.99},
    "source": {"kind": "ocr", "image_uri": "s4.jpg",
               "image_hash": "placeholder-hash-s4", "model": "hand-label"},
}

# S5: 7-Eleven (CP All), 28.25. 2-digit BE year WITH a TID anchor;
# faded thermal (the realistic capture); TrueMoney wallet.
S5_SEVEN = {
    "schema_version": "1.0",
    "document_type": "combined",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "document_number": "R#0000677955P3",
    "status": "paid",
    "dates": {
        "issue_date": "2026-08-28",
        "raw_date_string": "28/08/69 20:14",
        "era_resolution": {"detected_era": "BE", "year_digits": 2,
                           "anchor_used": "TID#2026082800000005170679622"},
    },
    "issuer": {
        "legal_name": "CP ALL",
        "brand_name": "7-Eleven",
        "branch_name": "ประชาราษฎร์ 12",
        "branch_code": "02304",
        "tax_id": "0107542000011",  # real, checksum-verified
        "vat_registered": True,
    },
    "line_items": [
        {"line_number": 1, "description": "นมพาสฯเมจิ 450",
         "description_raw": "Hนมพาสฯเมจิ 450",  # stray H glyph on the print
         "line_total": 2825, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "V"},
    ],
    "payments": [
        {"amount": 2825, "method": "truemoney_wallet",
         "method_raw": "ทรูวอลเล็ท7App"},
    ],
    "totals": {
        "grand_total": 2825, "subtotal": 2825, "discount_total": 0,
        "total": 2825, "vatable_amount": 2640, "vat_amount": 185,
        "vat_amount_computed": 185, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    # condition: faded thermal (tracked via eval faded_ids, no schema field)
    "pos_identifier": "E020100002A0368",
    "field_confidence": {"totals.grand_total": 0.93, "totals.vat_amount": 0.9,
                         "dates.issue_date": 0.95, "issuer.tax_id": 0.99,
                         "document_number": 0.9},
    "source": {"kind": "ocr", "image_uri": "s5.jpg",
               "image_hash": "placeholder-hash-s5", "model": "hand-label"},
}

# S6: Saint Etoile (Thai Yamazaki), 32.00. Three-level naming
# (legal/brand/branch); clean VAT 29.91/2.09; V suffixes; RD: label.
S6_ETOILE = {
    "schema_version": "1.0",
    "document_type": "combined",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "document_number": "0196768",
    "status": "paid",
    "dates": {
        "issue_date": "2026-08-29",
        "raw_date_string": "29/08/2026 16:10:20",
        "era_resolution": {"detected_era": "AD", "year_digits": 4,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "Thai yamazaki Co.,Ltd.",
        "brand_name": "Saint Etoile",
        "branch_name": "Central Westville",
        "branch_code": "00198",
        "tax_id": "0105527027239",  # real, checksum-verified
        "vat_registered": True,
    },
    "line_items": [
        {"line_number": 1, "description": "โดนัทช็อกโกแลต",
         "description_raw": "โดนัทช็อกโกแลต",
         "line_total": 3200, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "V"},
    ],
    "payments": [
        {"amount": 3200, "method": "truemoney_wallet",
         "method_raw": "ทรูวอลเล็ท 7App"},
    ],
    "totals": {
        "grand_total": 3200, "subtotal": 3200, "discount_total": 0,
        "total": 3200, "vatable_amount": 2991, "vat_amount": 209,
        "vat_amount_computed": 209, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": "E041210002A5885",
    "field_confidence": {"totals.grand_total": 0.99, "totals.vat_amount": 0.98,
                         "dates.issue_date": 0.99, "issuer.tax_id": 0.99},
    "source": {"kind": "ocr", "image_uri": "s6.jpg",
               "image_hash": "placeholder-hash-s6", "model": "hand-label"},
}

SEEDS = {
    "S1": S1_CAFE_AMAZON,
    "S2": S2_LOTUS,
    "S3": S3_JONES,
    "S4": S4_STARBUCKS,
    "S5": S5_SEVEN,
    "S6": S6_ETOILE,
}


def fresh_seed(name):
    return copy.deepcopy(SEEDS[name])
