from flask import Flask
from flask_cors import CORS
from auth import auth_bp
from config import Config
from create_account import accounting_bp
from goldapi import price_bp
from trade import trade_bp
app = Flask(__name__)
CORS(app)
app.config.from_object(Config)

app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(accounting_bp, url_prefix="/accounting")
app.register_blueprint(price_bp, url_prefix="/coin")
app.register_blueprint(trade_bp, url_prefix="/trade")

@app.route('/')
def home():
    return {"message": "Flask JWT OTP Blueprint API Running ✅"}

if __name__ == '__main__':
    app.run(port=5001,debug=True)
