from flask import Blueprint

checker_bp = Blueprint('checker', __name__, template_folder='../templates/checker')

from app.checker import routes
