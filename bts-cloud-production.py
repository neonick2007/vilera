# bts-simple.py - VERSIÓN MÍNIMA PARA PROBAR

import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objects as go
import time
import routeros_api
from datetime import datetime
import threading
import os
import logging

# ============================================
# CONFIGURACIÓN
# ============================================
MIKROTIK_HOST = os.environ.get('MIKROTIK_HOST', '190.120.249.39')
MIKROTIK_USER = os.environ.get('MIKROTIK_USER', 'neoapi')
MIKROTIK_PASSWORD = os.environ.get('MIKROTIK_PASSWORD', 'Xradio01*!')
MIKROTIK_PORT = int(os.environ.get('MIKROTIK_PORT', 8728))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# DATOS SIMPLES
# ============================================
class DataStore:
    def __init__(self):
        self.down = 0
        self.up = 0
        self.ts = ""
        self.online = False
        self.last_rx = 0
        self.last_tx = 0
        self.last_time = time.time()

data = DataStore()

# ============================================
# OBTENER DATOS - SOLO UNA INTERFAZ PARA PRUEBA
# ============================================
def fetch_data():
    conn = None
    while True:
        try:
            if conn is None:
                conn = routeros_api.RouterOsApiPool(
                    MIKROTIK_HOST,
                    username=MIKROTIK_USER,
                    password=MIKROTIK_PASSWORD,
                    port=MIKROTIK_PORT,
                    plaintext_login=True
                )
                api = conn.get_api()
                data.online = True

            # Obtener solo la interfaz WAN
            interfaces = api.get_resource('/interface').get()
            raw = next((i for i in interfaces if i.get('name') == 'sfp1-WAN-FIBEX'), {})
            
            if raw:
                rx = int(raw.get('rx-byte', 0))
                tx = int(raw.get('tx-byte', 0))
                
                now = time.time()
                dt = now - data.last_time
                data.last_time = now
                
                if dt > 0:
                    data.down = round(((rx - data.last_rx) * 8) / (dt * 1_000_000), 2)
                    data.up = round(((tx - data.last_tx) * 8) / (dt * 1_000_000), 2)
                
                data.last_rx = rx
                data.last_tx = tx
                data.ts = datetime.now().strftime("%H:%M:%S")
                
                logger.info(f"📊 DOWN: {data.down} Mbps, UP: {data.up} Mbps")

        except Exception as e:
            logger.error(f"Error: {e}")
            data.online = False
            conn = None
            time.sleep(5)
        
        time.sleep(1)

threading.Thread(target=fetch_data, daemon=True).start()

# ============================================
# DASH APP SIMPLE
# ============================================
app = dash.Dash(__name__)
server = app.server

app.layout = html.Div(
    style={
        'backgroundColor': '#0a0e1a',
        'padding': '40px',
        'minHeight': '100vh',
        'fontFamily': 'Arial, sans-serif',
        'display': 'flex',
        'flexDirection': 'column',
        'alignItems': 'center',
        'justifyContent': 'center'
    },
    children=[
        html.H1(
            "📡 BTS - PRUEBA",
            style={'color': '#00f3ff', 'fontSize': '40px'}
        ),
        html.Div(
            id='status',
            style={'color': '#00ff88', 'fontSize': '20px', 'marginTop': '20px'}
        ),
        html.Div(
            id='valores',
            style={
                'display': 'flex',
                'gap': '40px',
                'marginTop': '30px',
                'fontSize': '30px'
            },
            children=[
                html.Div(id='down', style={'color': '#00d4ff'}),
                html.Div(id='up', style={'color': '#ffaa00'})
            ]
        ),
        dcc.Interval(id='tick', interval=1000)
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
    down = f"▼ DOWN: {data.down:.1f} Mbps"
    up = f"▲ UP: {data.up:.1f} Mbps"
    status = f"🟢 {data.ts}" if data.online else f"🔴 Desconectado"
    return down, up, status

# ============================================
# INICIO
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    app.run(host='0.0.0.0', port=port, debug=False)
