#ifndef PASM_OVERLAY_H
#define PASM_OVERLAY_H

#include "pasm_overlay_draw.h"

/* Compatibility for generated outputs that predate the generic overlay name. */
#define sms_overlay_put_pixel pasm_overlay_put_pixel
#define sms_overlay_blend_pixel pasm_overlay_blend_pixel
#define sms_overlay_fill_rect pasm_overlay_fill_rect
#define sms_overlay_fill_rect_alpha pasm_overlay_fill_rect_alpha
#define sms_overlay_glyph pasm_overlay_glyph
#define sms_overlay_draw_char pasm_overlay_draw_char
#define sms_overlay_text_width pasm_overlay_text_width
#define sms_overlay_draw_text pasm_overlay_draw_text
#define sms_overlay_draw_perf pasm_overlay_draw_perf
#define sms_overlay_update_perf pasm_overlay_update_perf

#endif
