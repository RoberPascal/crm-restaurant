#!/usr/bin/env python3
import sqlite3
import json
from datetime import date

DB = 'app.db'
TARGET_DATE = '2025-11-13'
TARGET_TIME_PREFIX = '12:'

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print('=== time_slots matching date and time prefix')
for row in cur.execute("SELECT id,date,time,capacity_category,available_table_count,total_table_count,booked_tables,table_ids,status FROM time_slots WHERE date = ? AND time LIKE ? ORDER BY capacity_category", (TARGET_DATE, TARGET_TIME_PREFIX+'%')):
    print(dict(row))

print('\n=== bookings at exact time')
for row in cur.execute("SELECT id,restaurant_id,date,time,end_time,status,adults,table_id,capacity_category FROM bookings WHERE date = ? AND time LIKE ? ORDER BY id", (TARGET_DATE, TARGET_TIME_PREFIX+'%')):
    print(dict(row))

print('\n=== tables summary for restaurants in time_slots results')
# find distinct restaurant_ids from time_slots
res = cur.execute("SELECT DISTINCT restaurant_id FROM time_slots WHERE date = ? AND time LIKE ?", (TARGET_DATE, TARGET_TIME_PREFIX+'%')).fetchall()
rest_ids = [r[0] for r in res]
for rid in rest_ids:
    print(f'\n-- restaurant_id = {rid} --')
    for t in cur.execute("SELECT id,number,type,seats_min,seats_max,is_active FROM tables WHERE restaurant_id = ? ORDER BY id", (rid,)):
        print(dict(t))

conn.close()
