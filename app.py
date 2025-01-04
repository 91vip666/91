from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
import calendar

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'events.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    events = db.relationship('Event', backref='author', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)
    likes = db.relationship('Like', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    approved = db.Column(db.Boolean, default=False)
    comments = db.relationship('Comment', backref='event', lazy=True)
    likes = db.relationship('Like', backref='event', lazy=True)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def init_admin():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(username='admin', is_admin=True)
        admin.set_password('1q2w3e4r5t')
        db.session.add(admin)
        db.session.commit()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录', 'warning')
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            flash('需要管理员权限', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('请先登录', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    # 获取当前月份和年份
    selected_month = request.args.get('month', type=int, default=datetime.now().month)
    selected_year = request.args.get('year', type=int, default=datetime.now().year)
    
    # 获取已审核的事件
    events = Event.query.filter_by(approved=True)\
        .filter(db.extract('year', Event.date) == selected_year)\
        .filter(db.extract('month', Event.date) == selected_month)\
        .order_by(Event.date.desc()).all()
    
    # 生成月份选择器的数据
    months = []
    for i in range(1, 13):
        months.append({
            'number': i,
            'name': calendar.month_name[i],
            'selected': i == selected_month
        })
    
    return render_template('index.html', 
                         events=events, 
                         months=months,
                         selected_month=selected_month,
                         selected_year=selected_year)

@app.route('/add_event', methods=['GET', 'POST'])
@login_required
def add_event():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        date_str = request.form.get('date')
        date = datetime.strptime(date_str, '%Y-%m-%d')
        
        event = Event(title=title, description=description, date=date, user_id=session['user_id'])
        db.session.add(event)
        db.session.commit()
        
        flash('事件已提交，等待管理员审核', 'success')
        return redirect(url_for('index'))
    return render_template('add.html')

@app.route('/add_comment/<int:event_id>', methods=['POST'])
@login_required
def add_comment(event_id):
    content = request.form.get('content')
    comment = Comment(content=content, user_id=session['user_id'], event_id=event_id)
    db.session.add(comment)
    db.session.commit()
    flash('评论已发布', 'success')
    return redirect(url_for('index'))

@app.route('/toggle_like/<int:event_id>')
@login_required
def toggle_like(event_id):
    like = Like.query.filter_by(user_id=session['user_id'], event_id=event_id).first()
    if like:
        db.session.delete(like)
        db.session.commit()
        return jsonify({'likes': Like.query.filter_by(event_id=event_id).count()})
    else:
        like = Like(user_id=session['user_id'], event_id=event_id)
        db.session.add(like)
        db.session.commit()
        return jsonify({'likes': Like.query.filter_by(event_id=event_id).count()})

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'danger')
            return redirect(url_for('register'))
        
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        # 直接登录用户
        session['user_id'] = user.id
        flash(f'注册成功！请记住您的账号和密码：<br>账号：{username}<br>密码：{password}', 'success')
        return redirect(url_for('index'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            flash('登录成功！', 'success')
            return redirect(url_for('index'))
        
        flash('用户名或密码错误', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('已退出登录', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        init_admin()
    app.run(debug=True, host='0.0.0.0', port=8080)
