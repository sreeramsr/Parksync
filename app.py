from flask import Flask, render_template, redirect, url_for, session, flash, request, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, ValidationError, Regexp
import bcrypt
from flask_mysqldb import MySQL
from datetime import datetime, timedelta
import re,math
import razorpay

import folium
import networkx as nx


app = Flask(__name__)

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'carparking'
app.secret_key = 'moni'

mysql = MySQL(app)

class RegisterForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired()])
    phone = StringField("Phone", validators=[
        DataRequired(), 
        Regexp(r'^\d{10}$', message="Phone number must be 10 digits.")
    ])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Register")

    def validate_email(self, field):
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE email=%s", (field.data,))
        user = cursor.fetchone()
        cursor.close()
        if user:
            raise ValidationError('Email Already Taken')

class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        name = form.name.data
        phone = form.phone.data
        email = form.email.data
        password = form.password.data

        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        cursor = mysql.connection.cursor()
        cursor.execute("INSERT INTO users (name, phone, email, password) VALUES (%s, %s, %s, %s)", 
                       (name, phone, email, hashed_password))
        mysql.connection.commit()
        cursor.close()

        return redirect(url_for('login'))

    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
        user = cursor.fetchone()
        cursor.close()
        if user and bcrypt.checkpw(password.encode('utf-8'), user[4].encode('utf-8')):
            session['user_id'] = user[0]
            session['user'] = user[3] 
            return redirect(url_for('selbook'))
        else:
            flash("Login failed. Please check your email and password")
            return redirect(url_for('login'))

    return render_template('login.html', form=form)


@app.route('/dashboards')
def dashboards():
    if 'user_id' in session:
        user_id = session['user_id']

        cursor = mysql.connection.cursor()
        cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
        user = cursor.fetchone()
        cursor.execute("""
    SELECT 
        b.id, 
        b.vehicle_number,
        b.vehicle_type, 
        b.datetime_from, 
        b.datetime_to, 
        b.slot_id, 
        s.area_name,
        b.pay_amount
    FROM advbookings b
    LEFT JOIN slotdisplay s ON b.areaid = s.areaid
    WHERE b.user_id = %s
""", (user_id,))

        
        
        bookings = cursor.fetchall()
        cursor.close()

        if user:
            return render_template('dashboard.html', user=user, bookings=bookings)
            
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear() 
    flash("You have been logged out successfully.")
    return redirect(url_for('login'))

@app.route('/booking', methods=['POST', 'GET'])
def book():
    if 'user_id' in session:
        if request.method == 'POST':
            bvehicleno = request.form['bvehicleno']
            
            bdate = datetime.now().strftime('%Y-%m-%d')
            bfromtime = request.form['bfromtime']
            btotime = request.form['btotime']
            user_id = session['user_id']

            if not re.match(r'^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$', bvehicleno):
                flash('Invalid vehicle number format. Please use the format XX00XX0000.')
                return redirect(url_for('book'))
            
            cursor = mysql.connection.cursor()
            cursor.execute("INSERT INTO bookingdetails (user_id, bvehicleno, bdate, bfromtime, btotime) VALUES (%s, %s, %s, %s, %s)", 
                           (user_id, bvehicleno, bdate, bfromtime, btotime))
            mysql.connection.commit()
            cursor.close()
            return redirect(url_for('dashboards'))

        return render_template('book.html')
    return redirect(url_for('login'))


@app.route('/advslotform/<int:areaid>', methods=['GET'])
def show_advslot_form(areaid):
    # Render the form with the areaid passed
    current_date = datetime.now().strftime('%Y-%m-%d')
    current_time = datetime.now().strftime('%H:%M')
    return render_template('advslotform.html', areaid=areaid,current_date=current_date, current_time=current_time)

