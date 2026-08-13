#!/usr/bin/env python3
# bts-simple.py - VERSIÓN CORREGIDA Y OPTIMIZADA

import os
import time
import logging
import threading
from datetime import datetime

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import routeros_api

# ============================================
# CONFIGURACIÓN
# ============================================
# Se removieron las credenciales explícitas por seguridad.
MIKROTIK_HOST = os.environ.get('MIKROTIK_HOST', '127.0.0.1')
MIKROTIK_USER = os.environ.get('MIKROTIK_USER', 'admin')
MIKROTIK_PASSWORD = os.environ.get('MIKROTIK_PASSWORD', '')
MIKROTIK_PORT = int(os.environ.get('MIKROTIK_PORT', 8728))
WAN_INTERFACE = os.environ.get('WAN_INTERFACE', 'sfp1-WAN-FIBEX')

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================
# DATOS THREAD-SAFE
# ============================================
class DataStore:
    def __init__(self):
        self._lock = threading.Lock()
        self.down = 0.0
        self.up = 0.0
        self.ts = ""
        self.online = False
        self.last_rx = 0
        self.last_tx = 0
        self.last_time = time.time()

    def update_data(self, down, up, ts, online):
        with self._lock:
            self.down = down
            self.up = up
            self.ts = ts
            self.online = online

    def get_data(self):
        with self._lock:
            return self.down, self.up, self.ts, self.online

data = DataStore()

# ============================================
# CONEXIÓN PERSISTENTE Y LECTURA
# ============================================
def fetch_data():
    connection = None
    api = None
    first_run = True
    
    while True:
        try:
            if connection is None:
                logger.info("🔗 Conectando a MikroTik...")
                connection = routeros_api.RouterOsApiPool(
                    MIKROTIK_HOST,
                    username=MIKROTIK_USER,
                    password=MIKROTIK_PASSWORD,
                    port=MIKROTIK_PORT,
                    plaintext_login=True
                )
                api = connection.get_api()
                first_run = True
                logger.info("✅ Conectado exitosamente")

            interfaces = api.get_resource('/interface').get()
            raw = next((i for i in interfaces if i.get('name') == WAN_INTERFACE), {})
            
            if raw:
                rx = int(raw.get('rx-byte', 0))
                tx = int(raw.get('tx-byte', 0))
                
                now = time.time()
                dt = now - data.last_time
                data.last_time = now
                
                if first_run:
                    data.last_rx = rx
                    data.last_tx = tx
                    first_run = False
                    data.update_data(0.0, 0.0, datetime.now().strftime("%H:%M:%S"), True)
                    logger.info("📊 Contadores inicializados")
                else:
                    if dt > 0:
                        diff_rx = rx - data.last_rx
                        diff_tx = tx - data.last_tx

                        # Manejo de reinicio de contadores/Overflow
                        if diff_rx < 0:
                            diff_rx = 0
                        if diff_tx < 0:
                            diff_tx = 0

                        d_mbps = (diff_rx * 8) / (dt * 1_000_000)
                        u_mbps = (diff_tx * 8) / (dt * 1_000_000)

                        down = round(d_mbps, 2) if d_mbps > 0 else 0.0
                        up = round(u_mbps, 2) if u_mbps > 0 else 0.0
                        ts = datetime.now().strftime("%H:%M:%S")

                        data.update_data(down, up, ts, True)

                    data.last_rx = rx
                    data.last_tx = tx

        except Exception as e:
            logger.error(f"Error de comunicación/red: {e}")
            data.update_data(0.0, 0.0, "N/A", False)
            
            # Limpieza de conexión para reconectar en el siguiente ciclo
            if connection:
                try:
                    connection.disconnect()
                except Exception:
                    pass
            connection = None
            api = None
            time.sleep(5)
        
        time.sleep(0.5)

threading.Thread(target=fetch_data, daemon=True).start()

# ============================================
# DASH APP
# ============================================
app = dash.Dash(__name__)
server = app.server

app.layout = html.Div(
    style={
        'backgroundColor': '#0a0e1a',
        'padding': '40px',
        'minHeight': '100vh',
        'display': 'flex',
        'flexDirection': 'column',
        'alignItems': 'center',
        'justifyContent': 'center',
        'fontFamily': 'Arial, sans-serif'
    },
    children=[
        html.H1(
            "📡 BTS - MONITOREO WAN",
            style={'color': '#00d4ff', 'fontSize': '36px'}
        ),
        html.Div(
            id='status',
            style={'color': '#00ff88', 'fontSize': '18px', 'marginTop': '20px'}
        ),
        html.Div(
            style={
                'display': 'flex',
                'gap': '60px',
                'marginTop': '30px',
                'fontSize': '32px',
                'fontWeight': 'bold'
            },
            children=[
                html.Div(id='down', style={'color': '#00d4ff'}),
                html.Div(id='up', style={'color': '#ffaa00'})
            ]
        ),
        dcc.Interval(id='tick', interval=500)
    ]
)

# ============================================
# CALLBACK
# ============================================
@app.callback(
    [Output('down', 'children'),
     Output('up', 'children'),
     Output('status', 'children')],
    [Input('tick', 'n_intervals')]
)
def update(n):
    down_val, up_val, ts_val, is_online = data.get_data()
    
    down_text = f"▼ DOWN: {down_val:.1f} Mbps"
    up_text = f"▲ UP: {up_val:.1f} Mbps"
    status_text = f"🟢 {ts_val}" if is_online else "🔴 Desconectado"
    
    return down_text, up_text, status_text

# ============================================
# INICIO
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    app.run(host='0.0.0.0', port=port, debug=False)
