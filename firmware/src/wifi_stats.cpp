#include "wifi_stats.h"
#include "wifi_config.h"

#if WIFI_ENABLED

#include <WiFi.h>
#include <ESPmDNS.h>

static WiFiServer *stats_server = nullptr;
static WiFiClient stats_client;
static wifi_stats_line_cb_t line_callback = nullptr;
static String line_buffer;
static bool wifi_ready = false;
static char ip_text[16] = "0.0.0.0";

static void start_mdns(void)
{
    if (MDNS.begin(DEVICE_HOSTNAME)) {
        MDNS.addService("pcmonitor", "tcp", STATS_TCP_PORT);
        Serial.printf("mDNS: http://%s.local (pcmonitor tcp/%d)\n", DEVICE_HOSTNAME, STATS_TCP_PORT);
    } else {
        Serial.println("mDNS start failed");
    }
}

void wifi_stats_init(wifi_stats_line_cb_t on_line)
{
    line_callback = on_line;

    WiFi.mode(WIFI_STA);
    WiFi.setHostname(DEVICE_HOSTNAME);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    Serial.printf("WiFi connecting to \"%s\"...\n", WIFI_SSID);

    const uint32_t timeout_ms = 20000;
    const uint32_t start_ms = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - start_ms) < timeout_ms) {
        delay(250);
        Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi connect failed — USB serial still works");
        return;
    }

    wifi_ready = true;
    snprintf(ip_text, sizeof(ip_text), "%s", WiFi.localIP().toString().c_str());
    Serial.printf("WiFi connected: %s\n", ip_text);

    stats_server = new WiFiServer(STATS_TCP_PORT);
    stats_server->begin();
    start_mdns();
    Serial.printf("Stats TCP server on port %d\n", STATS_TCP_PORT);
}

void wifi_stats_poll(void)
{
    if (!wifi_ready || stats_server == nullptr || line_callback == nullptr) {
        return;
    }

    if (!stats_client || !stats_client.connected()) {
        WiFiClient next_client = stats_server->available();
        if (next_client) {
            stats_client = next_client;
            line_buffer = "";
            Serial.println("WiFi client connected");
        }
        return;
    }

    while (stats_client.available()) {
        char c = static_cast<char>(stats_client.read());
        if (c == '\n' || c == '\r') {
            if (!line_buffer.isEmpty()) {
                line_callback(line_buffer);
                line_buffer = "";
            }
            continue;
        }
        if (line_buffer.length() < 512) {
            line_buffer += c;
        }
    }
}

bool wifi_stats_is_connected(void)
{
    return wifi_ready && WiFi.status() == WL_CONNECTED;
}

const char *wifi_stats_ip_address(void)
{
    return ip_text;
}

#else

void wifi_stats_init(wifi_stats_line_cb_t on_line)
{
    (void)on_line;
}

void wifi_stats_poll(void)
{
}

bool wifi_stats_is_connected(void)
{
    return false;
}

const char *wifi_stats_ip_address(void)
{
    return "0.0.0.0";
}

#endif
