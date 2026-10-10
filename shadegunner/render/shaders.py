"""GLSL-Shader für ShadeGunner.

Vendored/adaptiert aus `asciiplay` (Alex Riedel): derselbe Bayer-Ordered-Dither
gegen eine feste Palette und dieselbe CRT-Kette. Die Paletten-Tabelle wird aus
`config.PALETTES` erzeugt, damit Look und Software-Preview identisch sind.

`ASCII_VERT` zeichnet ein bildschirmfüllendes Dreieck über gl_VertexID (kein VBO).
"""

from .. import config


def _glsl_common():
    entries, offsets = [], {}
    for name, colours in config.PALETTES.items():
        offsets[name] = len(entries)
        entries.extend(colours)
    table = ", ".join(f"vec3({r / 255:.4f}, {g / 255:.4f}, {b / 255:.4f})" for r, g, b in entries)
    code = f"const vec3 PAL[{len(entries)}] = vec3[{len(entries)}]({table});\n" + """
vec3 nearest_pal(vec3 c, int off, int n) {
    vec3 best = PAL[off];
    float bd = 1e9;
    for (int i = 0; i < 32; ++i) {
        if (i >= n) break;
        vec3 q = PAL[off + i];
        vec3 d = (c - q) * vec3(0.9, 1.1, 0.8);
        float dd = dot(d, d);
        if (dd < bd) { bd = dd; best = q; }
    }
    return best;
}
float bayer(ivec2 p, int k) {
    int v = 0; int x = p.x; int y = p.y;
    for (int i = 0; i < k; ++i) {
        v = (v << 2) | (((x ^ y) & 1) << 1) | (y & 1);
        x >>= 1; y >>= 1;
    }
    return (float(v) + 0.5) / float(1 << (2 * k));
}
"""
    return code, offsets


GLSL_COMMON, PAL_OFFSETS = _glsl_common()

ASCII_VERT = """
void main() {
    vec2 v = vec2(gl_VertexID == 1 ? 3.0 : -1.0, gl_VertexID == 2 ? 3.0 : -1.0);
    gl_Position = vec4(v, 0.0, 1.0);
}
"""

BAYER_FRAG = """
uniform sampler2D u_frame;    // Szene: ein Pixel pro Dither-Zelle, row 0 = top
uniform vec2 u_origin;
uniform vec2 u_cell;          // Größe einer Dither-Zelle auf dem Schirm, Framebuffer-Pixel
uniform vec2 u_grid;          // cols, rows
uniform float u_fbh;
uniform float u_gamma;
uniform int u_mode;           // 0 rgb, 1 b/w, 2 phosphor, 3 palette
uniform vec3 u_phosphor;
uniform int u_order;          // 1,2,3 -> 2x2, 4x4, 8x8
uniform float u_spread;
uniform int u_pal_off;
uniform int u_pal_n;
out vec4 fragColor;
void main() {
    vec2 p = vec2(gl_FragCoord.x, u_fbh - gl_FragCoord.y) - u_origin;
    vec2 cf = p / u_cell;
    if (any(lessThan(cf, vec2(0.0))) || any(greaterThanEqual(cf, u_grid))) {
        fragColor = vec4(0.0, 0.0, 0.0, 1.0);
        return;
    }
    ivec2 cell = ivec2(floor(cf));
    vec3 c = texelFetch(u_frame, cell, 0).rgb;
    float t = bayer(cell, u_order);
    vec3 col;
    if (u_mode == 0) {
        col = step(vec3(t), pow(c, vec3(u_gamma)));
    } else if (u_mode == 3) {
        col = nearest_pal(clamp(c + (t - 0.5) * u_spread, 0.0, 1.0), u_pal_off, u_pal_n);
    } else {
        float lum = pow(dot(c, vec3(77.0, 151.0, 28.0) / 256.0), u_gamma);
        col = (u_mode == 1 ? vec3(1.0) : u_phosphor) * step(t, lum);
    }
    fragColor = vec4(col, 1.0);
}
"""

CRT_PERSIST_FRAG = """
uniform sampler2D u_cur;
uniform sampler2D u_prev;
uniform vec2 u_res;
uniform vec3 u_decay;
uniform float u_floor;
uniform float u_dtn;
uniform vec3 u_tint;
uniform float u_tint_mix;
out vec4 fragColor;
void main() {
    vec2 uv = gl_FragCoord.xy / u_res;
    vec3 c = texture(u_cur, uv).rgb;
    vec3 p = texture(u_prev, uv).rgb;
    float keep = pow(mix(0.8, 1.0, smoothstep(0.15, 0.7, max(max(p.r, p.g), p.b))), u_dtn);
    vec3 kept = p * u_decay * keep - u_floor;
    if (u_tint_mix > 0.0) kept = mix(kept, max(max(kept.r, kept.g), kept.b) * u_tint, u_tint_mix);
    fragColor = vec4(max(c, kept), 1.0);
}
"""

