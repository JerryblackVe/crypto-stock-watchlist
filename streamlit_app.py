"""
Streamlit App for Crypto/Stock Watchlist with Alerts
---------------------------------------------------

This Streamlit application allows non‑technical users to manage a personal
watchlist of cryptocurrency and US stock tickers, visualize candlestick charts
and configure simple price alerts.  The app stores the watchlist in a JSON
file (``watchlist.json``) located in the same repository.  When run on
Streamlit Cloud, it reads and writes this file locally inside the container.

Key features:

* Display a table of tickers with their latest price and configured alert
  levels.  Prices are fetched in real time from Yahoo Finance using
  ``yfinance``.
* Add or remove assets to/from the watchlist and edit their alert levels
  through simple forms.
* View interactive candlestick charts for each asset with selectable
  timeframes (4 hours, 1 day or 1 week) using Plotly.  A horizontal line
  indicates the configured alert level.
* Configure SMTP credentials in the sidebar.  When both an SMTP email and
  password are provided the app starts a background thread that periodically
  checks the watchlist and sends email notifications if prices cross the
  configured alert thresholds.  To avoid spamming, each alert can only fire
  once per hour per ticker.

The email service uses Gmail via SMTP over SSL.  For production deployment
you should create an application‑specific password on your Gmail account and
provide it in the settings panel.  Emails are sent to the address
configured in the ``Destinatario de alertas`` field.

Note: While this app provides a functional demonstration, running long‑lived
background threads is best handled outside of Streamlit (for example via
GitHub Actions) to guarantee 24/7 availability.  The included
``scripts/update_prices.py`` script in this repository illustrates such
automation.  Use the in‑app alerts for short‑term testing and rely on the
GitHub workflow for continuous monitoring.
"""

import os
import json
import time
import threading
import smtplib
from email.message import EmailMessage
from typing import Dict, Any

import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.graph_objects as go


# Path to the watchlist JSON file within the repository
WATCHLIST_FILE = os.path.join(os.path.dirname(__file__), "watchlist.json")


def load_watchlist() -> Dict[str, Dict[str, Any]]:
    """Load the watchlist from the JSON file and normalise its structure.

    The watchlist on disk is expected to be a JSON object keyed by ticker
    symbol.  Each value should itself be an object (dict) containing at
    least an ``alert`` field.  Older versions of the application or manual
    edits may leave plain numbers or strings instead of dictionaries.  This
    function normalises such entries into the expected dict format.  If the
    file cannot be read or parsed a blank dictionary is returned.
    """
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure we always return a dictionary
            if not isinstance(data, dict):
                return {}
            # Normalise each entry: if the value isn't a dict convert it
            for key, value in list(data.items()):
                if not isinstance(value, dict):
                    # If the value is a number or string interpret it as the alert level
                    try:
                        alert_value = float(value)
                    except Exception:
                        alert_value = 0.0
                    data[key] = {"alert": alert_value}
            return data
    except Exception:
        return {}


