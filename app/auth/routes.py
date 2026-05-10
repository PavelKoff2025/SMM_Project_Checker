from urllib.parse import urlparse, urljoin

from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, login_required
from app import db, limiter
from app.models import User
from app.forms import LoginForm, RegisterForm
from app.auth import auth_bp


def _is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10/minute')
def login():
    data = request.get_json(silent=True)
    if data:
        username = data.get('username', '')
        password = data.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.is_locked():
            return jsonify({'ok': False, 'error': 'Аккаунт заблокирован на 15 минут.'}), 429
        if user and user.check_password(password):
            user.reset_failed_attempts()
            db.session.commit()
            login_user(user)
            return jsonify({'ok': True, 'redirect': url_for('checker.index')})
        if user:
            user.record_failed_attempt()
            db.session.commit()
        return jsonify({'ok': False, 'error': 'Неверное имя пользователя или пароль.'}), 401

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.is_locked():
            flash('Аккаунт заблокирован на 15 минут.', 'danger')
            return render_template('auth/login.html', form=form)
        if user and user.check_password(form.password.data):
            user.reset_failed_attempts()
            db.session.commit()
            login_user(user)
            next_page = request.args.get('next')
            if next_page and _is_safe_url(next_page):
                return redirect(next_page)
            return redirect(url_for('checker.index'))
        if user:
            user.record_failed_attempt()
            db.session.commit()
        flash('Неверное имя пользователя или пароль.', 'danger')
    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'ok': True})


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit('3/hour')
def register():
    if request.method == 'GET':
        form = RegisterForm()
        return render_template('auth/register.html', form=form)

    data = request.get_json(silent=True)
    if data:
        if User.query.filter_by(username=data.get('username', '')).first():
            return jsonify({'ok': False, 'error': 'Это имя пользователя уже занято.'}), 409

        user = User(username=data['username'])
        user.set_password(data['password'])
        db.session.add(user)
        db.session.commit()
        return jsonify({'ok': True, 'redirect': url_for('auth.login')})

    form = RegisterForm()
    if form.validate_on_submit():
        user = User(username=form.username.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Регистрация успешна. Пожалуйста, войдите.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)
