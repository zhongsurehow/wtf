import requests

try:
    response = requests.get("http://localhost:8501")
    response.raise_for_status()  # Raise an exception for bad status codes
    print(response.text)
except requests.exceptions.RequestException as e:
    print(f"An error occurred: {e}")
