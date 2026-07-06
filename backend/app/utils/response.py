"""统一响应格式工具"""
from flask import jsonify


def success(data=None, message='操作成功'):
    return jsonify(code=200, message=message, data=data)


def error(message='操作失败', code=400):
    return jsonify(code=code, message=message), code
