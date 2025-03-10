from flask import Flask, render_template_string
import requests
import os

app = Flask(__name__)

# Prometheus metrics endpoint
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://llm-monitoring:8000/")

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Services Status</title>
    <style>
        body {
            font-family: 'Arial', sans-serif;
            text-align: center;
            background-color: #f4f4f4;
            color: #333;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 800px;
            margin: auto;
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0px 4px 6px rgba(0, 0, 0, 0.1);
        }
        .header {
            display: flex;
            align-items: center;
            justify-content: left;
        }
        .header img {
            height: 50px;
            margin-right: 15px;
        }
        h2 {
            color: #444;
            text-align: left;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }
        td {
            border-bottom: 1px solid #ddd;
            padding: 20px;
            font-size: 20px;
            font-family: 'Helvetica', monospace;
        }
        td:first-child {
            text-align: left;
            font-weight: normal;
        }
        .status {
            font-weight: normal;
            text-align: right;
            font-size: 16px;
            padding: 5px 10px;
            border-radius: 5px;
        }
        .up {
            color: #155724;
        }
        .down {
            color: #721c24;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <img src="https://access.redhat.com/chrome_themes/nimbus/img/logo_red_hat__normal_480.png" alt="Logo">
        </div>
        <h2>Services Status</h2>
        <table>
            {% for model in models %}
            <tr>
                <td>{{ model.name }}</td>
                <td class="status {{ 'up' if model.status == 1 else 'down' }}">
                    {{ 'Operational ✅' if model.status == 1 else 'Down ❌' }}
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
</body>
</html>
"""

def fetch_metrics():
    """Fetch metrics from Prometheus and parse the LLM statuses."""
    try:
        response = requests.get(PROMETHEUS_URL)
        response.raise_for_status()
        data = response.text.split('\n')
        models = []
        
        for line in data:
            if line.startswith("llm_endpoint_status") or line.startswith("website_status"):  # Filter for status metrics
                parts = line.split()
                if len(parts) == 2:
                    metadata, status = parts
                    name = metadata.split('name="')[1].split('"')[0]
                    models.append({"name": name, "status": int(float(status))})
        return models
    except Exception as e:
        print("Error fetching metrics:", e)
        return []

@app.route('/')
def index():
    models = fetch_metrics()
    return render_template_string(HTML_TEMPLATE, models=models)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)