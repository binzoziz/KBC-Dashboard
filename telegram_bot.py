from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
from pathlib import Path
from typing import Any
from contextlib import asynccontextmanager

import gspread
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
import uvicorn

from kbc_processor import parse_upload

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kbc-import-bot")

TABLE_COLUMNS = ["ID Unik", "No Order", "Tanggal", "Table Number", "Tamu", "Order", "Mulai", "Selesai", "Table", "F&B", "Sub total", "Total", "Sumber"]
FNB_COLUMNS = ["ID Unik", "No Faktur", "Tanggal", "Jam", "F&B", "Modal", "Jual", "Qty", "Sub total", "Nama PDF", "Sumber", "Status Pemetaan"]


def allowed_ids() -> set[int]:
    raw = os.getenv("ALLOWED_TELEGRAM_USER_IDS", "")
    return {int(value.strip()) for value in raw.split(",") if value.strip().isdigit()}


def is_authorized(update: Update) -> bool:
    user = update.effective_user
    return bool(user and user.id in allowed_ids())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            "Bot import laporan KBC siap. Kirim /myid untuk melihat ID Telegram-mu. "
            "Admin perlu memasukkan ID itu ke ALLOWED_TELEGRAM_USER_IDS. Setelah diizinkan, kirim PDF/ZIP dengan caption /com1 atau /com2, atau pastikan nama file memuat COM1/COM2."
        )


async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if update.effective_message and user:
        await update.effective_message.reply_text(f"Telegram user ID kamu: {user.id}")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            "Cara pakai:\n"
            "1. Kirim PDF/ZIP dengan caption /com1 atau /com2 sesuai komputer sumber. Nama file yang memuat COM1/COM2 juga dikenali otomatis.\n"
            "2. Bisa juga kirim /com1 atau /com2 sebelum file, lalu kirim PDF/ZIP.\n"
            "3. Bot mengenali otomatis laporan Table atau F&B, memetakan nama item, lalu append baris baru.\n"
            "4. Kirim ulang file aman: ID transaksi dipakai untuk melewati baris yang sudah masuk.\n"
            "Perintah: /com1, /com2, /source, /myid, /help. Kirim laporan lewat chat pribadi dengan bot."
        )


async def select_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return
    if not is_authorized(update):
        await update.effective_message.reply_text("Akun ini belum diizinkan mengirim data. Minta admin memasukkan Telegram user ID-mu ke daftar akses.")
        return
    command = update.effective_message.text.split()[0].split("@")[0].lower()
    source = "COM1" if command == "/com1" else "COM2"
    if os.getenv("BOT_MODE", "polling").strip().lower() == "webhook":
        await update.effective_message.reply_text(
            f"Sumber {source}. Untuk memastikan sumber terbaca di server, kirim file dengan caption /{source.lower()} "
            f"atau sertakan {source} di nama file."
        )
    else:
        context.user_data["source"] = source
        await update.effective_message.reply_text(f"Sumber disetel ke {source}. Sekarang kirim PDF atau ZIP.")


async def current_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(f"Sumber saat ini: {context.user_data.get('source', 'belum disetel')}")


def _col_letter(number: int) -> str:
    result = ""
    while number:
        number, rem = divmod(number - 1, 26)
        result = chr(65 + rem) + result
    return result


def _worksheet(book: Any, title: str, required: list[str]):
    try:
        ws = book.worksheet(title)
    except gspread.WorksheetNotFound:
        raise RuntimeError(f"Tab Google Sheets '{title}' tidak ditemukan. Periksa nilai TABLE_WORKSHEET/FNB_WORKSHEET.")
    headers = ws.row_values(1)
    if not any(str(h).strip() for h in headers):
        ws.update(range_name=f"A1:{_col_letter(len(required))}1", values=[required], value_input_option="RAW")
        headers = list(required)
    elif "ID Unik" not in headers and len(ws.get_all_values()) > 1:
        raise RuntimeError(f"Tab '{title}' sudah berisi data tetapi belum memiliki kolom ID Unik. Gunakan master siap impor yang sudah diberi ID agar bot dapat mencegah duplikasi.")
    missing = [name for name in required if name not in headers]
    if missing:
        start = len(headers) + 1
        end = start + len(missing) - 1
        ws.update(range_name=f"{_col_letter(start)}1:{_col_letter(end)}1", values=[missing], value_input_option="RAW")
        headers.extend(missing)
    return ws, headers


