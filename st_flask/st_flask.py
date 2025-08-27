from flask import Flask, request, jsonify, render_template, redirect, make_response, flash
import mysql.connector
from datetime import datetime
import os
import configparser
import csv
import io
import math
import random
import json



#=======Bugs and Features=======
#update_avg_table creates overlapping squares. recalculate_grid works fine
#"Update calls" - need to add option to upload a file (maybe hide this button, currently getting BUSY result)
#If importing and file size too large/ wrong format then need to add exception
#No exception handler for database not connected
#In gps add indicator if browser location or simbox location (Maybe in modems-tab)
#Start transmission and stop remotely (future feature)
#Layer for active transmission and inactive
#Add option to stop automatically after x surveys (maybe in settings)
#Split frontend files
#If script stops sending messages then set back to unknown (No need because there are running/stopping status indicators)
#Make the tooltip the upper layer
#Export by filter?
#Clean latest json after receiving it. This problem is in fetchData(), since latest_json_data is not getting deleted 
#Collapsing not work anymore?
#Add analytics tab? able to run sql queries and save them, and can only run select queries. Will display on graph.
#Note that call timeout sometimes needs to be 10 seconds and not five
#Add a button to refresh analysis map
#Add a parameter to update_call_result which will include offset from real time. also parameter for difference
#Combine inject_json inside code


#Fix:
#Add "please choose trail" message if not selected
#Reduce button size of switching modes. Also, just advanced/simple without switch
#Remove backend and frontend from simple mode
#When switching to simple mode - should jump to main page




#======================================================
# Global state flags
app = Flask(__name__)
app.secret_key = 'imsi'  
#HTTPS_PORT=8999 #Currently unused because https in nginx
HTTP_PORT=8990
system_mode = 'stop'  # can be 'start' or 'stop', is sent to backend to activate script
current_gps_location = ''   # Current gps location used
modem_gps_location = ''   # from backend modem JSON requests
browser_gps_location = ''  # from browser geolocation updates
current_survey_running = '' # Live status of backend
battery_voltage = '' #Current battery voltage of simbox
latest_json_data = {}  # Global variable to store the latest JSON data

#Grid size parameters, multiply by factor to increase square. Grid factor 1 is 10mx10m
GRID_FACTOR=10
GRID_SIZE_LAT = 0.00009*GRID_FACTOR
GRID_SIZE_LON = 0.0001 *GRID_FACTOR

#======================================================
# Database configuration for remote connection
DB_CONFIG_FILE = '/home/guard3/st_flask/db_config.ini'

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


