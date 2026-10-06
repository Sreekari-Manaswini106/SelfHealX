from flask import Flask, render_template, jsonify
import pandas as pd
import serial
import threading
import time
import os

app = Flask(__name__)

# ----- CONFIG -----
SERIAL_PORT = 'COM9'
BAUD_RATE = 9600

CSV_FILE = 'data/data.csv'

SENSOR_SLEEP_TIME = 0.5

LOADCELL_THRESHOLD = 400
PIEZO_THRESHOLD = 780

# ----- AI CONFIG -----

RISK_HISTORY = []
MAX_HISTORY = 15

# ----- LIVE DATA -----

live_data = {
    'timestamp': '',
    'loadcell': 0,
    'piezo': 0,
    'alert': False,

    # AI FEATURES
    'risk': 0,
    'resistance': 100,
    'danger_score': 0,
    'prediction': 'STABLE',
    'sensor_status': 'ACTIVE',
    'event_log': []
}

ser = None

# ----- SERIAL CONNECT -----

def connect_serial():

    global ser

    while True:

        try:

            print("Trying to connect to Arduino...")

            ser = serial.Serial(
                SERIAL_PORT,
                BAUD_RATE,
                timeout=2
            )

            time.sleep(2)
            ser.reset_input_buffer()
            ser.reset_output_buffer()

            print("Connected to Arduino ✅")

            break

        except Exception as e:

            print("Retrying connection...", e)

            live_data['sensor_status'] = "DISCONNECTED"

            time.sleep(3)

# ----- SERIAL THREAD -----

def read_serial():

    global live_data, ser

    connect_serial()

    while True:

        try:

            line = ser.readline().decode('utf-8').strip()

            # ⭐ ADDED DEBUG LINE (IMPORTANT)
            print("SERIAL DATA =", line)

            if not line:
                continue

            print("Received:", line)

            # IGNORE BAD LINES
            if "SD_OK" in line or "SD_FAIL" in line:
                continue

            parts = line.split(',')

            if len(parts) != 3:
                continue

            status, loadcell, piezo = parts

            try:
                loadcell = int(float(loadcell))
                piezo = int(piezo)

            except:
                continue

            # ----- TIMESTAMP -----

            current_time = time.strftime("%Y-%m-%d %H:%M:%S")

            # ----- AI RISK CALCULATION -----

            crack_risk = min(100, int((loadcell * 0.10) + (piezo * 0.05)))
            resistance = max(0, 100 - int(crack_risk / 1.4))

            danger_score = min(
                100,
                int((loadcell * 0.4) + (piezo * 0.08))
            )

            # ----- HISTORY -----

            RISK_HISTORY.append(crack_risk)

            if len(RISK_HISTORY) > MAX_HISTORY:
                RISK_HISTORY.pop(0)

            # ----- AI PREDICTION -----

            prediction = "STABLE"

            if len(RISK_HISTORY) >= 5:

                recent_avg = sum(RISK_HISTORY[-5:]) / 5
                old_avg = sum(RISK_HISTORY[:5]) / 5

                if recent_avg > old_avg + 20:
                    prediction = "HIGH STRUCTURAL STRESS"

                elif recent_avg > old_avg + 10:
                    prediction = "RISK INCREASING"

            # ----- ALERT LOGIC -----

            alert = (
                loadcell > LOADCELL_THRESHOLD or
                piezo > PIEZO_THRESHOLD or
                crack_risk > 70
            )

            # ----- EVENT LOG -----

            event = (
                f"{current_time} | Risk: {crack_risk}% | {prediction}"
            )

            live_data['event_log'].append(event)

            if len(live_data['event_log']) > 10:
                live_data['event_log'].pop(0)

            # ----- UPDATE LIVE DATA -----

            live_data['timestamp'] = current_time
            live_data['loadcell'] = loadcell
            live_data['piezo'] = piezo
            live_data['alert'] = alert
            live_data['risk'] = crack_risk
            live_data['resistance'] = resistance
            live_data['danger_score'] = danger_score
            live_data['prediction'] = prediction
            if alert:
                live_data['sensor_status'] = "ALERT"
            else:
                live_data['sensor_status'] = "ACTIVE"

            # ----- SAVE CSV -----

            df = pd.DataFrame([{
                'timestamp': current_time,
                'loadcell': loadcell,
                'piezo': piezo
            }])

            if os.path.exists(CSV_FILE):
                df.to_csv(CSV_FILE, mode='a', header=False, index=False)
            else:
                df.to_csv(CSV_FILE, index=False)

        except Exception as e:

            print("Serial error:", e)

            live_data['sensor_status'] = "DISCONNECTED"

            connect_serial()

        time.sleep(0.5)

# ----- START THREAD -----

threading.Thread(
    target=read_serial,
    daemon=True
).start()

# ----- ROUTES -----

@app.route('/')
def index():
    return render_template('index.html', sleep_time=SENSOR_SLEEP_TIME)

@app.route('/graphs')
def graphs():

    if os.path.exists(CSV_FILE):

        df = pd.read_csv(CSV_FILE)
        df.columns = ['timestamp', 'loadcell', 'piezo']

        timestamps = df['timestamp'].astype(str).tolist()
        loadcells = df['loadcell'].astype(int).tolist()
        piezos = df['piezo'].astype(int).tolist()

    else:
        timestamps, loadcells, piezos = [], [], []

    return render_template(
        'graphs.html',
        timestamps=timestamps,
        loadcells=loadcells,
        piezos=piezos,
        loadcell_threshold=LOADCELL_THRESHOLD,
        piezo_threshold=PIEZO_THRESHOLD
    )

@app.route('/live_data')
def get_live_data():
    return jsonify(live_data)

# ----- MAIN -----

if __name__ == '__main__':

    os.makedirs('data', exist_ok=True)

    print("Starting SelfHealX Web App...")

    app.run(debug=True, use_reloader=False)