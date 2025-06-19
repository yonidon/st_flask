from flask import Flask, request, jsonify, render_template, redirect, url_for, make_response, flash
import subprocess
import mysql.connector
from datetime import datetime
import time
import os
import configparser
import csv
import io
import math

app = Flask(__name__)
app.secret_key = 'imsi'  
PORT=8999 #Port to run web server on

# Global state flag to indicate if script is running
system_mode = 'stop'  # can be 'start' or 'stop'

# Database configuration for remote connection
#======================================================
DB_CONFIG_FILE = '/home/guard3/st_flask/st_flask/db_config.ini'

#Grid size parameters, multiply by factor to increase square. Grid factor 1 is 10mx10m
GRID_FACTOR=10
GRID_SIZE_LAT = 0.00009*GRID_FACTOR
GRID_SIZE_LON = 0.0001*GRID_FACTOR


def load_db_config():
    config = configparser.ConfigParser()
    if not os.path.exists(DB_CONFIG_FILE):
        config['database'] = {
            'host': 'localhost',
            'port': '3306',
            'user': 'root',
            'password': '',
            'database': 'sgb'
        }
        with open(DB_CONFIG_FILE, 'w') as f:
            config.write(f)
    else:
        config.read(DB_CONFIG_FILE)
    return config['database']

DATABASE_CONFIG = load_db_config()
#======================================================

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

