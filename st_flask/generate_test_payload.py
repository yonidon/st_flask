import random
import json
import time

# Boundaries for latitude and longitude
LAT_MIN = 32.085
LAT_MAX = 32.100
LON_MIN = 34.840
LON_MAX = 34.860

# Template for modem entry
def generate_modem(modem_number):
    lat = round(random.uniform(LAT_MIN, LAT_MAX), 6)
    lon = round(random.uniform(LON_MIN, LON_MAX), 6)
    alt = round(random.uniform(40.0, 50.0), 1)

    #call_result = random.choice(["OK", "failed_timeout", "failed_atd", ""])
    call_result = random.choice([["failed_timeout", "failed_timeout"],["OK", "failed_timeout"],["OK", "OK"],["OK","failed_timeout", "failed_timeout"]])

    modem = {
        "status": "IDLE",
        "error": "",
        "error_code": 0,
        "msisdn": f"+56962515275",
        "sent": 0,
        "modem_index_i2c": modem_number,
        "ts": time.time(),
        "network": "auto",
        "use_call": 1,
        "use_sms": 0,
        "is_loopback_msisdn": 0,
        "modem_msisdn": f"+569123456{modem_number:02}",
        "survey_results": {
            "model": "Quectel EG25",
            "imei": f"8679290685{random.randint(10000,99999)}",
            "imsi": f"73001145584{random.randint(1000,9999)}",
            "registration_status": str(random.choice(["1", "3", "5"])),
            "operator": "Operator X",
            "rat": "LTE",
            "arfcn": str(random.randint(9000, 10000)),
            "bsic": "",
            "psc": "",
            "pci": str(random.randint(1, 100)),
            "mcc": "730",
            "mnc": "02",
            "lac": str(random.randint(1000, 9999)),
            "cell_id": str(random.randint(10000, 999999)),
            "rssi": str(random.randint(-80, -50)),
            "snr": str(random.randint(-20, 0)),
            "call_result": call_result,
            "sms_result": "",
            "gps_location": f"{lat},{lon},{alt}"
        }
    }
    return modem

lat = round(random.uniform(LAT_MIN, LAT_MAX), 6)
lon = round(random.uniform(LON_MIN, LON_MAX), 6)
alt = round(random.uniform(40.0, 50.0), 1)

# Build full payload
payload = {
    "simbox_name": "PC",
    "gps_location": f"{lat},{lon},{alt}",
    "psms_name": "PSMS",
    "status": "IDLE",
    "senders": {str(i): generate_modem(i) for i in range(1, 17)}
}

# Save JSON file
with open("test_payload.json", "w") as f:
    json.dump(payload, f, indent=2)

print("Generated test_payload.json successfully!")