def _append_new(book: Any, title: str, required: list[str], rows: list[dict[str, Any]]) -> tuple[int, int]:
    if not rows:
        return 0, 0
    ws, headers = _worksheet(book, title, required)
    id_column = headers.index("ID Unik") + 1
    existing = set(value for value in ws.col_values(id_column)[1:] if value)
    fresh = []
    skipped = 0
    for row in rows:
        identity = str(row["ID Unik"])
        if identity in existing:
            skipped += 1
            continue
        existing.add(identity)
        fresh.append([row.get(header, "") for header in headers])
    if fresh:
        # Chunk requests to stay within Sheets API payload limits.
        for offset in range(0, len(fresh), 500):
            ws.append_rows(fresh[offset:offset + 500], value_input_option="USER_ENTERED", insert_data_option="INSERT_ROWS")
    return len(fresh), skipped


def _write_to_sheets(data: dict[str, list[dict[str, Any]]]) -> dict[str, tuple[int, int]]:
    credential_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")
    spreadsheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    if not spreadsheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID belum diisi pada .env.")
    credential_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if credential_json:
        try:
            client = gspread.service_account_from_dict(json.loads(credential_json))
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON bukan JSON service account yang valid.") from exc
    else:
        if not Path(credential_file).is_file():
            raise RuntimeError(f"File service account tidak ditemukan: {credential_file}")
        client = gspread.service_account(filename=credential_file)
    book = client.open_by_key(spreadsheet_id)
    table_name = os.getenv("TABLE_WORKSHEET", "Billiard Master")
    fnb_name = os.getenv("FNB_WORKSHEET", "F&B Master")
    return {
        "TABLE": _append_new(book, table_name, TABLE_COLUMNS, data["TABLE"]),
        "FNB": _append_new(book, fnb_name, FNB_COLUMNS, data["FNB"]),
    }


async def receive_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not message.document:
        return
    if not is_authorized(update):
        await message.reply_text("Akun ini belum diizinkan mengirim data. Minta admin memasukkan Telegram user ID-mu ke daftar akses.")
        return
    document = message.document
    filename = document.file_name or "laporan.pdf"
    if document.file_size and document.file_size > 20 * 1024 * 1024:
        await message.reply_text("File lebih dari 20 MB. Pecah ZIP atau kirim PDF satu per satu.")
        return
    caption = message.caption or ""
    caption_source = "COM1" if "/com1" in caption.lower() else "COM2" if "/com2" in caption.lower() else None
    default_source = caption_source or context.user_data.get("source")
    if os.getenv("BOT_MODE", "polling").strip().lower() == "webhook" and not caption_source:
        default_source = None
    await message.reply_text(f"Saya sedang membaca {filename}. Data baru akan ditulis setelah seluruh file lolos pembacaan dan pemetaan.")
    try:
        tg_file = await context.bot.get_file(document.file_id)
        content = bytes(await tg_file.download_as_bytearray())
        parsed = await asyncio.to_thread(parse_upload, filename, content, default_source)
        result = await asyncio.to_thread(_write_to_sheets, parsed)
        table_added, table_skipped = result["TABLE"]
        fnb_added, fnb_skipped = result["FNB"]
        await message.reply_text(
            "Import selesai.\n"
            f"Table: {table_added:,} baris baru, {table_skipped:,} dilewati karena sudah ada.\n"
            f"F&B: {fnb_added:,} baris baru, {fnb_skipped:,} dilewati karena sudah ada.\n"
            "Modal diambil dari daftar menu. Harga Jual transaksi PDF tetap dipertahankan."
        )
    except Exception as exc:
        log.exception("Gagal memproses upload %s", filename)
        await message.reply_text(f"Proses berhenti karena terjadi kesalahan. Jika sebagian tab sudah terisi, kirim ulang file dengan aman—ID Unik akan melewati baris yang sudah masuk.\nAlasan: {exc}")


