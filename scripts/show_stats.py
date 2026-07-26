import sqlite3
import sys

try:
    conn = sqlite3.connect('data/agent.db')
    c = conn.cursor()
    c.execute('''
        SELECT v.youtube_video_id, v.upload_time, p.views, p.likes, p.comments, p.average_view_percentage 
        FROM videos v 
        LEFT JOIN performance_metrics p ON v.id = p.video_id 
        WHERE v.status = 'uploaded' AND p.views IS NOT NULL 
        ORDER BY v.upload_time DESC 
        LIMIT 5
    ''')
    rows = c.fetchall()
    
    if rows:
        print(f"{'YouTube ID':<15} | {'Upload Time':<20} | {'Views':<6} | {'Likes':<6} | {'Comments':<8} | {'AVP (%)'}")
        print("-" * 75)
        for row in rows:
            print(f"{str(row[0]):<15} | {str(row[1])[:19]:<20} | {str(row[2]):<6} | {str(row[3]):<6} | {str(row[4]):<8} | {str(row[5])}")
    else:
        print("No mature videos have analytics data yet.")
        
    conn.close()
except Exception as e:
    print(f"Error reading DB: {e}")
