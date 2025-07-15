import json
import mysql.connector

with open('offline_calls.json', 'r') as f:
    data = json.load(f)

conn = mysql.connector.connect(
    host="localhost",
    user="sgb",
    password="sgb",
    database="sgb"
)

cursor = conn.cursor()


# Create table if it doesn't exist
cursor.execute("""
    CREATE TABLE IF NOT EXISTS TBL_ST_SIMBOX_CALLS (
        MSISDN VARCHAR(30) NOT NULL,
        EVENT_TIME DATETIME NOT NULL,
        PRIMARY KEY (MSISDN, EVENT_TIME),
        INDEX idx_event_time (EVENT_TIME)       
    )
""")



for record in data:
    msisdn = record['msisdn']
    event_time = record['EVENT_TIME']
    cursor.execute(
        "INSERT INTO TBL_ST_SIMBOX_CALLS (msisdn, EVENT_TIME) VALUES (%s, %s)",
        (msisdn, event_time)
    )

conn.commit()
cursor.close()
conn.close()
print("✅ All data inserted.")