def build_application() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN belum diisi pada .env.")
    if not os.getenv("ALLOWED_TELEGRAM_USER_IDS", "").strip():
        raise RuntimeError("ALLOWED_TELEGRAM_USER_IDS harus diisi agar bot tidak menerima laporan dari akun umum.")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("com1", select_source))
    app.add_handler(CommandHandler("com2", select_source))
    app.add_handler(CommandHandler("source", current_source))
    app.add_handler(MessageHandler(filters.Document.ALL, receive_document))
    return app


telegram_app: Application | None = None
webhook_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(_: FastAPI):
    global telegram_app
    telegram_app = build_application()
    await telegram_app.initialize()
    await telegram_app.start()

    webhook_url = os.getenv("WEBHOOK_URL", "").strip()
    if webhook_url:
        secret = os.getenv("WEBHOOK_SECRET", "").strip()
        if not secret:
            raise RuntimeError("WEBHOOK_SECRET wajib diisi saat WEBHOOK_URL digunakan.")
        path = os.getenv("WEBHOOK_PATH", "telegram-webhook").strip("/")
        if not webhook_url.rstrip("/").endswith("/" + path):
            raise RuntimeError(f"WEBHOOK_URL harus berakhir dengan /{path}.")
        await telegram_app.bot.set_webhook(
            url=webhook_url,
            secret_token=secret,
            allowed_updates=Update.ALL_TYPES,
        )
        log.info("Telegram webhook aktif di %s", webhook_url)
    else:
        log.warning("WEBHOOK_URL belum diisi; layanan aktif tetapi Telegram belum diarahkan ke webhook.")

    try:
        yield
    finally:
        await telegram_app.stop()
        await telegram_app.shutdown()
        telegram_app = None


web_app = FastAPI(lifespan=lifespan)


@web_app.get("/")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "kbc-telegram-importer"}


@web_app.post("/{webhook_path}")
async def telegram_webhook(webhook_path: str, request: Request) -> dict[str, str]:
    expected_path = os.getenv("WEBHOOK_PATH", "telegram-webhook").strip("/")
    if webhook_path != expected_path:
        raise HTTPException(status_code=404, detail="Not found")

    secret = os.getenv("WEBHOOK_SECRET", "").strip()
    provided_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not secret or not hmac.compare_digest(provided_secret, secret):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    if telegram_app is None or not telegram_app.running:
        raise HTTPException(status_code=503, detail="Bot is starting")
    try:
        update_data = await request.json()
        update = Update.de_json(update_data, telegram_app.bot)
        # Keep work inside the HTTP request so Cloud Run keeps CPU allocated
        # while a PDF is parsed and rows are appended to Google Sheets.
        async with webhook_lock:
            await telegram_app.process_update(update)
    except Exception:
        log.exception("Webhook menerima payload yang tidak valid")
        raise HTTPException(status_code=400, detail="Invalid Telegram update")
    return {"ok": "true"}


def main() -> None:
    mode = os.getenv("BOT_MODE", "polling").strip().lower()
    if mode == "webhook":
        port = int(os.getenv("PORT", "8080"))
        log.info("KBC Telegram importer berjalan dalam mode webhook pada port %s", port)
        uvicorn.run(web_app, host="0.0.0.0", port=port)
        return
    if mode != "polling":
        raise RuntimeError("BOT_MODE hanya boleh bernilai polling atau webhook.")
    app = build_application()
    log.info("KBC Telegram importer berjalan; hentikan dengan Ctrl+C.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
