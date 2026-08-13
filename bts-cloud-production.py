#!/usr/bin/env python3
# bts-cloud-production.py
# BTS - Bandwidth Telemetry System - VERSIÓN CORREGIDA PARA RENDER

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
# INTERFACES - IDs SIN CARACTERES ESPECIALES
# ============================================
COLORS = [
    {'down': '#00f3ff', 'up': '#008b91'},
    {'down': '#70ff00', 'up': '#459900'},
    {'down': '#ffb800', 'up': '#a37500'},
    {'down': '#ff007a', 'up': '#a6004f'},
    {'down': '#a855f7', 'up': '#7c3aed'},
    {'down': '#f472b6', 'up': '#db2777'},
    {'down': '#f59e0b', 'up': '#b45309'},
]

INTERFACES = [
    {
        'id': 'wan',
        'display': '🌐 WAN',
        'color': COLORS[0],
        'limit': 50,
        'mikrotik_name': 'sfp1-WAN-FIBEX'
    },
    {
        'id': 'bridge',
        'display': '🔗 Bridge',
        'color': COLORS[1],
        'limit': 30,
        'mikrotik_name': 'bridge'
    },
    {
        'id': 'clientes',
        'display': '🏢 Clientes',
        'color': COLORS[2],
        'limit': 20,
        'mikrotik_name': 'ether2'
    },
    {
        'id': 'casa',
        'display': '🏠 Casa',
        'color': COLORS[3],
        'limit': 15,
        'mikrotik_name': 'ether1'
    },
    {
        'id': 'andres',
        'display': '👤 Andrés',
        'color': COLORS[4],
        'limit': 10,
        'mikrotik_name': '<pppoe-andres.bodega>'
    },
    {
        'id': 'isaura',
        'display': '👤 Isaura',
        'color': COLORS[5],
        'limit': 15,
        'mikrotik_name': '<pppoe-isaura.zambrano>'
    },
    {
        'id': 'wifi',
        'display': '📶 WiFi',
        'color': COLORS[6],
        'limit': 20,
        'mikrotik_name': 'ether6'
    },
]

ALL_IDS = [i['id'] for i in INTERFACES]
ALL_BOX_IDS = ALL_IDS + ['system-hw']

# ============================================
# GESTOR DE DATOS
# ============================================
class BTSDataManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.stats = {uid: {
            'd_last': 0, 'u_last': 0, 'time': time.time(),
            'x': [], 'yd': [], 'yu': []
        } for uid in ALL_IDS}
        self.hardware = {'cpu': 0, 'ram': 0}
        self.last_ts = ""
        self.connection_status = False

data_manager = BTSDataManager()

# ============================================
# FUNCIÓN DE OBTENCIÓN DE DATOS
# ============================================
def fetch_mikrotik_data():
    connection = None
    while True:
        try:
            if connection is None:
                logger.info(f"🔗 Conectando a {MIKROTIK_HOST}")
                connection = routeros_api.RouterOsApiPool(
                    MIKROTIK_HOST,
                    username=MIKROTIK_USER,
                    password=MIKROTIK_PASSWORD,
                    port=MIKROTIK_PORT,
                    plaintext_login=True
                )
                api = connection.get_api()
                data_manager.connection_status = True
                logger.info("✅ Conectado")

            raw_data = api.get_resource('/interface').get()
            raw_resource = api.get_resource('/system/resource').get()
            timestamp = datetime.now().strftime("%H:%M:%S")
            data_manager.last_ts = timestamp

            for item in INTERFACES:
                uid = item['id']
                mikrotik_name = item['mikrotik_name']
                
                raw = next((i for i in raw_data if i.get('name') == mikrotik_name), {})
                rx = int(raw.get('rx-byte', 0)) if raw else 0
                tx = int(raw.get('tx-byte', 0)) if raw else 0
                
                now = time.time()
                dt = now - data_manager.stats[uid]['time']
                
                if dt > 0:
                    d_mbps = round((((rx - data_manager.stats[uid]['d_last']) * 8) / dt) / 1e6, 2) \
                        if data_manager.stats[uid]['d_last'] > 0 else 0
                    u_mbps = round((((tx - data_manager.stats[uid]['u_last']) * 8) / dt) / 1e6, 2) \
                        if data_manager.stats[uid]['u_last'] > 0 else 0
                else:
                    d_mbps = u_mbps = 0

                data_manager.stats[uid].update({'d_last': rx, 'u_last': tx, 'time': now})
                data_manager.stats[uid]['x'].append(timestamp)
                data_manager.stats[uid]['yd'].append(d_mbps)
                data_manager.stats[uid]['yu'].append(u_mbps)

                if len(data_manager.stats[uid]['x']) > 30:
                    for key in ['x', 'yd', 'yu']:
                        data_manager.stats[uid][key].pop(0)

            if raw_resource:
                res = raw_resource[0]
                cpu_usage = float(res.get('cpu-load', 0))
                total_mem = float(res.get('total-memory', 1))
                free_mem = float(res.get('free-memory', 0))
                ram_usage = round(((total_mem - free_mem) / total_mem) * 100, 1)
                data_manager.hardware = {'cpu': cpu_usage, 'ram': ram_usage}

        except Exception as e:
            logger.error(f"Error: {e}")
            connection = None
            data_manager.connection_status = False
            time.sleep(5)
        
        time.sleep(0.5)  # 500ms para más fluidez

threading.Thread(target=fetch_mikrotik_data, daemon=True).start()

