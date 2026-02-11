import httpx
import sys

def stop_server():
    try:
        # Try to call the shutdown endpoint
        response = httpx.post("http://127.0.0.1:8123/shutdown", timeout=2.0)
        if response.status_code == 200:
            print("Shutdown signal sent successfully.")
        else:
            print(f"Server responded with status code: {response.status_code}")
    except httpx.ConnectError:
        print("Server is not currently running.")
    except Exception as e:
        print(f"An error occurred while trying to stop the server: {e}")

if __name__ == "__main__":
    stop_server()
