from flask import Flask, request, jsonify, session, render_template, redirect, url_for,flash,send_file
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime, timedelta
import google.generativeai as genai
from google.api_core import retry
import logging
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import random
import string
import smtplib
from email.mime.text import MIMEText
from werkzeug.utils import secure_filename

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your-very-secure-secret-key'  # Change this for production

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Add these configurations after the app initialization
UPLOAD_FOLDER = 'static/uploads/profile_images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ======================
# SMTP CONFIGURATION
# ======================
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587
SMTP_USERNAME = 'zoyajungkm@gmail.com'
SMTP_PASSWORD = 'byff cjyv yudr yxcb'
FROM_EMAIL = 'Carbon Tracker <zoyajungkm@gmail.com>'


# ========== HARDCODED CONFIGURATIONS (DEVELOPMENT ONLY) ==========
# Gemini AI Configuration
GEMINI_API_KEY = "AIzaSyAT4TJfOmiD8Uxy80Fqj_rKQ2ckRnQroO0"  # Replace with your actual key
genai.configure(api_key=GEMINI_API_KEY)


app = Flask(__name__)
app.secret_key = 'your-very-secure-secret-key'
app.config['SESSION_COOKIE_NAME'] = 'your_app_session'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)
app.config['SESSION_REFRESH_EACH_REQUEST'] = True

# MySQL configurations
db_config = {
    'user': 'root',
    'password': 'Rizwana*123',
    'host': 'localhost',
    'database': 'project'
}
verification_tokens = {}
password_reset_tokens = {}

def get_db_connection():
    return mysql.connector.connect(**db_config)
# Model initialization with fallback
try:
    gemini_model = genai.GenerativeModel('gemini-2.5-flash')
    logger.info("Using Gemini 2.5 Flash model")
except Exception as e:
    logger.warning(f"Falling back to Gemini 1.0 Pro: {str(e)}")
    gemini_model = genai.GenerativeModel('gemini-pro')

# ======================
# EMAIL FUNCTIONS
# ======================
def send_verification_email(email, otp):
    """Send OTP email via SMTP with TLS"""
    message = MIMEText(f"""
        <h2>Carbon Tracker Verification</h2>
        <p>Your verification code is: <strong>{otp}</strong></p>
        <p>This code expires in 15 minutes.</p>
    """, 'html')
    
    message['Subject'] = 'Your Verification Code'
    message['From'] = FROM_EMAIL
    message['To'] = email

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)
        print(f"Email sent to {email}")
        return True
    except Exception as e:
        print(f"Failed to send email: {str(e)}")
        return False

def send_password_reset_email(email, otp):
    """Send password reset OTP email"""
    message = MIMEText(f"""
        <h2>Password Reset Request</h2>
        <p>Your password reset code is: <strong>{otp}</strong></p>
        <p>This code expires in 15 minutes.</p>
    """, 'html')
    
    message['Subject'] = 'Password Reset Code'
    message['From'] = FROM_EMAIL
    message['To'] = email

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)
        print(f"Password reset email sent to {email}")
        return True
    except Exception as e:
        print(f"Failed to send password reset email: {str(e)}")
        return False
    
# ======================
# CORE ROUTES
# ======================
@app.route('/')
def index():
    return send_file('index.html')

@app.route('/signup.html')
def signup():
    return render_template('signup.html')

@app.route('/login.html')
def login():
    return render_template('login.html')
@app.route('/challenges.html')
def challenges():
    return render_template('challenges.html')


# ======================
# AUTHENTICATION ROUTES
# ======================
@app.route('/api/signup', methods=['POST'])
def handle_signup():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'message': 'Email and password are required'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'Database error'}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            return jsonify({'message': 'Email already exists'}), 400

        otp = ''.join(random.choices(string.digits, k=6))
        hashed_password = generate_password_hash(password)
        
        verification_tokens[email] = {
            'otp': otp,
            'hashed_password': hashed_password,
            'expires_at': datetime.now() + timedelta(minutes=15)
        }

        if send_verification_email(email, otp):
            return jsonify({
                'message': 'Verification email sent',
                'email': email
            }), 200
        else:
            return jsonify({'message': 'Failed to send verification email'}), 500

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'message': 'Server error'}), 500
    finally:
        if conn.is_connected():
            cursor.close() 
            conn.close()

@app.route('/verify-email', methods=['POST'])
def verify_email_endpoint():
    return verify_email_handler()

@app.route('/api/verify', methods=['POST'])
def verify_email_handler():
    data = request.get_json()
    email = data.get('email')
    otp = data.get('otp')

    if not email or not otp:
        return jsonify({'message': 'Email and OTP are required'}), 400

    token_data = verification_tokens.get(email)
    if not token_data or token_data['expires_at'] < datetime.now():
        return jsonify({'message': 'Invalid or expired OTP'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'Database error'}), 500

    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (email, password, verified) VALUES (%s, %s, %s)",
            (email, token_data['hashed_password'], True)
        )
        conn.commit()

         # Get the new user's ID and set session
        user_id = cursor.lastrowid
        session['user_id'] = user_id
        del verification_tokens[email]
         # Get the new user's ID and set session
        user_id = cursor.lastrowid
        session['user_id'] = user_id
    
        return jsonify({
            'message': 'Email verified successfully',
            'redirect': '/details.html'  # Add this line
        }), 200
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'message': 'Database error'}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/login', methods=['POST'])
def handle_login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'message': 'Email and password are required'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'Database error'}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if not user:
            return jsonify({'message': 'Email not found'}), 404

        if not check_password_hash(user['password'], password):
            return jsonify({'message': 'Incorrect password'}), 401

        if not user['verified']:
            return jsonify({'message': 'Email not verified'}), 403
        
         
        session['user_id'] = user['id']
        return jsonify({
            'message': 'Login successful',
            'redirect': '/main.html'  # Add this line
        }), 200

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'message': 'Server error'}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

# ======================
# PASSWORD RESET ROUTES
# ======================
@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({'message': 'Email is required'}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({'message': 'Database error'}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()

        if not user:
            return jsonify({'message': 'Email not found'}), 404

        otp = ''.join(random.choices(string.digits, k=6))
        password_reset_tokens[email] = {
            'otp': otp,
            'expires_at': datetime.now() + timedelta(minutes=15)
        }

        if send_password_reset_email(email, otp):
            return jsonify({
                'message': 'Reset OTP sent',
                'token': email  # Using email as token identifier
            }), 200
        else:
            return jsonify({'message': 'Failed to send reset email'}), 500

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({'message': 'Failed to process request'}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    email = data.get('email')
    otp = data.get('otp')
    new_password = data.get('newPassword')

    # Validate all required fields
    if not email or not otp or not new_password:
        return jsonify({
            'success': False,
            'message': 'All fields are required'
        }), 400

    # Check password length
    if len(new_password) < 6:
        return jsonify({
            'success': False,
            'message': 'Password must be at least 6 characters'
        }), 400

    # Check if OTP exists and is valid
    token_data = password_reset_tokens.get(email)
    if not token_data:
        return jsonify({
            'success': False,
            'message': 'Invalid or expired OTP'
        }), 400

    # Check OTP expiration
    if token_data['expires_at'] < datetime.now():
        return jsonify({
            'success': False,
            'message': 'OTP has expired'
        }), 400

    # Verify OTP matches
    if token_data['otp'] != otp:
        return jsonify({
            'success': False,
            'message': 'Invalid verification code'
        }), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({
            'success': False,
            'message': 'Database connection error'
        }), 500

    try:
        # Hash the new password
        hashed_password = generate_password_hash(new_password)
        cursor = conn.cursor()
        
        # Update password in database
        cursor.execute(
            "UPDATE users SET password = %s WHERE email = %s",
            (hashed_password, email)
        )
        
        # Only commit if the update was successful
        if cursor.rowcount == 1:
            conn.commit()
            # Clear the used OTP
            del password_reset_tokens[email]
            return jsonify({
                'success': True,
                'message': 'Password reset successful'
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': 'Email not found'
            }), 404

    except Exception as e:
        conn.rollback()
        logger.error(f"Password reset error: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Failed to reset password'
        }), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/resend-otp', methods=['POST'])
def resend_otp():
    data = request.get_json()
    email = data.get('email')
    
    if not email:
        return jsonify({'message': 'Email is required'}), 400

    # Check if this is for verification or password reset
    if email in verification_tokens:
        # Resend verification OTP
        new_otp = ''.join(random.choices(string.digits, k=6))
        verification_tokens[email]['otp'] = new_otp
        verification_tokens[email]['expires_at'] = datetime.now() + timedelta(minutes=15)
        
        if send_verification_email(email, new_otp):
            return jsonify({'message': 'OTP resent successfully'}), 200
        else:
            return jsonify({'message': 'Failed to resend verification email'}), 500
            
    elif email in password_reset_tokens:
        # Resend password reset OTP
        new_otp = ''.join(random.choices(string.digits, k=6))
        password_reset_tokens[email]['otp'] = new_otp
        password_reset_tokens[email]['expires_at'] = datetime.now() + timedelta(minutes=15)
        
        if send_password_reset_email(email, new_otp):
            return jsonify({'message': 'OTP resent successfully'}), 200
        else:
            return jsonify({'message': 'Failed to resend reset email'}), 500
    else:
        return jsonify({'message': 'No pending verification for this email'}), 400


@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully"}), 200

@app.route('/details.html')
def details_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('details.html')

@app.route('/main.html')
def main_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('main.html')

@app.route('/details', methods=['GET', 'POST'])
def details():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'User not logged in'}), 401

    if request.method == 'GET':
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute('''
                SELECT name, household_members, gender, dob 
                FROM Details 
                WHERE user_id = %s
                ORDER BY entry_date DESC
                LIMIT 1
            ''', (user_id,))
            user_details = cursor.fetchone()
            
            # Default response if no details exist
            response = {
                "name": user_details.get("name", "") if user_details else "",
                "household_members": user_details.get("household_members", "") if user_details else "",
                "gender": user_details.get("gender", "") if user_details else "",
                "dob": user_details.get("dob", "") if user_details else ""
            }
            return jsonify(response), 200
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            conn.close()

    elif request.method == 'POST':
        data = request.json
        name = data.get('name')
        household_members = data.get('household_members')
        gender = data.get('gender')
        dob = data.get('dob')

        if not all([name, household_members, gender, dob]):
            return jsonify({'error': 'All fields are required'}), 400

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # First check if details exist for this user
            cursor.execute('SELECT 1 FROM Details WHERE user_id = %s', (user_id,))
            exists = cursor.fetchone()
            
            if exists:
                # Update existing record
                cursor.execute('''
                    UPDATE Details 
                    SET name = %s, 
                        household_members = %s, 
                        gender = %s, 
                        dob = %s,
                        entry_date = NOW()
                    WHERE user_id = %s
                ''', (name, household_members, gender, dob, user_id))
            else:
                # Insert new record
                cursor.execute('''
                    INSERT INTO Details 
                    (user_id, name, household_members, gender, dob, entry_date)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                ''', (user_id, name, household_members, gender, dob))
                
            conn.commit()
            return jsonify({'message': 'Details saved successfully'}), 200
            
        except Exception as e:
            conn.rollback()
            return jsonify({'error': str(e)}), 500
        finally:
            cursor.close()
            conn.close()