#======================================================
#Utility functions
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
        if len(parts) >= 2:
            latitude = float(parts[0])
            longitude = float(parts[1])
            if len(parts) >= 3:
                altitude = float(parts[2])
            else:
                altitude = 0
        else:
            print(f"Warning: Insufficient parts in GPS string '{coordinates_part}'. Expected 2 or 3, got {len(parts)}.")

    except (ValueError, IndexError) as e:
        print(f"Error parsing GPS location string '{gps_location_string}': {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    return latitude, longitude, altitude

#Jitter coordinates so they won't overlap. This is currently unused because jitter using frotend instead.
def jitter_coordinates(lat, lon):
    # Shift about +/- ~5 meters (depending on latitude scale)
    delta_lat = random.uniform(-0.000005, 0.000005)
    delta_lon = random.uniform(-0.000005, 0.000005)
    return lat + delta_lat, lon + delta_lon

#Compare floats with less precision
def floats_equal(a, b, epsilon=1e-6):
    try:
        return abs(float(a) - float(b)) < epsilon
    except:
        return False

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
                ALTITUDE  DECIMAL(6,1),
                SESSION_NAME VARCHAR(255)   
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
                DESCRIPTION VARCHAR(255),
                IS_MARKED BOOLEAN DEFAULT FALSE,
                TIMESTAMP DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        #Table for settings
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS TBL_ST_SIMBOX_SETTINGS (
                ID INT AUTO_INCREMENT PRIMARY KEY,
                CONFIG_KEY VARCHAR(64) UNIQUE,
                CONFIG_VALUE TEXT
            )
        ''')
        
        #Table for rssi average
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS TBL_ST_SIMBOX_RSSI_AVG (
                ID INT AUTO_INCREMENT PRIMARY KEY,
                LAT_MIN DECIMAL(10,6),
                LAT_MAX DECIMAL(10,6),
                LON_MIN DECIMAL(10,6),
                LON_MAX DECIMAL(10,6),
                TOTAL_POINTS INT,
                RSSI_SUM FLOAT
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
def insert_modem_data(modem_number, modem_data,gps_location):
    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor()

    # Convert epoch timestamp to MySQL-compatible format
    readable_timestamp = convert_epoch_to_datetime(modem_data['ts'])

    #Parse gps coordinates from json for each sim
    gps_string_from_modem = gps_location
    try:
        latitude, longitude, altitude = parse_gps_location(gps_string_from_modem)
        #latitude, longitude = jitter_coordinates(latitude, longitude) #Jitter coordinates so they don't overlap
    except Exception:
        print("Failed to get GPS")
        latitude, longitude, altitude = None, None, None

    session_name = get_setting("session_name") or ""


    # Normalize call_result values to only "OK" or "FAIL"
    call_results = modem_data['survey_results'].get('call_result', [])
    normalized_results = []

    for result in call_results:
        if isinstance(result, str):
            result_lower = result.lower()
            if result_lower.startswith('ok'):
                normalized_results.append('OK')
            elif result_lower.startswith('failed'):
                normalized_results.append('FAIL')

    # Replace with normalized array
    modem_data['survey_results']['call_result'] = normalized_results



    cursor.execute('''
        INSERT INTO TBL_ST_SIMBOX_EVENTS (
            MODEM_NUMBER, STATUS, ERROR, ERROR_CODE, MSISDN, SENT, MODEM_INDEX_I2C,
            TIMESTAMP, NETWORK, USE_CALL, USE_SMS, IS_LOOPBACK_MSISDN, MODEM_MSISDN, MODEL, IMEI,
            IMSI, REGISTRATION_STATUS, OPERATOR, RAT, ARFCN, BSIC, PSC, PCI, MCC,
            MNC, LAC, CELL_ID, RSSI, SNR, CALL_RESULT, SMS_RESULT, LATITUDE, LONGITUDE, ALTITUDE,SESSION_NAME 
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        json.dumps(modem_data['survey_results']['call_result']), modem_data['survey_results']['sms_result'],
        latitude, 
        longitude, 
        altitude,
        session_name 
    ))
    

    try:
        conn.commit()  # Commit the transaction
        print("Data inserted successfully.")
        flash(f'Inserted data for modem {modem_number}')
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        conn.rollback()  # Roll back the transaction on failure
    cursor.close()
    conn.close()

    #Update grid table
    if latitude is not None and longitude is not None:
        update_avg_table(
            float(latitude),
            float(longitude),
            modem_data['survey_results']['call_result']
        )




