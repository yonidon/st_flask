import json
import mysql.connector

with open('offline_calls.json', 'r') as f:
    data = json.load(f)

conn = mysql.connector.connect(
    host="192.192.193.125",
    user="sgb",
    password="sgb",
    database="sgb"
)

cursor = conn.cursor()

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