# Section Redirection
@app.route('/redirect/<section>')
def redirect_section(section):
    if section == "energy":
        return redirect(url_for('energy_page'))
    elif section == "travel":
        return redirect(url_for('travel_page'))
    elif section == "food":
        return redirect(url_for('food_page'))
    elif section == "waste":
        return redirect(url_for('waste_page'))
    else:
        return jsonify({'error': 'Invalid section'}), 400

# Energy Routes
@app.route('/energy.html')
def energy_page():
    return render_template('energy.html')

@app.route('/energycalc.html')
def energy_calc_page():
    return render_template('energycalc.html')
@app.route('/save_energy_devices', methods=['POST'])
def save_energy_devices():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    user_id = session['user_id']
    data = request.get_json()
    devices = data.get('devices', [])

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # First delete all existing devices for this user
        cursor.execute('DELETE FROM energy_devices WHERE user_id = %s', (user_id,))

        # Then insert the new unique devices
        seen_devices = set()
        for device in devices:
            if device not in seen_devices:
                cursor.execute('''
                    INSERT INTO energy_devices (user_id, device_name)
                    VALUES (%s, %s)
                ''', (user_id, device))
                seen_devices.add(device)

        conn.commit()
        return jsonify({'message': 'Devices saved successfully!'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': f'Error saving devices: {str(e)}'}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/get_energy_devices', methods=['GET'])
def get_energy_devices():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    user_id = session['user_id']

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT device_name FROM energy_devices WHERE user_id = %s', (user_id,))
        devices = [row[0] for row in cursor.fetchall()]
        return jsonify({'devices': devices}), 200
    except Exception as e:
        return jsonify({'message': f'Error fetching devices: {str(e)}'}), 500
    finally:
        cursor.close()
        conn.close()
@app.route('/save_energy_data', methods=['POST'])
def save_energy_data():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    user_id = session['user_id']
    data = request.get_json()
    
    # Validate required fields
    if not data or 'devices' not in data:
        return jsonify({'message': 'Invalid data format'}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Delete only today's entries
        cursor.execute('''
            DELETE FROM energy_devices 
            WHERE user_id = %s AND DATE(entry_date) = CURDATE()
        ''', (user_id,))

        # Insert new device data
        for device in data['devices']:
            cursor.execute('''
                INSERT INTO energy_devices 
                (user_id, device_name, hours, emission, entry_date)
                VALUES (%s, %s, %s, %s, NOW())
            ''', (
                user_id,
                device['device_name'],
                device['hours_used'],
                device['carbon_emissions']
            ))

        conn.commit()
        return jsonify({
            'success': True,
            'message': 'Energy data saved successfully!',
            'total_emissions': data.get('total_emissions', 0)
        }), 200
    except Exception as e:
        conn.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/get_saved_energy_data', methods=['GET'])
def get_saved_energy_data():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    user_id = session['user_id']

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT 
                device_name, 
                hours, 
                emission 
            FROM energy_devices 
            WHERE user_id = %s AND DATE(entry_date) = CURDATE()
        ''', (user_id,))
        
        devices = {}
        for row in cursor.fetchall():
            devices[row['device_name']] = {
                'hours': row['hours'],
                'emission': row['emission']
            }
            
        return jsonify({
            'success': True,
            'savedData': devices
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
    finally:
        cursor.close()
        conn.close()
# Travel Routes
@app.route('/travel.html')
def travel_page():
    return render_template('travel.html')

@app.route('/travelcalc.html')
def travel_calc_page():
    return render_template('travelcalc.html')
@app.route('/save_vehicles', methods=['POST'])
def save_vehicles():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    user_id = session['user_id']
    data = request.get_json()
    vehicles = data.get('vehicles', [])

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # First delete all existing vehicles for this user
        cursor.execute('DELETE FROM vehicles WHERE user_id = %s', (user_id,))
        
        # Then insert the new unique vehicles
        seen_vehicles = set()
        for vehicle in vehicles:
            vehicle_key = (vehicle['name'], vehicle['category'])
            if vehicle_key not in seen_vehicles:
                cursor.execute('''
                    INSERT INTO vehicles 
                    (user_id, vehicle_name, vehicle_category)
                    VALUES (%s, %s, %s)
                ''', (user_id, vehicle['name'], vehicle['category']))
                seen_vehicles.add(vehicle_key)

        conn.commit()
        return jsonify({'message': 'Vehicles saved successfully!'}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({'message': f'Error saving vehicles: {str(e)}'}), 500
    finally:
        cursor.close()
        conn.close()
        
@app.route('/get_saved_vehicles', methods=['GET'])
def get_saved_vehicles():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    user_id = session['user_id']

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT vehicle_name, vehicle_category 
            FROM vehicles 
            WHERE user_id = %s
            AND vehicle_category NOT IN (
                'City Bus', 'Electric Bus', 'Metro Rail', 'Suburban Train',
                'Auto-Rickshaw (Petrol)', 'Auto-Rickshaw (Electric)',
                'Taxi (Petrol)', 'Taxi (Diesel)', 'Domestic Flight'
            )
        ''', (user_id,))
        vehicles = cursor.fetchall()
        return jsonify({'vehicles': vehicles}), 200
    except Exception as e:
        return jsonify({'message': f'Error fetching vehicles: {str(e)}'}), 500
    finally:
        cursor.close()
        conn.close()

# Update the save_travel_data route
@app.route('/save_travel_data', methods=['POST'])
def save_travel_data():
    print("Received request to save travel data")  # Debug log
    if 'user_id' not in session:
        print("Unauthorized - no user_id in session")  # Debug log
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    try:
        data = request.get_json()
        print("Received data:", data)  # Debug log
        
        if not data or 'savedData' not in data:
            print("Invalid data format received")  # Debug log
            return jsonify({'success': False, 'message': 'Invalid data format'}), 400

        user_id = session['user_id']
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Delete previous entries for today
        cursor.execute("""
            DELETE FROM vehicles 
            WHERE user_id = %s AND DATE(entry_date) = CURDATE()
        """, (user_id,))
        
        # Insert new data
        for vehicle_name, details in data['savedData'].items():
            cursor.execute("""
                INSERT INTO vehicles 
                (user_id, vehicle_name, vehicle_category, distance, emission, entry_date)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """, (
                user_id,
                vehicle_name,
                details['category'],
                details['distance'],
                details['emission']
            ))
        
        conn.commit()
        return jsonify({
            'success': True,
            'message': 'Travel data saved successfully!'
        })
        
    except Exception as e:
        conn.rollback()
        print("Error saving travel data:", str(e))
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
        
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals(): conn.close()




@app.route('/get_saved_travel_data', methods=['GET'])
def get_saved_travel_data():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    user_id = session['user_id']
    today = datetime.now().date()

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get all today's vehicles
        cursor.execute('''
            SELECT 
                vehicle_name, 
                vehicle_category, 
                distance, 
                emission,
                CASE
                    WHEN vehicle_category IN ('City Bus', 'Electric Bus', 'Metro Rail', 'Suburban Train', 'Domestic Flight')
                    THEN 'public'
                    ELSE 'private'
                END as vehicle_type
            FROM vehicles 
            WHERE user_id = %s AND DATE(entry_date) = %s
        ''', (user_id, today))
        
        vehicles = cursor.fetchall()
        
        # Separate and format data
        saved_data = {}
        vehicle_emissions = []
        public_transport = []
        
        for vehicle in vehicles:
            saved_data[vehicle['vehicle_name']] = {
                'category': vehicle['vehicle_category'],
                'distance': vehicle['distance'],
                'emission': vehicle['emission']
            }
            
            vehicle_emissions.append({
                'name': vehicle['vehicle_name'],
                'category': vehicle['vehicle_category'],
                'distance': vehicle['distance'],
                'emission': vehicle['emission'],
                'type': vehicle['vehicle_type']
            })
            
            if vehicle['vehicle_type'] == 'public':
                public_transport.append({
                    'name': vehicle['vehicle_name'],
                    'distance': vehicle['distance']
                })
        
        return jsonify({
            'savedData': saved_data,
            'vehicleEmissions': vehicle_emissions,
            'publicTransport': public_transport
        }), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()
# Food Routes
@app.route('/food.html')
def food_page():
    return render_template('food.html')

@app.route('/foodcalc.html')
def food_calc_page():
    return render_template('foodcalc.html')

# Waste Routes
@app.route('/waste.html')
def waste_page():
    return render_template('waste.html')

@app.route('/wastecalc.html')
def waste_calc_page():
    return render_template('wastecalc.html')

# Waste Routes
@app.route('/get_user_id')
def get_user_id():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    return jsonify({'user_id': session['user_id']})

# Add this at the top with other configurations
WASTE_EMISSION_FACTORS = {
    'disposed': {
        'wet-waste': 0.25,
        'dry-waste': 0.5,
        'e-waste': 1.2,
        'textile-waste': 0.8,
        'footwear-waste': 0.6,
        'furniture-waste': 1.5
    },
    'burned': {
        'wet-waste': 1.5,
        'dry-waste': 4,
        'e-waste': 30,
        'textile-waste': 15,
        'footwear-waste': 20,
        'furniture-waste': 15
    }
}




@app.route('/calculate_waste_emission', methods=['POST'])
def calculate_waste_emission():
    try:
        if 'user_id' not in session:
            return jsonify({"error": "Unauthorized"}), 401

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        waste_type = data.get("type")
        category = data.get("category")
        quantity = data.get("quantity")

        if not all([waste_type, category, quantity]):
            return jsonify({"error": "Missing required fields"}), 400

        try:
            quantity = float(quantity)
        except ValueError:
            return jsonify({"error": "Invalid quantity value"}), 400

        factor = WASTE_EMISSION_FACTORS.get(category, {}).get(waste_type)
        if factor is None:
            return jsonify({"error": "Invalid waste type or category"}), 400

        emission = quantity * factor

        return jsonify({
            "emission": round(emission, 2),
            "factor": factor,
            "message": "Calculation successful"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_saved_waste', methods=['GET'])
def get_saved_waste():
    conn = None
    try:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'error': 'user_id required'}), 400
            
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT type, category, quantity, emission, entry_date
            FROM waste
            WHERE user_id = %s
            ORDER BY entry_date DESC, created_at DESC
        """, (user_id,))
        
        results = cursor.fetchall()
        return jsonify({'savedWaste': results})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/get_todays_waste', methods=['GET'])
def get_todays_waste():
    conn = None
    try:
        # Get user_id from session instead of query param for security
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
            
        user_id = session['user_id']
        today = datetime.now().date()
            
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT type, category, quantity 
            FROM waste 
            WHERE user_id = %s AND entry_date = %s
            ORDER BY created_at DESC
        """, (user_id, today))
        
        results = cursor.fetchall()
        return jsonify({'wasteData': results})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/save_waste', methods=['POST'])