@app.route('/instslotform/<int:areaid>', methods=['GET'])
def show_instslot_form(areaid):
    # Render the form with the areaid passed
    current_date = datetime.now().strftime('%Y-%m-%d')
    current_time = datetime.now().strftime('%H:%M')
    return render_template('instslotform.html', areaid=areaid,current_date=current_date, current_time=current_time)



@app.route('/advbook', methods=['POST'])

def advbook():
    vehicle_number = request.form['vehicle_no']
    date_from = request.form['date_from']
    time_from = request.form['time_from']
    date_to = request.form['date_to']
    time_to = request.form['time_to']
    areaid = request.form['areaid']
    vehicle_type = request.form['vehicle_type']

    if not re.match(r'^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$', vehicle_number):
        return jsonify({"error": "Invalid vehicle number format. Use XX00XX0000 (e.g., KA12AB3456)."}), 400

    if 'user_id' not in session:
        return jsonify({"error": "User not logged in."}), 401

    user_id = session['user_id']

    try:
        datetime_from = datetime.strptime(f"{date_from} {time_from}", '%Y-%m-%d %H:%M')
        datetime_to = datetime.strptime(f"{date_to} {time_to}", '%Y-%m-%d %H:%M')
        current_datetime = datetime.now()

        if datetime_from < current_datetime - timedelta(minutes=2):
            return jsonify({"error": "Booking cannot be made for past times."}), 400

        if datetime_from >= datetime_to:
            return jsonify({"error": "End time must be after start time."}), 400

        duration = datetime_to - datetime_from
        if duration < timedelta(minutes=60):
            return jsonify({"error": "Booking must be at least 60 minutes."}), 400

        basepay = 0.833
        if vehicle_type == "2":
            basepay = 0.433
        duration_in_minutes = duration.total_seconds() / 60
        total_pay = round(basepay * duration_in_minutes, 2)

        # Create a Razorpay order
        order = razorpay_client.order.create({
            "amount": int(total_pay * 100),  # Razorpay expects amount in paisa
            "currency": "INR",
            "payment_capture": "1"
        })

        return jsonify({
            "order_id": order['id'],
            "amount": total_pay,
            "booking_details": {
                "vehicle_no": vehicle_number,
                "vehicle_type": vehicle_type,
                "date_from": date_from,
                "time_from": time_from,
                "date_to": date_to,
                "time_to": time_to,
                "areaid": areaid,
                "user_id": user_id,
                "amount": total_pay
            }
        })

    except ValueError:
        return jsonify({"error": "Invalid date or time format."}), 400


@app.route('/verify_payment', methods=['POST'])
def verify_payment():
    data = request.json
    params_dict = {
        'razorpay_payment_id': data['razorpay_payment_id'],
        'razorpay_order_id': data['razorpay_order_id'],
        'razorpay_signature': data['razorpay_signature']
    }

    try:
        # Verify Razorpay payment signature
        razorpay_client.utility.verify_payment_signature(params_dict)

        # Extract booking details
        booking_details = data['booking_details']

        cursor = mysql.connection.cursor()

        # Check for available slots
        datetime_from = datetime.strptime(f"{booking_details['date_from']} {booking_details['time_from']}", '%Y-%m-%d %H:%M')
        datetime_to = datetime.strptime(f"{booking_details['date_to']} {booking_details['time_to']}", '%Y-%m-%d %H:%M')

        booked_slots = check_availability(datetime_from, datetime_to, booking_details['areaid'])

        #booked_slots = check_availability(booking_details['date_from'], booking_details['date_to'], booking_details['areaid'])
        cursor.execute("SELECT total_slot FROM slotdisplay WHERE areaid = %s", (booking_details['areaid'],))
        result = cursor.fetchone()

        if result:
            total_slot = result[0]

        for slot_id in range(1, total_slot+1):
            if slot_id not in booked_slots:
                cursor.execute('''
    INSERT INTO advbookings (slot_id, vehicle_number, user_id, datetime_from, datetime_to, areaid, vehicle_type, pay_amount)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
''', (slot_id, booking_details['vehicle_no'], booking_details['user_id'], 
      booking_details['date_from'] + " " + booking_details['time_from'], 
      booking_details['date_to'] + " " + booking_details['time_to'], 
      booking_details['areaid'], booking_details['vehicle_type'], booking_details['amount']))  # Add amount here

                mysql.connection.commit()
                cursor.close()

                return jsonify({"success": True, "message": f"Payment successful! Slot {slot_id} booked."})

        return jsonify({"success": False, "message": "No slots available."})

    except razorpay.errors.SignatureVerificationError:
        return jsonify({"success": False, "message": "Payment verification failed!"})






