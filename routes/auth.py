from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, Company, Role
from app import bcrypt
from flask import abort

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
    return redirect(url_for('auth.login'))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            flash('You have been logged in successfully', 'success')

            # Redirect cleaners to their dashboard
            if user.is_cleaner:
                return redirect(url_for('cleaners.cleaner_dashboard'))

            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard.dashboard'))
        else:
            flash('Login failed. Please check your email and password', 'danger')

    return render_template('login.html')

# Removed the register route entirely

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/register')
def register():
    # Return 404 for any register attempts
    abort(404)