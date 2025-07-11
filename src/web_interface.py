"""
Simple web interface for the Itinerary Generator with improved session management.
"""

from flask import Flask, request, jsonify, render_template_string
import threading
import asyncio
import uuid
from google.genai import types
from main import create_agent_runtime
import os

# Create Flask app
flask_app = Flask(__name__)

# Initialize global runtime and results store
agent_runtime = create_agent_runtime()
results = {}

# HTML template for the web interface
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Itinerary Generator</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        h1 { color: #2c3e50; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input[type="text"], textarea, select { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }
        textarea { height: 100px; }
        button { background-color: #3498db; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer; }
        button:hover { background-color: #2980b9; }
        #result { margin-top: 20px; padding: 15px; border: 1px solid #ddd; border-radius: 4px; white-space: pre-wrap; display: none; }
        #loading { display: none; margin-top: 20px; text-align: center; }
    </style>
</head>
<body>
    <h1>Automated Itinerary Generator</h1>
    <div class="form-group">
        <label for="request">Describe your trip:</label>
        <textarea id="request" placeholder="Example: I want a 3-day trip to San Francisco focusing on food and culture with a moderate budget."></textarea>
    </div>
    <button onclick="generateItinerary()">Generate Itinerary</button>
    
    <div id="loading">Generating your itinerary... This may take a minute or two.</div>
    <div id="result"></div>
    
    <script>
        function generateItinerary() {
            const request = document.getElementById('request').value;
            if (!request) {
                alert('Please describe your trip first.');
                return;
            }
            
            document.getElementById('loading').style.display = 'block';
            document.getElementById('result').style.display = 'none';
            
            fetch('/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({request: request}),
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'processing') {
                    checkStatus(data.id);
                } else {
                    displayResult(data.result);
                }
            })
            .catch(error => {
                document.getElementById('loading').style.display = 'none';
                alert('Error: ' + error);
            });
        }
        
        function checkStatus(id) {
            fetch('/status/' + id)
            .then(response => response.json())
            .then(data => {
                if (data.status === 'completed') {
                    displayResult(data.result);
                } else if (data.status === 'processing') {
                    setTimeout(() => checkStatus(id), 2000);
                } else {
                    document.getElementById('loading').style.display = 'none';
                    alert('Error: ' + data.message);
                }
            })
            .catch(error => {
                document.getElementById('loading').style.display = 'none';
                alert('Error checking status: ' + error);
            });
        }
        
        function displayResult(result) {
            document.getElementById('loading').style.display = 'none';
            const resultDiv = document.getElementById('result');
            resultDiv.innerHTML = result;
            resultDiv.style.display = 'block';
        }
    </script>
</body>
</html>
"""

def run_agent(request_id, request_text):
    """Run the agent in a separate thread with its own event loop."""

    async def _run():
        try:
            content = types.Content(role='user', parts=[types.Part(text=request_text)])
            response_text = ""
            
            app_name = "itinerary_generator"

            # Check if session already exists before creating
            try:
                existing_session = await agent_runtime.session_service.get_session(
                    app_name=app_name,
                    user_id=request_id,
                    session_id=request_id
                )
                print(f"Using existing session: {existing_session.id}")
            except Exception:
                # Session doesn't exist, create a new one
                session = await agent_runtime.session_service.create_session(
                    app_name=app_name,
                    user_id=request_id,
                    session_id=request_id,
                    state={}
                )
                print(f"Created new session: {session.id}")

            # Run the agent
            async for event in agent_runtime.run_async(
                user_id=request_id,
                session_id=request_id,
                new_message=content
            ):
                if event.is_final_response():
                    for part in event.content.parts:
                        response_text += part.text

            results[request_id] = {
                "status": "completed",
                "result": response_text
            }
            
        except Exception as e:
            print(f"Error in run_agent: {str(e)}")
            results[request_id] = {
                "status": "error",
                "message": str(e)
            }

    # Create new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()

@flask_app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@flask_app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    request_text = data.get('request', '').strip()

    if not request_text:
        return jsonify({"status": "error", "message": "Request text is required."}), 400

    request_id = str(uuid.uuid4())
    results[request_id] = {"status": "processing"}

    # Start agent in separate thread
    thread = threading.Thread(target=run_agent, args=(request_id, request_text))
    thread.daemon = True  # Make thread daemon so it doesn't prevent app shutdown
    thread.start()

    return jsonify({"status": "processing", "id": request_id})

@flask_app.route('/status/<request_id>')
def status(request_id):
    if request_id not in results:
        return jsonify({"status": "error", "message": "Request not found"}), 404
    return jsonify(results[request_id])

# Optional: Add endpoint to list active sessions (for debugging)
@flask_app.route('/sessions')
def list_sessions():
    async def _list_sessions():
        try:
            sessions = await agent_runtime.session_service.list_sessions(
                app_name="itinerary_generator"
            )
            session_info = [
                {
                    "id": session.id,
                    "user_id": session.user_id,
                    "created_at": str(session.created_at) if hasattr(session, 'created_at') else 'Unknown'
                }
                for session in sessions
            ]
            return {"sessions": session_info}
        except Exception as e:
            return {"error": str(e)}
    
    # Run the async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(_list_sessions())
        if "error" in result:
            return jsonify(result), 500
        return jsonify(result)
    finally:
        loop.close()


def run_web_interface():
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting Itinerary Generator Web Interface on port {port}...")
    flask_app.run(host="0.0.0.0", port=port, debug=False)

if __name__ == "__main__":
    run_web_interface()