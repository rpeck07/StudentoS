from flask import Flask
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "STUDENTOS IS LIVE 🚀"

@app.route("/health")
def health():
    return {"status": "ok"}, 200