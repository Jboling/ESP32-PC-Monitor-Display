#include "stats_ui.h"
#include "user_config.h"
#include "lvgl.h"
#include <stdio.h>

#define TEXT_WHITE lv_color_hex(0xFFFFFF)
#define CONTENT_W (EXAMPLE_LCD_H_RES - 12)

typedef struct {
    lv_obj_t *status_label;
    lv_obj_t *gpu_bar;
    lv_obj_t *gpu_label;
    lv_obj_t *gpu_temp_label;
    lv_obj_t *gpu_mem_bar;
    lv_obj_t *gpu_mem_label;
    lv_obj_t *cpu_bar;
    lv_obj_t *cpu_label;
    lv_obj_t *ram_bar;
    lv_obj_t *ram_label;
    lv_obj_t *vol_bar;
    lv_obj_t *vol_label;
} stats_ui_t;

static stats_ui_t ui;

static void style_container(lv_obj_t *obj)
{
    lv_obj_set_style_bg_opa(obj, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(obj, 0, 0);
    lv_obj_set_style_pad_all(obj, 0, 0);
}

static void style_label_white(lv_obj_t *label, const lv_font_t *font)
{
    lv_obj_set_style_text_color(label, TEXT_WHITE, 0);
    lv_obj_set_style_text_font(label, font, 0);
}

static lv_obj_t *create_metric_card(lv_obj_t *parent, const char *title, lv_obj_t **bar_out, lv_obj_t **value_out)
{
    lv_obj_t *card = lv_obj_create(parent);
    lv_obj_set_width(card, 118);
    lv_obj_set_height(card, LV_PCT(100));
    style_container(card);
    lv_obj_set_style_pad_row(card, 2, 0);
    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);

    lv_obj_t *title_label = lv_label_create(card);
    lv_label_set_text(title_label, title);
    style_label_white(title_label, &lv_font_montserrat_12);

    *bar_out = lv_bar_create(card);
    lv_obj_set_width(*bar_out, LV_PCT(100));
    lv_obj_set_height(*bar_out, 8);
    lv_bar_set_range(*bar_out, 0, 100);
    lv_obj_set_style_radius(*bar_out, 3, LV_PART_MAIN);
    lv_obj_set_style_bg_color(*bar_out, lv_color_hex(0x2A3440), LV_PART_MAIN);
    lv_obj_set_style_bg_color(*bar_out, lv_color_hex(0xFFFFFF), LV_PART_INDICATOR);

    *value_out = lv_label_create(card);
    lv_label_set_text(*value_out, "--");
    style_label_white(*value_out, &lv_font_montserrat_12);

    return card;
}

void stats_ui_create(void)
{
    lv_obj_t *screen = lv_screen_active();
    lv_obj_set_size(screen, EXAMPLE_LCD_H_RES, EXAMPLE_LCD_V_RES);
    lv_obj_set_style_bg_color(screen, lv_color_hex(0x101418), 0);
    lv_obj_set_style_pad_all(screen, 6, 0);
    lv_obj_set_style_pad_row(screen, 4, 0);
    lv_obj_set_flex_flow(screen, LV_FLEX_FLOW_COLUMN);

    lv_obj_t *header = lv_obj_create(screen);
    lv_obj_set_size(header, CONTENT_W, 24);
    style_container(header);
    lv_obj_set_flex_flow(header, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(header, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);

    lv_obj_t *title = lv_label_create(header);
    lv_label_set_text(title, "PC Monitor");
    style_label_white(title, &lv_font_montserrat_16);

    ui.status_label = lv_label_create(header);
    lv_label_set_text(ui.status_label, "Waiting for PC...");
    style_label_white(ui.status_label, &lv_font_montserrat_12);

    lv_obj_t *metrics_row = lv_obj_create(screen);
    lv_obj_set_size(metrics_row, CONTENT_W, EXAMPLE_LCD_V_RES - 36);
    style_container(metrics_row);
    lv_obj_set_style_pad_column(metrics_row, 6, 0);
    lv_obj_set_flex_flow(metrics_row, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(metrics_row, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);

    lv_obj_t *gpu_card = create_metric_card(metrics_row, "GPU", &ui.gpu_bar, &ui.gpu_label);
    ui.gpu_temp_label = lv_label_create(gpu_card);
    lv_label_set_text(ui.gpu_temp_label, "-- C");
    style_label_white(ui.gpu_temp_label, &lv_font_montserrat_12);

    create_metric_card(metrics_row, "VRAM", &ui.gpu_mem_bar, &ui.gpu_mem_label);
    create_metric_card(metrics_row, "CPU", &ui.cpu_bar, &ui.cpu_label);
    create_metric_card(metrics_row, "RAM", &ui.ram_bar, &ui.ram_label);
    create_metric_card(metrics_row, "VOL", &ui.vol_bar, &ui.vol_label);
}

static void set_bar_value(lv_obj_t *bar, int value)
{
    if (value < 0) {
        value = 0;
    } else if (value > 100) {
        value = 100;
    }
    lv_bar_set_value(bar, value, LV_ANIM_OFF);
}

void stats_ui_update(const stats_snapshot_t *stats)
{
    char text[48];

    lv_label_set_text(ui.status_label, stats->connected ? "Connected" : "Waiting for PC...");

    set_bar_value(ui.gpu_bar, stats->gpu);
    snprintf(text, sizeof(text), "%d%%", stats->gpu);
    lv_label_set_text(ui.gpu_label, text);

    snprintf(text, sizeof(text), "%d C", stats->gpu_temp);
    lv_label_set_text(ui.gpu_temp_label, text);

    set_bar_value(ui.gpu_mem_bar, stats->gpu_mem);
    snprintf(text, sizeof(text), "%d%%", stats->gpu_mem);
    lv_label_set_text(ui.gpu_mem_label, text);

    set_bar_value(ui.cpu_bar, stats->cpu);
    snprintf(text, sizeof(text), "%d%%", stats->cpu);
    lv_label_set_text(ui.cpu_label, text);

    set_bar_value(ui.ram_bar, stats->ram);
    snprintf(text, sizeof(text), "%d%%", stats->ram);
    lv_label_set_text(ui.ram_label, text);

    set_bar_value(ui.vol_bar, stats->vol);
    if (stats->muted) {
        lv_label_set_text(ui.vol_label, "Mute");
    } else {
        snprintf(text, sizeof(text), "%d%%", stats->vol);
        lv_label_set_text(ui.vol_label, text);
    }
}
