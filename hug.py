# assistive_web_speech.py
from pywebio import start_server
from pywebio.output import put_html
from pywebio.session import run_js
from pywebio.input import input_group, textarea
import threading
import queue

# Thread-safe queue to get recognized text
speech_queue = queue.Queue()

def web_speech_app():
    put_html("""
    <h2>Speech Recognition Active</h2>
    <p>Say something and it will be sent to Python.</p>
    <button onclick="startRecognition()">Start Listening</button>
    <button onclick="stopRecognition()">Stop Listening</button>
    <div id="output"></div>

    <script>
    var recognition;
    function startRecognition() {
        recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = 'en-US';

        recognition.onresult = function(event) {
            var transcript = '';
            for (var i = event.resultIndex; i < event.results.length; ++i) {
                transcript += event.results[i][0].transcript;
            }
            document.getElementById('output').innerText = transcript;
            fetch('/speech', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({text: transcript})
            });
        }

        recognition.start();
    }

    function stopRecognition() {
        if(recognition) recognition.stop();
    }
    </script>
    """)

# HTTP endpoint to receive speech from JS
from pywebio.platform.flask import webio_view
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/speech', methods=['POST'])
def receive_speech():
    data = request.get_json()
    text = data.get('text', '')
    if text:
        speech_queue.put(text)
    return jsonify({"status":"ok"})

# Python background thread to process recognized text
def process_speech_loop():
    while True:
        text = speech_queue.get()
        print(f"[voice] {text}")
        # Call your existing command processor here
        # perform_command_from_text(text)

# Start background thread
threading.Thread(target=process_speech_loop, daemon=True).start()

# Run PyWebIO on Flask
start_server(web_speech_app, port=8080, cdn=False)
