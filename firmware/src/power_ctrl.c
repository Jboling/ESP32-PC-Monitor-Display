#include "power_ctrl.h"

#include <stdint.h>

#include "user_config.h"
#include "src/lcd_bl_bsp/lcd_bl_pwm_bsp.h"
#include "src/tca9554/esp_io_expander_tca9554.h"
#include "i2c_bsp.h"
#include "driver/gpio.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

static const char *TAG = "power_ctrl";

#define PWR_BUTTON_GPIO GPIO_NUM_16
#define PWR_SHUTDOWN_HOLD_MS 3000

static esp_io_expander_handle_t io_expander = NULL;

static void tca9554_init(void)
{
    i2c_master_bus_handle_t i2c_bus = NULL;
    ESP_ERROR_CHECK(i2c_master_get_bus_handle(0, &i2c_bus));
    ESP_ERROR_CHECK(esp_io_expander_new_i2c_tca9554(
        i2c_bus, ESP_IO_EXPANDER_I2C_TCA9554_ADDRESS_000, &io_expander));
    ESP_ERROR_CHECK(esp_io_expander_set_dir(io_expander, IO_EXPANDER_PIN_NUM_6, IO_EXPANDER_OUTPUT));
    ESP_ERROR_CHECK(esp_io_expander_set_level(io_expander, IO_EXPANDER_PIN_NUM_6, 1));
}

static void power_shutdown(void)
{
    ESP_LOGI(TAG, "PWR held for %d ms, shutting down", PWR_SHUTDOWN_HOLD_MS);
    setUpduty(LCD_PWM_MODE_0);
    vTaskDelay(pdMS_TO_TICKS(100));
    ESP_ERROR_CHECK(esp_io_expander_set_level(io_expander, IO_EXPANDER_PIN_NUM_6, 0));
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

static void pwr_button_task(void *arg)
{
    (void)arg;
    uint32_t pressed_ms = 0;

    for (;;) {
        if (gpio_get_level(PWR_BUTTON_GPIO) == 0) {
            pressed_ms += 50;
            if (pressed_ms >= PWR_SHUTDOWN_HOLD_MS) {
                power_shutdown();
            }
        } else {
            pressed_ms = 0;
        }
        vTaskDelay(pdMS_TO_TICKS(50));
    }
}

void power_ctrl_init(void)
{
    gpio_config_t gpio_conf = {};
    gpio_conf.intr_type = GPIO_INTR_DISABLE;
    gpio_conf.mode = GPIO_MODE_INPUT;
    gpio_conf.pin_bit_mask = (1ULL << PWR_BUTTON_GPIO);
    gpio_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
    gpio_conf.pull_up_en = GPIO_PULLUP_ENABLE;
    ESP_ERROR_CHECK(gpio_config(&gpio_conf));

    tca9554_init();
    xTaskCreatePinnedToCore(pwr_button_task, "pwr_button", 3072, NULL, 1, NULL, 1);
    ESP_LOGI(TAG, "Hold PWR for %d seconds to shut down", PWR_SHUTDOWN_HOLD_MS / 1000);
}
