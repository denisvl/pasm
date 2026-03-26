#ifndef SMS_OVERLAY_H
#define SMS_OVERLAY_H

#include <stdint.h>
#include <stdio.h>

static inline void sms_overlay_put_pixel(
    uint32_t *pixels,
    uint32_t w,
    uint32_t h,
    int x,
    int y,
    uint32_t color
) {
    if (!pixels || x < 0 || y < 0) return;
    if ((uint32_t)x >= w || (uint32_t)y >= h) return;
    pixels[(uint32_t)y * w + (uint32_t)x] = color;
}

static inline void sms_overlay_blend_pixel(
    uint32_t *pixels,
    uint32_t w,
    uint32_t h,
    int x,
    int y,
    uint32_t rgb,
    uint8_t alpha
) {
    if (!pixels || x < 0 || y < 0) return;
    if ((uint32_t)x >= w || (uint32_t)y >= h) return;
    if (alpha == 0u) return;
    if (alpha == 255u) {
        pixels[(uint32_t)y * w + (uint32_t)x] = 0xFF000000u | (rgb & 0x00FFFFFFu);
        return;
    }

    uint32_t *dst_ptr = &pixels[(uint32_t)y * w + (uint32_t)x];
    uint32_t dst = *dst_ptr;
    uint8_t dr = (uint8_t)((dst >> 16) & 0xFFu);
    uint8_t dg = (uint8_t)((dst >> 8) & 0xFFu);
    uint8_t db = (uint8_t)(dst & 0xFFu);
    uint8_t sr = (uint8_t)((rgb >> 16) & 0xFFu);
    uint8_t sg = (uint8_t)((rgb >> 8) & 0xFFu);
    uint8_t sb = (uint8_t)(rgb & 0xFFu);
    uint16_t inv = (uint16_t)(255u - alpha);

    uint8_t orr = (uint8_t)((dr * inv + sr * alpha + 127u) / 255u);
    uint8_t org = (uint8_t)((dg * inv + sg * alpha + 127u) / 255u);
    uint8_t orb = (uint8_t)((db * inv + sb * alpha + 127u) / 255u);
    *dst_ptr = 0xFF000000u | ((uint32_t)orr << 16) | ((uint32_t)org << 8) | (uint32_t)orb;
}

static inline void sms_overlay_fill_rect(
    uint32_t *pixels,
    uint32_t w,
    uint32_t h,
    int x,
    int y,
    int rw,
    int rh,
    uint32_t color
) {
    if (!pixels || rw <= 0 || rh <= 0) return;
    for (int yy = 0; yy < rh; ++yy) {
        for (int xx = 0; xx < rw; ++xx) {
            sms_overlay_put_pixel(pixels, w, h, x + xx, y + yy, color);
        }
    }
}

static inline void sms_overlay_fill_rect_alpha(
    uint32_t *pixels,
    uint32_t w,
    uint32_t h,
    int x,
    int y,
    int rw,
    int rh,
    uint32_t rgb,
    uint8_t alpha
) {
    if (!pixels || rw <= 0 || rh <= 0 || alpha == 0u) return;
    for (int yy = 0; yy < rh; ++yy) {
        for (int xx = 0; xx < rw; ++xx) {
            sms_overlay_blend_pixel(pixels, w, h, x + xx, y + yy, rgb, alpha);
        }
    }
}

