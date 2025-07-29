# Pico W / Pico2 W + RL7023-11 Wi-SUN B-route → InfluxDB v1
# 単一ファイル。シークレットは secrets.py に退避（このファイルには一切書かない）
# 自動再接続/再JOIN、HTTP送信の指数バックオフ込み
import time, board, busio, wifi, socketpool, adafruit_requests

# ==== secrets 読み込み ==================================================
try:
    from secrets import secrets
except ImportError:
    secrets = {}
def _need(key):
    v = secrets.get(key, None)
    if v in (None, ""):
        raise RuntimeError("secrets['%s'] が未設定です" % key)
    return v

WIFI_SSID     = _need("ssid")
WIFI_PASSWORD = _need("password")

INFLUX_HOST   = _need("influx_host")
INFLUX_PORT   = int(secrets.get("influx_port", 8086))
INFLUX_DB     = _need("influx_db")
INFLUX_USER   = _need("influx_user")
INFLUX_PASS   = _need("influx_pass")

RBID          = _need("rbid")     # B-route 認証ID
RBPWD         = _need("rbpwd")    # B-route パスワード

# 計測のタグ（公開して問題ない情報のみを推奨）
MEASUREMENT   = secrets.get("measurement", "power")
TAGS          = secrets.get("tags", "place=uni,host=RL7023")
# ======================================================================

# InfluxDB v1 /write URL（BasicAuth ではなくクエリ認証を使用）
INFLUX_URL = (
    "http://%s:%d/write?db=%s&u=%s&p=%s"
    % (INFLUX_HOST, INFLUX_PORT, INFLUX_DB, INFLUX_USER, INFLUX_PASS)
)

# --- UART (RL7023) -----------------------------------------------------
UART_TX = board.GP0   # Pico TX → RL7023 RX
UART_RX = board.GP1   # Pico RX ← RL7023 TX
UART_BAUD = 115_200

uart = busio.UART(tx=UART_TX, rx=UART_RX, baudrate=UART_BAUD,
                  timeout=1.0, receiver_buffer_size=8192)

def _write(cmd, delay=0.1):
    uart.write((cmd + "\r\n").encode())
    time.sleep(delay)

def _readline():
    b = uart.readline()
    if not b:
        return None
    try:
        return b.decode().strip()
    except UnicodeDecodeError:
        return None

def _drain(seconds):
    t0 = time.monotonic()
    while time.monotonic() - t0 < seconds:
        _ = _readline()

# --- Wi‑Fi / HTTP ------------------------------------------------------
def ensure_wifi(max_retry=3):
    for i in range(max_retry):
        try:
            if wifi.radio.ipv4_address:
                return
        except Exception:
            pass
        try:
            print("Wi‑Fi connecting...")
            wifi.radio.connect(WIFI_SSID, WIFI_PASSWORD)
            print("Wi‑Fi OK:", wifi.radio.ipv4_address)
            return
        except Exception as e:
            print("Wi‑Fi err:", e)
            time.sleep(2 * (i + 1))
    raise RuntimeError("Wi‑Fi connect failed")

_pool = None
_req  = None
def renew_http_session():
    global _pool, _req
    _pool = socketpool.SocketPool(wifi.radio)
    _req  = adafruit_requests.Session(_pool)

ensure_wifi()
renew_http_session()

def post_influx(fields):
    """InfluxDB /write へ指数バックオフ付きでPOST。成功:True/失敗:False"""
    lp  = f"{MEASUREMENT},{TAGS} " + ",".join(f"{k}={v}" for k, v in fields.items())
    backoffs = [1, 2, 4, 8, 16]  # 秒
    for wait in [0] + backoffs:  # 初回は待たない
        if wait:
            time.sleep(wait)
        try:
            r = _req.post(INFLUX_URL, data=lp, headers={"Content-Type": "text/plain"})
            sc = r.status_code
            r.close()
            if sc == 204:
                return True
            print("Influx NG status:", sc)
        except Exception as e:
            print("Influx exc:", e)
            # 通信層エラー → Wi‑Fiを張り直してセッション再生成
            try:
                ensure_wifi()
            except Exception as ee:
                print("Wi‑Fi re-connect failed:", ee)
            renew_http_session()
    return False

# --- helpers -----------------------------------------------------------
def _parse_lqi(s):
    s = s.strip()
    try:
        # 16進/10進どちらも許容
        return int(s, 16) if all(c in "0123456789ABCDEFabcdef" for c in s) else int(s)
    except Exception:
        return -1

def sendto_raw(ipv6, payload):
    """SKSENDTO: ヘッダの直後に生バイナリを流す"""
    hdr = f"SKSENDTO 1 {ipv6} 0E1A 1 0 {len(payload):04X} "
    uart.write(hdr.encode())
    uart.write(payload)
    t0 = time.monotonic()
    while time.monotonic() - t0 < 3:
        l = _readline()
        if not l:
            continue
        if l.startswith("OK"):
            return True
    return False

