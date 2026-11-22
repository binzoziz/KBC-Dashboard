from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from zipfile import ZipFile
import io

import pdfplumber

MENU = json.loads((Path(__file__).parent / "menu.json").read_text(encoding="utf-8"))


def norm(value: Any) -> str:
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", value.upper())


MENU_MAP = {norm(item): {"item": item, "modal": modal, "jual": jual} for item, modal, jual in MENU}

ORDER_NAME_MAP = {
    norm("VIP WEEKDAY NORMA"): "VIP WEEKDAY NORMAL",
    norm("HAPPY HOUR WEEKDA"): "HAPPY HOUR WEEKDAY",
    norm("WEEKDAY 16.00 - 18"): "WEEKDAY 16.00 - 18.00",
    norm("VIP WEEKDAY 16.00 - 1"): "VIP WEEKDAY 16.00 - 18.00",
    norm("HAPPY HOUR WEEKEN"): "HAPPY HOUR WEEKEND",
    norm("VIP HAPPY HOUR WEEK"): "VIP HAPPY HOUR WEEKEND",
    norm("VIP WEEKEND NORMA"): "VIP WEEKEND NORMAL",
    norm("WEEKDAY NORMAL A"): "WEEKDAY NORMAL ALL DAY",
    norm("WEEKEND NORMAL A"): "WEEKEND NORMAL ALL DAY",
    norm("PAKET FRE 3 JAM"): "PAKET FREE 3 JAM",
    norm("HAPPY HOUR WEKEN"): "HAPPY HOUR WEEKEND",
    norm("30K"): "PROMO 30K",
    norm("NORMAL"): "WEEKEND NORMAL",
    norm("WEEKEND NORMA"): "WEEKEND NORMAL",
}


def normalize_order_name(value: str) -> str:
    """Standardize known KBC package names while preserving other labels as-is."""
    return ORDER_NAME_MAP.get(norm(value), value)


def money(value: str) -> int | None:
    value = str(value or "").strip().replace(",", "").replace("Rp", "")
    return int(float(value)) if re.fullmatch(r"\d+(?:\.\d+)?", value) else None


def parse_date(value: str) -> str:
    fmt = "%Y/%m/%d" if value[:4].isdigit() else "%d/%m/%Y"
    return datetime.strptime(value, fmt).strftime("%Y-%m-%d")