static inline const uint8_t *sms_overlay_glyph(char ch) {
    static const uint8_t G_SPACE[7] = {0, 0, 0, 0, 0, 0, 0};
    static const uint8_t G_DOT[7] = {0, 0, 0, 0, 0, 0x0C, 0x0C};
    static const uint8_t G_COMMA[7] = {0, 0, 0, 0, 0, 0x0C, 0x08};
    static const uint8_t G_COLON[7] = {0, 0x0C, 0x0C, 0, 0x0C, 0x0C, 0};
    static const uint8_t G_SEMI[7] = {0, 0x0C, 0x0C, 0, 0x0C, 0x08, 0};
    static const uint8_t G_BANG[7] = {0x04, 0x04, 0x04, 0x04, 0x04, 0, 0x04};
    static const uint8_t G_QUES[7] = {0x0E, 0x11, 0x01, 0x02, 0x04, 0, 0x04};
    static const uint8_t G_MINUS[7] = {0, 0, 0, 0x1E, 0, 0, 0};
    static const uint8_t G_PLUS[7] = {0, 0x04, 0x04, 0x1F, 0x04, 0x04, 0};
    static const uint8_t G_SLASH[7] = {0x01, 0x02, 0x04, 0x08, 0x10, 0, 0};
    static const uint8_t G_EQ[7] = {0, 0x1F, 0, 0x1F, 0, 0, 0};
    static const uint8_t G_LPAREN[7] = {0x02, 0x04, 0x08, 0x08, 0x08, 0x04, 0x02};
    static const uint8_t G_RPAREN[7] = {0x08, 0x04, 0x02, 0x02, 0x02, 0x04, 0x08};
    static const uint8_t G_SQ[7] = {0x0E, 0x11, 0x01, 0x02, 0x04, 0, 0x04};
    static const uint8_t G_PCT[7] = {0x19, 0x19, 0x02, 0x04, 0x08, 0x13, 0x13};

    static const uint8_t G_0[7] = {0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E};
    static const uint8_t G_1[7] = {0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E};
    static const uint8_t G_2[7] = {0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F};
    static const uint8_t G_3[7] = {0x1E, 0x01, 0x01, 0x0E, 0x01, 0x01, 0x1E};
    static const uint8_t G_4[7] = {0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02};
    static const uint8_t G_5[7] = {0x1F, 0x10, 0x10, 0x1E, 0x01, 0x01, 0x1E};
    static const uint8_t G_6[7] = {0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E};
    static const uint8_t G_7[7] = {0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08};
    static const uint8_t G_8[7] = {0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E};
    static const uint8_t G_9[7] = {0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C};

    static const uint8_t G_A[7] = {0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11};
    static const uint8_t G_B[7] = {0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E};
    static const uint8_t G_C[7] = {0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E};
    static const uint8_t G_D[7] = {0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E};
    static const uint8_t G_E[7] = {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F};
    static const uint8_t G_F[7] = {0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10};
    static const uint8_t G_G[7] = {0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F};
    static const uint8_t G_H[7] = {0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11};
    static const uint8_t G_I[7] = {0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x1F};
    static const uint8_t G_J[7] = {0x01, 0x01, 0x01, 0x01, 0x11, 0x11, 0x0E};
    static const uint8_t G_K[7] = {0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11};
    static const uint8_t G_L[7] = {0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F};
    static const uint8_t G_M[7] = {0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11};
    static const uint8_t G_N[7] = {0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11};
    static const uint8_t G_O[7] = {0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E};
    static const uint8_t G_P[7] = {0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10};
    static const uint8_t G_Q[7] = {0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D};
    static const uint8_t G_R[7] = {0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11};
    static const uint8_t G_S[7] = {0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E};
    static const uint8_t G_T[7] = {0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04};
    static const uint8_t G_U[7] = {0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E};
    static const uint8_t G_V[7] = {0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04};
    static const uint8_t G_W[7] = {0x11, 0x11, 0x11, 0x15, 0x15, 0x15, 0x0A};
    static const uint8_t G_X[7] = {0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11};
    static const uint8_t G_Y[7] = {0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04};
    static const uint8_t G_Z[7] = {0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F};

    switch (ch) {
        case '0': return G_0;
        case '1': return G_1;
        case '2': return G_2;
        case '3': return G_3;
        case '4': return G_4;
        case '5': return G_5;
        case '6': return G_6;
        case '7': return G_7;
        case '8': return G_8;
        case '9': return G_9;
        case '.': return G_DOT;
        case ',': return G_COMMA;
        case ':': return G_COLON;
        case ';': return G_SEMI;
        case '!': return G_BANG;
        case '?': return G_QUES;
        case '-': return G_MINUS;
        case '+': return G_PLUS;
        case '/': return G_SLASH;
        case '=': return G_EQ;
        case '(': return G_LPAREN;
        case ')': return G_RPAREN;
        case '%': return G_PCT;
        case 'A': case 'a': return G_A;
        case 'B': case 'b': return G_B;
        case 'C': case 'c': return G_C;
        case 'D': case 'd': return G_D;
        case 'E': case 'e': return G_E;
        case 'F': case 'f': return G_F;
        case 'G': case 'g': return G_G;
        case 'H': case 'h': return G_H;
        case 'I': case 'i': return G_I;
        case 'J': case 'j': return G_J;
        case 'K': case 'k': return G_K;
        case 'L': case 'l': return G_L;
        case 'M': case 'm': return G_M;
        case 'N': case 'n': return G_N;
        case 'O': case 'o': return G_O;
        case 'P': case 'p': return G_P;
        case 'Q': case 'q': return G_Q;
        case 'R': case 'r': return G_R;
        case 'S': case 's': return G_S;
        case 'T': case 't': return G_T;
        case 'U': case 'u': return G_U;
        case 'V': case 'v': return G_V;
        case 'W': case 'w': return G_W;
        case 'X': case 'x': return G_X;
        case 'Y': case 'y': return G_Y;
        case 'Z': case 'z': return G_Z;
        case ' ': return G_SPACE;
        default: return G_SQ;
    }
}

static inline void sms_overlay_draw_char(
    uint32_t *pixels,
    uint32_t w,
    uint32_t h,
    int x,
    int y,
    char ch,
    int scale,
    uint32_t color
) {
    if (scale < 1) scale = 1;
    const uint8_t *glyph = sms_overlay_glyph(ch);
    for (int row = 0; row < 7; ++row) {
        uint8_t bits = glyph[row];
        for (int col = 0; col < 5; ++col) {
            if ((bits & (uint8_t)(1u << (4 - col))) == 0u) continue;
            int px = x + col * scale;
            int py = y + row * scale;
            for (int yy = 0; yy < scale; ++yy) {
                for (int xx = 0; xx < scale; ++xx) {
                    sms_overlay_put_pixel(pixels, w, h, px + xx, py + yy, color);
                }
            }
        }
    }
}

