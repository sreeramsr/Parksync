import cv2
import pandas as pd
import numpy as np
from ultralytics import YOLO
import time
import pymysql
from flask import Flask

# Flask app configuration
app = Flask(__name__)
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''  # Set your MySQL password
app.config['MYSQL_DB'] = 'carparking'  # Ensure this database exists
app.secret_key = 'moni'

# Initialize YOLO model
model = YOLO('yolov8s.pt')  # Ensure the YOLO model weights are available

# Function to update database
def update_database(slot_status):
    try:
        connection = pymysql.connect(
            host=app.config['MYSQL_HOST'],
            user=app.config['MYSQL_USER'],
            password=app.config['MYSQL_PASSWORD'],
            db=app.config['MYSQL_DB']
        )
        cursor = connection.cursor()

        # Update each slot in the database
        for i, status in enumerate(slot_status):
            slot_column = f'slot{i+1}'  # Dynamically determine slot column
            sql_query = f"UPDATE slotavl SET {slot_column} = %s WHERE id = 1"
            print(f"Executing: {sql_query} with value {status}")
            cursor.execute(sql_query, (status,))
        
        connection.commit()
        print("Database updated successfully")
    except Exception as e:
        print(f"Database Error: {e}")
    finally:
        cursor.close()
        connection.close()

# Debugging mouse callback function
def RGB(event, x, y, flags, param):
    if event == cv2.EVENT_MOUSEMOVE:
        colorsBGR = [x, y]
        print(colorsBGR)

# Set up OpenCV window and mouse callback
cv2.namedWindow('RGB')
cv2.setMouseCallback('RGB', RGB)

# Load video for parking slot detection
cap = cv2.VideoCapture('parking1.mp4')  # Ensure this file exists

# Load COCO class names
with open("coco.txt", "r") as my_file:
    class_list = my_file.read().split("\n")

# Define parking slot areas
areas = [
    [(52,364),(30,417),(73,412),(88,369)],
    [(105,353),(86,428),(137,427),(146,358)],
    [(159,354),(150,427),(204,425),(203,353)],
    [(217,352),(219,422),(273,418),(261,347)],
    [(274,345),(286,417),(338,415),(321,345)],
    [(336,343),(357,410),(409,408),(382,340)],
    [(396,338),(426,404),(479,399),(439,334)],
    [(458,333),(494,397),(543,390),(495,330)],
    [(511,327),(557,388),(603,383),(549,324)],
    [(564,323),(615,381),(654,372),(596,315)],
    [(616,316),(666,369),(703,363),(642,312)],
    [(674,311),(730,360),(764,355),(707,308)]
]

while True:
    ret, frame = cap.read()
    if not ret:
        break
    time.sleep(1)  # Optional: Slow down processing for testing
    frame = cv2.resize(frame, (1020, 500))

    # YOLO object detection
    results = model.predict(frame)
    detections = results[0].boxes.data
    px = pd.DataFrame(detections).astype("float")

    # Initialize slot occupancy status
    occupied = [0] * len(areas)

    for _, row in px.iterrows():
        x1, y1, x2, y2, _, class_id = map(int, row)
        detected_class = class_list[class_id]
        if 'car' in detected_class:
            # Calculate center of the bounding box
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2

            for i, area in enumerate(areas):
                if cv2.pointPolygonTest(np.array(area, np.int32), (cx, cy), False) >= 0:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.circle(frame, (cx, cy), 3, (0, 0, 255), -1)
                    occupied[i] = 1  # Mark slot as occupied
                    cv2.putText(frame, detected_class, (x1, y1), cv2.FONT_HERSHEY_COMPLEX, 0.5, (255, 255, 255), 1)
                    break

    # Calculate available slots
    available_slots = len(areas) - sum(occupied)
    print(f"Available Spaces: {available_slots}")

    # Update database with current slot status
    update_database(occupied)

    # Draw parking slot boundaries
    for i, area in enumerate(areas):
        color = (0, 0, 255) if occupied[i] > 0 else (0, 255, 0)
        cv2.polylines(frame, [np.array(area, np.int32)], True, color, 2)
        cv2.putText(frame, str(i + 1), (area[0][0], area[0][1]), cv2.FONT_HERSHEY_COMPLEX, 0.5, color, 1)

    # Display available spaces
    cv2.putText(frame, f"Available Spaces: {available_slots}", (23, 30), cv2.FONT_HERSHEY_PLAIN, 3, (255, 255, 255), 2)
    cv2.imshow("RGB", frame)

    # Exit condition
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