def classify_item(raw: str, price: int) -> tuple[str | None, int | None, str]:
    n = norm(raw)
    if n in {"SPAGHETTIBOLOGNESE", "SPAGHETTICARBONARA"} or n.startswith("SPAGHETTIBOLOGN") or n.startswith("SPAGHETTICARBON"):
        return "SPAGHETTI (BOLOGNESE/CARBONARA)", 20000, "VARIAN DINORMALISASI; HARGA HISTORIS DIPERTAHANKAN"
    if n in MENU_MAP:
        m = MENU_MAP[n]
        status = "OK" if price == m["jual"] else "HARGA HISTORIS BERBEDA"
        return m["item"], m["modal"], status

    aliases = {
        "AIRPUTIHES": "AIR MINERAL",
        "SPRIT": "SPRITE",
        "FRENCHFRIESREGU": "FRENCH FRIES",
        "FRENCHFRIESREGULAR": "FRENCH FRIES",
        "TEHPAKET": "TEH",
    }
    if n in aliases:
        m = MENU_MAP[norm(aliases[n])]
        return m["item"], m["modal"], "ALIAS; HARGA HISTORIS BERBEDA" if price != m["jual"] else "ALIAS"
    if n.startswith("FRENCHFRIESPAK"):
        m = MENU_MAP[norm("FRENCH FRIES")]
        return m["item"], m["modal"], "PAKET; HARGA PDF DIPERTAHANKAN"
    if n == "SUSUPUTIH":
        m = MENU_MAP[norm("SUSU VANILLA")]
        status = "ALIAS SUSU PUTIH" if price == m["jual"] else "ALIAS SUSU PUTIH; HARGA HISTORIS BERBEDA"
        return m["item"], m["modal"], status
    if n == "SPAGHETTI" and price == 35000:
        return "SPAGHETTI (BOLOGNESE/CARBONARA)", 20000, "VARIAN PDF TIDAK TERCANTUM"
    if n.startswith("NASIGORENGBAKS"):
        m = MENU_MAP[norm("NASI GORENG BAKSO")]
        return m["item"], m["modal"], "NAMA COCOK; HARGA HISTORIS BERBEDA"
    if n.startswith("ROIPANGGANGSTRA"):
        m = MENU_MAP[norm("ROTI PANGGANG STRAWBERRY")]
        return m["item"], m["modal"], "TYPO PDF DINORMALISASI"

    candidates = [row for row in MENU if norm(row[0]).startswith(n) and len(n) >= 8]
    by_price = [row for row in candidates if row[2] == price]
    if len(by_price) == 1:
        return by_price[0][0], by_price[0][1], "NAMA TERPOTONG; DIPILIH DENGAN HARGA"
    if len(by_price) > 1:
        costs = {(row[1], row[2]) for row in by_price}
        if len(costs) == 1 and n.startswith(norm("ROTI PANGGANG CO")):
            return "ROTI PANGGANG COKLAT (COKLAT/CRUNCHY)", by_price[0][1], "VARIAN DIGABUNG; MODAL/HARGA SAMA"
        if len(costs) == 1 and n.startswith(norm("ROTI PANGGANG ST")):
            return "ROTI PANGGANG STRAWBERRY (KEJU/COKELAT)", by_price[0][1], "VARIAN DIGABUNG; MODAL/HARGA SAMA"
    if len(candidates) == 1:
        return candidates[0][0], candidates[0][1], "NAMA TERPOTONG; HARGA HISTORIS DIPERTAHANKAN"
    if n.startswith(norm("FRENCH FRIES CRUN")):
        m = MENU_MAP[norm("FRENCH FRIES CRUNCHY")]
        return m["item"], m["modal"], "NAMA TERPOTONG; HARGA HISTORIS DIPERTAHANKAN"
    if n.startswith(norm("FRENCH FRIES NUGG")):
        m = MENU_MAP[norm("FRENCH FRIES NUGGET")]
        return m["item"], m["modal"], "NAMA TERPOTONG"
    if n.startswith(norm("ROTI PANGGANG ST")) and price == 20000:
        return "ROTI PANGGANG STRAWBERRY", 6188, "NAMA DISTANDARKAN; VARIAN TIDAK TERBACA; HARGA HISTORIS DIPERTAHANKAN"
    return None, None, "CEK MANUAL; BELUM ADA PEMETAAN"


def source_from_name(name: str) -> str | None:
    match = re.search(r"\bcom\s*([12])\b|\bcom([12])\b", name, re.I)
    if not match:
        return None
    return "COM1" if (match.group(1) or match.group(2)) == "1" else "COM2"


def _get_id(words: list[dict[str, Any]], limit: float = 0.18) -> str | None:
    for word in words:
        if word["x0"] < 842 * limit and re.fullmatch(r"\d{8,16}", word["text"]):
            return word["text"]
    return None


def _date(words: list[dict[str, Any]]) -> str | None:
    for word in words:
        text = word["text"]
        if re.fullmatch(r"(?:20\d{2}/\d{2}/\d{2}|\d{2}/\d{2}/20\d{2})", text):
            return text
    return None


