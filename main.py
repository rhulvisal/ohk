import re
import json
import uuid
import urllib.parse
import requests
import sys
import os
import concurrent.futures
import threading
import time
import random
from typing import Dict, Optional, Tuple, List
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
import asyncio


TOR_PROXY_URL = "socks5h://127.0.0.1:9050"
SUPABASE_DB_URL = "postgresql://postgres.ihkpvrrotqvdmassywyz:Hogaya,.12**@aws-1-ap-southeast-1.pooler.supabase.com:5432/postgres"
SUPABASE_TABLE = "fb_checks"

HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.7",
    "priority": "u=0, i",
    "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    "sec-ch-ua-full-version-list": '"Chromium";v="146.0.0.0", "Not-A.Brand";v="24.0.0.0", "Google Chrome";v="146.0.0.0"',
    "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-model": '"iPhone"',
    "sec-ch-ua-platform": '"iOS"',
    "sec-ch-ua-platform-version": '"18.5"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "none",
    "sec-fetch-user": "?1",
    "sec-gpc": "1",
    "upgrade-insecure-requests": "1",
    "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"
}

AJAX_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.7",
    "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
    "origin": "https://m.facebook.com",
    "priority": "u=1, i",
    "referer": "https://m.facebook.com/login/identify/",
    "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"',
    "sec-ch-ua-full-version-list": '"Chromium";v="146.0.0.0", "Not-A.Brand";v="24.0.0.0", "Google Chrome";v="146.0.0.0"',
    "sec-ch-ua-mobile": "?1",
    "sec-ch-ua-model": '"iPhone"',
    "sec-ch-ua-platform": '"iOS"',
    "sec-ch-ua-platform-version": '"18.5"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "sec-gpc": "1",
    "user-agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1"
}

URL_IDENTIFY = "https://m.facebook.com/login/identify/"
URL_SEARCH = "https://m.facebook.com/async/wbloks/fetch/"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global TOR_AVAILABLE, TOR_IP
    TOR_AVAILABLE, TOR_IP = check_tor_availability()
    print(f"[INFO] Tor availability: {TOR_AVAILABLE}")
    if TOR_IP:
        print(f"[INFO] Tor IP: {TOR_IP}")
    yield


app = FastAPI(title="Facebook Number Checker API", lifespan=lifespan)

TOR_AVAILABLE = False
TOR_IP = None

class TaskStore:
    def __init__(self):
        self.tasks: Dict[str, dict] = {}
        self.lock = threading.Lock()

    def create(self, task_id: str, numbers: List[str]):
        with self.lock:
            self.tasks[task_id] = {
                "status": "processing",
                "created_at": datetime.utcnow().isoformat(),
                "numbers": numbers,
                "results": [],
                "error": None,
                "completed_at": None
            }

    def get(self, task_id: str):
        with self.lock:
            return self.tasks.get(task_id)

    def update_status(self, task_id: str, status: str, error: str = None, completed_at: str = None):
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id]["status"] = status
                if error:
                    self.tasks[task_id]["error"] = error
                if completed_at:
                    self.tasks[task_id]["completed_at"] = completed_at

    def add_result(self, task_id: str, result: dict):
        with self.lock:
            if task_id in self.tasks:
                self.tasks[task_id]["results"].append(result)

task_store = TaskStore()


