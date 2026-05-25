import threading
import webview
from server import app

PORT = 5151


def start_server():
    app.run(port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    t = threading.Thread(target=start_server, daemon=True)
    t.start()

    webview.create_window(
        "Personal PM — Today",
        f"http://127.0.0.1:{PORT}",
        width=960,
        height=820,
        min_size=(600, 500),
    )
    webview.start()
