from urllib.parse import urljoin, urlparse

from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user

from app import db, limiter
from app.auth import auth_bp
from app.forms import LoginForm, RegisterForm
from app.models import User


def _is_safe_url(target: str) -> bool:
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10/minute')
def login():
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
    form = RegisterForm()
    if form.validate_on_submit():
        user = User(username=form.username.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Регистрация успешна. Пожалуйста, войдите.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)
