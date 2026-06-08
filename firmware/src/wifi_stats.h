#pragma once

#include <Arduino.h>

typedef void (*wifi_stats_line_cb_t)(const String &line);

void wifi_stats_init(wifi_stats_line_cb_t on_line);
void wifi_stats_poll(void);
bool wifi_stats_is_connected(void);
const char *wifi_stats_ip_address(void);
