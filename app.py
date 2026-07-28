import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'gaming_lounge_final_v3'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///gaming_lounge_final.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- MODELS ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))
    role = db.Column(db.String(10)) # admin/staff

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

# --- DB INIT ---
with app.app_context():
    db.create_all()
    if not User.query.filter_by(username="admin").first():
        pw = generate_password_hash("admin123", method='pbkdf2:sha256')
        db.session.add(User(username="admin", password=pw, role="admin"))
        for i in range(1, 31):
            db.session.add(Station(name=f"STATION {i}"))
        db.session.add(Game(name="FIFA 24", rate_per_hour=200.0))
        db.session.commit()

# --- ROUTES ---
@app.route('/')
def index(): return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p, r = request.form['username'], request.form['password'], request.form['role']
        user = User.query.filter_by(username=u, role=r).first()
        if user and check_password_hash(user.password, p):
            session['user_id'], session['role'] = user.id, user.role
            return redirect(url_for('admin_dashboard' if r == 'admin' else 'user_dashboard'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- ADMIN FUNCTIONS ---
@app.route('/admin_dashboard')
def admin_dashboard():
    if session.get('role') != 'admin': return redirect(url_for('login'))
    
    # Calculate daily sales
    today = date.today()
    completed = GameSession.query.filter(db.func.date(GameSession.end_time) == today, GameSession.is_active == False).all()
    total_sales = sum(s.total_cost for s in completed)
    
    return render_template('admin_dashboard.html', 
                           stations=Station.query.all(), 
                           games=Game.query.all(), 
                           total_sales=round(total_sales, 2), 
                           reports=completed)

@app.route('/toggle_service/<int:id>')
def toggle_service(id):
    s = Station.query.get(id)
    s.status = 'Out of Service' if s.status != 'Out of Service' else 'Available'
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/add_game', methods=['POST'])
def add_game():
    name = request.form['name']
    rate = float(request.form['rate'])
    db.session.add(Game(name=name, rate_per_hour=rate))
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/update_game', methods=['POST'])
def update_game():
    g = Game.query.get(request.form['game_id'])
    g.rate_per_hour = float(request.form['rate'])
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

@app.route('/add_user', methods=['POST'])
def add_user():
    pw = generate_password_hash(request.form['password'], method='pbkdf2:sha256')
    db.session.add(User(username=request.form['username'], password=pw, role='staff'))
    db.session.commit()
    return redirect(url_for('admin_dashboard'))

# --- STAFF FUNCTIONS ---
@app.route('/user_dashboard')
def user_dashboard():
    if not session.get('user_id'): return redirect(url_for('login'))
    return render_template('user_dashboard.html', 
                           stations=Station.query.all(), 
                           games=Game.query.all(), 
                           active_sessions=GameSession.query.filter_by(is_active=True).all())

@app.route('/start_session', methods=['POST'])
def start_session():
    s = Station.query.get(request.form['station_id'])
    s.status = 'Busy'
    db.session.add(GameSession(station_id=s.id, game_name=request.form['game_name']))
    db.session.commit()
    return redirect(url_for('user_dashboard'))

@app.route('/stop_session/<int:id>', methods=['POST'])
def stop_session(id):
    gs = GameSession.query.get(id)
    game = Game.query.filter_by(name=gs.game_name).first()
    gs.end_time = datetime.now()
    duration = (gs.end_time - gs.start_time).total_seconds() / 3600
    gs.total_cost = round(max(duration * game.rate_per_hour, 10.0), 2)
    gs.payment_method, gs.is_active = request.form['payment_method'], False
    Station.query.get(gs.station_id).status = 'Available'
    db.session.commit()
    return render_template('receipt.html', session=gs)

if __name__ == '__main__':
    app.run(debug=True)