def _times(words: list[dict[str, Any]]) -> list[str]:
    return [w["text"] for w in sorted(words, key=lambda x: x["x0"]) if re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", w["text"])]


def _lines(page) -> list[list[dict[str, Any]]]:
    words = page.extract_words(x_tolerance=1.5, y_tolerance=2, keep_blank_chars=False)
    words.sort(key=lambda w: (w["top"], w["x0"]))
    result: list[list[dict[str, Any]]] = []
    for word in words:
        if not result or abs(word["top"] - result[-1][0]["top"]) > 4.5:
            result.append([word])
        else:
            result[-1].append(word)
    return result


def _amounts(words: list[dict[str, Any]], width: float, bands: list[tuple[float, float]]) -> list[int | None]:
    bins: list[list[str]] = [[] for _ in bands]
    for word in words:
        x = word["x0"] / width
        for i, (lo, hi) in enumerate(bands):
            if lo <= x < hi:
                bins[i].append(word["text"])
                break
    return [money("".join(bucket)) for bucket in bins]


def _parse_table_line(words: list[dict[str, Any]], width: float, source: str) -> dict[str, Any] | None:
    words = sorted(words, key=lambda w: w["x0"])
    order_id, raw_date, times = _get_id(words), _date(words), _times(words)
    if not order_id or not raw_date or len(times) < 3:
        return None
    cells = {"table": [], "guest": [], "order": []}
    for word in words:
        x, text = word["x0"] / width, word["text"].strip()
        if text == order_id or text == raw_date or re.fullmatch(r"\d{1,2}:\d{2}:\d{2}", text):
            continue
        if .245 <= x < .315:
            cells["table"].append(text)
        elif source == "COM1" and .315 <= x < .375:
            cells["guest"].append(text)
        elif source == "COM1" and .375 <= x < .545:
            cells["order"].append(text)
        elif source == "COM2" and .47 <= x < .525:
            cells["guest"].append(text)
        elif source == "COM2" and .525 <= x < .675:
            cells["order"].append(text)
    values = _amounts(words, width, [(.675, .745), (.745, .805), (.805, .88), (.88, 1.01)])
    if any(value is None for value in values):
        return None
    table_name = " ".join(cells["table"]).strip()
    if source == "COM2" and norm(table_name) == "TABLEVIP":
        table_name = "Table 7"
    return {
        "ID Unik": f"{source}-{order_id}", "No Order": order_id, "Tanggal": parse_date(raw_date),
        "Table Number": table_name, "Tamu": " ".join(cells["guest"]).strip(), "Order": normalize_order_name(" ".join(cells["order"]).strip()),
        "Mulai": times[-2], "Selesai": times[-1], "Table": values[0], "F&B": values[1],
        "Sub total": values[2], "Total": values[3], "Sumber": source,
    }


FNB_START = re.compile(r"^\s*(?P<invoice>\d{8,16})\s+(?P<date>20\d{2}/\d{2}/\d{2}|\d{2}/\d{2}/20\d{2})\s+(?P<time>\d{1,2}:\d{2}:\d{2})\s+(?P<rest>.+?)\s*$")
FNB_TAIL = re.compile(r"^(?P<item>.+?)\s+(?P<modal>\d[\d,]*)\s+(?P<price>\d[\d,]*)\s+(?P<qty>\d+)(?:\s|$)")


def _read_layout_text(pdf_bytes: bytes) -> str:
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("Poppler pdftotext belum terpasang. Install Poppler lalu jalankan ulang bot.")
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as file:
            file.write(pdf_bytes)
            path = file.name
        completed = subprocess.run([exe, "-layout", path, "-"], capture_output=True, check=True, timeout=90)
        return completed.stdout.decode("utf-8", "replace")
    finally:
        if path:
            Path(path).unlink(missing_ok=True)


def _parse_fnb_text(text: str, source: str) -> list[dict[str, Any]]:
    rows = []
    for line in text.splitlines():
        match = FNB_START.match(line)
        if not match:
            continue
        details = FNB_TAIL.match(match.group("rest"))
        if not details:
            continue
        item = details.group("item").strip()
        pdf_modal = money(details.group("modal"))  # intentionally ignored
        price, qty = money(details.group("price")), int(details.group("qty"))
        canonical, modal, status = classify_item(item, price)
        rows.append({
            "No Faktur": match.group("invoice"), "Tanggal": parse_date(match.group("date")),
            "Jam": match.group("time"), "Nama PDF": item, "F&B": canonical or item,
            "Modal": modal, "Jual": price, "Qty": qty, "Sub total": price * qty,
            "Sumber": source, "Status Pemetaan": status, "_Modal PDF Diabaikan": pdf_modal,
        })
    return rows


def parse_pdf(pdf_bytes: bytes, filename: str, source: str) -> tuple[str, list[dict[str, Any]]]:
    table_rows: list[dict[str, Any]] = []
    report_type = None
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if len(pdf.pages) > 1000:
            raise ValueError("PDF terlalu panjang untuk diproses dalam satu upload.")
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "no order" in text.lower() and "mulai" in text.lower() and "selesai" in text.lower():
                report_type = "TABLE"
                for line in _lines(page):
                    row = _parse_table_line(line, page.width, source)
                    if row:
                        table_rows.append(row)
            if "no faktur" in text.lower() and "modal" in text.lower():
                report_type = "FNB"
    if report_type == "TABLE":
        if not table_rows:
            raise ValueError("Format laporan terdeteksi sebagai Table, tetapi tidak ada baris transaksi terbaca.")
        ids = [row["ID Unik"] for row in table_rows]
        if len(ids) != len(set(ids)):
            raise ValueError("Nomor order yang sama terulang dalam PDF Table ini. File ditahan untuk pemeriksaan.")
        return "TABLE", table_rows
    if report_type == "FNB":
        rows = _parse_fnb_text(_read_layout_text(pdf_bytes), source)
        if not rows:
            raise ValueError("Format laporan terdeteksi sebagai F&B, tetapi tidak ada baris transaksi terbaca.")
        unresolved = sorted({row["Nama PDF"] for row in rows if row["Modal"] is None})
        if unresolved:
            raise ValueError("Nama item belum bisa dipetakan ke daftar harga; tidak ada data yang ditulis: " + ", ".join(unresolved[:15]))
        # Combine identical product lines in one invoice to keep the master tidy.
        groups: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in rows:
            # Preserve Bolognese and Carbonara as separate source lines after
            # standardizing both display names to the shared master label.
            raw_name = norm(row["Nama PDF"])
            distinct_variant = raw_name if raw_name.startswith("SPAGHETTIBOLOGN") or raw_name.startswith("SPAGHETTICARBON") else ""
            key = (source, row["No Faktur"], row["Tanggal"], row["Jam"], norm(row["F&B"]), row["Jual"], row["Modal"], distinct_variant)
            if key not in groups:
                groups[key] = dict(row)
            else:
                groups[key]["Qty"] += row["Qty"]
                groups[key]["Sub total"] = groups[key]["Jual"] * groups[key]["Qty"]
        clean = []
        invoice_indexes: dict[tuple[str, str], int] = defaultdict(int)
        for row in groups.values():
            invoice_key = (source, row["No Faktur"])
            invoice_indexes[invoice_key] += 1
            # Same source/invoice/sequence scheme as the prepared historical master.
            row["ID Unik"] = f"{source}-{row['No Faktur']}-{invoice_indexes[invoice_key]:02d}"
            row.pop("_Modal PDF Diabaikan", None)
            clean.append(row)
        return "FNB", clean
    raise ValueError("Jenis PDF tidak dikenali. Kirim laporan Table atau F&B dari KBC.")


def parse_upload(filename: str, content: bytes, default_source: str | None = None) -> dict[str, list[dict[str, Any]]]:
    """Parse one PDF or a ZIP containing PDFs; any bad file stops the whole upload."""
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("Ukuran file lebih dari 20 MB.")
    pdfs: list[tuple[str, bytes]] = []
    if filename.lower().endswith(".pdf"):
        pdfs = [(filename, content)]
    elif filename.lower().endswith(".zip"):
        with ZipFile(io.BytesIO(content)) as archive:
            members = [m for m in archive.infolist() if not m.is_dir() and m.filename.lower().endswith(".pdf")]
            if not members or len(members) > 50 or sum(m.file_size for m in members) > 80 * 1024 * 1024:
                raise ValueError("ZIP harus berisi 1–50 PDF dengan total ukuran maksimal 80 MB.")
            pdfs = [(m.filename, archive.read(m)) for m in members]
    else:
        raise ValueError("Kirim file PDF atau ZIP berisi PDF.")

    result: dict[str, list[dict[str, Any]]] = {"TABLE": [], "FNB": []}
    for pdf_name, pdf_bytes in pdfs:
        source = source_from_name(pdf_name) or default_source or source_from_name(filename)
        if source not in {"COM1", "COM2"}:
            raise ValueError(f"Sumber COM1/COM2 belum jelas untuk {Path(pdf_name).name}. Kirim /com1 atau /com2 sebelum upload.")
        kind, rows = parse_pdf(pdf_bytes, pdf_name, source)
        result[kind].extend(rows)
    if not result["TABLE"] and not result["FNB"]:
        raise ValueError("Tidak ditemukan laporan transaksi di upload ini.")
    for kind in result:
        ids = [row["ID Unik"] for row in result[kind]]
        if len(ids) != len(set(ids)):
            raise ValueError(f"ID transaksi ganda ditemukan dalam upload {kind}. Tidak ada data yang ditulis.")
    return result