# --- Wi‑SUN: scan/join -------------------------------------------------
def _scan_once(duration):
    _write(f"SKSCAN 2 FFFFFFFF {duration} 0")
    print(f"SKSCAN start (dur={duration})")
    candidates, cur = [], None
    t_end = time.monotonic() + 30 + 2 * duration
    while time.monotonic() < t_end:
        line = _readline()
        if not line:
            continue
        if line == "EPANDESC":
            if cur and cur.get("Channel") and cur.get("Pan ID") and cur.get("Addr"):
                candidates.append(cur)
            cur = {}
            continue
        if line.startswith("EVENT 22"):
            if cur and cur.get("Channel") and cur.get("Pan ID") and cur.get("Addr"):
                candidates.append(cur)
            break
        s = line.strip()
        if ":" in s and cur is not None:
            k, v = s.split(":", 1)
            k = k.strip(); v = v.strip()
            if k in ("Channel", "Pan ID", "Addr", "LQI"):
                cur[k] = v
    if not candidates:
        return None
    for c in candidates:
        c["LQI_num"] = _parse_lqi(c.get("LQI", ""))
    return max(candidates, key=lambda x: x["LQI_num"])

def wisun_join():
    """JOIN 完了まで。IPv6 を返す。"""
    _write("SKVER")
    _write(f"SKSETPWD C {RBPWD}")
    _write(f"SKSETRBID {RBID}")

    chosen = None
    for dur in range(4, 12):
        chosen = _scan_once(dur)
        if chosen:
            break
    if not chosen:
        raise RuntimeError("SKSCAN failed: EPANDESC 取得ゼロ")

    ch, pan, addr = chosen["Channel"], chosen["Pan ID"], chosen["Addr"]
    print("EPANDESC chosen:", chosen)

    _write(f"SKSREG S2 {ch}")
    _write(f"SKSREG S3 {pan}")
    _write(f"SKLL64 {addr}")
    ipv6, t0 = None, time.monotonic()
    while time.monotonic() - t0 < 5:
        l = _readline()
        if l and ":" in l:
            ipv6 = l.strip(); break
    if not ipv6:
        raise RuntimeError("SKLL64 failed: IPv6 取れず")

    _write(f"SKJOIN {ipv6}")
    ok, t0 = False, time.monotonic()
    while time.monotonic() - t0 < 30:
        l = _readline()
        if not l:
            continue
        if "EVENT 25" in l:  # success
            ok = True; break
        if "EVENT 24" in l:  # fail
            break
    if not ok:
        raise RuntimeError("SKJOIN failed")

    _drain(3)  # JOIN直後のERXUDPを軽く捨てておく
    return ipv6

# --- ECHONET Lite ------------------------------------------------------
def _frame(epc):
    return bytes([0x10,0x81,0x00,0x01, 0x05,0xFF,0x01, 0x02,0x88,0x01, 0x62, 0x01, epc, 0x00])

def read_meter(ipv6, epc_code, timeout_s=5.0):
    epc  = 0xE0 if epc_code == "E0" else 0xE7
    frm  = _frame(epc)
    if not sendto_raw(ipv6, frm):
        return None
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout_s:
        l = _readline()
        if not l:
            continue
        if "ERXUDP" not in l:
            continue
        parts = l.strip().split()
        if len(parts) < 10:
            continue
        udp = parts[9]  # UDP payload hex
        # seoj=028801, ESV=72, EPC一致
        if udp[8:14] == "028801" and udp[20:22] == "72" and udp[24:26] == f"{epc:02X}":
            try:
                val_hex = udp[-8:]
                return int(val_hex, 16)
            except Exception:
                return None
    return None

# --- メイン ------------------------------------------------------------
ensure_wifi()
ipv6_addr = wisun_join()
print("JOIN OK:", ipv6_addr)

echonet_fail = 0
http_fail    = 0
cnt          = 0

while True:
    try:
        fields = {}
        if cnt == 0:
            v_e0 = read_meter(ipv6_addr, "E0")
            if v_e0 is not None:
                fields["E0"] = v_e0
                echonet_fail = 0
            else:
                echonet_fail += 1
        v_e7 = read_meter(ipv6_addr, "E7")
        if v_e7 is not None:
            fields["E7"] = v_e7
            echonet_fail = 0
        else:
            echonet_fail += 1

        if fields:
            ok = post_influx(fields)
            if ok:
                http_fail = 0
            else:
                http_fail += 1

        # 自動回復
        if echonet_fail >= 3:
            print("ECHONET fail x3 → Re-JOIN...")
            ensure_wifi()
            renew_http_session()
            ipv6_addr = wisun_join()
            echonet_fail = 0

        if http_fail >= 5:
            print("HTTP fail x5 → Wi‑Fi reconnect & HTTP session renew")
            ensure_wifi()
            renew_http_session()
            http_fail = 0

    except Exception as e:
        print("Loop exc:", e)
        try:
            ensure_wifi()
            renew_http_session()
            ipv6_addr = wisun_join()
            echonet_fail = 0
            http_fail    = 0
        except Exception as ee:
            print("Recovery failed:", ee)

    cnt = (cnt + 1) % 5
    time.sleep(30)
