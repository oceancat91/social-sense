"""认证相关路由"""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from app import db
from app.models.user import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/register', methods=['POST'])
def register():
    """用户注册"""
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')

    if not all([username, email, password]):
        return jsonify(code=400, message='缺少必要参数'), 400

    if User.query.filter_by(email=email).first():
        return jsonify(code=400, message='该邮箱已注册'), 400

    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify(code=200, message='注册成功', data=user.to_dict())


@auth_bp.route('/login', methods=['POST'])
def login():
    """用户登录"""
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify(code=401, message='邮箱或密码错误'), 401

    token = create_access_token(identity=str(user.id))
    return jsonify(code=200, message='登录成功', data={
        'token': token,
        'user': user.to_dict()
    })