def extract_bkv(html: str) -> Optional[str]:
    patterns = [
        r'"versioningID":"([^"]+)"',
        r'versioningID:"([^"]+)"',
        r'WebBloksVersioningID[^"]*"([^"]{40,})"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def extract_rev(html: str) -> Optional[str]:
    patterns = [
        r'"client_revision":(\d+)',
        r'"rev":(\d+)',
        r'"server_revision":(\d+)',
        r'require\("ScriptPath"\).*"version":(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def extract_dtsg(html: str) -> Optional[str]:
    patterns = [
        r'"token":"(NAf[^"]+)"',
        r'"dtsg":\{"token":"([^"]+)"',
        r'"dtsg_ag":\{"token":"([^"]+)"',
        r'DTSGInitialData.*"token":"([^"]+)"',
        r'DTSGInitData.*"token":"([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            token = match.group(1)
            if ':0:0' not in token and token.startswith('NAf'):
                token += ':0:0'
            return token
    return None


def extract_lsd(html: str) -> Optional[str]:
    patterns = [
        r'"lsd":"([^"]+)"',
        r'"LSD",\[\],\{"token":"([^"]+)"',
        r'LSD[^"]*"([A-Za-z0-9_-]{20,})"',
        r'<input[^>]*name="lsd"[^>]*value="([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return None


def calculate_jazoest(dtsg: str) -> str:
    if not dtsg:
        return "24821"
    digits = sum(int(c) for c in dtsg if c.isdigit())
    return str(digits + 2)


def extract_fb_dtsg(html: str) -> Optional[str]:
    match = re.search(r'"fb_dtsg":"([^"]+)"', html)
    if match:
        return match.group(1)
    return None


def extract_all_tokens(html: str) -> Dict[str, str]:
    tokens = {}

    bkv = extract_bkv(html)
    if bkv:
        tokens['__bkv'] = bkv

    rev = extract_rev(html)
    if rev:
        tokens['rev'] = rev

    dtsg = extract_dtsg(html)
    if dtsg:
        tokens['dtsg'] = dtsg
        tokens['jazoest'] = calculate_jazoest(dtsg)

    lsd = extract_lsd(html)
    if lsd:
        tokens['lsd'] = lsd

    fb_dtsg = extract_fb_dtsg(html)
    if fb_dtsg:
        tokens['fb_dtsg'] = fb_dtsg

    tokens['event_request_id'] = str(uuid.uuid4())
    tokens['__hsi'] = generate_hsi()

    return tokens


def generate_hsi() -> str:
    return str(random.randint(10**18, 10**19 - 1))


def extract_cookies(response) -> Dict[str, str]:
    cookies = {}
    cookie_names = ['datr', 'sb', 'fr']

    for cookie in response.cookies:
        if cookie.name in cookie_names:
            cookies[cookie.name] = cookie.value

    set_cookie_headers = response.headers.get('Set-Cookie')
    if set_cookie_headers:
        if isinstance(set_cookie_headers, str):
            set_cookie_headers = [set_cookie_headers]
        else:
            set_cookie_headers = list(set_cookie_headers) if hasattr(set_cookie_headers, '__iter__') else [str(set_cookie_headers)]

        for header in set_cookie_headers:
            for name in cookie_names:
                if f'{name}=' in header:
                    try:
                        value = header.split(f'{name}=')[1].split(';')[0]
                        cookies[name] = value
                    except IndexError:
                        pass

    return cookies


def format_cookie_string(cookies: Dict[str, str]) -> str:
    extras = {
        'm_pixel_ratio': '3',
        'wd': '1440x900'
    }
    all_cookies = {**cookies, **extras}
    return '; '.join(f"{k}={v}" for k, v in all_cookies.items())


def build_search_data(tokens: Dict[str, str], phone_number: str) -> Dict[str, str]:
    data = {
        "__aaid": "0",
        "__user": "0",
        "__a": "1",
        "__req": "6",
        "__hs": "20581.BP%3Awbloks_caa_pkg.2.0...0",
        "dpr": "3",
        "__ccg": "EXCELLENT",
        "__rev": tokens.get('rev', ''),
        "__s": "krq94y%3Annmule%3Aw79uli",
        "__hsi": tokens.get('__hsi', generate_hsi()),
        "__dyn": "0wzpawlE72fDg9ppo5S12wAxu13wqobE6u7E39x67o1g8hw23E52q1ew2io0D24o1MUaE1Do1u81x82ewnE3fwww5NyE25w8W0Lo6-1CwOw5jw4JwzK0zo3jwea",
        "fb_dtsg": tokens.get('dtsg', ''),
        "jazoest": tokens.get('jazoest', '24821'),
        "lsd": tokens.get('lsd', ''),
    }

    data["params"] = json.dumps({
        "params": json.dumps({
            "server_params": {
                "event_request_id": tokens.get('event_request_id', str(uuid.uuid4())),
                "INTERNAL__latency_qpl_marker_id": 36707139,
                "INTERNAL__latency_qpl_instance_id": "167872800200122",
                "device_id": None,
                "family_device_id": None,
                "waterfall_id": None,
                "offline_experiment_group": None,
                "layered_homepage_experiment_group": None,
                "is_platform_login": 0,
                "is_from_logged_in_switcher": 0,
                "is_from_logged_out": 0,
                "access_flow_version": "pre_mt_behavior",
                "login_surface": "unknown",
                "context_data": "Ac_rbzblRWvJ3ySnRI4Q7Gtzh2_HVz46meQICifthMzu6f_5v6rN-H7inB8lscrASwNw-zk0mwQVN6PZrMaKkcb-arym8QJBXsNsyMW9BwuU9ftBpa-KA0zE9gqfz-xxlvd4cgF-j1duuKQd3L2umM0gQaii_QT8Dkn9HrutxTn54MSkb03b1yj1Yy4csY5EE5tbDdePYhMfCXNbzwW17XB8UFSBV21yTFN_JWZitFUUm8_1QyT9ppmao8U3Vh0PBJ1ePTf0BV9Hcb-fKAr0n9YV8866x8TU9_Z9Ae9ILK9cKQNWo0EjF3IAUlCxAVy1qbEKvTamltc6Wf3z7zgm2EBUSNyR_GsW5M8tV6kYxqbaUsvNruDyjCjWelh25oBO_T9Xc-umYdjKwZcWhZS5y0oLqZw2nTYTktVCevIjYpKbzKq2bWS9asLWckXsC73lAndQzye4n7TUWDggIw|arm"
            },
            "client_input_params": {
                "zero_balance_state": None,
                "search_query": phone_number,
                "fetched_email_list": [],
                "fetched_email_token_list": {},
                "sso_accounts_auth_data": [],
                "sfdid": "",
                "text_input_id": "rrgyte:67",
                "encrypted_msisdn": "",
                "headers_infra_flow_id": "",
                "was_headers_prefill_available": 0,
                "was_headers_prefill_used": 0,
                "ig_oauth_token": [],
                "android_build_type": "",
                "is_whatsapp_installed": 0,
                "device_network_info": None,
                "accounts_list": [],
                "is_oauth_without_permission": 0,
                "search_screen_type": "mobile",
                "ig_vetted_device_nonce": "",
                "gms_incoming_call_retriever_eligibility": "client_not_supported",
                "auth_secure_device_id": "",
                "blocked_uids": [],
                "cloud_trust_token": None,
                "network_bssid": None,
                "lois_settings": {"lois_token": ""},
                "aac": ""
            }
        })
    })

    return data


def parse_search_response(response_text: str) -> Dict:
    result = {
        "registered": False,
        "confidence": "low",
        "details": {},
        "raw_response": response_text[:1000] if response_text else "",
        "parsed_json": None,
        "error": None
    }

    if not response_text:
        result["error"] = "Empty response"
        return result

    
    clean_text = response_text.strip()

    
    prefix_patterns = [
        r'^for\s*\(;;;\)\s*;',      
        r'^for\s*\(\s*;\s*;\s*;\s*\)\s*;',  
        r'^for\s*\([;]+\)\s*;',     
    ]

    for pattern in prefix_patterns:
        if re.match(pattern, clean_text):
            clean_text = re.sub(pattern, '', clean_text, count=1)
            break

    
    if not clean_text.startswith(('{', '[')):
        json_start = max(
            clean_text.find('{'),
            clean_text.find('[')
        )
        if json_start > 0:
            clean_text = clean_text[json_start:]
        elif json_start == -1:
            result["error"] = "No JSON object found in response"
            return result

    try:
        data = json.loads(clean_text)
        result["parsed_json"] = data
    except json.JSONDecodeError as e:
        result["error"] = f"Invalid JSON response: {str(e)}"
        return result

    
    response_str = json.dumps(data)

    
    if "We couldn't find your account" in response_str or "search_error_dialog_shown" in response_str:
        result["registered"] = False
        result["confidence"] = "very_high"
        result["details"]["explicit_no_results"] = True
        result["details"]["indicator"] = "Account not found dialog triggered"
        return result

    
    if "search_failure_client" in response_str:
        result["registered"] = False
        result["confidence"] = "high"
        result["details"]["search_failure"] = True
        result["details"]["indicator"] = "Search failure event logged"
        return result

    
    if "push_screen_BloksCAAAccountRecoveryAuthMethodController" in response_str:
        result["registered"] = True
        result["confidence"] = "very_high"
        result["details"]["auth_method_screen"] = True
        result["details"]["indicator"] = "Auth method screen pushed (account found)"

        
        if "caa_core_data_encrypted" in response_str:
            result["details"]["has_encrypted_profile"] = True

        return result

    
    if "caa_core_data_encrypted" in response_str and len(response_str) > 5000:
        result["registered"] = True
        result["confidence"] = "very_high"
        result["details"]["encrypted_profile_data"] = True
        result["details"]["indicator"] = "Encrypted profile data detected (large payload)"
        return result

    
    if "search_success_client" in response_str:
        result["registered"] = True
        result["confidence"] = "high"
        result["details"]["search_success"] = True
        result["details"]["indicator"] = "Search success event logged"

        
        img_matches = re.findall(r"https://scontent[^\s\"'<>]+", response_str)
        if img_matches:
            result["confidence"] = "very_high"
            result["details"]["image_urls"] = img_matches[:3]
            result["details"]["indicator"] = "Account found with profile images"

        return result

    
    if "search_performed_client" in response_str:
        result["registered"] = False
        result["confidence"] = "medium"
        result["details"]["indicator"] = "Search performed but no success/failure flag found"
        return result

    
    if '"name"' in response_str and ('"user"' in response_str or '"account"' in response_str):
        result["registered"] = True
        result["confidence"] = "medium"
        result["details"]["indicator"] = "Account-like data structure detected"
        return result

    
    result["registered"] = False
    result["confidence"] = "low"
    result["details"]["indicator"] = "No clear registration indicators found"

    return result


class FacebookNumberChecker:
    def __init__(self, use_tor: bool = True):
        self.session = requests.Session()
        self.tokens = {}
        self.cookies = {}
        self.use_tor = use_tor

        if use_tor and TOR_AVAILABLE:
            proxy_dict = {'http': TOR_PROXY_URL, 'https': TOR_PROXY_URL}
            self.session.proxies.update(proxy_dict)

    def fetch_identify_page(self, max_retries: int = 3) -> bool:
        for attempt in range(max_retries):
            try:
                response = self.session.get(
                    URL_IDENTIFY,
                    headers=HEADERS,
                    timeout=30,
                    allow_redirects=True
                )
                response.raise_for_status()

                self.cookies = extract_cookies(response)
                self.tokens = extract_all_tokens(response.text)

                required = ['__bkv', 'rev', 'dtsg', 'lsd']
                missing = [r for r in required if r not in self.tokens]

                if missing:
                    if attempt < max_retries - 1:
                        time.sleep(1 + attempt)
                        continue
                    return False

                return True

            except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                if attempt < max_retries - 1:
                    time.sleep(2 + attempt)
                    continue
                return False
            except requests.exceptions.RequestException:
                if attempt < max_retries - 1:
                    time.sleep(1 + attempt)
                    continue
                return False

        return False

    def search_number(self, phone_number: str, max_retries: int = 2) -> Dict:
        if not phone_number.startswith('+'):
            phone_number = '+' + phone_number

        search_url = f"{URL_SEARCH}?appid=com.bloks.www.caa.ar.search.async&type=action&__bkv={self.tokens['__bkv']}"
        data = build_search_data(self.tokens, phone_number)

        headers = AJAX_HEADERS.copy()
        if self.cookies:
            headers["Cookie"] = format_cookie_string(self.cookies)
        headers["x-fb-lsd"] = self.tokens.get('lsd', '')

        for attempt in range(max_retries):
            try:
                response = self.session.post(
                    search_url,
                    headers=headers,
                    data=data,
                    timeout=30,
                    allow_redirects=False
                )

                result = parse_search_response(response.text)
                result["response_status"] = response.status_code
                return result

            except (requests.exceptions.ProxyError, requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return {
                    "registered": None,
                    "confidence": "none",
                    "error": "Network error",
                    "details": {}
                }
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                return {
                    "registered": None,
                    "confidence": "none",
                    "error": str(e),
                    "details": {}
                }

        return {
            "registered": None,
            "confidence": "none",
            "error": "Max retries exceeded",
            "details": {}
        }

    def check_number(self, phone_number: str) -> Dict:
        if not self.fetch_identify_page():
            return {
                "registered": None,
                "confidence": "none",
                "error": "Failed to fetch/extract tokens",
                "details": {}
            }

        return self.search_number(phone_number)


def check_tor_availability() -> Tuple[bool, Optional[str]]:
    try:
        proxy_dict = {'http': TOR_PROXY_URL, 'https': TOR_PROXY_URL}
        response = requests.get(
            'https://api.ipify.org?format=json',
            proxies=proxy_dict,
            timeout=10
        )
        if response.status_code == 200:
            ip = response.json().get('ip')
            return True, ip
    except:
        pass
    return False, None


def save_to_supabase(results: List[Dict]):
    try:
        import psycopg2
        from psycopg2.extras import execute_values

        conn = psycopg2.connect(SUPABASE_DB_URL)
        cur = conn.cursor()

        rows = []
        for result in results:
            if result.get('registered') is not None:
                rows.append((
                    result.get('number'),
                    result.get('registered'),
                    datetime.utcnow().isoformat()
                ))

        if rows:
            execute_values(
                cur,
                f"INSERT INTO {SUPABASE_TABLE} (number, registered, checked_at) VALUES %s",
                rows
            )
            conn.commit()

        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"[ERROR] Supabase save failed: {e}")
        return False


def process_numbers_for_task(task_id: str, numbers: List[str]):
    try:
        for number in numbers:
            checker = FacebookNumberChecker(use_tor=True)
            result = checker.check_number(number)

            result_obj = {
                "number": number,
                "registered": result.get('registered'),
                "confidence": result.get('confidence'),
                "error": result.get('error'),
                "checked_at": datetime.utcnow().isoformat()
            }

            task_store.add_result(task_id, result_obj)
            time.sleep(0.5)  

        
        task = task_store.get(task_id)
        if task:
            save_to_supabase(task['results'])
            task_store.update_status(task_id, 'completed', completed_at=datetime.utcnow().isoformat())
    except Exception as e:
        task_store.update_status(task_id, 'failed', error=str(e), completed_at=datetime.utcnow().isoformat())


@app.get("/")
async def root():
    return {
        "service": "Facebook Number Checker API",
        "endpoints": {
            "GET /": "This help page",
            "GET /test": "Test Tor availability + sample check",
            "GET /check": "Start checking numbers (query: ?numbers=+123,+456)",
            "POST /check": "Start checking numbers (body: {numbers: [...]})",
            "GET /result/{task_id}": "Stream results via SSE"
        },
        "usage": {
            "step_1": "GET /check?numbers=+231770636537,+1234567890 or POST /check with JSON body",
            "step_2": "Receive task_id in response",
            "step_3": "GET /result/{task_id} to stream results as SSE",
            "step_4": "Results are saved to Supabase after completion"
        },
        "tor_status": {
            "available": TOR_AVAILABLE,
            "ip": TOR_IP or "Unknown"
        }
    }


@app.get("/test")
async def test_endpoint():
    results = []

    
    tor_available, tor_ip = check_tor_availability()
    results.append({
        "test": "tor_availability",
        "available": tor_available,
        "ip": tor_ip or "Unknown"
    })

    
    sample_number = "+231770636537"
    try:
        checker = FacebookNumberChecker(use_tor=tor_available)
        result = checker.check_number(sample_number)
        results.append({
            "test": "sample_check",
            "number": sample_number,
            "registered": result.get('registered'),
            "confidence": result.get('confidence'),
            "error": result.get('error'),
            "tor_used": tor_available
        })
    except Exception as e:
        results.append({
            "test": "sample_check",
            "error": str(e)
        })

    return {"results": results}


def parse_numbers_query(raw_numbers: str) -> List[str]:
    if not raw_numbers:
        return []
    parts = [p.strip() for p in raw_numbers.replace(";", ",").split(",")]
    return [p for p in parts if p]


@app.get("/check")
async def check_numbers_get(numbers: str = Query("")):
    number_list = parse_numbers_query(numbers)

    if not number_list:
        raise HTTPException(status_code=400, detail="Invalid query: numbers must be a non-empty list")

    task_id = str(uuid.uuid4())
    task_store.create(task_id, number_list)

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
    executor.submit(process_numbers_for_task, task_id, number_list)
    executor.shutdown(wait=False)

    return {
        "task_id": task_id,
        "numbers_count": len(number_list),
        "status": "processing",
        "result_url": f"/result/{task_id}"
    }


@app.post("/check")
async def check_numbers(payload: dict):
    numbers = payload.get('numbers', [])

    if not numbers or not isinstance(numbers, list):
        raise HTTPException(status_code=400, detail="Invalid payload: numbers must be a non-empty list")

    task_id = str(uuid.uuid4())
    task_store.create(task_id, numbers)

    
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
    executor.submit(process_numbers_for_task, task_id, numbers)
    executor.shutdown(wait=False)

    return {
        "task_id": task_id,
        "numbers_count": len(numbers),
        "status": "processing",
        "result_url": f"/result/{task_id}"
    }


@app.get("/result/{task_id}")
async def get_results(task_id: str):
    task = task_store.get(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        last_result_count = 0

        while True:
            current_task = task_store.get(task_id)
            if not current_task:
                break

            
            current_results = current_task['results']
            for result in current_results[last_result_count:]:
                yield f"data: {json.dumps({'event': 'result', 'data': result})}\n\n"
                last_result_count += 1

            
            if current_task['status'] in ['completed', 'failed']:
                final_event = {
                    "event": "complete",
                    "task_status": current_task['status'],
                    "total_results": len(current_task['results']),
                    "completed_at": current_task['completed_at'],
                    "error": current_task['error']
                }
                yield f"data: {json.dumps(final_event)}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