#Update call results in DB from TBL_ST_SIMBOX_CALLS. This table is usually updated by the phone receiving the calls from simbox
def update_call_result():
    try:
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT e.ID, e.CALL_RESULT
            FROM TBL_ST_SIMBOX_EVENTS e
            JOIN TBL_ST_SIMBOX_CALLS c 
            ON e.MODEM_MSISDN = c.MSISDN
            WHERE ABS(TIMESTAMPDIFF(SECOND, e.TIMESTAMP, c.EVENT_TIME)) <= 10
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        updated = 0

        for row in rows:
            try:
                result_list = json.loads(row['CALL_RESULT'])
                if not isinstance(result_list, list) or not result_list:
                    continue

                for i, val in enumerate(result_list):
                    if val.upper() != "OK":
                        result_list[i] = "OK"
                        updated_result = json.dumps(result_list)
                        cursor.execute("""
                            UPDATE TBL_ST_SIMBOX_EVENTS
                            SET CALL_RESULT = %s
                            WHERE ID = %s
                        """, (updated_result, row['ID']))
                        updated += 1
                        break  # Only replace the first non-OK

            except Exception as err:
                print(f"Skipping ID {row['ID']}: {err}")

        conn.commit()
        print(f"Updated {updated} CALL_RESULT arrays with one OK replacement.")

    except mysql.connector.Error as err:
        print(f"DB Error: {err}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()


#Delete this
def update_call_result_old():
    try:
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()

        #This query is between full tables, not optimal.
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

    ok_count = sum(1 for res in call_result if res == 'OK')
    fail_count = len(call_result) - ok_count
    total_points = len(call_result)

    if not call_result:
        return  # Skip this entry entirely

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
        cursor.execute('''
            UPDATE TBL_ST_SIMBOX_AVG
            SET TOTAL_POINTS = TOTAL_POINTS + %s,
                OK_COUNT = OK_COUNT + %s,
                FAIL_COUNT = FAIL_COUNT + %s
            WHERE ID = %s
        ''', (total_points, ok_count, fail_count, id))
    else:
        cursor.execute('''
            INSERT INTO TBL_ST_SIMBOX_AVG
            (LAT_MIN, LAT_MAX, LON_MIN, LON_MAX, TOTAL_POINTS, OK_COUNT, FAIL_COUNT)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (lat_min, lat_max, lon_min, lon_max, total_points, ok_count, fail_count))

    conn.commit()
    cursor.close()
    conn.close()


#Recalculate grid table
def recalculate_grid_table():
    lat_size, lon_size = GRID_SIZE_LAT, GRID_SIZE_LON

    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor(dictionary=True)

    cursor.execute('DELETE FROM TBL_ST_SIMBOX_AVG')
    conn.commit()

    # Read events
    cursor.execute('SELECT LATITUDE, LONGITUDE, CALL_RESULT FROM TBL_ST_SIMBOX_EVENTS WHERE LATITUDE IS NOT NULL AND LONGITUDE IS NOT NULL')
    rows = cursor.fetchall()

    grid = {}

    for row in rows:
        lat = float(row['LATITUDE'])
        lon = float(row['LONGITUDE'])

        try:
            call_results = json.loads(row['CALL_RESULT'])  # safely parse JSON string
        except (json.JSONDecodeError, TypeError):
            continue  # skip invalid data

        if not isinstance(call_results, list):
            continue

        if not call_results:
            continue  # Skip empty CALL_RESULT

        ok_count = sum(1 for res in call_results if res == 'OK')
        fail_count = len(call_results) - ok_count
        total = len(call_results)

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

        grid[key]['TOTAL_POINTS'] += total
        grid[key]['OK_COUNT'] += ok_count
        grid[key]['FAIL_COUNT'] += fail_count

    # Insert updated grid
    insert_query = '''
        INSERT INTO TBL_ST_SIMBOX_AVG (LAT_MIN, LAT_MAX, LON_MIN, LON_MAX, TOTAL_POINTS, OK_COUNT, FAIL_COUNT)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    '''

    for square in grid.values():
        cursor.execute(insert_query, (
            square['LAT_MIN'], square['LAT_MAX'],
            square['LON_MIN'], square['LON_MAX'],
            square['TOTAL_POINTS'], square['OK_COUNT'], square['FAIL_COUNT']
        ))

    conn.commit()
    cursor.close()
    conn.close()

#Recalculate rssi layer
def recalculate_rssi_table():
    lat_size, lon_size = GRID_SIZE_LAT, GRID_SIZE_LON

    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor(dictionary=True)

    # Clear existing data
    cursor.execute('DELETE FROM TBL_ST_SIMBOX_RSSI_AVG')
    conn.commit()

    # Fetch all events with RSSI
    cursor.execute('SELECT LATITUDE, LONGITUDE, RSSI FROM TBL_ST_SIMBOX_EVENTS WHERE LATITUDE IS NOT NULL AND LONGITUDE IS NOT NULL AND RSSI IS NOT NULL AND RSSI != ""')
    rows = cursor.fetchall()

    grid = {}

    for row in rows:
        lat = float(row['LATITUDE'])
        lon = float(row['LONGITUDE'])
        try:
            rssi_value = float(row['RSSI'])
        except ValueError:
            continue  # skip bad data

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
                'RSSI_SUM': 0
            }

        grid[key]['TOTAL_POINTS'] += 1
        grid[key]['RSSI_SUM'] += rssi_value

    insert_query = '''
        INSERT INTO TBL_ST_SIMBOX_RSSI_AVG
        (LAT_MIN, LAT_MAX, LON_MIN, LON_MAX, TOTAL_POINTS, RSSI_SUM)
        VALUES (%s, %s, %s, %s, %s, %s)
    '''

    for square in grid.values():
        cursor.execute(insert_query, (
            square['LAT_MIN'],
            square['LAT_MAX'],
            square['LON_MIN'],
            square['LON_MAX'],
            square['TOTAL_POINTS'],
            square['RSSI_SUM']
        ))

    conn.commit()
    cursor.close()
    conn.close()


#Receive json from backend and insert it to mysql table. Maybe change receive code? 
@app.route('/receive_json', methods=['POST'])
def receive_json():
    global latest_json_data, system_mode, current_gps_location, browser_gps_location, current_survey_running,modem_gps_location,battery_voltage
    data = request.json
    latest_json_data = data  # update global json

    #Update global gps lock status
    gps_location = data.get("gps_location", "")
    current_survey_running = data.get("survey_running", False)
    battery_voltage=data.get("battery_voltage", "")
    modem_gps_location= gps_location
   
    if gps_location and gps_location.strip() != "":
        current_gps_location = gps_location  # only update when non-empty
    elif browser_gps_location and get_setting("use_geolocation")!='false':
        current_gps_location = browser_gps_location
        print("using geolocation")
    else:
        default_lat = get_setting("default_latitude")
        default_lon = get_setting("default_longitude")
        if default_lat and default_lon:
            current_gps_location = f"{default_lat},{default_lon},0"
            print("using default location")
    
    senders = data.get('senders', {})
    if senders:    
        for modem_number, modem_data in senders.items():
            insert_modem_data(modem_number, modem_data,current_gps_location)    

    if system_mode == 'stop':
        # Acknowledge stop mode
        return jsonify({"status": "stop"}), 200
    # Acknowledge start mode
    return jsonify({"status": "start"}), 200


#Fetch data for table tab
@app.route('/fetch_table_data', methods=['GET'])
def fetch_table_data():
    try:
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT ID,SESSION_NAME, MODEM_NUMBER, STATUS, ERROR, ERROR_CODE, 
            TIMESTAMP, NETWORK, MODEM_MSISDN, MODEL, IMEI,
            IMSI, REGISTRATION_STATUS, OPERATOR, RAT, ARFCN, BSIC, PSC, PCI, MCC,
            MNC, LAC, CELL_ID, RSSI, SNR, CALL_RESULT, LATITUDE, LONGITUDE, ALTITUDE
            FROM TBL_ST_SIMBOX_EVENTS 
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


#When stop mode is pressed, default location is incremented to next trail point (If users presses ok on prompt)
@app.route('/stop_script', methods=['POST'])
def stop_script():
    global system_mode
    system_mode = 'stop'

    default_trail_id = get_setting('default_is_trail')
    

    # If not set, just return
    if not default_trail_id or default_trail_id == "0":
        return jsonify({"status": "stop mode active"})

    # If set, get all points of this trail
    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT LATITUDE, LONGITUDE, TIMESTAMP
        FROM TBL_ST_SIMBOX_TRAIL
        WHERE TRAIL_ID=%s
        ORDER BY ID ASC
    """, (default_trail_id,))

    points = cursor.fetchall()

    cursor.close()
    conn.close()

    # If no points found
    if not points:
        return jsonify({"status": "stop mode active"})

    # Determine which point was last set as default
    default_lat = get_setting('default_latitude')
    default_lon = get_setting('default_longitude')

    current_idx = None
    for idx, point in enumerate(points):
        if (
            floats_equal(point['LATITUDE'], default_lat)
            and floats_equal(point['LONGITUDE'], default_lon)
        ):
            current_idx = idx
            break


    # If last point in trail
    if current_idx is not None and current_idx + 1 >= len(points):
        # Clear the default trail
        set_setting('default_is_trail', "0")

        # Mark current point as IS_MARKED=1
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE TBL_ST_SIMBOX_TRAIL
            SET IS_MARKED=1
            WHERE TRAIL_ID=%s AND LATITUDE=%s AND LONGITUDE=%s
        """, (default_trail_id, default_lat, default_lon))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"status": "trail_finished"})

    # If next point exists, return coordinates
    if current_idx is not None:

        # Mark current point as IS_MARKED=1
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE TBL_ST_SIMBOX_TRAIL
            SET IS_MARKED=1
            WHERE TRAIL_ID=%s AND LATITUDE=%s AND LONGITUDE=%s
        """, (default_trail_id, default_lat, default_lon))
        conn.commit()
        cursor.close()
        conn.close()

        next_point = points[current_idx + 1]
        return jsonify({
            "status": "next_point",
            "latitude": str(next_point['LATITUDE']),
            "longitude": str(next_point['LONGITUDE']),
            "trail_id": default_trail_id
        })
    
    # If no matching current point, return stop
    return jsonify({"status": "stop mode active"})


@app.route('/get_mode', methods=['GET'])
def get_mode():

    global current_gps_location, browser_gps_location, current_survey_running, modem_gps_location, battery_voltage

    # Determine effective GPS location and source
    gps_source = "none"
    effective_gps_location = ""
    if modem_gps_location:
        gps_source = "modem"
        effective_gps_location = current_gps_location
    elif browser_gps_location:
        gps_source = "browser"
        effective_gps_location = browser_gps_location
    else:
        default_lat = get_setting("default_latitude")
        default_lon = get_setting("default_longitude")
        if default_lat and default_lon:
            gps_source = "default"
            effective_gps_location = f"{default_lat},{default_lon},0"

    return jsonify({
        "mode": system_mode,
        "gps_location": effective_gps_location,
        "gps_source": gps_source,
        "survey_running": current_survey_running,
        "battery_status": latest_json_data.get("battery_status", "Unknown"),
        "battery_voltage": battery_voltage
    })


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
            SELECT LATITUDE, LONGITUDE, RSSI, OPERATOR, LAC, CELL_ID, CALL_RESULT, ARFCN, PCI, TIMESTAMP, SESSION_NAME
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
        try:
            cursor.execute(insert_query, row)
        except mysql.connector.IntegrityError as e:
            # Handle duplicate keys or constraints
            flash(f"Skipped a row due to database error: {str(e)}")
        except Exception as e:
            flash(f"Skipped a row due to unexpected error: {str(e)}")    

    conn.commit()
    cursor.close()
    conn.close()

    flash('CSV imported successfully.')
    return redirect(request.referrer or '/')

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

#=================Statistics grid section==========================

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
    cursor.execute('DELETE FROM TBL_ST_SIMBOX_RSSI_AVG')
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'status': 'cleared'})

@app.route('/recalculate_grid', methods=['POST'])
def recalculate_grid():
    recalculate_grid_table()
    recalculate_rssi_table()
    return jsonify({'status': 'recalculated'})


@app.route('/rssi_grid')
def get_rssi_grid():
    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT * FROM TBL_ST_SIMBOX_RSSI_AVG')
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(rows)


#============================================================


#=================Trail section=============================

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
@app.route('/get_trail', methods=['GET'])
def get_trail():
    try:
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor(dictionary=True)
        cursor.execute('SELECT TRAIL_ID, LATITUDE, LONGITUDE, ALTITUDE, DESCRIPTION, IS_MARKED FROM TBL_ST_SIMBOX_TRAIL')
        rows = cursor.fetchall()
        return jsonify(rows)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()



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


@app.route('/update_trail_description', methods=['POST'])
def update_trail_description():
    data = request.json
    trail_id = data.get('trail_id')
    lat = data.get('lat')
    lon = data.get('lon')
    description = data.get('description')



    try:
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE TBL_ST_SIMBOX_TRAIL
            SET DESCRIPTION=%s
            WHERE TRAIL_ID=%s AND LATITUDE=%s AND LONGITUDE=%s
        """, (description, trail_id, lat, lon))
        conn.commit()
        return jsonify({"status": "updated"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/update_marker_status', methods=['POST'])
def update_marker_status():
    data = request.json
    trail_id = data['trail_id']
    lat = data['lat']
    lon = data['lon']
    is_marked = data['is_marked']
    
    try:
        conn = mysql.connector.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE TBL_ST_SIMBOX_TRAIL
            SET IS_MARKED=%s
            WHERE TRAIL_ID=%s AND LATITUDE=%s AND LONGITUDE=%s
        """, (is_marked, trail_id, lat, lon))
        conn.commit()
        return jsonify({"status": "updated"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()





#============================================================

#If browser got location then use it instead
@app.route('/update_browser_location', methods=['POST'])
def update_browser_location():
    global browser_gps_location
    data = request.json
    browser_gps_location = data.get("gps_location", "")
    return jsonify({"status": "received"}), 200


#==================Settings segment============================
def get_setting(key):
    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor()
    cursor.execute("SELECT CONFIG_VALUE FROM TBL_ST_SIMBOX_SETTINGS WHERE CONFIG_KEY = %s", (key,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row[0] if row else None

def set_setting(key, value):
    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO TBL_ST_SIMBOX_SETTINGS (CONFIG_KEY, CONFIG_VALUE)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE CONFIG_VALUE = %s
    """, (key, value, value))
    conn.commit()
    cursor.close()
    conn.close()

def get_all_settings():
    conn = mysql.connector.connect(**DATABASE_CONFIG)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT CONFIG_KEY, CONFIG_VALUE FROM TBL_ST_SIMBOX_SETTINGS")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {row['CONFIG_KEY']: row['CONFIG_VALUE'] for row in rows}

@app.route('/get_settings')
def get_settings():
    return jsonify(get_all_settings())

@app.route('/update_settings', methods=['POST'])
def update_settings():
    data = request.json
    for k, v in data.items():
        set_setting(k, v)
    return jsonify({"status": "ok"})

@app.route('/set_default_location', methods=['POST'])
def set_default_location():
    data = request.json
    lat = str(data.get('latitude'))
    lon = str(data.get('longitude'))
    trail_id = str(data.get('trail_id', '0'))  # 0 if not from trail
    set_setting('default_latitude', lat)
    set_setting('default_longitude', lon)
    set_setting('default_is_trail', trail_id)

    return jsonify({"status": "default location saved"})


#============================================================































if __name__ == '__main__':
    init_db()  # Initialize the database when the app starts

    #No need to use this, https runs through nginx
    #app.run(host='0.0.0.0', port=PORT, ssl_context=('/home/guard3/st_flask/certs/cert.pem', '/home/guard3/st_flask/certs/key.pem'))
    app.run(host='0.0.0.0', port=HTTP_PORT)
    
#How to create certificate:
#openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 36500 -nodes