@app.route('/advbook1', methods=['POST'])#1
def advbooka():
    vehicle_number = request.form['vehicle_no']
    date_from = request.form['date_from']
    time_from = request.form['time_from']
    date_to = request.form['date_to']
    time_to = request.form['time_to']
    areaid = request.form['areaid'] 
    vehicle_type = request.form['vehicle_type']

    if not re.match(r'^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$', vehicle_number):
        flash('Invalid vehicle number format. Please use the format XX00XX0000 (e.g., KA12AB3456).', 'danger')
        return redirect(url_for('advslotform'))
    
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    try:
        # Parse the dates and times to datetime objects
        datetime_from = datetime.strptime(f"{date_from} {time_from}", '%Y-%m-%d %H:%M')
        datetime_to = datetime.strptime(f"{date_to} {time_to}", '%Y-%m-%d %H:%M')
        current_datetime = datetime.now()

        # Ensure from date-time is not in the past
        if datetime_from < current_datetime - timedelta(minutes=2):
            flash("Booking cannot be made for past dates or times.", "danger")
            return redirect(url_for('dashboards'))

        # Ensure valid datetime range
        if datetime_from >= datetime_to:
            flash("End date and time must be after start date and time.", "danger")
            return redirect(url_for('dashboards'))

        # Ensure booking duration is at least 60 minutes
        duration = datetime_to - datetime_from
        if duration < timedelta(minutes=60):
            flash("Booking must be for at least 60 minutes.", "danger")
            return redirect(url_for('dashboards'))

        # Calculate total pay
        basepay = 0.833  # Example base rate (per minute)
        duration_in_minutes = duration.total_seconds() / 60
        total_pay = basepay * duration_in_minutes

        # Check for availability of the slots
        booked_slots = check_availability(datetime_from, datetime_to,areaid)
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT total_slot FROM slotdisplay WHERE areaid = %s", (areaid,))
        result = cursor.fetchone()

        if result:
            total_slot = result[0]

        # Try to book a slot if available
        for slot_id in range(1, total_slot+1):  # Assuming 10 slots available
            if slot_id not in booked_slots:
                cursor = mysql.connection.cursor()
                cursor.execute('''
                    INSERT INTO advbookings (slot_id, vehicle_number, user_id, datetime_from, datetime_to,areaid,vehicle_type)
                    VALUES (%s, %s, %s, %s, %s,%s,%s)
                ''', (slot_id, vehicle_number, user_id, datetime_from.strftime('%Y-%m-%d %H:%M'), datetime_to.strftime('%Y-%m-%d %H:%M'),areaid,vehicle_type))
                mysql.connection.commit()
                cursor.close()

                flash(f"Slot {slot_id} booked successfully! ", "success")
                return redirect(url_for('dashboards'))

        flash("No slots available for the selected date and time range.", "danger")
        return redirect(url_for('dashboards'))

    except ValueError:
        flash("Invalid date or time format. Use YYYY-MM-DD for date and HH:MM for time.", "danger")
        return redirect(url_for('dashboards'))


