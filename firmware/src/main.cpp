#include <Arduino.h>
#include <ArduinoJson.h>
#include "user_config.h"
#include "lvgl_port.h"
#include "i2c_bsp.h"
#include "src/lcd_bl_bsp/lcd_bl_pwm_bsp.h"
#include "stats_ui.h"
#include "power_ctrl.h"
#include "wifi_stats.h"
#include "wifi_config.h"

static stats_snapshot_t current_stats = {
    .gpu = 0,
    .gpu_temp = 0,
    .gpu_mem = 0,
    .cpu = 0,
    .ram = 0,
    .vol = 0,
    .muted = false,
    .connected = false,
};

static String serial_line;
static uint32_t last_packet_ms = 0;

static void apply_stats_to_ui(void)
{
    if (lvgl_port_lock(50)) {
        stats_ui_update(&current_stats);
        lvgl_port_unlock();
    }
}

static void parse_stats_line(const String &line)
{
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, line);
    if (err) {
        Serial.printf("JSON parse error: %s\n", err.c_str());
        return;
    }

    current_stats.gpu = doc["gpu"] | current_stats.gpu;
    current_stats.gpu_temp = doc["gpu_temp"] | current_stats.gpu_temp;
    current_stats.gpu_mem = doc["gpu_mem"] | current_stats.gpu_mem;
    current_stats.cpu = doc["cpu"] | current_stats.cpu;
    current_stats.ram = doc["ram"] | current_stats.ram;
    current_stats.vol = doc["vol"] | current_stats.vol;
    current_stats.muted = doc["muted"] | current_stats.muted;
    current_stats.connected = true;
    last_packet_ms = millis();

    apply_stats_to_ui();
}

void setup()
{
    Serial.begin(115200);
    delay(500);

    i2c_master_Init();
    power_ctrl_init();
    lvgl_port_init();
    lcd_bl_pwm_bsp_init(LCD_PWM_MODE_255);
    wifi_stats_init(parse_stats_line);

    Serial.println("ESP32 PC Monitor ready");
    Serial.println("Send newline-delimited JSON over USB serial or WiFi TCP, e.g.:");
    Serial.println(R"({"gpu":45,"gpu_temp":62,"gpu_mem":78,"cpu":23,"ram":56,"vol":67,"muted":false})");
    if (wifi_stats_is_connected()) {
        Serial.printf("WiFi stats endpoint: %s:%d\n", wifi_stats_ip_address(), STATS_TCP_PORT);
    }
}

void loop()
{
    while (Serial.available()) {
        char c = static_cast<char>(Serial.read());
        if (c == '\n' || c == '\r') {
            if (!serial_line.isEmpty()) {
                parse_stats_line(serial_line);
                serial_line = "";
            }
            continue;
        }
        if (serial_line.length() < 512) {
            serial_line += c;
        }
    }

    wifi_stats_poll();

    if (current_stats.connected && (millis() - last_packet_ms) > 3000) {
        current_stats.connected = false;
        apply_stats_to_ui();
    }

    delay(10);
}