#Create table if not exists
def init_db():
    try:
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
        #Table for grid
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS TBL_ST_SIMBOX_AVG (
                ID INT AUTO_INCREMENT PRIMARY KEY,
                LAT_MIN DECIMAL(13,5),
                LAT_MAX DECIMAL(13,5),
                LON_MIN DECIMAL(13,5),
                LON_MAX DECIMAL(13,5),
                TOTAL_POINTS INT,
                OK_COUNT INT,
                FAIL_COUNT INT
            )
        ''')

        #Table for trail
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS TBL_ST_SIMBOX_TRAIL (
                ID INT AUTO_INCREMENT PRIMARY KEY,
                TRAIL_ID INT,
                LATITUDE DECIMAL(13, 5),
                LONGITUDE DECIMAL(13, 5),
                ALTITUDE DECIMAL(6, 1),
                TIMESTAMP DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        print("Tables initialized successfully.")
    except mysql.connector.Error as err:
        print(f"Error initializing database: {err}")
    finally:
        try:
            cursor.close()
            conn.close()
        except:
            pass

#When json from simbox comes, insert to DB
def insert_modem_data(modem_number, modem_data):
    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor()

    # Convert epoch timestamp to MySQL-compatible format
    readable_timestamp = convert_epoch_to_datetime(modem_data['ts'])

    #Parse gps coordinates from json
    gps_string_from_modem = modem_data['survey_results']['gps_location'] 
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
        latitude, 
        longitude, 
        altitude 
    ))
    

    try:
        conn.commit()  # Commit the transaction
        print("Data inserted successfully.")
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        conn.rollback()  # Roll back the transaction on failure
    cursor.close()
    conn.close()

    #Update grid table
    update_avg_table(
        float(latitude),
        float(longitude),
        modem_data['survey_results']['call_result']
    )



#Update call results in DB from TBL_ST_SIMBOX_CALLS. This table is usually updated by the phone receiving the calls from simbox
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


#Calculate average of updated/failed calls. Is called only when new records are added
def update_avg_table(lat, lon, call_result):
    lat_min = math.floor(lat / GRID_SIZE_LAT) * GRID_SIZE_LAT
    lat_max = lat_min + GRID_SIZE_LAT
    lon_min = math.floor(lon / GRID_SIZE_LON) * GRID_SIZE_LON
    lon_max = lon_min + GRID_SIZE_LON

    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor()

    # Try to update existing square
    cursor.execute('''
        SELECT ID FROM TBL_ST_SIMBOX_AVG
        WHERE LAT_MIN = %s AND LON_MIN = %s
    ''', (lat_min, lon_min))
    row = cursor.fetchone()

    if row:
        id = row[0]
        if call_result == 'OK':
            cursor.execute('''
                UPDATE TBL_ST_SIMBOX_AVG
                SET TOTAL_POINTS = TOTAL_POINTS + 1,
                    OK_COUNT = OK_COUNT + 1
                WHERE ID = %s
            ''', (id,))
        else:
            cursor.execute('''
                UPDATE TBL_ST_SIMBOX_AVG
                SET TOTAL_POINTS = TOTAL_POINTS + 1,
                    FAIL_COUNT = FAIL_COUNT + 1
                WHERE ID = %s
            ''', (id,))
    else:
        ok_count = 1 if call_result == 'OK' else 0
        fail_count = 0 if call_result == 'OK' else 1
        cursor.execute('''
            INSERT INTO TBL_ST_SIMBOX_AVG
            (LAT_MIN, LAT_MAX, LON_MIN, LON_MAX, TOTAL_POINTS, OK_COUNT, FAIL_COUNT)
            VALUES (%s, %s, %s, %s, 1, %s, %s)
        ''', (lat_min, lat_max, lon_min, lon_max, ok_count, fail_count))

    conn.commit()
    cursor.close()
    conn.close()


#Recalculate grid table
def recalculate_grid_table():
    # Load current grid size dynamically
    lat_size, lon_size = GRID_SIZE_LAT ,GRID_SIZE_LON

    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor(dictionary=True)

    # Start fresh
    cursor.execute('DELETE FROM TBL_ST_SIMBOX_AVG')
    conn.commit()

    # Fetch all data from events table
    cursor.execute('SELECT LATITUDE, LONGITUDE, CALL_RESULT FROM TBL_ST_SIMBOX_EVENTS')
    rows = cursor.fetchall()

    grid = {}  # in-memory aggregation

    for row in rows:
        lat = float(row['LATITUDE'])
        lon = float(row['LONGITUDE'])
        call_result = row['CALL_RESULT']

        lat_min = math.floor(lat / lat_size) * lat_size
        lat_max = lat_min + lat_size
        lon_min = math.floor(lon / lon_size) * lon_size
        lon_max = lon_min + lon_size

        key = (lat_min, lon_min)

        if key not in grid:
            grid[key] = {
                'LAT_MIN': lat_min,
                'LAT_MAX': lat_max,
                'LON_MIN': lon_min,
                'LON_MAX': lon_max,
                'TOTAL_POINTS': 0,
                'OK_COUNT': 0,
                'FAIL_COUNT': 0
            }

        grid[key]['TOTAL_POINTS'] += 1
        if call_result == 'OK':
            grid[key]['OK_COUNT'] += 1
        else:
            grid[key]['FAIL_COUNT'] += 1

    # Insert into AVG table
    insert_query = '''
        INSERT INTO TBL_ST_SIMBOX_AVG (LAT_MIN, LAT_MAX, LON_MIN, LON_MAX, TOTAL_POINTS, OK_COUNT, FAIL_COUNT)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    '''

    for square in grid.values():
        cursor.execute(insert_query, (
            square['LAT_MIN'], square['LAT_MAX'], square['LON_MIN'], square['LON_MAX'],
            square['TOTAL_POINTS'], square['OK_COUNT'], square['FAIL_COUNT']
        ))

    conn.commit()
    cursor.close()
    conn.close()




#Receive json from backend and insert it to mysql table. Maybe change receive code? 
@app.route('/receive_json', methods=['POST'])
def receive_json():
    global latest_json_data, system_mode
    data = request.json
    latest_json_data = data  # update global json

    if system_mode == 'stop':
        # Just acknowledge stop mode, discard incoming data
        return jsonify({"status": "stop"}), 200

    # If in start mode, handle as before
    senders = data.get('senders', {})
    for modem_number, modem_data in senders.items():
        insert_modem_data(modem_number, modem_data)

    return jsonify({"status": "start"}), 200


#Fetch data for table tab
@app.route('/fetch_table_data', methods=['GET'])
def fetch_table_data():
    try:
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT ID, MODEM_NUMBER, STATUS, ERROR, ERROR_CODE, 
            TIMESTAMP, NETWORK, MODEM_MSISDN, MODEL, IMEI,
            IMSI, REGISTRATION_STATUS, OPERATOR, RAT, ARFCN, BSIC, PSC, PCI, MCC,
            MNC, LAC, CELL_ID, RSSI, SNR, CALL_RESULT, LATITUDE, LONGITUDE, ALTITUDE
            FROM TBL_ST_SIMBOX_EVENTS 
            WHERE LATITUDE IS NOT NULL AND LONGITUDE IS NOT NULL
            ORDER BY ID DESC
        ''')
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
    global system_mode
    system_mode = 'start'
    return jsonify({"status": "start mode active"})

