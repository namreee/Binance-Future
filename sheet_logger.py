# sheet_logger.py
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# JSON dosyanın yolunu buraya yaz
SERVICE_ACCOUNT_FILE = "futures-trading-logs-965c986957e0.json"

# Spreadsheet ID'ni buraya yaz
SPREADSHEET_ID = "13cuMEl7RFTT_OR_dNhNZb-o9e96I4-qvxVblry5LK5U"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

creds = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
client = gspread.authorize(creds)

sheet = client.open_by_key(SPREADSHEET_ID).sheet1

def log_trade(data):
    """
    data: dict
    {
        'symbol': str,
        'action': str,
        'quantity': float,
        'entry_price': float,
        'stop_price': float,
        'trailing_activation': float,
        'trailing_callback': float,
        'note': str,
        'timeframe': str,
        'leverage': int,
        'order_id': str,
        'executed': str
    }
    """
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    row = [
        now,
        data.get("symbol", ""),
        data.get("action", ""),
        str(data.get("quantity", "")),
        str(data.get("entry_price", "")),
        str(data.get("stop_price", "")),
        str(data.get("trailing_activation", "")),
        str(data.get("trailing_callback", "")),
        data.get("timeframe", ""),
        str(data.get("leverage", "")),
        data.get("order_id", ""),
        data.get("executed", ""),
        data.get("note", "")
    ]
    sheet.append_row(row, value_input_option="USER_ENTERED")
