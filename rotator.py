import time
import requests
from stem import Signal
from stem.control import Controller

CONTROL_PASSWORD = "mypassword"
PROXY = {"http": "socks5h://127.0.0.1:9050", "https": "socks5h://127.0.0.1:9050"}

def get_ip():
    """Get current IP through Tor"""
    try:
        r = requests.get("https://api.ipify.org?format=json", proxies=PROXY, timeout=10)
        return r.json().get("ip", "unknown")
    except Exception as e:
        return f"error: {e}"

def rotate_ip():
    """Force Tor to build new circuit"""
    try:
        with Controller.from_port(port=9051) as controller:
            controller.authenticate(password=CONTROL_PASSWORD)
            controller.signal(Signal.NEWNYM)
            return True
    except Exception as e:
        print(f"[ROTATOR] Control error: {e}")
        return False

if __name__ == "__main__":
    print("[ROTATOR] IP rotator started")

    # Wait for Tor to be ready
    time.sleep(5)

    last_ip = None
    while True:
        try:
            # Force new circuit
            if rotate_ip():
                # Wait for circuit to build
                time.sleep(3)

                # Verify IP actually changed
                current_ip = get_ip()

                if current_ip != last_ip:
                    print(f"[ROTATOR] IP changed: {last_ip} -> {current_ip}")
                    last_ip = current_ip
                else:
                    print(f"[ROTATOR] IP same after rotation: {current_ip} (retrying...)")
                    # Force again immediately
                    rotate_ip()
                    time.sleep(3)
                    current_ip = get_ip()
                    print(f"[ROTATOR] After retry: {current_ip}")
                    last_ip = current_ip
            else:
                print("[ROTATOR] Rotation failed, retrying in 10s")

        except Exception as e:
            print(f"[ROTATOR] Error: {e}")

        time.sleep(10)