CRT_FOCUS_FRAG = """
uniform sampler2D u_src;
uniform vec2 u_res;
uniform vec2 u_dir;
uniform float u_sigma;
out vec4 fragColor;
void main() {
    vec2 uv = gl_FragCoord.xy / u_res;
    float s = max(u_sigma, 0.05);
    float tap = max(1.0, s * 0.5);
    vec3 acc = texture(u_src, uv).rgb;
    float wsum = 1.0;
    for (int i = 1; i <= 4; ++i) {
        float d = float(i) * tap;
        float w = exp(-0.5 * d * d / (s * s));
        acc += (texture(u_src, uv + u_dir * d).rgb + texture(u_src, uv - u_dir * d).rgb) * w;
        wsum += 2.0 * w;
    }
    fragColor = vec4(acc / wsum, 1.0);
}
"""

CRT_BLUR_FRAG = """
uniform sampler2D u_src;
uniform vec2 u_res;
uniform vec2 u_dir;
uniform int u_prep;
out vec4 fragColor;
const float W[7] = float[7](0.137023, 0.129618, 0.109719, 0.083109, 0.056332, 0.034167, 0.018544);
void main() {
    vec2 uv = gl_FragCoord.xy / u_res;
    vec3 acc = vec3(0.0);
    for (int i = -6; i <= 6; ++i) {
        vec3 s = texture(u_src, uv + u_dir * float(i)).rgb;
        if (u_prep == 1) s *= s;
        acc += s * W[i < 0 ? -i : i];
    }
    fragColor = vec4(acc, 1.0);
}
"""

CRT_FRAG = """
uniform sampler2D u_scene;
uniform sampler2D u_bloom;
uniform vec2 u_res;
uniform vec4 u_rect;
uniform float u_curve;
uniform float u_corner;
uniform float u_mask;
uniform float u_mask_px;
uniform float u_scan;
uniform float u_scan_period;
uniform float u_bloom_amt;
uniform float u_grain;
uniform float u_hum;
uniform float u_vignette;
uniform float u_aberr;
uniform float u_time;
uniform int u_seed;
out vec4 fragColor;

float hash(uvec2 v, uint t) {
    uint h = v.x * 1597334677u ^ v.y * 3812015801u ^ t * 2798796415u;
    h = h * 747796405u + 2891336453u;
    h = (h >> 16u) ^ h;
    h *= 0x7feb352du;
    h = (h >> 15u) ^ h;
    return float(h & 0x00ffffffu) / 16777216.0;
}

void main() {
    vec2 p = gl_FragCoord.xy;
    vec2 n = (p - u_rect.xy) / u_rect.zw * 2.0 - 1.0;
    vec2 ns = n * (1.0 + u_curve * vec2(n.y * n.y, n.x * n.x));
    vec2 d = (abs(ns) - 1.0) * u_rect.zw * 0.5 + u_corner;
    float dist = length(max(d, vec2(0.0))) + min(max(d.x, d.y), 0.0) - u_corner;
    float face = 1.0 - smoothstep(-0.75, 0.75, dist);
    if (face <= 0.0) { fragColor = vec4(0.0, 0.0, 0.0, 1.0); return; }
    vec2 src = u_rect.xy + (ns * 0.5 + 0.5) * u_rect.zw;
    vec2 uv = src / u_res;
    vec2 ab = ns * (0.25 + 0.75 * dot(ns, ns)) * u_aberr / u_res;
    vec3 col = vec3(texture(u_scene, uv + ab).r, texture(u_scene, uv).g, texture(u_scene, uv - ab).b);
    float lum = dot(col, vec3(0.299, 0.587, 0.114));
    float s = 0.5 + 0.5 * cos(6.2831853 * (src.y - u_rect.y) / u_scan_period);
    float scan = (1.0 - u_scan * (1.0 - s) * (1.0 - 0.6 * lum)) / (1.0 - 0.35 * u_scan);
    int stripe = int(mod(floor(p.x / u_mask_px), 3.0));
    vec3 sel = vec3(stripe == 0 ? 1.0 : 0.0, stripe == 1 ? 1.0 : 0.0, stripe == 2 ? 1.0 : 0.0);
    vec3 mask = mix(vec3(1.0), sel, u_mask) * (1.0 + 0.6 * u_mask);
    col = col * scan * mask + texture(u_bloom, uv).rgb * u_bloom_amt;
    float mx = max(col.r, max(col.g, col.b));
    if (mx > 1.0) col = mix(col / mx, vec3(1.0), clamp((mx - 1.0) * 0.6, 0.0, 1.0));
    col += (hash(uvec2(p), uint(u_seed)) - 0.5) * u_grain * (0.3 + lum);
    float bar = pow(0.5 + 0.5 * sin(6.2831853 * (ns.y * 0.5 + 0.5 + u_time * 0.12)), 6.0);
    col *= 1.0 - u_hum * bar;
    col *= 1.0 - u_vignette * 0.35 * dot(ns, ns);
    col += vec3(0.010, 0.011, 0.013) * (1.0 - 0.3 * dot(ns, ns));
    fragColor = vec4(col * face, 1.0);
}
"""

# CRT-Intensität "normal" (aus asciiplay CRT_LEVELS).
CRT_LEVEL = dict(curve=0.06, mask=0.22, scan=0.30, bloom=0.70, grain=0.035, hum=0.02,
                 vignette=0.40, aberr=2.0, blur=0.65, tau=(0.12, 0.18, 0.10))