@app.route('/stop_script', methods=['POST'])
def stop_script():
    global system_mode
    system_mode = 'stop'
    return jsonify({"status": "stop mode active"})

@app.route('/get_mode', methods=['GET'])
def get_mode():
    return jsonify({"mode": system_mode})

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/update_call_result', methods=['POST'])
def trigger_update_call_result():
    update_call_result()
    return jsonify({"status": "CALL_RESULT updated"})

#Load locations from database to be used on map. This is probably redundant.
@app.route('/modem_locations')
def modem_locations():
    try:
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT LATITUDE, LONGITUDE, MCC, MNC, LAC, CELL_ID, CALL_RESULT, ARFCN, PCI, TIMESTAMP
            FROM TBL_ST_SIMBOX_EVENTS 
            WHERE LATITUDE IS NOT NULL AND LONGITUDE IS NOT NULL
            ORDER BY ID DESC
        ''')
        rows = cursor.fetchall()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

#Endpoint to export database to csv
@app.route('/export_csv')
def export_csv():
    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM TBL_ST_SIMBOX_EVENTS')
    rows = cursor.fetchall()
    headers = [i[0] for i in cursor.description]

    csv_io = io.StringIO()
    writer = csv.writer(csv_io)
    writer.writerow(headers)
    writer.writerows(rows)

    cursor.close()
    conn.close()

    response = make_response(csv_io.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=simbox_events.csv"
    response.headers["Content-type"] = "text/csv"
    return response

#Endpoint to import csv to main table
@app.route('/import_csv', methods=['POST'])
def import_csv():
    file = request.files.get('file')
    if not file or not file.filename.endswith('.csv'):
        flash('Please upload a valid CSV file.')
        return redirect(request.referrer or '/')

    csv_io = io.StringIO(file.stream.read().decode('utf-8'))
    reader = csv.reader(csv_io)
    headers = next(reader)  # Skip header row

    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor()

    insert_query = f"INSERT INTO TBL_ST_SIMBOX_EVENTS ({', '.join(headers)}) VALUES ({', '.join(['%s'] * len(headers))})"

    for row in reader:
        cursor.execute(insert_query, row)

    conn.commit()
    cursor.close()
    conn.close()

    flash('CSV imported successfully.')
    return redirect('/')

#Endpoint to clear table
@app.route('/clear_table', methods=['POST'])
def clear_table():
    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM TBL_ST_SIMBOX_EVENTS')
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'status': 'cleared'})

#Serve map grid layer
@app.route('/map_grid_layer')
def map_grid_layer():
    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM TBL_ST_SIMBOX_AVG')
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(data)


#Clear grid table
@app.route('/clear_grid_table', methods=['POST'])
def clear_grid_table():
    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM TBL_ST_SIMBOX_AVG')
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'status': 'cleared'})

@app.route('/recalculate_grid', methods=['POST'])
def recalculate_grid():
    recalculate_grid_table()
    return jsonify({'status': 'recalculated'})



#Add trail to db
@app.route('/save_trail', methods=['POST'])
def save_full_trail():
    data = request.json
    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor()

    # Get next trail ID
    cursor.execute('SELECT IFNULL(MAX(TRAIL_ID), 0) + 1 FROM TBL_ST_SIMBOX_TRAIL')
    next_trail_id = cursor.fetchone()[0]

    # Insert new trail
    for point in data:
        cursor.execute('''
            INSERT INTO TBL_ST_SIMBOX_TRAIL (TRAIL_ID, LATITUDE, LONGITUDE, ALTITUDE)
            VALUES (%s, %s, %s, %s)
        ''', (next_trail_id, point['lat'], point['lon'], point['alt']))

    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'status': 'trail saved'})




#Load trails from db
@app.route('/get_trail')
def get_all_trails():
    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT TRAIL_ID, LATITUDE, LONGITUDE FROM TBL_ST_SIMBOX_TRAIL ORDER BY TRAIL_ID, ID')
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(rows)


#Delete trail with trail trail_id from db
@app.route('/delete_trail/<int:trail_id>', methods=['POST'])
def delete_trail(trail_id):
    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM TBL_ST_SIMBOX_TRAIL WHERE TRAIL_ID = %s', (trail_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'status': 'deleted'})







if __name__ == '__main__':
    init_db()  # Initialize the database when the app starts
    app.run(host='0.0.0.0', port=PORT)