# ============================================
# FUNCIÓN DE GAUGE
# ============================================
def make_gauge(val, color, title, limit=None, is_percentage=False):
    if is_percentage:
        display_val, unit, r_max = val, " %", 100
    else:
        if limit is None:
            if val >= 1000:
                display_val, unit, r_max = val / 1000, " Gb", 10
            else:
                display_val, unit, r_max = val, " Mb", 1000
        else:
            display_val, unit, r_max = val, " Mb", limit

    pct = display_val / r_max if r_max > 0 else 0
    bar_color = '#ff2244' if pct > 0.9 else ('#ffb800' if pct > 0.7 else color)

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=display_val,
        number={
            'valueformat': '.1f',
            'suffix': unit,
            'font': {'size': 18, 'color': 'white', 'family': 'Share Tech Mono'}
        },
        gauge={
            'axis': {'range': [0, r_max], 'tickfont': {'size': 7, 'color': '#444', 'family': 'Share Tech Mono'}, 'nticks': 5},
            'bar': {'color': bar_color, 'thickness': 0.35},
            'bgcolor': 'rgba(255,255,255,0.02)',
            'borderwidth': 0,
            'steps': [
                {'range': [0, r_max * 0.7], 'color': 'rgba(255,255,255,0.015)'},
                {'range': [r_max * 0.7, r_max * 0.9], 'color': 'rgba(255,184,0,0.04)'},
                {'range': [r_max * 0.9, r_max], 'color': 'rgba(255,34,68,0.06)'},
            ],
            'threshold': {'line': {'color': bar_color, 'width': 2}, 'thickness': 0.8, 'value': display_val}
        }
    ))

    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        autosize=True,
        margin=dict(l=6, r=6, t=28, b=5),
        font={'family': 'Share Tech Mono'},
        title={
            'text': f'<b>{title}</b>',
            'font': {'color': color, 'size': 9, 'family': 'Share Tech Mono'},
            'y': 0.92, 'x': 0.5
        }
    )
    return fig

# ============================================
# APLICACIÓN DASH
# ============================================
app = dash.Dash(__name__)
server = app.server

app.layout = html.Div(
    style={
        'backgroundColor': '#0a0e1a',
        'padding': '20px',
        'minHeight': '100vh',
        'fontFamily': 'Share Tech Mono, monospace'
    },
    children=[
        html.H1(
            "📡 BANDWIDTH TELEMETRY",
            style={
                'textAlign': 'center',
                'color': '#00f3ff',
                'textShadow': '0 0 20px rgba(0,243,255,0.3)',
                'letterSpacing': '4px',
                'marginBottom': '5px'
            }
        ),
        html.P(
            "MikroTik Monitor • 7 Interfaces • Tiempo Real",
            style={'textAlign': 'center', 'color': 'rgba(0,243,255,0.6)', 'marginBottom': '20px'}
        ),
        html.Div(
            id='ts-display',
            style={'textAlign': 'center', 'color': 'rgba(0,243,255,0.5)', 'marginBottom': '20px'}
        ),
        html.Div(
            style={'display': 'grid', 'gridTemplateColumns': 'repeat(3, 1fr)', 'gap': '15px'},
            children=[html.Div(
                id=f"box-{uid}",
                style={
                    'background': 'rgba(6,10,18,0.95)',
                    'borderRadius': '12px',
                    'border': '1px solid rgba(0,243,255,0.1)',
                    'padding': '10px'
                }
            ) for uid in ALL_BOX_IDS]
        ),
        dcc.Interval(id='tick', interval=500)  # 500ms para más fluidez
    ]
)

# ============================================
# CALLBACKS
# ============================================
@app.callback(
    [Output(f"box-{uid}", "children") for uid in ALL_BOX_IDS] +
    [Output("ts-display", "children")],
    [Input('tick', 'n_intervals')]
)
def update_ui(n):
    card_contents = []
    
    for box_id in ALL_BOX_IDS:
        if box_id == 'system-hw':
            hw_cpu = data_manager.hardware['cpu']
            hw_ram = data_manager.hardware['ram']
            card_contents.append(html.Div([
                html.Div("🖥️ SISTEMA", style={'color': '#00f3ff', 'fontSize': '0.8em', 'textAlign': 'center', 'letterSpacing': '2px'}),
                dcc.Graph(figure=make_gauge(hw_cpu, '#00f3ff', "CPU", is_percentage=True), config={'displayModeBar': False}),
                dcc.Graph(figure=make_gauge(hw_ram, '#ff007a', "RAM", is_percentage=True), config={'displayModeBar': False})
            ]))
        else:
            item = next((i for i in INTERFACES if i['id'] == box_id), None)
            if item:
                st = data_manager.stats[box_id]
                d_mbps = st['yd'][-1] if st['yd'] else 0
                u_mbps = st['yu'][-1] if st['yu'] else 0
                color = item['color']['down']
                card_contents.append(html.Div([
                    html.Div(item['display'], style={'color': color, 'fontSize': '0.8em', 'textAlign': 'center', 'letterSpacing': '2px'}),
                    dcc.Graph(figure=make_gauge(d_mbps, color, "▼ DOWN", item['limit']), config={'displayModeBar': False}),
                    dcc.Graph(figure=make_gauge(u_mbps, item['color']['up'], "▲ UP", item['limit']), config={'displayModeBar': False})
                ]))
    
    status = "🟢" if data_manager.connection_status else "🔴"
    ts = data_manager.last_ts or "Esperando datos..."
    return card_contents + [f"{status} LIVE · {ts} · {len(ALL_IDS)} interfaces"]

# ============================================
# INICIO
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8050))
    app.run(host='0.0.0.0', port=port, debug=False)
