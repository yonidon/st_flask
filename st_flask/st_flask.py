from flask import Flask, request, jsonify, render_template, redirect, url_for
import subprocess
import configparser
import mysql.connector
from datetime import datetime
import time


app = Flask(__name__)

# Database configuration for remote connection
DATABASE_CONFIG = {
    'host': '192.192.193.163',  # Replace with remote IP or hostname
    'port': 3306,              # Default MariaDB/MySQL port, adjust if needed
    'user': 'sgb',
    'password': 'sgb',
    'database': 'sgb'
}

CONFIG_FILE = '/home/guard3/st_simbox/st_simbox.ini'
latest_json_data = {}  # Global variable to store the latest JSON data

def convert_epoch_to_datetime(epoch_time):
    """Convert epoch time to MySQL-compatible DATETIME string."""
    return datetime.fromtimestamp(epoch_time).strftime('%Y-%m-%d %H:%M:%S')

def parse_gps_location(gps_location_string):
    """
    Parses a GPS location string in the format '"gps_location":"lat,lon,alt"'
    and returns latitude, longitude, and altitude as floats.

    Args:
        gps_location_string (str): The string containing the GPS location.

    Returns:
        tuple: (latitude, longitude, altitude) as floats, or (None, None, None) if parsing fails.
    """
    latitude, longitude, altitude = None, None, None
    try:
        # First, remove the '"gps_location":' prefix and any surrounding quotes.
        # This handles cases like '"gps_location":"32.099322,34.848692,44.9"'
        # or just '"32.099322,34.848692,44.9"'
        start_index = gps_location_string.find(':')
        if start_index != -1:
            # Extract the part after the colon and strip surrounding quotes
            coordinates_part = gps_location_string[start_index + 1:].strip().strip('"')
        else:
            # If no "gps_location":" prefix is found, assume the string is just the coordinates
            coordinates_part = gps_location_string.strip('"')

        # Split the string by comma
        parts = coordinates_part.split(',')

        # Ensure we have at least 3 parts (latitude, longitude, altitude)
        if len(parts) >= 3:
            latitude = float(parts[0])
            longitude = float(parts[1])
            altitude = float(parts[2])
        else:
            print(f"Warning: Insufficient parts in GPS string '{coordinates_part}'. Expected 3, got {len(parts)}.")

    except (ValueError, IndexError) as e:
        print(f"Error parsing GPS location string '{gps_location_string}': {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    return latitude, longitude, altitude

def init_db():
    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS TBL_ST_SIMBOX_EVENTS (
            ID INT AUTO_INCREMENT PRIMARY KEY,
            MODEM_NUMBER INT,
            STATUS VARCHAR(255),
            ERROR VARCHAR(255),
            ERROR_CODE INT,
            MSISDN VARCHAR(255),
            SENT INT,
            MODEM_INDEX_I2C INT,
            TIMESTAMP DATETIME,
            NETWORK VARCHAR(255),
            USE_CALL INT,
            USE_SMS INT,
            IS_LOOPBACK_MSISDN INT,
            MODEM_MSISDN VARCHAR(255),
            MODEL VARCHAR(255),
            IMEI VARCHAR(255),
            IMSI VARCHAR(255),
            REGISTRATION_STATUS VARCHAR(255),
            OPERATOR VARCHAR(255),
            RAT VARCHAR(255),
            ARFCN VARCHAR(255),
            BSIC VARCHAR(255),
            PSC VARCHAR(255),
            PCI VARCHAR(255),
            MCC VARCHAR(255),
            MNC VARCHAR(255),
            LAC VARCHAR(255),
            CELL_ID VARCHAR(255),
            RSSI VARCHAR(255),
            SNR VARCHAR(255),
            CALL_RESULT VARCHAR(255),
            SMS_RESULT VARCHAR(255),
            INDEX idx_timestamp (TIMESTAMP),
            LATITUDE DECIMAL(13,5),
            LONGITUDE DECIMAL(11,5),
            ALTITUDE  DECIMAL(6,1)                         
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

def insert_modem_data(modem_number, modem_data):
    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor()

    # Convert epoch timestamp to MySQL-compatible format
    readable_timestamp = convert_epoch_to_datetime(modem_data['ts'])

    #Parse gps coordinates from json
    gps_string_from_modem = modem_data['survey_results']['gps_location'] # Use .get() for safer access
    latitude, longitude, altitude = parse_gps_location(gps_string_from_modem)

    cursor.execute('''
        INSERT INTO TBL_ST_SIMBOX_EVENTS (
            MODEM_NUMBER, STATUS, ERROR, ERROR_CODE, MSISDN, SENT, MODEM_INDEX_I2C,
            TIMESTAMP, NETWORK, USE_CALL, USE_SMS, IS_LOOPBACK_MSISDN, MODEM_MSISDN, MODEL, IMEI,
            IMSI, REGISTRATION_STATUS, OPERATOR, RAT, ARFCN, BSIC, PSC, PCI, MCC,
            MNC, LAC, CELL_ID, RSSI, SNR, CALL_RESULT, SMS_RESULT, LATITUDE, LONGITUDE, ALTITUDE
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        modem_number, modem_data['status'], modem_data['error'], modem_data['error_code'],
        modem_data['msisdn'], modem_data['sent'], modem_data['modem_index_i2c'], readable_timestamp,
        modem_data['network'], modem_data['use_call'], modem_data['use_sms'], modem_data['is_loopback_msisdn'],modem_data['modem_msisdn'],
        modem_data['survey_results']['model'], modem_data['survey_results']['imei'],
        modem_data['survey_results']['imsi'], modem_data['survey_results']['registration_status'],
        modem_data['survey_results']['operator'], modem_data['survey_results']['rat'],
        modem_data['survey_results']['arfcn'], modem_data['survey_results']['bsic'],
        modem_data['survey_results']['psc'], modem_data['survey_results']['pci'],
        modem_data['survey_results']['mcc'], modem_data['survey_results']['mnc'],
        modem_data['survey_results']['lac'], modem_data['survey_results']['cell_id'],
        modem_data['survey_results']['rssi'], modem_data['survey_results']['snr'],
        modem_data['survey_results']['call_result'], modem_data['survey_results']['sms_result'],
        latitude, # Passed directly
        longitude, # Passed directly
        altitude # Passed directly
    ))
    

    try:
        conn.commit()  # Commit the transaction
        print("Data inserted successfully.")
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        conn.rollback()  # Roll back the transaction on failure
    cursor.close()
    conn.close()

def update_call_result():
    try:
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()

        #There was LIMIT 16 when selecting from TBL_ST_SIMBOX_EVENTS, to make it less heavy. We thought that it would run in real time
        #ABS was 120, but that doesn't always work because clocks are not always synchronized. 180 should work.
        update_query_light= """
            UPDATE TBL_ST_SIMBOX_EVENTS e
            JOIN (
                SELECT * FROM TBL_ST_SIMBOX_EVENTS ORDER BY TIMESTAMP DESC
            ) latest_events
            ON e.ID = latest_events.ID
            JOIN (
                SELECT * FROM TBL_ST_SIMBOX_CALLS ORDER BY EVENT_TIME DESC
            ) latest_calls
            ON latest_events.MODEM_MSISDN = latest_calls.MSISDN
            SET e.CALL_RESULT = 'OK'
            WHERE ABS(TIMESTAMPDIFF(SECOND, latest_events.TIMESTAMP, latest_calls.EVENT_TIME)) <= 180
        """

        #This query is between full tables, not optimal. Maybe should use this one because it works.
        update_query = """
            UPDATE TBL_ST_SIMBOX_EVENTS e
            JOIN TBL_ST_SIMBOX_CALLS c 
            ON e.MODEM_MSISDN = c.MSISDN
            SET e.CALL_RESULT = 'OK'
            WHERE ABS(TIMESTAMPDIFF(SECOND, e.TIMESTAMP, c.EVENT_TIME)) <= 180
        """

        cursor.execute(update_query)
        conn.commit()
        print("CALL_RESULT updated successfully where TIMESTAMP difference is within 3 minutes.")

    except mysql.connector.Error as err:
        print(f"Error: {err}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


@app.route('/receive_json', methods=['POST'])
def receive_json():
    global latest_json_data
    data = request.json
    latest_json_data = data  # Update the global latest_json_data with the received JSON
    senders = data.get('senders', {})

    for modem_number, modem_data in senders.items():
        insert_modem_data(modem_number, modem_data)

    return jsonify({"status": "success"}), 200

#I don't know what this method is for
@app.route('/fetch_data', methods=['GET'])
def fetch_data():
    try:
        # Connect to the MariaDB database
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor(dictionary=True)  # Use dictionary=True for key-value row format
        cursor.execute('SELECT * FROM ST_SIMBOX_EVENTS')  # Execute the query
        rows = cursor.fetchall()  # Fetch all rows
    except mysql.connector.Error as err:
        return jsonify({"error": f"Database error: {err}"}), 500
    finally:
        # Close cursor and connection
        cursor.close()
        conn.close()

    return jsonify(rows)  # Return rows as JSON response

@app.route('/fetch_table_data', methods=['GET'])
def fetch_table_data():
    try:
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT ID,MODEM_NUMBER,STATUS,ERROR,MSISDN,TIMESTAMP,IMEI,IMSI,OPERATOR,ARFCN,CALL_RESULT,MODEM_MSISDN FROM TBL_ST_SIMBOX_EVENTS ORDER BY ID DESC LIMIT 16')
        rows = cursor.fetchall()
        # Get column names dynamically
        column_names = cursor.column_names

    except mysql.connector.Error as err:
        return jsonify({"error": f"Database error: {err}"}), 500
    finally:
        cursor.close()
        conn.close()

    return jsonify({"columns": column_names, "data": rows})

@app.route('/latest_json', methods=['GET'])
def latest_json():
    return jsonify(latest_json_data)

@app.route('/start_script', methods=['POST'])
def start_script():
    with open('/home/guard3/st_simbox/script_output.log', 'w') as f:
        subprocess.Popen(['python3', '/home/guard3/st_simbox/st_simbox.py', 'st_simbox.ini'], cwd='/home/guard3/st_simbox', stderr=f, stdout=f)
    return jsonify({"status": "script started"})

@app.route('/stop_script', methods=['POST'])
def stop_script():
    subprocess.Popen(['sudo', 'pkill', '-f', 'st_simbox.py'])
    return jsonify({"status": "script stopped"})

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/edit_config', methods=['GET', 'POST'])
def edit_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    
    if request.method == 'POST':
        # Update config with the form data
        for section in config.sections():
            for key in config[section]:
                form_value = request.form.get(f"{section}_{key}")
                if form_value is not None:
                    config[section][key] = form_value
        
        # Save the updated config back to the file
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)
        
        return redirect(url_for('edit_config'))

    # Render the edit form with the current config values
    return render_template('edit_config.html', config=config)

@app.route('/update_call_result', methods=['POST'])
def trigger_update_call_result():
    update_call_result()
    return jsonify({"status": "CALL_RESULT updated"})


@app.route('/modem_locations')
def modem_locations():
    try:
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT LATITUDE, LONGITUDE, MCC, MNC, LAC, CELL_ID, CALL_RESULT 
            FROM TBL_ST_SIMBOX_EVENTS 
            WHERE LATITUDE IS NOT NULL AND LONGITUDE IS NOT NULL
            ORDER BY ID DESC LIMIT 100
        ''')
        rows = cursor.fetchall()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()



if __name__ == '__main__':
    init_db()  # Initialize the database when the app starts
    app.run(host='0.0.0.0', port=8999)
