
secrets = {
    # Wi‑Fi
    "ssid":          "YOUR_WIFI_SSID",
    "password":      "YOUR_WIFI_PASSWORD",

    # InfluxDB v1 (/write)
    "influx_host":   "YOUR_INFLUX_HOST",   # 例: "192.168.0.10"
    "influx_port":   8086,
    "influx_db":     "YOUR_DB_NAME",
    "influx_user":   "YOUR_USER",
    "influx_pass":   "YOUR_PASSWORD",

    # B‑route 認証（電力会社が発行したもの）
    "rbid":          "YOUR_BROUTE_ID",
    "rbpwd":         "YOUR_BROUTE_PASSWORD",

    # 任意（公開OKな情報のみ）
    "measurement":   "power",
    "tags":          "place=lab,host=RL7023",
}