# Helper function to check booked slots
def check_availability(datetime_from, datetime_to, areaid):
    cursor = mysql.connection.cursor()
    cursor.execute('''
        SELECT slot_id 
        FROM advbookings
        WHERE areaid = %s AND datetime_from < %s AND datetime_to > %s
    ''', (areaid, datetime_to.strftime('%Y-%m-%d %H:%M'), datetime_from.strftime('%Y-%m-%d %H:%M')))
    results = cursor.fetchall()
    cursor.close()
    return {row[0] for row in results}



@app.route('/slot')
def slot():
    return render_template('selslot.html')

@app.route('/selbook')
def selbook():
    return render_template('selectbook.html')

@app.route('/seladvbook')
def seladvbook():
    return render_template('advslot.html')

@app.route('/advslotform')
def advslotform():
    return render_template('advslotform.html')


@app.route('/advslot')
def advslot():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cursor = mysql.connection.cursor()
    
    # Fetch parking area data
    cursor.execute("SELECT areaid, area_name, total_slot FROM slotdisplay")  
    parking_data = cursor.fetchall()

    # Fetch occupied slot count per areaid from bookingdetails
    cursor.execute("""
        SELECT areaid, COUNT(*) 
        FROM advbookings
        WHERE datetime_from <= NOW() AND datetime_to >= NOW() 
        GROUP BY areaid
    """)
    occupied_slots = dict(cursor.fetchall())  # Convert result into a dictionary

    updated_parking_data = []
    for area in parking_data:
        area_id = area[0]
        total_slots = area[2]  # Assuming slotdisplay has a total_slots column
        occupied = occupied_slots.get(area_id, 0)
        available_slots = max(0, total_slots - occupied)  # Ensure non-negative values
        updated_parking_data.append((area[0], area[1], available_slots))

    cursor.close()
    
    return render_template('advslot.html', parking_data=updated_parking_data)



@app.route('/parking_availability')
def parking_availability():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT s.id, a.area_name,
               s.slot1, s.slot2, s.slot3, s.slot4, s.slot5, s.slot6, 
               s.slot7, s.slot8, s.slot9, s.slot10, s.slot11, s.slot12
        FROM slotavl s
        INNER JOIN slotdisplay a ON s.id = a.areaid
    """)
    results = cur.fetchall()
    cur.close()

    parking_data = []
    for row in results:
        id = row[0]
        area_name = row[1]
        slots = row[2:]  # Extract slots (slot1 to slot12)
        available_count = slots.count(0)  # Count available slots
        parking_data.append({
            'id': id,
            'area_name': area_name,
            'available_count': available_count
        })

    return render_template('selslot.html', parking_data=parking_data)

# New API Route to Fetch Updated Parking Data
@app.route('/get_parking_data')
def get_parking_data():
    if 'user_id' not in session:
        return jsonify([])  # Return empty list if not logged in

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT s.id, s.slot1, s.slot2, s.slot3, s.slot4, s.slot5, s.slot6, 
               s.slot7, s.slot8, s.slot9, s.slot10, s.slot11, s.slot12
        FROM slotavl s
    """)
    results = cur.fetchall()
    cur.close()

    parking_data = []
    for row in results:
        id = row[0]
        slots = row[1:]  # Extract slots (slot1 to slot12)
        available_count = slots.count(0)  # Count available slots
        parking_data.append({
            'id': id,
            'available_count': available_count
        })

    return jsonify(parking_data)  # Return JSON data


