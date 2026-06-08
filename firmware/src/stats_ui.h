#ifndef STATS_UI_H
#define STATS_UI_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    int gpu;
    int gpu_temp;
    int gpu_mem;
    int cpu;
    int ram;
    int vol;
    bool muted;
    bool connected;
} stats_snapshot_t;

void stats_ui_create(void);
void stats_ui_update(const stats_snapshot_t *stats);

#ifdef __cplusplus
}
#endif

#endif
