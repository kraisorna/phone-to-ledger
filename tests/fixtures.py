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

# S22: 7-Eleven (CP All), same branch as S5, 77.25. 2-digit BE year
# WITH a TID anchor; stray H glyphs on both lines; Vat Code 02314 decoy
# beside branch (02304); no printed VAT rows (computed 505/7220);
# member points (+42/10469) that must not leak into totals.
S22_SEVEN2 = {
    "schema_version": "1.0",
    "document_type": "combined",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "document_number": "R#0000240606P1",  # 5x zoom: 6, not G (matches S5's 10-digit+P shape)
    "status": "paid",
    "dates": {
        "issue_date": "2026-10-29",
        "raw_date_string": "29/10/69 15:33",
        "era_resolution": {"detected_era": "BE", "year_digits": 2,
                           "anchor_used": "TID#2026102900000005417306139"},
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
        {"line_number": 1, "description": "วอลล์ 2in1 ช็อกโก",
         "description_raw": "Hวอลล์ 2in1 ช็อกโก",  # stray H on the print
         "line_total": 4900, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "V"},
        {"line_number": 2, "description": "นมพาสฯเมจิ 450",
         "description_raw": "Hนมพาสฯเมจิ 450",
         "line_total": 2825, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "V"},
    ],
    "payments": [
        {"amount": 7725, "method": "truemoney_wallet",
         "method_raw": "ทรูวอลเล็ท7App"},
    ],
    "totals": {
        "grand_total": 7725, "subtotal": 7725, "discount_total": 0,
        "total": 7725, "vatable_amount": 7220, "vat_amount": 505,
        "vat_amount_computed": 505, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    # Verbatim 14 digits past E: breaks the E+12 POS convention.
    "pos_identifier": "E02010000202474",
    "discarded_text": ["02314", "+42", "10469"],  # Vat Code decoy, points
    "field_confidence": {"totals.grand_total": 0.93, "totals.vat_amount": 0.9,
                         "dates.issue_date": 0.95, "issuer.tax_id": 0.99,
                         "document_number": 0.9},
    "source": {"kind": "ocr", "image_uri": "s22.jpg",
               "image_hash": "placeholder-hash-s22", "model": "hand-label"},
}

# S21: noodle shop (Rad Na Fachai), 99.00, no receipt number, no tender
# rows, no branch marking, no ABB/full marks. 4-digit AD date; count
# row "จำนวน : 3" is not a line; clean inclusive VAT (648/9252).
S21_RADNA = {
    "schema_version": "1.0",
    "document_type": "combined",
    "form": "unknown",
    "can_claim_input_vat": False,
    "document_number": None,
    "status": "unpaid",
    "dates": {
        "issue_date": "2026-10-29",
        "raw_date_string": "29/10/2026 13:13:27",
        "era_resolution": {"detected_era": "AD", "year_digits": 4,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "บ.จำเริญรส เรสเตอร์รอง แอนด์ไลฟ์ จำกัด",
        "brand_name": "ราดหน้าฟาไฉ ปตท.บางพูน",
        "branch_name": None,
        "branch_code": None,
        "address": "72/28 ต.บางพูน อ.เมืองปทุมธานี จ.ปทุมธานี 12000",
        "tax_id": "0105566224155",  # real, checksum-verified
        "phone": "0955292838",
        "email": None,
        "vat_registered": True,
    },
    "line_items": [
        {"line_number": 1, "description": "โค้ก",
         "description_raw": "โค้ก",
         "line_total": 1500, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "V"},
        {"line_number": 2, "description": "ข้าวหน้ากระเทียมหมูนุ่ม",
         "description_raw": "ข้าวหน้ากระเทียมหมูนุ่ม",
         "line_total": 6900, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "V"},
        {"line_number": 3, "description": "ไข่ดาวสุก",
         "description_raw": "ไข่ดาวสุก",
         "line_total": 1500, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "V"},
    ],
    "payments": [],
    "totals": {
        "grand_total": 9900, "subtotal": 9900, "discount_total": 0,
        "total": 9900, "vatable_amount": 9252, "vat_amount": 648,
        "vat_amount_computed": 648, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": None,
    "discarded_text": ["3", "User Owner"],  # count row, cashier name
    "field_confidence": {"totals.grand_total": 0.95, "totals.vat_amount": 0.9,
                         "dates.issue_date": 0.97, "issuer.tax_id": 0.99,
                         "document_number": 0.9},
    "source": {"kind": "ocr", "image_uri": "s21.jpg",
               "image_hash": "placeholder-hash-s21", "model": "hand-label"},
}

# S23: Oasis Coffee plain receipt, 120.00. No tax ID, no ABB/full marks,
# anchorless 2-digit year (YYMMDD-looking "102569" inside the receipt
# number never resolves it); printed VATABLE 120.00 is the gross, so
# vatable recomputes to 11215; wifi password + 31/10/69 expiry are fake
# dates; ITEMS count row is not a line.
S23_OASIS = {
    "schema_version": "1.0",
    "document_type": "receipt",
    "form": "unknown",
    "can_claim_input_vat": False,
    "document_number": "1RC102569/008592",
    "status": "paid",
    "dates": {
        "issue_date": None,
        "raw_date_string": "30/10/69 14:38",
        "era_resolution": {"detected_era": "ambiguous", "year_digits": 2,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "OASIS COFFEE",
        "brand_name": "OASIS COFFEE",
        "branch_name": None,
        "branch_code": None,
        "address": ("70 ถนนประชาราษฎร์บำเพ็ญ แขวงห้วยขวาง "
                    "เขตห้วยขวาง กรุงเทพฯ 10310"),
        "tax_id": None,
        "phone": "0855318496",
        "email": None,
        # Prints VAT figures yet shows no tax ID: unverifiable, not False.
        "vat_registered": None,
    },
    "line_items": [
        {"line_number": 1, "description": "Mango Smoothie",
         "description_raw": "Mango Smoothie",
         "line_total": 12000, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "V"},
    ],
    "payments": [
        {"amount": 12000, "method": "mobile_payment",
         "method_raw": "Mobile Payment :"},
    ],
    "totals": {
        "grand_total": 12000, "subtotal": 12000, "discount_total": 0,
        "total": 12000, "vatable_amount": 11215, "vat_amount": 785,
        "vat_amount_computed": 785, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": None,
    "discarded_text": ["1", "2008 Cake", "scjraa63", "31/10/69"],
    "field_confidence": {"totals.grand_total": 0.95, "totals.vat_amount": 0.9,
                         "document_number": 0.9},
    "source": {"kind": "ocr", "image_uri": "s23.jpg",
               "image_hash": "placeholder-hash-s23", "model": "hand-label"},
}

# S7: CP AXTRA (Lotus's) ABB receipt, 69.00, branch 6662. Same POS
# family as S2, whose day-27 date proves DD/MM/YYYY ordering: raw
# 05/09/2026 is 5 Sept 2026. (The 05 plan's MM/DD note traces to a
# stale sample map — it also labels S7 "Dairy Queen".) Masked RID and
# member number, QR ref as PSP external_ref, coin rows as traps.
S7_CPAXTRA_6662 = {
    "schema_version": "1.0",
    "document_type": "combined",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "document_number": None,
    "status": "paid",
    "dates": {
        "issue_date": "2026-09-05",
        "raw_date_string": "05/09/2026 13:28",
        "era_resolution": {"detected_era": "AD", "year_digits": 4,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "CP AXTRA",
        "brand_name": "Lotus's",
        "branch_name": "ฟรีเว่ แสนปินกก",
        "branch_code": "6662",
        "tax_id": "0107567000414",
        "vat_registered": True,
    },
    "line_items": [
        {"line_number": 1, "description": "อาหารพร้อมทาน 69 บาท",
         "description_raw": "อาหารพร้อมทาน 69 บาท",
         "line_total": 6900, "quantity": 1, "quantity_source": "assumed",
         "supply_type": "goods", "vat_flag": "V"},
    ],
    "payments": [
        {"amount": 6900, "method": "card",
         "method_raw": "On-line card",
         "external_ref": "61399177Q8HQ100000"},
    ],
    "totals": {
        "grand_total": 6900, "subtotal": 6900, "discount_total": 0,
        "total": 6900, "vatable_amount": None, "vat_amount": None,
        "vat_amount_computed": 451, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": None,
    "discarded_text": ["XXXXXXXXXXXX01", "*******7974", "QR PromptP",
                       "Auth Code = 793591", "0.20", "10.73",
                       "6662 001 66623002 5619"],
    "field_confidence": {"totals.grand_total": 0.97,
                         "dates.issue_date": 0.95,
                         "issuer.tax_id": 0.99},
    "source": {"kind": "ocr", "image_uri": "s7.jpg",
               "image_hash": "placeholder-hash-s7", "model": "hand-label"},
}

# S8: Jay To seafood shop bill (Ocha POS), 240.00 over 3 lines. Two
# same-date timestamps: print time issues the bill, check-in time is
# discarded. No tax ID, no VAT rows, no ABB/full marks; master-data
# typo น้ำโศก kept verbatim (never "corrected" to น้ำโค้ก); the ยอดรวม
# count 3 and zone นอก-3 are not lines.
S8_JAYTO_SEAFOOD = {
    "schema_version": "1.0",
    "document_type": "receipt",
    "form": "unknown",
    "can_claim_input_vat": False,
    "document_number": None,
    "status": "unpaid",
    "dates": {
        "issue_date": "2026-09-05",
        "raw_date_string": "05-09-2569 18:57",
        "era_resolution": {"detected_era": "BE", "year_digits": 4,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "เจ๊โต อาหารทะเล หัวปลาหม้อไฟ",
        "brand_name": "เจ๊โต อาหารทะเล หัวปลาหม้อไฟ",
        "branch_name": None,
        "branch_code": None,
        "tax_id": None,
        "vat_registered": None,
    },
    "line_items": [
        {"line_number": 1, "description": "ยำหอยนางรม",
         "description_raw": "ยำหอยนางรม",
         "line_total": 15000, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 2, "description": "(คะน้า,แขนง)หมูกรอบราดข้าว",
         "description_raw": "(คะน้า,แขนง)หมูกรอบราดข้าว",
         "line_total": 7000, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 3, "description": "น้ำโศก(เล็ก)",
         "description_raw": "น้ำโศก(เล็ก)",
         "line_total": 2000, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
    ],
    "payments": [],
    "totals": {
        "grand_total": 24000, "subtotal": 24000, "discount_total": 0,
        "total": 24000, "vatable_amount": None, "vat_amount": None,
        "vat_amount_computed": 1570, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": None,
    "discarded_text": ["05-09-2569 18:53", "นอก - 3", "3",
                       "เจ๊โต อาหารทะเล หัวปลาห...",
                       "Powered by Ocha"],
    "field_confidence": {"totals.grand_total": 0.97,
                         "dates.issue_date": 0.95},
    "source": {"kind": "ocr", "image_uri": "s8.jpg",
               "image_hash": "placeholder-hash-s8", "model": "hand-label"},
}

# S9: Dairy Queen ABB slip (US-origin POS), 99.00. MM/DD/YYYY date:
# the 12-hour "3:32 PM" clock plus Micros-style Host/Check Closed
# vocabulary prove a US locale, so 09/06/2026 is June 9. +KITKAT is a
# priced modifier of line 1; the spaced POS stamp joins to E+14; the
# survey figures (499/429/30/8) and Q#3/10174 are traps.
S9_DQ_JPARK = {
    "schema_version": "1.0",
    "document_type": "combined",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "document_number": "11390",
    "status": "paid",
    "dates": {
        "issue_date": "2026-06-09",
        "raw_date_string": "09/06/2026 3:32 PM",
        "era_resolution": {"detected_era": "AD", "year_digits": 4,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "KAMRAIRUNGRUEANG 2022 CO..LTD",
        "brand_name": "DQ",
        "branch_name": "DQ_J-PARK SRIRACHA",
        "branch_code": "71498",
        "tax_id": "0215565010037",
        "vat_registered": True,
    },
    "line_items": [
        {"line_number": 1, "description": "MINT CHOC CHIP L",
         "description_raw": "MINT CHOC CHIP L",
         "line_total": 8900, "quantity": 1, "quantity_source": "assumed",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 2, "description": "+KITKAT",
         "description_raw": "+KITKAT",
         "line_total": 1000, "quantity": 1, "quantity_source": "assumed",
         "supply_type": "goods", "vat_flag": "unknown",
         "is_modifier": True, "parent_line_number": 1},
    ],
    "payments": [
        {"amount": 9900, "method": "qr_promptpay",
         "method_raw": "PROMPTPAY"},
    ],
    "totals": {
        "grand_total": 9900, "subtotal": 9900, "discount_total": 0,
        "total": 9900, "vatable_amount": None, "vat_amount": None,
        "vat_amount_computed": 648, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": "E052010002A3693",
    "discarded_text": ["Q#3", "10174", "www.talktoDQthailand.com",
                       "รับสิทธิ์ส่วนลดซื้อเค้กใหญ่ 8 นิ้ว 30 บาท",
                       "*จากเค้กราคาปกติ 499 และ 429 เท่านั้น*",
                       "Points will be collected next day"],
    "field_confidence": {"totals.grand_total": 0.97,
                         "dates.issue_date": 0.90,
                         "issuer.tax_id": 0.99},
    "source": {"kind": "ocr", "image_uri": "s9.jpg",
               "image_hash": "placeholder-hash-s9", "model": "hand-label"},
}

# S10: Tsuruha drugstore ABB slip, 364.00. Three 125/125/299 items
# with V flags plus three negative promo rows (B1G1 pair, Biore 239
# reference) that sum into the subtotal as lines. First seed with
# printed Vatable/VAT split rows (340.19/23.81, exactly recomputed).
# DD/MM by 24h clock plus the 2609 inside NO:S2609008002-0005567.
# Member and salesperson names omitted (PII, no validation value).
S10_TSURUHA_JPARK = {
    "schema_version": "1.0",
    "document_type": "combined",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "document_number": "S2609008002-0005567",
    "status": "paid",
    "dates": {
        "issue_date": "2026-09-06",
        "raw_date_string": "06/09/2026 16:10",
        "era_resolution": {"detected_era": "AD", "year_digits": 4,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "TSURUHA THAILAND",
        "brand_name": "TSURUHA",
        "branch_name": "TSURUHA-DRUG J-PARK",
        "branch_code": None,
        "tax_id": "0105554157903",
        "phone": "081-375-6270",
        "vat_registered": True,
    },
    "line_items": [
        {"line_number": 1,
         "description": "โชกุบุสซี ครีมอาบน้ำชาย สูตรเอ็กซ์ตรีม 400 มล.ขวดปั๊ม",
         "description_raw": "โชกุบุสซี ครีมอาบน้ำชาย สูตรเอ็กซ์ตรีม 400 มล.ขวดปั๊ม",
         "line_total": 12500, "quantity": 1, "quantity_source": "assumed",
         "supply_type": "goods", "vat_flag": "V"},
        {"line_number": 2, "description": "Shokubutsu Buy 1 Get 1 Free",
         "description_raw": "Shokubutsu Buy 1 Get 1 Free",
         "line_total": -6250, "quantity": 1, "quantity_source": "assumed",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 3,
         "description": "โชกุบุสซี ครีมอาบน้ำชาย สูตรเย็น 400 มล.ขวดปั๊ม",
         "description_raw": "โชกุบุสซี ครีมอาบน้ำชาย สูตรเย็น 400 มล.ขวดปั๊ม",
         "line_total": 12500, "quantity": 1, "quantity_source": "assumed",
         "supply_type": "goods", "vat_flag": "V"},
        {"line_number": 4, "description": "Shokubutsu Buy 1 Get 1 Free",
         "description_raw": "Shokubutsu Buy 1 Get 1 Free",
         "line_total": -6250, "quantity": 1, "quantity_source": "assumed",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 5,
         "description": "บิโอเร ยูวี อะควา วอเตอร์รี่ เจลลี่ SPF50 90 มล.",
         "description_raw": "บิโอเร ยูวี อะควา วอเตอร์รี่ เจลลี่ SPF50 90 มล.",
         "line_total": 29900, "quantity": 1, "quantity_source": "assumed",
         "supply_type": "goods", "vat_flag": "V"},
        {"line_number": 6, "description": "Biore UV Aqua W 239.--",
         "description_raw": "Biore UV Aqua W 239.--",
         "line_total": -6000, "quantity": 1, "quantity_source": "assumed",
         "supply_type": "goods", "vat_flag": "unknown"},
    ],
    "payments": [
        {"amount": 36400, "method": "credit_card",
         "method_raw": "MasterCard 559233XXXXXX3717",
         "card_mask": "559233XXXXXX3717",
         "card_mask_position": "middle"},
    ],
    "totals": {
        "grand_total": 36400, "subtotal": 36400, "discount_total": 0,
        "total": 36400, "vatable_amount": 34019, "vat_amount": 2381,
        "vat_amount_computed": 2381, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": "E052010003A1384",
    "discarded_text": ["POS NO:002", "Total 3.00 Items",
                       "Last Pt Reg Pt Promo Pt Redemp Pt", "0 18 72 -",
                       "90", "***รับคืนหรือเปลี่ยนสินค้าภายใน 7 วัน***",
                       "คะแนนสะสมมีอายุ 1 ปี"],
    "field_confidence": {"totals.grand_total": 0.97,
                         "dates.issue_date": 0.95,
                         "issuer.tax_id": 0.99},
    "source": {"kind": "ocr", "image_uri": "s10.jpg",
               "image_hash": "placeholder-hash-s10", "model": "hand-label"},
}

# S11: Pa Boon Cafe branch 3 billing check, 486.00 net. Food/drinks
# category headers precede their items; the *-prefix on food lines is
# systematic and kept verbatim. Printed ยอดรวม 535.50 is a +0.50 POS
# print bug: lines, categories and the downstream chain all agree on
# 535.00, so gold total is the true gross. First seed with nonzero
# discount (49.50 = 10% of the FOOD 495.00, not of the total) and
# rounding (+0.50 to 486.00): total = gross lines, subtotal = net
# before service, grand = subtotal + service. Member name, staff name
# and the 16-digit member ref omitted (PII).
S11_PABOON_CAFE3 = {
    "schema_version": "1.0",
    "document_type": "receipt",
    "form": "unknown",
    "can_claim_input_vat": False,
    "document_number": None,
    "status": "unpaid",
    "dates": {
        "issue_date": "2026-09-06",
        "raw_date_string": "06/09/2569 15:05",
        "era_resolution": {"detected_era": "BE", "year_digits": 4,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "ป้าบุญคาเฟ 3",
        "brand_name": "ป้าบุญคาเฟ",
        "branch_name": None,
        "branch_code": "3",
        "tax_id": None,
        "vat_registered": None,
    },
    "line_items": [
        {"line_number": 1, "description": "อาหาร",
         "description_raw": "อาหาร",
         "line_total": 49500, "is_category_subtotal": True,
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 2, "description": "*ข้าวผัดปู จานเล็ก",
         "description_raw": "*ข้าวผัดปู จานเล็ก",
         "line_total": 18000, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 3, "description": "*ต้มยำทะเล",
         "description_raw": "*ต้มยำทะเล",
         "line_total": 28500, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 4, "description": "*ข้าวเปล่า จาน",
         "description_raw": "*ข้าวเปล่า จาน",
         "line_total": 3000, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 5, "description": "เครื่องดื่ม",
         "description_raw": "เครื่องดื่ม",
         "line_total": 4000, "is_category_subtotal": True,
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 6, "description": "น้ำเปล่า",
         "description_raw": "น้ำเปล่า",
         "line_total": 3000, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 7, "description": "น้ำแข็ง แก้ว",
         "description_raw": "น้ำแข็ง แก้ว",
         "line_total": 1000, "quantity": 2, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
    ],
    "payments": [],
    "totals": {
        "grand_total": 48600, "subtotal": 48600, "discount_total": 4950,
        "service_charge": 0, "rounding_adjustment": 50,
        "total": 53500, "vatable_amount": None, "vat_amount": None,
        "vat_amount_computed": 3179, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": None,
    "discarded_text": ["เปิดโต๊ะ: 14:19", "โต๊ะ: 82",
                       "ค้างชำระ: 486.00", "Version (3.0.2508.3)"],
    "field_confidence": {"totals.grand_total": 0.97,
                         "dates.issue_date": 0.95},
    "source": {"kind": "ocr", "image_uri": "s11.jpg",
               "image_hash": "placeholder-hash-s11", "model": "hand-label"},
}

# S12: Starbucks Siam Future Esplanade ABB (sister slip to S4, same
# store/stamp), 25.00. Genuine one-digit tax-ID misprint (...6688 vs
# S4's ...8688): R6 hard-fails on true gold, the first blocked seed.
# "Sep09 26" stays ambiguous/null like S4's "Aug28 26" (2-digit year,
# no anchor; the 260909 invoice fragment never resolves). VAT prints
# amount-first ("1.64 VAT TTL") with a 25.00 total echo beside it.
# Member name omitted (PII).
S12_SBUX_ESPLANADE2 = {
    "schema_version": "1.0",
    "document_type": "combined",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "document_number": "260909-01-08576",
    "status": "paid",
    "dates": {
        "issue_date": None,
        "raw_date_string": "Sep09 26 2:06PM",
        "era_resolution": {"detected_era": "ambiguous", "year_digits": 2,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "Starbucks Coffee",
        "brand_name": "Starbucks",
        "branch_name": "Siam Future Esplanade",
        "branch_code": "14098",
        "tax_id": "0105541006688",
        "phone": "08 4438 7329",
        "vat_registered": True,
    },
    "line_items": [
        {"line_number": 1, "description": "NEW SBUX WATER",
         "description_raw": "NEW SBUX WATER",
         "line_total": 2500, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
    ],
    "payments": [
        {"amount": 2500, "method": "stored_value_redeem",
         "method_raw": "Sbux Redeem",
         "card_mask": "616698142248XXXX",
         "card_mask_position": "trailing"},
    ],
    "totals": {
        "grand_total": 2500, "subtotal": 2500, "discount_total": 0,
        "total": 2500, "vatable_amount": 2336, "vat_amount": 164,
        "vat_amount_computed": 164, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": "E020110002A1570",
    "discarded_text": ["Chk 0100339186",
                       "Card Balance is 1800.00 THB", "21Aug27",
                       "13Sep26", "31Dec26", "OTKIOHSLFT"],
    "field_confidence": {"totals.grand_total": 0.96,
                         "totals.vat_amount": 0.9,
                         "issuer.tax_id": 0.99},
    "source": {"kind": "ocr", "image_uri": "s12.jpg",
               "image_hash": "placeholder-hash-s12", "model": "hand-label"},
}

# S13: Watsons Esplanade ABB, 50.00. Printed VAT 3.28 vs recomputed
# 327: the POS rounds per line (164 x 2), the pipeline on the grand,
# and R3's +-1 tolerance absorbs exactly this policy gap. SKU codes
# strip from descriptions into description_raw; T flags are outside
# the V/N/E vocabulary (unknown). The # receipt number decomposes to
# store 604 + terminal 002 + date 09092026 + seq 0005, fixing
# branch_code "00604". Cashier name omitted (PII).
S13_WATSONS_ESPLANADE = {
    "schema_version": "1.0",
    "document_type": "combined",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "document_number": "604002090920260005",
    "status": "paid",
    "dates": {
        "issue_date": "2026-09-09",
        "raw_date_string": "9SEP2026 14:04:01",
        "era_resolution": {"detected_era": "AD", "year_digits": 4,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "watsons",
        "brand_name": "watsons",
        "branch_name": "WATSON Esplanade Rat",
        "branch_code": "00604",
        "tax_id": "0105539086260",
        "vat_registered": True,
    },
    "line_items": [
        {"line_number": 1, "description": "#HDBRPMNightRepa@",
         "description_raw": "311773 #HDBRPMNightRepa@",
         "line_total": 2500, "quantity": 1, "quantity_source": "assumed",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 2, "description": "#HadabireiPr@",
         "description_raw": "309086 #HadabireiPr@",
         "line_total": 2500, "quantity": 1, "quantity_source": "assumed",
         "supply_type": "goods", "vat_flag": "unknown"},
    ],
    "payments": [
        {"amount": 5000, "method": "qr_promptpay",
         "method_raw": "QR-Code",
         "external_ref": "EDC178937430213483"},
    ],
    "totals": {
        "grand_total": 5000, "subtotal": 5000, "discount_total": 0,
        "total": 5000, "vatable_amount": 4672, "vat_amount": 328,
        "vat_amount_computed": 327, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": "E020110002A1030",
    "discarded_text": ["2", "CHANGE 0.00",
                       "Opening eStamp Balance 10",
                       "Closing eStamp Balance 10",
                       "Loyalty acc.number 9930840801***", "525",
                       "527", "Tel: 02-0178899", "ISSUER# PROMPTPAY",
                       "TID# 73906252", "TRACE# 138340", "R 002",
                       "870604021403220260909"],
    "field_confidence": {"totals.grand_total": 0.97,
                         "totals.vat_amount": 0.9,
                         "dates.issue_date": 0.99,
                         "issuer.tax_id": 0.99},
    "source": {"kind": "ocr", "image_uri": "s13.jpg",
               "image_hash": "placeholder-hash-s13", "model": "hand-label"},
}

# S14: Jones Salad Esplanade delivery order via ShopeeFood, 249.00
# (sister slip to dine-in S3, same entity/branch). Two charge lines
# (110 + 139) under a ** delivery section header; the steak's inline
# promo math (219-109 = 110, 49.8%) and "249.-" set-total echo are
# traps, as are order/ref/table/cutlery rows. Symmetric 09/09 date
# needs no DD/MM inference. Cashier first name omitted (PII).
S14_JONES_DELIVERY = {
    "schema_version": "1.0",
    "document_type": "combined",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "document_number": "JS001/ESP017940",
    "status": "paid",
    "dates": {
        "issue_date": "2026-09-09",
        "raw_date_string": "09/09/2026",
        "printed_at": "2026-09-09T14:19:00",
        "era_resolution": {"detected_era": "AD", "year_digits": 4,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "Jones Salad",
        "brand_name": "Jones Salad",
        "branch_name": "Esplanade",
        "branch_code": "00001",
        "tax_id": "0105559141754",
        "vat_registered": True,
    },
    "line_items": [
        {"line_number": 1, "description": "** ShopeeFood (Delivery) **",
         "line_total": 0, "is_section_header": True},
        {"line_number": 2, "description": "สเต็กสะโพกไก่ ขี้โมโห",
         "description_raw": "สเต็กสะโพกไก่ ขี้โมโห",
         "line_total": 11000, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 3, "description": "ไม่เปลี่ยนเครื่องเคียง (Default)",
         "description_raw": "ไม่เปลี่ยนเครื่องเคียง (Default)",
         "line_total": 0, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown",
         "is_modifier": True, "parent_line_number": 2},
        {"line_number": 4, "description": "แรปทูน่าอ้วน",
         "description_raw": "แรปทูน่าอ้วน",
         "line_total": 13900, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
    ],
    "payments": [
        {"amount": 24900, "method": "shopeefood",
         "method_raw": "Shopee Food (Delivery)"},
    ],
    "totals": {
        "grand_total": 24900, "subtotal": 24900, "discount_total": 0,
        "total": 24900, "vatable_amount": 23271, "vat_amount": 1629,
        "vat_amount_computed": 1629, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": None,
    "discarded_text": ["Order No: 15142", "Ref No: 689", "Table No: 02",
                       "Cutlery: No",
                       "* SP สเต็กสะโพกไก่ขี้โมโห คู่ แรปทูน่าอ้วน",
                       "249.- (219.00-109.00)[49.8%]",
                       "** 09/09/2026 14:19 **",
                       "Scan here to share your feedback!",
                       "@Jonessalad"],
    "field_confidence": {"totals.grand_total": 0.97,
                         "totals.vat_amount": 0.9,
                         "dates.issue_date": 0.99,
                         "issuer.tax_id": 0.99},
    "source": {"kind": "ocr", "image_uri": "s14.jpg",
               "image_hash": "placeholder-hash-s14", "model": "hand-label"},
}

# S15: Tops Esplanade ABB, 37.00. Two Cokes with a -3.00 Mix&Match
# promo line (P flag outside the V/N/E vocabulary); first line's odd
# name kept verbatim (probable master-data abbreviation, cf. S8).
# QR tender via QPCB row; the slip also carries a coupon section with
# its own QR, barcode, 15% figures and three extra dates — all traps.
# Loyalty number, member and cashier names omitted (PII).
S15_TOPS_ESPLANADE = {
    "schema_version": "1.0",
    "document_type": "combined",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "document_number": "003 - 022725",
    "status": "paid",
    "dates": {
        "issue_date": "2026-09-09",
        "raw_date_string": "09.09.2026 14:43",
        "era_resolution": {"detected_era": "AD", "year_digits": 4,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "Tops",
        "brand_name": "Tops",
        "branch_name": "Tops Esplanade",
        "branch_code": None,
        "tax_id": "0105535134278",
        "phone": "02-660-9092-3",
        "vat_registered": True,
    },
    "line_items": [
        {"line_number": 1, "description": "โผล่น้ำแข็งกั่ว",
         "description_raw": "โผล่น้ำแข็งกั่ว",
         "line_total": 800, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 2, "description": "โก๊ก 325มล",
         "description_raw": "โก๊ก 325มล",
         "line_total": 1600, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 3, "description": "Mix&Match",
         "description_raw": "Mix&Match",
         "line_total": -300, "quantity": 1, "quantity_source": "assumed",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 4, "description": "โก๊ก 325มล",
         "description_raw": "โก๊ก 325มล",
         "line_total": 1600, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
    ],
    "payments": [
        {"amount": 3700, "method": "qr_promptpay",
         "method_raw": "QPCB 000201****27DC"},
    ],
    "totals": {
        "grand_total": 3700, "subtotal": 3700, "discount_total": 0,
        "total": 3700, "vatable_amount": None, "vat_amount": None,
        "vat_amount_computed": 242, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": None,
    "discarded_text": ["TP 003 - 023471", "NP_3724765260701",
                       "STID: 2609091443360023471CFR000516003",
                       "ประหยัดวันนี้ 3.00 บาท", "คะแนนสะสม: 291",
                       "โทร 1467", "662026090900516003023471",
                       "#EveryDayDISCOVERY",
                       "เพียงสแกน QR Code ด้านล่าง", "JOYNOW15",
                       "30/08/69", "15.07.2026", "30.09.2026"],
    "field_confidence": {"totals.grand_total": 0.97,
                         "dates.issue_date": 0.99,
                         "issuer.tax_id": 0.99},
    "source": {"kind": "ocr", "image_uri": "s15.jpg",
               "image_hash": "placeholder-hash-s15", "model": "hand-label"},
}

# S16: 7-Eleven 02304 ABB (sister slip to S22, same store/stamp),
# 77.00 net. Wall's plus 2 Cokes at 16, minus a 4.00 receipt-level
# Coke/Sprite discount row (S11 pattern: positioned after ยอดรวม,
# printed positive, discount_total not a line). Anchored BE date via
# the TID stamp like S22. VAT null + computed (S2/S7/S8 style, not
# S22's filled style). Member first name omitted (PII).
S16_SEVEN_02304B = {
    "schema_version": "1.0",
    "document_type": "combined",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "document_number": "R#0000230350P1",
    "status": "paid",
    "dates": {
        "issue_date": "2026-09-10",
        "raw_date_string": "10/09/69 11:30",
        "era_resolution": {"detected_era": "BE", "year_digits": 2,
                           "anchor_used": "TID#20260910000000005221682503"},
    },
    "issuer": {
        "legal_name": "CP ALL",
        "brand_name": "7-Eleven",
        "branch_name": "ประชาราษฎร์ 12",
        "branch_code": "02304",
        "tax_id": "0107542000011",
        "vat_registered": True,
    },
    "line_items": [
        {"line_number": 1, "description": "วอลล์ 2in1 ช็อกโก",
         "description_raw": "Hวอลล์ 2in1 ช็อกโก",
         "line_total": 4900, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 2, "description": "โค้ก 325 มล.",
         "description_raw": "โค้ก 325 มล.",
         "line_total": 3200, "quantity": 2, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
    ],
    "payments": [
        {"amount": 7700, "method": "truemoney_wallet",
         "method_raw": "ทรูวอลเล็ท7App"},
    ],
    "totals": {
        "grand_total": 7700, "subtotal": 7700, "discount_total": 400,
        "service_charge": 0,
        "total": 8100, "vatable_amount": None, "vat_amount": None,
        "vat_amount_computed": 504, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": "E02010000202474",
    "discarded_text": ["02314", "M-Stamp(บาท)", "3 ชิ้น",
                       "บิลนี้ประหยัด 4.00", ":0230463",
                       "0-2826-7777",
                       "** PayAtAll by Counter Service **",
                       "+42", "9143", "151269"],
    "field_confidence": {"totals.grand_total": 0.93,
                         "dates.issue_date": 0.95,
                         "issuer.tax_id": 0.99,
                         "document_number": 0.9},
    "source": {"kind": "ocr", "image_uri": "s16.jpg",
               "image_hash": "placeholder-hash-s16", "model": "hand-label"},
}

# S17: Zaab Ole Isaan restaurant invoice, 185.00, first invoice-typed
# seed and second faded-thermal member (contrast-boosted zooms to
# read). No tax ID, VAT rows, ABB marks or tender rows: unknown form,
# unpaid. Branch hides in the Staff row (สาขาห้วยขวาง); table,
# guest-count and item-count rows are traps.
S17_ZAABOLE_ISAAN = {
    "schema_version": "1.0",
    "document_type": "invoice",
    "form": "unknown",
    "can_claim_input_vat": False,
    "document_number": None,
    "status": "unpaid",
    "dates": {
        "issue_date": "2026-09-10",
        "raw_date_string": "10/09/2026 15:16",
        "era_resolution": {"detected_era": "AD", "year_digits": 4,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "แซ่บโอเล่ by เชฟแม่ยงตำซ่า",
        "brand_name": "แซ่บโอเล่",
        "branch_name": "ห้วยขวาง",
        "branch_code": None,
        "address": ("270/43, ซอยประชาสงเคราะห์ 45 รัชดาภิเษก "
                    "ดินแดง กรุงเทพมหานคร, 10400"),
        "tax_id": None,
        "phone": "0819203944",
        "vat_registered": None,
    },
    "line_items": [
        {"line_number": 1, "description": "นมหมูย่าง",
         "description_raw": "นมหมูย่าง",
         "line_total": 9000, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 2, "description": "ลาบเป็ด",
         "description_raw": "ลาบเป็ด",
         "line_total": 7000, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 3, "description": "ข้าวเหนียว",
         "description_raw": "ข้าวเหนียว",
         "line_total": 1000, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 4, "description": "โค้ก(ขวดเล็ก)375ML",
         "description_raw": "โค้ก(ขวดเล็ก)375ML",
         "line_total": 1500, "quantity": 1, "quantity_source": "column",
         "supply_type": "goods", "vat_flag": "unknown"},
    ],
    "payments": [],
    "totals": {
        "grand_total": 18500, "subtotal": 18500, "discount_total": 0,
        "total": 18500, "vatable_amount": None, "vat_amount": None,
        "vat_amount_computed": 1210, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": None,
    "discarded_text": ["Table: 2 นอก", "Guests: 1", "Items: 4"],
    "field_confidence": {"totals.grand_total": 0.97,
                         "dates.issue_date": 0.95},
    "source": {"kind": "ocr", "image_uri": "s17.jpg",
               "image_hash": "placeholder-hash-s17", "model": "hand-label"},
}

# S18: Pung Siam bakery ABB, Future Park Rangsit. Verified from 5 zoom
# crops: logo year is Thai digits (พ.ศ.๒๕๑๕ = 2515, duplicates the
# Arabic-digit body line used below); "ลูกค้าทั่วไป เงินสด" is a
# customer-type label, tender comes from the explicit BankTransfer row;
# VAT 4.51 = round(6900*7/107) pins the formula a third time (S13/S23);
# no barcode, no Power-by line — Version footer only.
S18_PUNGSIAM_FPARK = {
    "schema_version": "1.0",
    "document_type": "invoice",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "document_number": "RC6909130088",
    "status": "paid",
    "dates": {
        "issue_date": "2026-09-13",
        "raw_date_string": "13/09/2569 13:04",
        "era_resolution": {"detected_era": "BE", "year_digits": 4,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "บริษัท ปังสยาม พ.ศ.2515 จำกัด",
        "brand_name": "ปังสยาม",
        "branch_name": "ฟิวเจอร์พาร์ค รังสิต",
        "branch_code": "00012",
        "address": None,
        "tax_id": "0745557005220",
        "phone": "062-859-5951",
        "vat_registered": True,
    },
    "line_items": [
        {"line_number": 1, "description": "สเลอปี้ทูโทน",
         "description_raw": "สเลอปี้ทูโทน",
         "line_total": 6900, "quantity": 1, "quantity_source": "assumed",
         "supply_type": "goods", "vat_flag": "unknown"},
    ],
    "payments": [
        {"amount": 6900, "method": "bank_transfer",
         "method_raw": "BankTransfer:"},
    ],
    "totals": {
        "grand_total": 6900, "subtotal": 6900, "discount_total": 0,
        "total": 6900, "vatable_amount": 6449, "vat_amount": 451,
        "vat_amount_computed": 451, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": "E041310002A3489",
    "discarded_text": ["S/N# E720M01014", "เปิดโต๊ะ: 13:04",
                       "พิมพ์ใบเรียกเก็บเงิน: 13:04",
                       "ลูกค้าทั่วไป เงินสด", "เงินทอน: 0.00",
                       "หมายเหตุ:",
                       "ราคารวมภาษีมูลค่าเพิ่มแล้ว",
                       "Version (3.0.2502.1)"],
    "field_confidence": {"totals.grand_total": 0.97,
                         "totals.vat_amount": 0.93,
                         "dates.issue_date": 0.95,
                         "issuer.tax_id": 0.99,
                         "document_number": 0.93},
    "source": {"kind": "ocr", "image_uri": "s18.jpg",
               "image_hash": "placeholder-hash-s18", "model": "hand-label"},
}

# S19: Watsons The Street Ratchada ABB, 50.00 — sister slip to S13
# (same two products, same 50.00, same 328-vs-327 per-line-rounding
# gap absorbed by R3's +-1). Genuine slip inconsistency: doc number
# and barcode encode date 1003 while the header prints 30OCT2026 —
# gold issue_date follows the printed date. No E machine ID on the
# slip (POS(02)# is a terminal label, discarded); no phone key
# (02-0178899 is the call center, S13 precedent). SKU2 4th glyph
# reads C (309C76), differing from S13's 309086. Cashier PII omitted.
S19_WATSONS_RATCHADA = {
    "schema_version": "1.0",
    "document_type": "invoice",
    "form": "abbreviated",
    "can_claim_input_vat": False,
    "document_number": "634002100320260007",
    "status": "paid",
    "dates": {
        "issue_date": "2026-10-30",
        "raw_date_string": "30OCT2026 11:44:46",
        "era_resolution": {"detected_era": "AD", "year_digits": 4,
                           "anchor_used": None},
    },
    "issuer": {
        "legal_name": "watsons",
        "brand_name": "watsons",
        "branch_name": "WATSON THE STREET RATCHADA",
        "branch_code": "00634",
        "tax_id": "0105539086260",
        "vat_registered": True,
    },
    "line_items": [
        {"line_number": 1, "description": "#HDBRPMNightRepa@",
         "description_raw": "311773 #HDBRPMNightRepa@",
         "line_total": 2500, "quantity": 1, "quantity_source": "assumed",
         "supply_type": "goods", "vat_flag": "unknown"},
        {"line_number": 2, "description": "#HadabireiPr@",
         "description_raw": "309C76 #HadabireiPr@",
         "line_total": 2500, "quantity": 1, "quantity_source": "assumed",
         "supply_type": "goods", "vat_flag": "unknown"},
    ],
    "payments": [
        {"amount": 5000, "method": "qr_promptpay",
         "method_raw": "QR-Code",
         "external_ref": "EDC1791002675378943"},
    ],
    "totals": {
        "grand_total": 5000, "subtotal": 5000, "discount_total": 0,
        "total": 5000, "vatable_amount": 4672, "vat_amount": 328,
        "vat_amount_computed": 327, "non_vatable_amount": 0,
    },
    "vat_mode": "inclusive",
    "vat_rate_bp": 700,
    "currency": "THB",
    "pos_identifier": None,
    "discarded_text": ["POS(02)#", "2", "CHANGE 0.00",
                       "Loyalty acc.number 9930840807***",
                       "Opening Balance 30", "Earned value 2",
                       "Closing balance 32", "Tel: 02-0178899",
                       "ISSUER# PROMPTPAY", "TID# 73906592",
                       "TRACE# 103125", "R 002", "C00C5", "#0007",
                       "3706340211441120261003"],
    "field_confidence": {"totals.grand_total": 0.95,
                         "totals.vat_amount": 0.9,
                         "dates.issue_date": 0.95,
                         "issuer.tax_id": 0.99,
                         "document_number": 0.9},
    "source": {"kind": "ocr", "image_uri": "s19.jpg",
               "image_hash": "placeholder-hash-s19", "model": "hand-label"},
}

SEEDS = {
    "S1": S1_CAFE_AMAZON,
    "S2": S2_LOTUS,
    "S7": S7_CPAXTRA_6662,
    "S8": S8_JAYTO_SEAFOOD,
    "S9": S9_DQ_JPARK,
    "S10": S10_TSURUHA_JPARK,
    "S11": S11_PABOON_CAFE3,
    "S12": S12_SBUX_ESPLANADE2,
    "S13": S13_WATSONS_ESPLANADE,
    "S14": S14_JONES_DELIVERY,
    "S15": S15_TOPS_ESPLANADE,
    "S16": S16_SEVEN_02304B,
    "S17": S17_ZAABOLE_ISAAN,
    "S18": S18_PUNGSIAM_FPARK,
    "S19": S19_WATSONS_RATCHADA,
    "S3": S3_JONES,
    "S4": S4_STARBUCKS,
    "S5": S5_SEVEN,
    "S6": S6_ETOILE,
    "S21": S21_RADNA,
    "S22": S22_SEVEN2,
    "S23": S23_OASIS,
}


def fresh_seed(name):
    return copy.deepcopy(SEEDS[name])
