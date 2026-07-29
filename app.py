import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'gaming_lounge_graduation_project_2024'

# --- DATABASE CONFIGURATION ---
# This part ensures the database works on Render/Linux
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'gaming_system.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- DATABASE MODELS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    role = db.Column(db.String(10)) # admin or staff

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    rate_per_hour = db.Column(db.Float)

class Station(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20))
    status = db.Column(db.String(20), default='Available')

class GameSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    station_id = db.Column(db.Integer)
    game_name = db.Column(db.String(50))
    start_time = db.Column(db.DateTime, default=datetime.now)
    end_time = db.Column(db.DateTime, nullable=True)
    total_cost = db.Column(db.Float, default=0.0)
    payment_method = db.Column(db.String(20))
    is_active = db.Column(db.Boolean, default=True)

# --- INITIALIZE SYSTEM ---
with app.app_context():
    db.create_all()
    # Create Default Admin: admin | admin123
    if not User.query.filter_by(username="admin").first():
        hashed_pw = generate_password_hash("admin123", method='pbkdf2:sha256')
        db.session.add(User(username="admin", password=hashed_pw, role="admin"))
        # Create 30 Stations
        for i in range(1, 31):
            db.session.add(Station(name=f"STATION {i}"))
        # Default Game
        db.session.add(Game(name="FIFA 24", rate_per_hour=200.0))
        db.session.commit()

# --- ROUTES ---

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form.get('username')
        p = request.form.get('password')
        r = request.form.get('role')
        user = User.query.filter_by(username=u, role=r).first()
        if user and check_password_hash(user.password, p):
            session['user_id'] = user.id
            session['role'] = user.role
            return redirect(url_for('admin_dashboard' if r == 'admin' else 'user_dashboard'))
        flash("Invalid login credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- ADMIN ROUTES ---
@app.route('/admin_dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect(url_for('login'))
    
    today = date.today()
    # Get all finished sessions for today
    completed = GameSession.query.filter(db.func.date(GameSession.end_time) == today, GameSession.is_active == False).all()
    total_sales = sum(s.total_cost for s in completed)
    
    # Passing ALL variables needed by admin_dashboard.html
    return render_template('admin_dashboard.html', 
                           stations=Station.query.all(), 
                           games=Game.query.all(), 
                           total_sales=round(total_sales, 2),
                           reports=completed) # <--- THIS WAS MISSING AND CAUSED THE 500 ERROR

@app.route('/toggle_service/<int:id>')
def toggle_service(id):
    if session.get('role') != 'admin': return redirect(url_for('login'))
    s = Station.query.get(id)
    s.status = 'Out of Service' if s.status != 'Out of Service' else 'Available'
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/add_game', methods=['POST'])
def add_game():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    name = request.form.get('name')
    rate = request.form.get('rate')
    if name and rate:
        db.session.add(Game(name=name, rate_per_hour=float(rate)))
        db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/update_game', methods=['POST'])
def update_game():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    g_id = request.form.get('game_id')
    rate = request.form.get('rate')
    g = Game.query.get(g_id)
    if g and rate:
        g.rate_per_hour = float(rate)
        db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/add_user', methods=['POST'])
def add_user():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    u = request.form.get('username')
    p = request.form.get('password')
    if u and p:
        pw = generate_password_hash(p, method='pbkdf2:sha256')
        db.session.add(User(username=u, password=pw, role='staff'))
        db.session.commit()
    return redirect(url_for('admin_dashboard'))

# --- STAFF ROUTES ---
@app.route('/user_dashboard')
def user_dashboard():
    if not session.get('user_id'): return redirect(url_for('login'))
    active = GameSession.query.filter_by(is_active=True).all()
    return render_template('user_dashboard.html', 
                           stations=Station.query.all(), 
                           games=Game.query.all(), 
                           active_sessions=active)

@app.route('/start_session', methods=['POST'])
def start_session():
    sid = request.form.get('station_id')
    gn = request.form.get('game_name')
    s = Station.query.get(sid)
    if s and s.status == 'Available':
        s.status = 'Busy'
        db.session.add(GameSession(station_id=sid, game_name=gn))
        db.session.commit()
    return redirect(url_for('user_dashboard'))

@app.route('/stop_session/<int:id>', methods=['POST'])
def stop_session(id):
    gs = GameSession.query.get(id)
    game = Game.query.filter_by(name=gs.game_name).first()
    gs.end_time = datetime.now()
    duration = (gs.end_time - gs.start_time).total_seconds() / 3600
    gs.total_cost = round(max(duration * game.rate_per_hour, 10.0), 2)
    gs.payment_method = request.form.get('payment_method')
    gs.is_active = False
    Station.query.get(gs.station_id).status = 'Available'
    db.session.commit()
    return render_template('receipt.html', session=gs)

if __name__ == '__main__':
    app.run(debug=False) # Turned debug off for production
