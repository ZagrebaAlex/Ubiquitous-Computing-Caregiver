import json
from flask import Flask, render_template, request, jsonify

from ollama2 import run_narrator


app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    question = data.get("message", "").strip()

    if not question:
        return jsonify({
            "mode": "narrator",
            "answer": "Please type a question.",
            "confidence": "low",
            "reason": "No question was provided.",
            "alerts": []
        })

    try:
        result = run_narrator(question)
        return jsonify(result)

    except Exception as error:
        return jsonify({
            "mode": "error",
            "answer": "I could not process the question.",
            "confidence": "low",
            "reason": str(error),
            "alerts": []
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=True)