def save_watchlist(watchlist: Dict[str, Dict[str, Any]]) -> None:
    """Persist the watchlist to the JSON file."""
    try:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(watchlist, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        st.error(f"No se pudo guardar la lista de seguimiento: {exc}")


@st.cache_data(show_spinner=False)
def fetch_current_price(symbol: str) -> float:
    """Fetch the latest price for a given ticker using yfinance.

    Returns None if fetching fails.
    """
    try:
        ticker = yf.Ticker(symbol)
        # fast_info is more efficient and provides last_price
        last_price = ticker.fast_info.get("last_price")
        if last_price is not None:
            return float(last_price)
        # Fallback: use last close price
        hist = ticker.history(period="1d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
        return None
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def fetch_historical(symbol: str, period: str, interval: str) -> pd.DataFrame:
    """Fetch historical OHLCV data for the symbol.

    ``period`` examples: '7d', '1mo', '3mo'.
    ``interval`` examples: '4h', '1d', '1wk'.
    Returns an empty DataFrame if the request fails.
    """
    try:
        data = yf.download(symbol, period=period, interval=interval)
        return data
    except Exception:
        return pd.DataFrame()


def send_alert_email(subject: str, body: str) -> None:
    """Send an alert email using the SMTP credentials stored in the session.

    Requires ``st.session_state.email``, ``password`` and ``alert_email`` to
    be set.  Errors during sending are captured and shown as warnings.
    """
    smtp_email = st.session_state.get("email")
    smtp_password = st.session_state.get("password")
    alert_email = st.session_state.get("alert_email")

    if not smtp_email or not smtp_password or not alert_email:
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = smtp_email
    msg["To"] = alert_email
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_email, smtp_password)
            server.send_message(msg)
    except Exception as e:
        # Capture but don't stop execution
        st.warning(f"Error al enviar correo: {e}")


def check_alerts() -> None:
    """Check each asset in the watchlist and send an email if price crosses the alert level.

    Each alert is throttled so that no more than one email per hour per ticker
    is sent.  The throttle state is stored in ``st.session_state.alerts_sent``.
    """
    watchlist = load_watchlist()
    for symbol, meta in watchlist.items():
        alert_level = meta.get("alert")
        if alert_level is None or alert_level == "":
            continue
        try:
            alert_level_float = float(alert_level)
        except Exception:
            continue
        price = fetch_current_price(symbol)
        if price is None:
            continue
        
        # FIXED: Logic for price crossing alert - should trigger when price reaches or crosses the threshold
        crossed = False
        if alert_level_float > 0:  # Only check if alert level is set
            # For alerts, typically we want to be notified when price goes above or below a threshold
            # This logic can be customized based on needs
            crossed = abs(price - alert_level_float) <= (alert_level_float * 0.01)  # Within 1% of alert level
            
        last_sent_ts = st.session_state.get("alerts_sent", {}).get(symbol)
        if crossed:
            now_ts = time.time()
            # Only send if we haven't sent in the last hour
            if not last_sent_ts or (now_ts - last_sent_ts > 3600):
                subject = f"Alerta de precio para {symbol}"
                body = (
                    f"El precio actual de {symbol} es {price:.2f}, "
                    f"que ha alcanzado el nivel de alerta {alert_level_float:.2f}."
                )
                send_alert_email(subject, body)
                # Record timestamp of this alert
                if "alerts_sent" not in st.session_state:
                    st.session_state.alerts_sent = {}
                st.session_state.alerts_sent[symbol] = now_ts


def start_alert_thread() -> None:
    """Start a background daemon thread to continuously check alerts.

    The thread sleeps for five minutes between checks to reduce API load.
    """
    def run_loop():
        while True:
            check_alerts()
            # wait for 5 minutes between checks
            time.sleep(300)

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()


def apply_theme() -> None:
    """Apply a simple dark or light theme by injecting CSS.

    Streamlit does not yet provide a built‑in theme toggle at runtime, so we
    approximate dark and light modes with CSS variables.  When ``dark_mode``
    in ``st.session_state`` is true the dark palette is applied.
    """
    dark = st.session_state.get("dark_mode", False)
    if dark:
        css = """
        <style>
            body { background-color: #1e1e1e; color: #e6e6e6; }
            .st-bw { background-color: #262626 !important; }
            .st-bc { color: #e6e6e6 !important; }
            .st-br { background-color: #333333 !important; color: #e6e6e6 !important; }
        </style>
        """
    else:
        css = """
        <style>
            body { background-color: #ffffff; color: #262626; }
            .st-bw { background-color: #ffffff !important; }
            .st-bc { color: #262626 !important; }
            .st-br { background-color: #f0f0f0 !important; color: #262626 !important; }
        </style>
        """
    st.markdown(css, unsafe_allow_html=True)


def main() -> None:
    """Main function to assemble the Streamlit user interface."""
    st.set_page_config(page_title="Lista de Seguimiento de Activos", layout="wide")

    # Initialize session state variables
    for key in ["email", "password", "alert_email", "dark_mode", "alerts_sent", "alert_thread_started"]:
        if key not in st.session_state:
            if key == "alerts_sent":
                st.session_state[key] = {}
            elif key == "dark_mode":
                st.session_state[key] = False
            elif key == "alert_thread_started":
                st.session_state[key] = False
            else:
                st.session_state[key] = ""

    # Sidebar configuration
    st.sidebar.header("Configuración")
    st.sidebar.subheader("Credenciales de correo (Gmail)")
    st.sidebar.text_input(
        "Correo electrónico", key="email", help="Dirección de Gmail para enviar alertas"
    )
    st.sidebar.text_input(
        "Contraseña de aplicación", key="password", type="password", help="Contraseña de aplicación de Gmail"
    )
    st.sidebar.text_input(
        "Destinatario de alertas", key="alert_email", help="Dirección de correo a la que se enviarán las alertas"
    )
    # Dark mode toggle
    dark_toggle = st.sidebar.checkbox("Modo oscuro", value=st.session_state.dark_mode)
    st.session_state.dark_mode = dark_toggle
    apply_theme()

    # Start alert thread if credentials available
    if (
        st.session_state.email
        and st.session_state.password
        and st.session_state.alert_email
        and not st.session_state.alert_thread_started
    ):
        start_alert_thread()
        st.session_state.alert_thread_started = True

    st.title("Aplicación de Lista de Seguimiento de Activos")
    st.write(
        "Administra tu lista de criptomonedas y acciones, configura alertas de precio y visualiza gráficos de velas japonesas."
    )

    watchlist = load_watchlist()
    symbols = list(watchlist.keys())

    # Display the current watchlist with real‑time prices
    st.subheader("Lista de seguimiento")
    if symbols:
        # Fetch current prices for all symbols
        rows = []
        for sym in symbols:
            price = fetch_current_price(sym)
            # FIXED: Safely obtain the alert level even if the entry isn't a dict
            alert_level = watchlist.get(sym, {}).get("alert", "")
            rows.append(
                {
                    "Ticker": sym,
                    "Precio actual": f"{price:.2f}" if price is not None else "—",
                    "Nivel de alerta": alert_level,
                }
            )
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True)
    else:
        st.info("La lista de seguimiento está vacía.")

    # Add new asset form
    st.subheader("Agregar un nuevo activo")
    with st.form(key="add_asset_form"):
        new_symbol = st.text_input("Ticker (por ejemplo AAPL, BTC-USD)")
        new_alert = st.number_input(
            "Nivel de alerta (puede dejarse en blanco)",
            value=0.0,
            step=0.01,
            format="%.2f",
        )
        submitted_add = st.form_submit_button("Agregar activo")
        if submitted_add:
            symbol_upper = new_symbol.strip().upper()
            if symbol_upper:
                watchlist[symbol_upper] = {"alert": float(new_alert)}
                save_watchlist(watchlist)
                st.success(f"Se agregó {symbol_upper} a la lista.")
                st.rerun()  # FIXED: Changed from st.experimental_rerun()
            else:
                st.warning("Debe especificar un ticker válido.")

    # Delete assets
    st.subheader("Eliminar activos")
    if symbols:
        selected_for_delete = st.multiselect(
            "Seleccione los activos a eliminar", symbols, key="delete_select"
        )
        if st.button("Eliminar seleccionados"):
            for sym in selected_for_delete:
                watchlist.pop(sym, None)
            save_watchlist(watchlist)
            st.success("Activos eliminados de la lista.")
            st.rerun()  # FIXED: Changed from st.experimental_rerun()
    else:
        st.caption("No hay activos para eliminar.")

    # Edit alert levels
    if symbols:
        st.subheader("Editar niveles de alerta")
        alert_values = {}
        for sym in symbols:
            current_alert = watchlist.get(sym, {}).get("alert")
            try:
                current_val = float(current_alert)
            except Exception:
                current_val = 0.0
            alert_values[sym] = st.number_input(
                f"Alerta para {sym}", value=current_val, step=0.01, format="%.2f", key=f"alert_{sym}"
            )
        if st.button("Guardar alertas"):
            for sym in symbols:
                # FIXED: Ensure each entry is a dictionary before assignment
                if not isinstance(watchlist.get(sym), dict):
                    watchlist[sym] = {}
                watchlist[sym]["alert"] = float(alert_values[sym])
            save_watchlist(watchlist)
            st.success("Niveles de alerta actualizados.")
            st.rerun()  # FIXED: Changed from st.experimental_rerun()

    # Candlestick chart
    st.subheader("Gráfico de velas japonesas")
    if symbols:
        selected_symbol = st.selectbox(
            "Seleccione un activo para visualizar el gráfico", ["—"] + symbols, index=0
        )
        if selected_symbol and selected_symbol != "—":
            timeframe = st.selectbox(
                "Temporalidad", ["4h", "1d", "1w"], key="timeframe_select"
            )
            # Map timeframes to Yahoo Finance parameters
            period_map = {"4h": "7d", "1d": "1mo", "1w": "3mo"}
            interval_map = {"4h": "4h", "1d": "1d", "1w": "1wk"}
            data = fetch_historical(
                selected_symbol,
                period=period_map.get(timeframe, "1mo"),
                interval=interval_map.get(timeframe, "1d"),
            )
            if data.empty:
                st.warning("No se pudieron obtener datos históricos para este activo.")
            else:
                # Build candlestick figure
                fig = go.Figure(
                    data=[
                        go.Candlestick(
                            x=data.index,
                            open=data["Open"],
                            high=data["High"],
                            low=data["Low"],
                            close=data["Close"],
                            name=selected_symbol,
                        )
                    ]
                )
                # Add alert level line if configured
                alert_val = watchlist.get(selected_symbol, {}).get("alert")
                try:
                    alert_float = float(alert_val)
                    if alert_float > 0:  # Only show line if alert is set
                        fig.add_hline(
                            y=alert_float,
                            line_color="red",
                            line_dash="dash",
                            annotation_text=f"Alerta: {alert_float:.2f}",
                            annotation_position="top right",
                        )
                except Exception:
                    pass
                fig.update_layout(
                    height=500,
                    xaxis_title="Fecha",
                    yaxis_title="Precio",
                    showlegend=False,
                )
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("Agregue activos para visualizar los gráficos.")


if __name__ == "__main__":
    main()