@app.route('/tsummary')
def tsummary():
    # Ensure user is logged in
    if 'user_id' not in session:
        flash('Please log in to view your booking summary.', 'warning')
        return redirect(url_for('login'))

    user_id = session['user_id']  # Get logged-in user's ID

    # Create a cursor object using the MySQL connection
    cur = mysql.connection.cursor()

    # Fetch the most recent booking for the logged-in user
    query = """
        SELECT id, vehicle_number, datetime_from, datetime_to, created_at, slot_id, areaid,vehicle_type
        FROM advbookings 
        WHERE user_id = %s 
        ORDER BY created_at DESC 
        LIMIT 1
    """
    cur.execute(query, (user_id,))

    # Fetch the result (the most recent booking)
    booking = cur.fetchone()

    # Close the cursor
    cur.close()

    # If no booking is found
    if not booking:
        flash('No recent booking found.', 'danger')
        return redirect(url_for('index'))  # Redirect to home if no recent booking

    # Prepare the booking details in a dictionary
    booking_details = {
        'booking_id': booking[0],
        'vehicle_no': booking[1],
        'vehicle_type': booking[7],
        'date_from': booking[3],
        'date_to': booking[4],
        'slot_no': booking[5],  # slot_id
        'areaid': booking[6]  # areaid for location retrieval
    }

    # Return the template with booking details
    return render_template('tsummary.html', booking_details=booking_details)


@app.route('/get_slot_location/<int:areaid>', methods=['GET'])
def get_slot_location(areaid):
    cur = mysql.connection.cursor()
    cur.execute("SELECT lat, lon FROM slotdisplay WHERE areaid = %s", (areaid,))
    result = cur.fetchone()
    cur.close()
    
    if result and result[0] != 0 and result[1] != 0:
        return jsonify({'lat': result[0], 'lon': result[1]})
    else:
        return jsonify({'error': 'Invalid Area ID or location not found'}), 404






# Razorpay API credentials
RAZORPAY_KEY_ID = "rzp_test_cIeCwAX1qqUKB5"
RAZORPAY_KEY_SECRET = "u0I1RHXzBinlBqoOdeBIjOol"

razorpay_client = razorpay.Client(auth=("rzp_test_cIeCwAX1qqUKB5", "u0I1RHXzBinlBqoOdeBIjOol"))



#internal navigation
# Define parking spots and entrance
nodes = {
    "Entrance": (82, 15),
    "inter1": (82, 30),
    "inter2": (82, 32),
    "inter3": (82, 35),
    "inter4": (82, 38),
    "inter5": (82, 41),
    "inter6": (82, 44),
    "inter7": (82, 47),
    "inter8": (82, 50),
    "inter9": (82, 53),
    "inter10": (82, 56),
    "inter11": (82, 59),
    "inter12": (82, 62),
    "inter13": (82, 65),
    "inter14": (82, 68),
    "inter15": (82, 72),
    "inter16": (82, 75),
    
    "1": (75, 23),
    "2": (75, 26),
    "3": (75, 29),
    "4": (75, 32),
    "5": (75, 35),
    "6": (75, 39),
    "7": (75, 42),
    "8": (75, 45),
    "9": (75, 49),
    "10": (75, 52),
    "11": (75, 55),
    "12": (75, 58),
    "13": (75, 61),
    "14": (75, 64),
    "15": (75, 65),
    "16": (75, 68),
    "17": (75, 71),
    "18": (75, 74),
    "19": (73, 11),
    "20": (70, 11),
    "21": (67, 11),
    "22": (64, 11),
    "23": (62, 11),
    "24": (59, 11),
    "25": (57, 11),
    "26": (53, 11),
    "27": (51, 11),
    "28": (48, 11),
    "29": (45, 11),
    "30": (42, 11),
    "31": (39, 11),
    "32": (36, 11),
    "33": (34, 11),
    "34": (31, 11),
    "35": (29, 11),
    "36": (26, 11),
    "37": (23, 11),
    "38": (20, 11),
    "39": (15, 11),
}