def save_waste():
    # Check authentication
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    user_id = session['user_id']
    data = request.get_json()
    
    # Validate input
    if not data or 'wasteData' not in data:
        return jsonify({'success': False, 'message': 'Invalid data format'}), 400

    waste_data = data['wasteData']
    today = date.today()
    total_emission = 0
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Delete existing entries for today
        cursor.execute("""
            DELETE FROM waste 
            WHERE user_id = %s AND DATE(entry_date) = %s
        """, (user_id, today))

        # Prepare data for batch insert
        waste_entries = []
        for item in waste_data:
            if not all(key in item for key in ['type', 'category', 'quantity']):
                continue

            try:
                quantity = float(item['quantity'])
                if quantity <= 0:
                    continue
            except (ValueError, TypeError):
                continue

            factor = WASTE_EMISSION_FACTORS.get(item['category'], {}).get(item['type'], 0)
            emission = quantity * factor
            total_emission += emission

            waste_entries.append((
                user_id,
                item['type'],
                item['category'],
                quantity,
                round(emission, 2),  # Round to 2 decimal places
                today  # Use today's date instead of datetime.now()
            ))

        # Batch insert if we have valid entries
        if waste_entries:
            cursor.executemany("""
                INSERT INTO waste 
                (user_id, type, category, quantity, emission, entry_date)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, waste_entries)

        conn.commit()
        return jsonify({
            'success': True,
            'message': 'Waste data saved successfully',
            'total_emission': round(total_emission, 2)
        }), 200

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

@app.route('/get_todays_data', methods=['GET'])
def get_todays_data():
    conn = None
    try:
        user_id = request.args.get('user_id')
        today = datetime.now().date()
        
        if not user_id:
            return jsonify({'error': 'user_id required'}), 400
            
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check if user has submitted today using last_submit column
        cursor.execute("""
            SELECT 1 FROM submissions 
            WHERE user_id = %s AND DATE(last_submit) = %s
            LIMIT 1
        """, (user_id, today))
        is_submitted = cursor.fetchone() is not None
        
        # Simplified query that works for both submitted and draft data
        cursor.execute("""
            SELECT type, category, quantity 
            FROM waste 
            WHERE user_id = %s AND entry_date = %s
            ORDER BY created_at DESC
        """, (user_id, today))
        
        waste_data = cursor.fetchall()
        
        return jsonify({
            'isSubmitted': is_submitted,
            'wasteData': waste_data
        })
        
    except Exception as e:
        print(f"Error in get_todays_data: {str(e)}")
        return jsonify({'error': f"Database error: {str(e)}"}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@app.route('/can_submit', methods=['GET'])
def can_submit():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    user_id = session['user_id']

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT last_submit FROM submissions
            WHERE user_id = %s AND DATE(last_submit) = CURDATE()
        ''', (user_id,))
        existing_submission = cursor.fetchone()

        can_submit_today = not bool(existing_submission)
        return jsonify({'can_submit': can_submit_today}), 200
    except Exception as e:
        print(f"Error in /can_submit: {str(e)}")
        return jsonify({'message': f'Error checking submission status: {str(e)}'}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/check_submission_status', methods=['GET'])
def check_submission_status():
    if 'user_id' not in session:
        return jsonify({'message': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check for ACTUAL submission (not just saved data)
        cursor.execute('''
            SELECT 1 FROM submissions 
            WHERE user_id = %s AND DATE(last_submit) = CURDATE()
            AND (energy > 0 OR travel > 0 OR waste > 0 OR food > 0)
            LIMIT 1
        ''', (user_id,))
        
        submitted = cursor.fetchone() is not None
        return jsonify({
            'submitted': submitted,
            'user_id': user_id,
            'message': 'Checked successfully'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/submit_footprint', methods=['POST'])
def submit_footprint():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Not logged in'}), 401
    
    user_id = session['user_id']
    data = request.get_json()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check for existing submission today
        cursor.execute('''
            SELECT 1 FROM submissions 
            WHERE user_id = %s AND DATE(last_submit) = CURDATE()
            LIMIT 1
        ''', (user_id,))
        
        if cursor.fetchone():
            return jsonify({
                'success': False,
                'message': 'You have already submitted today'
            }), 400
        
        # Calculate total energy emissions from energy_devices table for today
        cursor.execute('''
            SELECT ROUND(COALESCE(SUM(emission), 0), 2) as total_energy
            FROM energy_devices
            WHERE user_id = %s AND DATE(entry_date) = CURDATE()
        ''', (user_id,))
        
        energy_result = cursor.fetchone()
        total_energy = float(energy_result[0]) if energy_result and energy_result[0] is not None else 0
        
        # Calculate total waste emissions from waste table for today
        cursor.execute('''
            SELECT ROUND(COALESCE(SUM(emission), 0), 2) as total_waste
            FROM waste
            WHERE user_id = %s AND DATE(entry_date) = CURDATE()
        ''', (user_id,))
        
        waste_result = cursor.fetchone()
        total_waste = float(waste_result[0]) if waste_result and waste_result[0] is not None else 0
        
        # Insert new submission with the calculated values
        cursor.execute('''
            INSERT INTO submissions 
            (user_id, energy, travel, waste, food, last_submit)
            VALUES (%s, %s, %s, %s, %s, NOW())
        ''', (
            user_id,
            total_energy,  # Use the calculated total energy
            data.get('travel', 0),
            total_waste,  # Use the calculated total waste
            data.get('food', 0)
        ))
        
        conn.commit()
        return jsonify({
            'success': True,
            'message': 'Submitted successfully',
            'energy_total': total_energy,  # Return the calculated energy total for verification
            'waste_total': total_waste  # Return the calculated waste total for verification
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

# ======================
# COMMUNITY ROUTES
# ======================
@app.route('/community.html', methods=['GET', 'POST'])
def community_page():
    if 'user_id' not in session:
        flash("Please log in to access community features", "error")
        return redirect(url_for('login'))

    user_id = session['user_id']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Handle form submissions
        if request.method == 'POST':
            # Create Community
            if 'create_community' in request.form:
                community_name = request.form.get('community_name', '').strip()
                
                if not 3 <= len(community_name) <= 50:
                    flash("Community name must be between 3-50 characters", "error")
                else:
                    try:
                        # Generate unique code
                        unique_code = ''.join(random.choices(
                            string.ascii_uppercase + string.digits, 
                            k=8
                        ))
                        
                        # Verify code is unique
                        cursor.execute("SELECT 1 FROM communities WHERE unique_code = %s", (unique_code,))
                        if cursor.fetchone():
                            raise Exception("Generated code already exists")

                        # Get admin details from users and Details tables
                        cursor.execute("""
                            SELECT u.email, 
                                   COALESCE(d.name, u.email) as display_name
                            FROM users u
                            LEFT JOIN Details d ON u.id = d.user_id AND d.user_id = %s
                            WHERE u.id = %s
                            ORDER BY d.entry_date DESC
                            LIMIT 1
                        """, (user_id, user_id))
                        admin_info = cursor.fetchone()
                        
                        if not admin_info:
                            raise Exception("Could not retrieve user information")

                        # Create community (matches your exact schema)
                        cursor.execute("""
                            INSERT INTO communities 
                            (name, unique_code, created_by, admin_id, admin_name, member_count, created_at)
                            VALUES (%s, %s, %s, %s, %s, 1, NOW())
                        """, (
                            community_name,
                            unique_code,
                            user_id,
                            user_id,
                            admin_info['display_name']
                        ))
                        community_id = cursor.lastrowid

                        # Add creator as admin member to community_members
                        cursor.execute("""
                            INSERT INTO community_members 
                            (user_id, community_id, display_name, role, joined_at)
                            VALUES (%s, %s, %s, 'Admin', NOW())
                        """, (
                            user_id,
                            community_id,
                            admin_info['display_name']
                        ))
                        
                        conn.commit()
                        flash(f"Community '{community_name}' created successfully! Code: {unique_code}", "success")
                        return redirect(url_for('community_page'))

                    except mysql.connector.IntegrityError as e:
                        conn.rollback()
                        if "Duplicate entry" in str(e):
                            if "unique_code" in str(e):
                                flash("Generated code already exists. Please try again.", "error")
                            else:
                                flash("Community name already exists. Please choose a different name.", "error")
                        else:
                            flash("Database error occurred. Please try again.", "error")
                        app.logger.error(f"IntegrityError: {str(e)}")
                    
                    except Exception as e:
                        conn.rollback()
                        flash(f"Failed to create community: {str(e)}", "error")
                        app.logger.error(f"Error creating community: {str(e)}", exc_info=True)

            # Join Community
            elif 'join_community' in request.form:
                join_code = request.form.get('unique_code', '').strip().upper()
                if len(join_code) == 8:
                    try:
                        # Find community with admin info
                        cursor.execute("""
                            SELECT c.id, c.name, c.admin_id, c.admin_name
                            FROM communities c
                            WHERE c.unique_code = %s
                        """, (join_code,))
                        community = cursor.fetchone()

                        if community:
                            # Check existing membership
                            cursor.execute("""
                                SELECT 1 FROM community_members
                                WHERE user_id = %s AND community_id = %s
                            """, (user_id, community['id']))
                            
                            if not cursor.fetchone():
                                # Get user's display name
                                cursor.execute("""
                                    SELECT COALESCE(
                                        (SELECT name FROM Details WHERE user_id = %s ORDER BY entry_date DESC LIMIT 1),
                                        (SELECT email FROM users WHERE id = %s)
                                    ) as display_name
                                """, (user_id, user_id))
                                result = cursor.fetchone()
                                display_name = result['display_name']

                                # Add member with Member role
                                cursor.execute("""
                                    INSERT INTO community_members 
                                    (user_id, community_id, display_name, role, joined_at)
                                    VALUES (%s, %s, %s, 'Member', NOW())
                                """, (user_id, community['id'], display_name))

                                # Update member count
                                cursor.execute("""
                                    UPDATE communities 
                                    SET member_count = member_count + 1
                                    WHERE id = %s
                                """, (community['id'],))
                                
                                conn.commit()
                                flash(f"You have successfully joined {community['name']}!", "success")
                                return redirect(url_for('community_page'))
                            else:
                                flash("You're already a member of this community", "error")
                        else:
                            flash("Invalid community code. Please check and try again.", "error")

                    except Exception as e:
                        conn.rollback()
                        flash("Failed to join community. Please try again.", "error")
                        app.logger.error(f"Error joining community: {str(e)}", exc_info=True)
                else:
                    flash("Community code must be exactly 8 characters", "error")

        # Get communities data
        # Communities I've Created (as admin)
        cursor.execute("""
            SELECT c.*
            FROM communities c
            WHERE c.admin_id = %s
            ORDER BY c.created_at DESC
        """, (user_id,))
        created_communities = cursor.fetchall()

        # Communities I've Joined (as member, not admin)
        cursor.execute("""
            SELECT c.*
            FROM communities c
            JOIN community_members cm ON c.id = cm.community_id
            WHERE cm.user_id = %s AND c.admin_id != %s
            ORDER BY cm.joined_at DESC
        """, (user_id, user_id))
        joined_communities = cursor.fetchall()

        return render_template('community.html',
            created_communities=created_communities,
            joined_communities=joined_communities
        )

    except Exception as e:
        flash("An error occurred while loading community data", "error")
        app.logger.error(f"Community page error: {str(e)}", exc_info=True)
        return redirect(url_for('index'))
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/community/<int:community_id>')
def community_details(community_id):
    if 'user_id' not in session:
        flash("Please log in to view community details", "error")
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get community info with admin details
        cursor.execute("""
            SELECT 
                c.*,
                u.email as admin_email,
                (SELECT name FROM Details WHERE user_id = c.admin_id ORDER BY entry_date DESC LIMIT 1) as admin_name,
                (c.admin_id = %s) as is_admin
            FROM communities c
            JOIN users u ON c.admin_id = u.id
            WHERE c.id = %s
        """, (user_id, community_id))
        community = cursor.fetchone()

        if not community:
            flash("Community not found", "error")
            return redirect(url_for('community_page'))

        # Verify access: Admin or Member
        if not community['is_admin']:
            cursor.execute("""
                SELECT 1 FROM community_members 
                WHERE user_id = %s AND community_id = %s
            """, (user_id, community_id))
            if not cursor.fetchone():
                flash("You must be a member to view this community", "error")
                return redirect(url_for('community_page'))

        # Get all members (including admin) with their roles
        cursor.execute("""
            SELECT 
                cm.*,
                u.email,
                (c.admin_id = cm.user_id) as is_admin
            FROM community_members cm
            JOIN users u ON cm.user_id = u.id
            JOIN communities c ON cm.community_id = c.id
            WHERE cm.community_id = %s
            ORDER BY 
                CASE WHEN c.admin_id = cm.user_id THEN 0 ELSE 1 END,
                cm.joined_at
        """, (community_id,))
        members = cursor.fetchall()

        # Get community statistics
        cursor.execute("""
            SELECT 
                COALESCE(SUM(s.energy + s.travel + s.waste + s.food), 0) as total_emissions,
                COUNT(DISTINCT s.id) as total_entries
            FROM submissions s
            JOIN community_members cm ON s.user_id = cm.user_id
            WHERE cm.community_id = %s
        """, (community_id,))
        stats = cursor.fetchone()
        
        # Ensure we have default values if no submissions exist
        total_emissions = float(stats['total_emissions']) if stats and stats['total_emissions'] is not None else 0
        total_entries = int(stats['total_entries']) if stats and stats['total_entries'] is not None else 0

        return render_template('community_details.html',
            community=community,
            members=members,
            total_emissions=total_emissions,
            total_entries=total_entries,
            is_admin=community['is_admin']
        )

    except Exception as e:
        app.logger.error(f"Community details error: {str(e)}", exc_info=True)
        flash("Error loading community details", "error")
        return redirect(url_for('community_page'))
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/delete_community/<int:community_id>', methods=['POST'])
def delete_community(community_id):
    if 'user_id' not in session:
        flash("Please log in to perform this action", "error")
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Verify user is the admin of this community
        cursor.execute("""
            SELECT admin_id FROM communities 
            WHERE id = %s
        """, (community_id,))
        result = cursor.fetchone()
        
        if not result or result[0] != user_id:
            flash("You are not authorized to delete this community", "error")
            return redirect(url_for('community_page'))

        # Delete all members first
        cursor.execute("""
            DELETE FROM community_members 
            WHERE community_id = %s
        """, (community_id,))
        
        # Then delete the community
        cursor.execute("""
            DELETE FROM communities 
            WHERE id = %s
        """, (community_id,))
        
        conn.commit()
        flash("Community deleted successfully", "success")
    except Exception as e:
        conn.rollback()
        flash(f"An error occurred: {str(e)}", "error")
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

    return redirect(url_for('community_page'))


@app.route('/leave_community/<int:community_id>', methods=['POST'])
def leave_community(community_id):
    if 'user_id' not in session:
        flash("Please log in to perform this action", "error")
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Get community name for flash message
        cursor.execute("""
            SELECT name FROM communities 
            WHERE id = %s
        """, (community_id,))
        community_name = cursor.fetchone()[0]
        
        # Remove user from community
        cursor.execute("""
            DELETE FROM community_members 
            WHERE user_id = %s AND community_id = %s
        """, (user_id, community_id))
        
        conn.commit()
        flash(f"You have left the community '{community_name}'", "success")
    except Exception as e:
        conn.rollback()
        flash(f"An error occurred: {str(e)}", "error")
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

    return redirect(url_for('community_page'))

@app.route('/community/<int:community_id>/daily_rankings')
def get_daily_rankings(community_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get today's submissions for all community members
        cursor.execute("""
            SELECT 
                cm.display_name,
                COALESCE(SUM(s.energy + s.travel + s.waste + s.food), 0) as total_emissions
            FROM community_members cm
            LEFT JOIN submissions s ON cm.user_id = s.user_id 
                AND DATE(s.last_submit) = CURDATE()
            WHERE cm.community_id = %s
            GROUP BY cm.user_id, cm.display_name
            HAVING total_emissions > 0
            ORDER BY total_emissions ASC
            LIMIT 10
        """, (community_id,))
        
        rankings = cursor.fetchall()
        
        # Convert total_emissions to float for each ranking
        for ranking in rankings:
            ranking['total_emissions'] = float(ranking['total_emissions'])
        
        # Add badges and rank numbers
        for i, ranking in enumerate(rankings, 1):
            ranking['rank'] = i
            if i == 1:
                ranking['badge'] = {
                    'type': 'gold',
                    'emoji': '🏅',
                    'tooltip': 'Emission Champion!'
                }
            elif i == 2:
                ranking['badge'] = {
                    'type': 'silver',
                    'emoji': '🥈',
                    'tooltip': 'Second Place!'
                }
            elif i == 3:
                ranking['badge'] = {
                    'type': 'bronze',
                    'emoji': '🥉',
                    'tooltip': 'Third Place!'
                }
        
        return jsonify({
            'success': True,
            'rankings': rankings
        })

    except Exception as e:
        app.logger.error(f"Error fetching daily rankings: {str(e)}", exc_info=True)
        return jsonify({
            'success': False, 
            'error': 'Failed to load rankings. Please try again later.'
        }), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

#report
@app.route('/report.html')
def report_page():
    return render_template('report.html')
# Summary Data Route
@app.route('/get_summary_data')
def get_summary_data():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Today's total
        cursor.execute('''
            SELECT COALESCE(SUM(energy + travel + waste + food), 0) as total
            FROM submissions
            WHERE user_id = %s AND DATE(last_submit) = CURDATE()
        ''', (user_id,))
        today = cursor.fetchone()['total']
        
        # Weekly average (last 7 days)
        cursor.execute('''
            SELECT COALESCE(AVG(energy + travel + waste + food), 0) as avg
            FROM submissions
            WHERE user_id = %s AND last_submit >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
        ''', (user_id,))
        weekly_avg = cursor.fetchone()['avg']
        
        # Monthly total (last 30 days)
        cursor.execute('''
            SELECT COALESCE(SUM(energy + travel + waste + food), 0) as total
            FROM submissions
            WHERE user_id = %s AND last_submit >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        ''', (user_id,))
        monthly = cursor.fetchone()['total']
        
        # Comparison with previous week
        cursor.execute('''
            SELECT 
                (SELECT COALESCE(AVG(energy + travel + waste + food), 0)
                 FROM submissions
                 WHERE user_id = %s AND last_submit BETWEEN DATE_SUB(CURDATE(), INTERVAL 7 DAY) AND CURDATE()) as current_week,
                
                (SELECT COALESCE(AVG(energy + travel + waste + food), 0)
                 FROM submissions
                 WHERE user_id = %s AND last_submit BETWEEN DATE_SUB(CURDATE(), INTERVAL 14 DAY) AND DATE_SUB(CURDATE(), INTERVAL 7 DAY)) as previous_week
        ''', (user_id, user_id))
        
        comparison_data = cursor.fetchone()
        current = comparison_data['current_week']
        previous = comparison_data['previous_week']
        
        if previous == 0:
            comparison = 0
        else:
            comparison = ((current - previous) / previous) * 100
        
        return jsonify({
            'today': float(today),
            'weekly_avg': float(weekly_avg),
            'monthly': float(monthly),
            'comparison': float(comparison)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()
@app.route('/get_todays_energy')
def get_todays_energy():
    """Get today's energy consumption data"""
    return fetch_daily_data(
        table='energy_devices',
        columns=['device_name', 'hours', 'emission'],
        order_by='emission DESC'  # Order by emission instead of ID
    )

@app.route('/get_todays_travel')
def get_todays_travel():
    """Get today's travel data"""
    return fetch_daily_data(
        table='vehicles',
        columns=['vehicle_name as name', 'distance', 'emission'],
        order_by='emission DESC'  # Order by emission instead of ID
    )

@app.route('/get_todays_wastee')
def get_todays_wastee():
    """Get today's waste data"""
    return fetch_daily_data(
        table='waste',
        columns=['type', 'category', 'quantity', 'emission'],
        order_by='emission DESC'  # Order by emission instead of ID
    )

def fetch_daily_data(table, columns, order_by):
    """
    Generic function to fetch daily data without requiring ID columns
    Args:
        table: Database table name
        columns: List of columns to select
        order_by: SQL ORDER BY clause
    """
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized', 'success': False}), 401

    user_id = session['user_id']
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Build and execute query without relying on ID columns
        query = f"""
            SELECT {', '.join(columns)}
            FROM {table}
            WHERE user_id = %s
            AND DATE(entry_date) = CURDATE()
            ORDER BY {order_by}
        """
        cursor.execute(query, (user_id,))
        data = cursor.fetchall()

        # Convert numeric fields to proper types
        numeric_fields = ['emission', 'distance', 'quantity', 'hours']
        for item in data:
            for field in numeric_fields:
                if field in item and item[field] is not None:
                    try:
                        item[field] = float(item[field])
                    except (ValueError, TypeError):
                        item[field] = 0.0
                elif field in item:
                    item[field] = 0.0

        return jsonify({
            'data': data,
            'success': True,
            'count': len(data),
            'timestamp': datetime.now().isoformat()
        })

    except mysql.connector.Error as db_error:
        return jsonify({
            'error': 'Database operation failed',
            'success': False,
            'details': str(db_error)
        }), 500
    except Exception as e:
        return jsonify({
            'error': 'Failed to fetch data',
            'success': False,
            'details': str(e)
        }), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()



@app.route('/get_weekly_data')
def get_weekly_data():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Get daily totals for the past 7 days
        cursor.execute('''
            SELECT 
                DATE(last_submit) as date,
                SUM(energy + travel + waste + food) as daily_total
            FROM submissions
            WHERE user_id = %s 
            AND last_submit >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            GROUP BY DATE(last_submit)
            ORDER BY date
        ''', (user_id,))
        
        raw_data = cursor.fetchall()

        # Create complete 7-day dataset
        dates = []
        totals = []
        
        for i in range(7):
            day = (datetime.now() - timedelta(days=6-i)).date()
            date_str = day.strftime('%a')  # 'Mon', 'Tue' etc.
            dates.append(date_str)
            
            # Find matching data or use 0
            daily_total = 0
            for row in raw_data:
                if row['date'] == day:
                    daily_total = float(row['daily_total'])
                    break
            totals.append(daily_total)

        return jsonify({
            'labels': dates,
            'data': totals,
            'success': True
        })

    except Exception as e:
        return jsonify({
            'error': str(e),
            'success': False
        }), 500
    finally:
        cursor.close()
        conn.close()
# Monthly Data Route (for pie charts)
@app.route('/get_monthly_data')
def get_monthly_data():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    chart_type = request.args.get('type', 'category')
    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        if chart_type == 'category':
            cursor.execute('''
                SELECT 
                    SUM(energy) as energy,
                    SUM(travel) as travel,
                    SUM(waste) as waste,
                    SUM(food) as food
                FROM submissions
                WHERE user_id = %s AND entry_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            ''', (user_id,))
            
            row = cursor.fetchone()
            return jsonify({
                'labels': ['Energy', 'Travel', 'Waste', 'Food'],
                'values': [
                    float(row['energy'] or 0),
                    float(row['travel'] or 0),
                    float(row['waste'] or 0),
                    float(row['food'] or 0)
                ]
            })
            
        elif chart_type == 'item':
            # Get top 10 items across all categories
            cursor.execute('''
                (SELECT device_name as name, SUM(emission) as total 
                 FROM energy_devices 
                 WHERE user_id = %s AND entry_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                 GROUP BY device_name 
                 ORDER BY total DESC 
                 LIMIT 5)
                
                UNION ALL
                
                (SELECT vehicle_name as name, SUM(emission) as total 
                 FROM vehicles 
                 WHERE user_id = %s AND entry_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                 GROUP BY vehicle_name 
                 ORDER BY total DESC 
                 LIMIT 3)
                
                UNION ALL
                
                (SELECT CONCAT(type, ' (', category, ')') as name, SUM(emission) as total 
                 FROM waste 
                 WHERE user_id = %s AND entry_date >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
                 GROUP BY type, category 
                 ORDER BY total DESC 
                 LIMIT 2)
            ''', (user_id, user_id, user_id))
            
            results = cursor.fetchall()
            return jsonify({
                'labels': [row['name'] for row in results],
                'values': [float(row['total'] or 0) for row in results]
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# Model initialization with fallback
try:
    gemini_model = genai.GenerativeModel('gemini-2.5-flash')
    logger.info("Using Gemini 1.5 Flash model")
except Exception as e:
    logger.warning(f"Falling back to Gemini 1.0 Pro: {str(e)}")
    gemini_model = genai.GenerativeModel('gemini-pro')

@app.route('/generate_tips', methods=['GET'])
@limiter.limit("5 per minute")
def generate_tips():
    if 'user_id' not in session:
        return jsonify({
            'success': False,
            'error': 'Unauthorized',
            'message': 'Please log in to access this feature'
        }), 401

    user_id = session['user_id']
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get user's weekly data
        cursor.execute('''
            SELECT 
                SUM(energy) as energy,
                SUM(travel) as travel,
                SUM(waste) as waste,
                SUM(food) as food
            FROM submissions
            WHERE user_id = %s AND last_submit >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
        ''', (user_id,))
        weekly_data = cursor.fetchone() or {'energy': 0, 'travel': 0, 'waste': 0, 'food': 0}

        # Get top energy devices
        cursor.execute('''
            SELECT device_name, SUM(emission) as emission
            FROM energy_devices
            WHERE user_id = %s AND entry_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            GROUP BY device_name
            ORDER BY emission DESC
            LIMIT 3
        ''', (user_id,))
        top_energy = cursor.fetchall() or [{'device_name': 'No data', 'emission': 0}]

        # Get top vehicles
        cursor.execute('''
            SELECT vehicle_name, SUM(emission) as emission
            FROM vehicles
            WHERE user_id = %s AND entry_date >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            GROUP BY vehicle_name
            ORDER BY emission DESC
            LIMIT 3
        ''', (user_id,))
        top_travel = cursor.fetchall() or [{'vehicle_name': 'No data', 'emission': 0}]

        # Build prompt for Gemini
        prompt = f"""Generate exactly 5 personalized carbon footprint reduction tips based on this data:
        
        Weekly Carbon Footprint:
        - Energy: {weekly_data['energy']:.2f} kg CO₂ (Top devices: {', '.join(f"{d['device_name']}: {d['emission']:.1f}kg" for d in top_energy)})
        - Travel: {weekly_data['travel']:.2f} kg CO₂ (Top vehicles: {', '.join(f"{v['vehicle_name']}: {v['emission']:.1f}kg" for v in top_travel)})
        - Waste: {weekly_data['waste']:.2f} kg CO₂
       

        Format each tip as a HTML list item (<li>) with this structure:
        <li><strong>[Action]</strong>: [Specific recommendation based on my data]</li>
        """

        # Call Gemini API
        response = gemini_model.generate_content(
            contents=[{'parts': [{'text': prompt}]}],
            generation_config={
                'temperature': 0.3,
                'top_p': 0.9,
                'max_output_tokens': 800
            }
        )

        # Process response into clean HTML
        tips_html = "<ul>"
        if response.text:
            # Extract just the list items from response
            for line in response.text.split('\n'):
                line = line.strip()
                if line.startswith('<li>'):
                    tips_html += line
                elif line.startswith(('•', '-', '*')):
                    # Convert markdown bullets to HTML
                    tips_html += f"<li>{line[1:].strip()}</li>"
        else:
            # Fallback tips if API fails
            fallback_tips = [
                f"<li><strong>Reduce {top_energy[0]['device_name']} usage</strong>: Could save {top_energy[0]['emission']*0.3:.1f} kg CO₂ weekly</li>",
                f"<li><strong>Combine {top_travel[0]['vehicle_name']} trips</strong>: Reduce travel emissions by 20-30%</li>",
                "<li><strong>Unplug idle devices</strong>: Eliminates standby power consumption</li>",
                "<li><strong>Adjust thermostat</strong>: 1°C change can reduce HVAC energy by 3-5%</li>",
                "<li><strong>Schedule energy audit</strong>: Identify hidden energy drains</li>"
            ]
            tips_html += ''.join(fallback_tips)
        
        tips_html += "</ul>"

        return jsonify({
            'success': True,
            'tips': tips_html,
            'model': gemini_model.model_name
        })

    except Exception as e:
        logger.error(f"Error generating tips: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'message': 'Failed to generate tips',
            'model': gemini_model.model_name if 'gemini_model' in locals() else 'unknown'
        }), 500

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()

@app.route('/profile.html', methods=['GET'])
def profile_page():
            if 'user_id' not in session:
                return redirect(url_for('login_page'))
        
            user_id = session['user_id']
        
            try:
                conn = get_db_connection()
                cursor = conn.cursor(dictionary=True)
        
                # Get the most recent details
                cursor.execute('''
                    SELECT name, household_members, gender, dob, profile_image
                    FROM Details 
                    WHERE user_id = %s
                    ORDER BY entry_date DESC
                    LIMIT 1
                ''', (user_id,))
                details_data = cursor.fetchone()
        
                # Get user email
                cursor.execute('SELECT email FROM users WHERE id = %s', (user_id,))
                user_data = cursor.fetchone()
        
                user_profile = None
                if details_data or user_data:
                    user_profile = {
                        'name': details_data.get('name', 'Not provided') if details_data else 'Not provided',
                        'household_members': details_data.get('household_members', 'Not provided') if details_data else 'Not provided',
                        'gender': details_data.get('gender', 'Not provided') if details_data else 'Not provided',
                        'dob': details_data.get('dob', 'Not provided') if details_data else 'Not provided',
                        'email': user_data.get('email', 'Not provided') if user_data else 'Not provided',
                        'profile_image': details_data.get('profile_image') if details_data else None,
                        'letter_dp': details_data['name'][0].upper() if details_data and details_data.get('name') else '?'
                    }
        
                return render_template('profile.html', user_profile=user_profile, community=True)
            except Exception as e:
                print(f"Error fetching profile: {e}")
                return render_template('profile.html', user_profile=None, community=True)
            finally:
                cursor.close()
                conn.close()
        
@app.route('/upload_profile_image', methods=['POST'])
def upload_profile_image():
            if 'user_id' not in session:
                return jsonify({'success': False, 'message': 'Unauthorized'}), 401
        
            if 'profile_image' not in request.files:
                return jsonify({'success': False, 'message': 'No file provided'}), 400
        
            file = request.files['profile_image']
            if file.filename == '':
                return jsonify({'success': False, 'message': 'No file selected'}), 400
        
            if not allowed_file(file.filename):
                return jsonify({'success': False, 'message': 'Invalid file type. Please upload PNG, JPG, JPEG, or GIF'}), 400
        
            try:
                # Ensure the upload directory exists with proper permissions
                upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', 'profile_images')
                os.makedirs(upload_dir, exist_ok=True)
                
                # Generate a unique filename
                filename = secure_filename(file.filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                user_id = session['user_id']
                new_filename = f'user_{user_id}_{timestamp}_{filename}'
                filepath = os.path.join(upload_dir, new_filename)
        
                # Save the file
                file.save(filepath)
                
                # Update database with image path
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # First check if profile_image column exists
                cursor.execute("""
                    SELECT COLUMN_NAME 
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_NAME = 'Details' 
                    AND COLUMN_NAME = 'profile_image'
                """)
                
                if not cursor.fetchone():
                    # Add profile_image column if it doesn't exist
                    cursor.execute("""
                        ALTER TABLE Details 
                        ADD COLUMN profile_image VARCHAR(255)
                    """)
                
                # Get the most recent details record for the user
                cursor.execute("""
                    SELECT id FROM Details 
                    WHERE user_id = %s 
                    ORDER BY entry_date DESC 
                    LIMIT 1
                """, (user_id,))
                result = cursor.fetchone()
                
                if result:
                    # Update the existing record
                    cursor.execute("""
                        UPDATE Details 
                        SET profile_image = %s 
                        WHERE id = %s
                    """, (f'/static/uploads/profile_images/{new_filename}', result[0]))
                else:
                    # Create a new record if none exists
                    cursor.execute("""
                        INSERT INTO Details (user_id, profile_image) 
                        VALUES (%s, %s)
                    """, (user_id, f'/static/uploads/profile_images/{new_filename}'))
                
                conn.commit()
                return jsonify({
                    'success': True, 
                    'message': 'Image uploaded successfully',
                    'image_path': f'/static/uploads/profile_images/{new_filename}'
                })
                
            except Exception as e:
                print(f"Error uploading image: {str(e)}")  # Add debug logging
                if 'conn' in locals():
                    conn.rollback()
                return jsonify({'success': False, 'message': f'Error uploading image: {str(e)}'}), 500
            finally:
                if 'cursor' in locals():
                    cursor.close()
                if 'conn' in locals() and conn.is_connected():
                    conn.close()




# Debug Routes
@app.route('/debug_session')
def debug_session():
    if 'user_id' not in session:
        return jsonify({'message': 'No user in session'})
    return jsonify({
        'user_id': session.get('user_id'),
        'session_keys': list(session.keys())
    })

@app.route('/debug_submissions')
def debug_submissions():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute('SELECT user_id, DATE(last_submit) as submit_date FROM submissions ORDER BY last_submit DESC LIMIT 10')
    submissions = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(submissions)

# Cache Control
@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/update_vehicle_categories', methods=['POST'])
def update_vehicle_categories():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # First, let's check the current category of Skoda Rapid
        cursor.execute('''
            SELECT vehicle_name, vehicle_category 
            FROM vehicles 
            WHERE user_id = %s AND vehicle_name LIKE '%Skoda Rapid%'
        ''', (session['user_id'],))
        current_categories = cursor.fetchall()
        print("Current Skoda Rapid categories:", current_categories)  # Debug log
        
        # Update vehicle categories based on engine capacity and type
        cursor.execute('''
            UPDATE vehicles 
            SET vehicle_category = CASE vehicle_name
                -- Motorcycles
                WHEN 'TVS Star City Plus' THEN 'Motorcycle <110 CC'
                WHEN 'Honda Livo' THEN 'Motorcycle <125 CC'
                WHEN 'Bajaj Platina 100' THEN 'Motorcycle <100 CC'
                WHEN 'Hero Splendor Plus' THEN 'Motorcycle <125 CC'
                WHEN 'TVS Apache RTR 160' THEN 'Motorcycle <200 CC'
                WHEN 'Royal Enfield Classic 350' THEN 'Motorcycle <500 CC'
                WHEN 'KTM Duke 390' THEN 'Motorcycle <500 CC'
                WHEN 'Honda CB Shine' THEN 'Motorcycle <125 CC'
                WHEN 'Bajaj Pulsar 150' THEN 'Motorcycle <150 CC'
                WHEN 'Hero Passion Pro' THEN 'Motorcycle <110 CC'
                WHEN 'Yamaha FZ' THEN 'Motorcycle <150 CC'
                WHEN 'Suzuki Gixxer' THEN 'Motorcycle <150 CC'
                
                -- Scooters
                WHEN 'Honda Activa 110' THEN 'Scooter <110 CC'
                WHEN 'TVS Jupiter' THEN 'Scooter <110 CC'
                WHEN 'Suzuki Access 125' THEN 'Scooter <125 CC'
                WHEN 'Honda Activa 125' THEN 'Scooter <125 CC'
                WHEN 'TVS NTORQ 125' THEN 'Scooter <125 CC'
                WHEN 'Aprilia SR 160' THEN 'Scooter <160 CC'
                
                -- Cars (Petrol)
                WHEN 'Maruti Suzuki Alto K10' THEN 'Hatchback <1000 CC'
                WHEN 'Maruti Suzuki S-Presso' THEN 'Hatchback <1000 CC'
                WHEN 'Hyundai Santro' THEN 'Hatchback <1000 CC'
                WHEN 'Tata Tiago' THEN 'Hatchback <1000 CC'
                WHEN 'Maruti Suzuki Celerio' THEN 'Hatchback <1000 CC'
                WHEN 'Datsun GO' THEN 'Hatchback <1000 CC'
                WHEN 'Datsun GO+' THEN 'Hatchback <1000 CC'
                WHEN 'Maruti Suzuki Swift' THEN 'Hatchback <1400 CC'
                WHEN 'Maruti Suzuki Baleno' THEN 'Hatchback <1400 CC'
                WHEN 'Maruti Suzuki Dzire' THEN 'Sedan <1400 CC'
                WHEN 'Hyundai i20' THEN 'Hatchback <1400 CC'
                WHEN 'Hyundai Grand i10 Nios' THEN 'Hatchback <1400 CC'
                WHEN 'Hyundai Aura' THEN 'Sedan <1400 CC'
                WHEN 'Tata Altroz' THEN 'Hatchback <1400 CC'
                WHEN 'Tata Punch' THEN 'Hatchback <1400 CC'
                WHEN 'Honda Amaze' THEN 'Sedan <1400 CC'
                WHEN 'Toyota Glanza' THEN 'Hatchback <1400 CC'
                WHEN 'Maruti Suzuki Wagon R' THEN 'Hatchback <1000 CC'
                WHEN 'Maruti Suzuki Ignis' THEN 'Hatchback <1400 CC'
                WHEN 'Renault Kwid' THEN 'Hatchback <1000 CC'
                WHEN 'Tata Tigor' THEN 'Sedan <1400 CC'
                WHEN 'Maruti Suzuki Fronx' THEN 'Hatchback <1400 CC'
                WHEN 'Honda WR-V' THEN 'Compact SUV <1600 CC'
                WHEN 'Toyota Urban Cruiser' THEN 'Compact SUV <1600 CC'
                WHEN 'Nissan Magnite' THEN 'Hatchback <1400 CC'
                WHEN 'Renault Kiger' THEN 'Hatchback <1400 CC'
                WHEN 'Volkswagen Vento' THEN 'Sedan <1600 CC'
                WHEN 'Skoda Rapid' THEN 'Sedan <1600 CC'
                WHEN 'Skoda Rapid TSI' THEN 'Sedan <1600 CC'
                WHEN 'Skoda Rapid Monte Carlo' THEN 'Sedan <1600 CC'
                WHEN 'Honda City' THEN 'Sedan <1600 CC'
                WHEN 'Hyundai Verna' THEN 'Sedan <1600 CC'
                WHEN 'Maruti Suzuki Ciaz' THEN 'Sedan <1600 CC'
                WHEN 'Toyota Yaris' THEN 'Sedan <1600 CC'
                WHEN 'Volkswagen Polo' THEN 'Hatchback <1400 CC'
                WHEN 'Hyundai Elite i20' THEN 'Hatchback <1400 CC'
                WHEN 'Maruti Suzuki Vitara Brezza' THEN 'Compact SUV <1600 CC'
                WHEN 'Tata Nexon' THEN 'Compact SUV <1600 CC'
                WHEN 'Ford EcoSport' THEN 'Compact SUV <1600 CC'
                WHEN 'Mahindra XUV300' THEN 'Compact SUV <1600 CC'
                
                -- Cars (Diesel)
                WHEN 'Hyundai Venue' THEN 'Compact SUV <1600 CC'
                WHEN 'Kia Sonet' THEN 'Compact SUV <1600 CC'
                WHEN 'Kia Seltos' THEN 'Compact SUV <1600 CC'
                WHEN 'Maruti Suzuki Brezza' THEN 'Compact SUV <1600 CC'
                WHEN 'Tata Nexon' THEN 'Compact SUV <1600 CC'
                WHEN 'Tata Altroz' THEN 'Hatchback <1400 CC'
                WHEN 'Maruti Suzuki Ertiga' THEN 'MUV <2000 CC'
                WHEN 'Maruti Suzuki XL6' THEN 'MUV <2000 CC'
                WHEN 'Hyundai Creta' THEN 'Compact SUV <1600 CC'
                WHEN 'Mahindra XUV300' THEN 'Compact SUV <1600 CC'
                WHEN 'Mahindra Scorpio-N' THEN 'SUV <2000 CC'
                WHEN 'Tata Harrier' THEN 'SUV <2000 CC'
                WHEN 'Tata Safari' THEN 'SUV <2000 CC'
                WHEN 'Jeep Compass' THEN 'SUV <2000 CC'
                WHEN 'Mahindra Bolero' THEN 'SUV <2000 CC'
                WHEN 'Mahindra XUV400' THEN 'SUV <2000 CC'
                WHEN 'Toyota Innova Crysta' THEN 'MUV <2000 CC'
                WHEN 'Toyota Fortuner Legender' THEN 'SUV <3000 CC'
                WHEN 'Toyota Fortuner' THEN 'SUV <3000 CC'
                WHEN 'Mahindra Thar' THEN 'SUV <2000 CC'
                WHEN 'Mahindra XUV700' THEN 'SUV <3000 CC'
                WHEN 'MG Gloster' THEN 'SUV <3000 CC'
                WHEN 'Land Rover Defender' THEN 'SUV <3000 CC'
                WHEN 'Force Gurkha' THEN 'SUV <2000 CC'
                WHEN 'Isuzu D-Max V-Cross' THEN 'SUV <3000 CC'
                WHEN 'Mahindra Alturas G4' THEN 'SUV <3000 CC'
                WHEN 'Mercedes-Benz GLS' THEN 'SUV >3000 CC'
                WHEN 'BMW X5' THEN 'SUV >3000 CC'
                WHEN 'BMW X7' THEN 'SUV >3000 CC'
                WHEN 'Audi Q7' THEN 'SUV >3000 CC'
                WHEN 'Mercedes-Benz GLE' THEN 'SUV >3000 CC'
                WHEN 'Land Rover Discovery' THEN 'SUV >3000 CC'
                WHEN 'Jaguar XF' THEN 'Sedan <2500 CC'
                ELSE vehicle_category  -- Keep existing category if no match
            END
            WHERE user_id = %s AND vehicle_category IS NOT NULL
        ''', (session['user_id'],))
        
        # Verify the update
        cursor.execute('''
            SELECT vehicle_name, vehicle_category 
            FROM vehicles 
            WHERE user_id = %s AND vehicle_name LIKE '%Skoda Rapid%'
        ''', (session['user_id'],))
        updated_categories = cursor.fetchall()
        print("Updated Skoda Rapid categories:", updated_categories)  # Debug log
        
        conn.commit()
        return jsonify({
            'success': True,
            'message': 'Categories updated successfully'
        }), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({
            'success': False,
            'message': f'Error updating categories: {str(e)}'
        }), 500
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@app.route('/complete_challenge', methods=['POST'])
def complete_challenge():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    data = request.get_json()
    
    if not data or 'challenge_id' not in data:
        return jsonify({'success': False, 'message': 'Challenge ID is required'}), 400
    
    challenge_id = data['challenge_id']
    points = data.get('points', 0)
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if challenge is already completed
        cursor.execute("""
            SELECT id FROM completed_challenges 
            WHERE user_id = %s AND challenge_id = %s
        """, (user_id, challenge_id))
        
        if cursor.fetchone():
            return jsonify({
                'success': False, 
                'message': 'Challenge already completed'
            }), 400
        
        # Insert new completed challenge
        cursor.execute("""
            INSERT INTO completed_challenges (user_id, challenge_id, points)
            VALUES (%s, %s, %s)
        """, (user_id, challenge_id, points))
        
        conn.commit()
        
        # Check for tree achievement
        if points >= 50:
            cursor.execute("""
                INSERT INTO tree_achievements (user_id, trees_planted)
                VALUES (%s, %s)
            """, (user_id, points // 50))
            conn.commit()
        
        return jsonify({
            'success': True,
            'message': 'Challenge completed successfully',
            'points': points
        })
        
    except Exception as e:
        print(f"Error completing challenge: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error completing challenge'
        }), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/get_total_points', methods=['GET'])
def get_total_points():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT COALESCE(SUM(points), 0) as total_points
            FROM completed_challenges
            WHERE user_id = %s
        """, (user_id,))
        
        result = cursor.fetchone()
        total_points = result['total_points'] if result['total_points'] else 0
        
        return jsonify({
            'success': True,
            'total_points': total_points
        })
        
    except Exception as e:
        print(f"Error fetching total points: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error fetching total points'
        }), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/get_tree_count', methods=['GET'])
def get_tree_count():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT COALESCE(SUM(trees_planted), 0) as total_trees
            FROM tree_achievements
            WHERE user_id = %s
        """, (user_id,))
        
        result = cursor.fetchone()
        total_trees = result['total_trees'] if result['total_trees'] else 0
        
        return jsonify({
            'success': True,
            'total_trees': total_trees
        })
        
    except Exception as e:
        print(f"Error fetching tree count: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error fetching tree count'
        }), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/check_tree_achievement', methods=['POST'])
def check_tree_achievement():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get total points
        cursor.execute("""
            SELECT SUM(points) as total_points
            FROM completed_challenges
            WHERE user_id = %s
        """, (user_id,))
        
        result = cursor.fetchone()
        total_points = result['total_points'] if result['total_points'] else 0
        
        # Calculate how many new trees should be planted (1 tree per 50 points)
        potential_trees = total_points // 50
        
        # Get current planted trees
        cursor.execute("""
            SELECT COALESCE(SUM(trees_planted), 0) as current_trees
            FROM tree_achievements
            WHERE user_id = %s
        """, (user_id,))
        
        current_result = cursor.fetchone()
        current_trees = current_result['current_trees'] if current_result['current_trees'] else 0
        
        new_trees = potential_trees - current_trees
        
        if new_trees > 0:
            # Insert new tree achievement
            cursor.execute("""
                INSERT INTO tree_achievements (user_id, trees_planted)
                VALUES (%s, %s)
            """, (user_id, new_trees))
            
            conn.commit()
            
            return jsonify({
                'success': True,
                'new_trees': new_trees,
                'total_trees': potential_trees,
                'message': f'Congratulations! {new_trees} new tree(s) will be planted!'
            })
        
        return jsonify({
            'success': True,
            'new_trees': 0,
            'total_trees': current_trees,
            'message': 'Keep earning points for more trees!'
        })
        
    except Exception as e:
        print(f"Error checking tree achievement: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error checking tree achievement'
        }), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/get_completed_challenges', methods=['GET'])
def get_completed_challenges():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT challenge_id, points, completion_date
            FROM completed_challenges
            WHERE user_id = %s
            ORDER BY completion_date DESC
        """, (user_id,))
        
        challenges = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'challenges': challenges
        })
        
    except Exception as e:
        print(f"Error fetching completed challenges: {str(e)}")
        return jsonify({
            'success': False,
            'message': 'Error fetching completed challenges'
        }), 500
    finally:
        cursor.close()
        conn.close()
# Database Initialization
if __name__ == '__main__':
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (id INT AUTO_INCREMENT PRIMARY KEY, email VARCHAR(255) UNIQUE, password VARCHAR(255))")
    cursor.execute("CREATE TABLE IF NOT EXISTS Details (id INT AUTO_INCREMENT PRIMARY KEY, user_id INT, name VARCHAR(255), household_members INT, transportation TEXT, devices TEXT, entry_date DATE, FOREIGN KEY (user_id) REFERENCES users(id))")
    cursor.execute("CREATE TABLE IF NOT EXISTS HomeDetails (id INT AUTO_INCREMENT PRIMARY KEY, user_id INT, devices TEXT, devices_result VARCHAR(255), total_result VARCHAR(255), entry_date DATE, FOREIGN KEY (user_id) REFERENCES users(id))")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS completed_challenges (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            challenge_id INT,
            points INT,
            completion_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE KEY unique_user_challenge (user_id, challenge_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tree_achievements (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            trees_planted INT DEFAULT 0,
            achievement_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    cursor.close()
    conn.close()
   
    app.run(debug=True)