static inline int sms_overlay_text_width(const char *text, int scale) {
    int count = 0;
    while (text && text[count] != '\0') count++;
    if (count <= 0) return 0;
    return count * (5 * scale + scale);
}

static inline void sms_overlay_draw_text(
    uint32_t *pixels,
    uint32_t w,
    uint32_t h,
    int x,
    int y,
    const char *text,
    int scale,
    uint32_t color
) {
    if (!text || !text[0]) return;
    int advance = 5 * scale + scale;
    int cursor = x;
    for (int i = 0; text[i] != '\0'; ++i) {
        sms_overlay_draw_char(pixels, w, h, cursor, y, text[i], scale, color);
        cursor += advance;
    }
}

static inline void sms_overlay_draw_perf(
    uint32_t *pixels,
    uint32_t w,
    uint32_t h,
    uint32_t fps_x100,
    uint64_t cpu_hz,
    uint32_t cpu_pct_x10
) {
    if (!pixels || w == 0u || h == 0u) return;
    char line[96];
    int scale = 1;
    int pad = 3 * scale;
    int text_h = 7 * scale;
    uint32_t bg_rgb = 0x00101010u;
    uint8_t bg_alpha = 88u;
    uint32_t fg = 0xFFECECECu;
    uint32_t shadow = 0xFF000000u;
    int box_w;
    int box_h;
    int box_x;
    int box_y = 2;
    int text_x;
    int text_y;

    snprintf(
        line,
        sizeof(line),
        "FPS %4u.%02u CPU %5llu.%03lluMHZ %3u.%u%%",
        fps_x100 / 100u,
        fps_x100 % 100u,
        (unsigned long long)(cpu_hz / 1000000u),
        (unsigned long long)((cpu_hz % 1000000u) / 1000u),
        cpu_pct_x10 / 10u,
        cpu_pct_x10 % 10u
    );

    box_w = sms_overlay_text_width(line, scale) + pad * 2;
    {
        int min_box_w =
            sms_overlay_text_width("FPS 0000.00 CPU 00000.000MHZ 000.0%", scale) + pad * 2;
        if (box_w < min_box_w) {
            box_w = min_box_w;
        }
    }
    box_h = text_h + pad * 2;
    box_x = ((int)w > box_w) ? (((int)w - box_w) / 2) : 0;
    text_x = box_x + pad;
    text_y = box_y + pad;

    sms_overlay_fill_rect_alpha(pixels, w, h, box_x, box_y, box_w, box_h, bg_rgb, bg_alpha);
    sms_overlay_draw_text(pixels, w, h, text_x + scale, text_y + scale, line, scale, shadow);
    sms_overlay_draw_text(pixels, w, h, text_x, text_y, line, scale, fg);
}

static inline void sms_overlay_update_perf(
    uint32_t tick_ms,
    uint64_t frame_count,
    uint64_t total_cycles,
    uint64_t target_cpu_hz,
    uint32_t *last_ms,
    uint64_t *last_frame_count,
    uint64_t *last_cycle_count,
    uint32_t *fps_x100,
    uint64_t *cpu_hz,
    uint32_t *cpu_pct_x10
) {
    if (
        last_ms == NULL ||
        last_frame_count == NULL ||
        last_cycle_count == NULL ||
        fps_x100 == NULL ||
        cpu_hz == NULL ||
        cpu_pct_x10 == NULL
    ) {
        return;
    }

    if (*last_ms == 0u) {
        *last_ms = tick_ms;
        *last_frame_count = frame_count;
        *last_cycle_count = total_cycles;
        return;
    }

    uint32_t dt_ms = tick_ms - *last_ms;
    if (dt_ms < 250u) return;

    uint64_t frame_delta = frame_count - *last_frame_count;
    uint64_t cycle_delta = total_cycles - *last_cycle_count;

    *fps_x100 = (dt_ms > 0u)
        ? (uint32_t)((frame_delta * 100000u + (uint64_t)(dt_ms / 2u)) / (uint64_t)dt_ms)
        : 0u;
    *cpu_hz = (dt_ms > 0u)
        ? ((cycle_delta * 1000u + (uint64_t)(dt_ms / 2u)) / (uint64_t)dt_ms)
        : 0u;
    *cpu_pct_x10 = (target_cpu_hz > 0u)
        ? (uint32_t)((*cpu_hz * 1000u + (target_cpu_hz / 2u)) / target_cpu_hz)
        : 0u;

    *last_ms = tick_ms;
    *last_frame_count = frame_count;
    *last_cycle_count = total_cycles;
}

#endif