# Graph Representation
edges = [
    ("Entrance","inter1",10), ("Entrance","inter2",10), ("Entrance","inter3",10),
    ("Entrance","inter4",10), ("Entrance","inter5",10), ("Entrance","inter6",10),
    ("Entrance","inter7",10), ("Entrance","inter8",10), ("Entrance","inter9",10),
    ("Entrance","inter10",10), ("Entrance","inter11",10), ("Entrance","inter12",10),
    ("Entrance","inter13",10), ("Entrance","inter14",10), ("Entrance","inter15",10),
    ("Entrance","inter16",10), ("Entrance", "19", 10), ("Entrance", "20", 15),
    ("Entrance", "21", 15), ("Entrance", "22", 15), ("Entrance", "23", 15),
    ("Entrance", "24", 15), ("Entrance", "25", 15), ("Entrance", "26", 15),
    ("Entrance", "27", 15), ("Entrance", "28", 15), ("Entrance", "29", 15),
    ("Entrance", "30", 15), ("Entrance", "31", 15), ("Entrance", "32", 15),
    ("Entrance", "33", 15), ("Entrance", "34", 15), ("Entrance", "35", 15),
    ("Entrance", "36", 15), ("Entrance", "37", 15), ("Entrance", "38", 15),
    ("Entrance", "39", 15), ("Entrance", "1", 10), ("Entrance", "2", 15),
    ("inter1", "3", 20), ("inter2", "4", 20), ("inter3", "5", 20),
    ("inter4", "6", 20), ("inter5", "7", 20), ("inter6", "8", 20),
    ("inter7", "9", 20), ("inter8", "10", 20), ("inter9", "11", 20),
    ("inter10", "12", 20), ("inter11", "13", 20), ("inter12", "14", 20),
    ("inter13", "15", 20), ("inter14", "16", 20), ("inter15", "17", 20),
    ("inter16", "18", 20),
]

graph = nx.Graph()
for edge in edges:
    graph.add_edge(edge[0], edge[1], weight=edge[2])

def get_shortest_path(start, end):
    """Return shortest path using A*."""
    return nx.astar_path(graph, start, end, weight="weight") if start in nodes and end in nodes else []

@app.route("/internalnav")
def internalnav():
    return render_template("internal.html", spots=nodes.keys())

@app.route("/internalmap")
def generate_map():
    if 'user_id' not in session:
        flash('Please log in to view your booking summary.', 'warning')
        return redirect(url_for('login'))
    user_id = session.get('user_id')  # Use .get() to avoid KeyError if 'user_id' is missing
    cur = mysql.connection.cursor()

# Fetch the most recent booking for the logged-in user
    query = """
    SELECT slot_id
    FROM advbookings 
    WHERE user_id = %s 
    ORDER BY created_at DESC 
    LIMIT 1
"""
    cur.execute(query, (user_id,))
    bookinginternal = cur.fetchone()

# Extract slot_id safely (or use a default value if no booking found)
    selected_spot = request.args.get("spot", default=str(bookinginternal[0]) if bookinginternal else "3")

    user_lat = request.args.get("lat", type=float, default=None)
    user_lng = request.args.get("lng", type=float, default=None)

    # Convert live user coordinates to the nearest node
    def get_nearest_node(lat, lng):
        return min(nodes.keys(), key=lambda node: (nodes[node][0] - lat)**2 + (nodes[node][1] - lng)**2)

    current_location = get_nearest_node(user_lat, user_lng) if user_lat and user_lng else "Entrance"
    path = get_shortest_path(current_location, selected_spot)

    # Initialize Folium map
    m = folium.Map(location=[50, 50], zoom_start=2, crs="Simple", tiles=None)

    # Overlay the parking layout image
    img_overlay = "static/pict4.png"
    folium.raster_layers.ImageOverlay(
        name="Parking Layout",
        image=img_overlay,
        bounds=[[0, 0], [100, 100]],  # Keep image size same
        opacity=1,
    ).add_to(m)

    # Draw only the shortest path (no markers)
    if path:
        folium.PolyLine([nodes[node] for node in path], color="red", weight=5).add_to(m)

    # Removed marker-adding loop (hides markers)
    
    

    m.save("templates/internalmap.html")
    return render_template("internalmap.html", spot=selected_spot, spots=nodes.keys(), current=current_location)


if __name__ == '__main__':
    app.run(debug=True)
    #app.run(host='0.0.0.0', port=5000, debug=True)
