"""GL-Compositor: Szenen-Textur -> Bayer-Dither -> CRT-Kette.

Die Szene kommt als fertiges RGB-Bytearray aus render/scene.py (CPU) herein, wird
als Textur hochgeladen und dann genau wie in `asciiplay` durch die Shader
geschickt. Kein mpv, keine Fremd-Dependencies: nur PyQt6-OpenGL.
"""

import ctypes
import math
import time

from PyQt6.QtGui import QImage, QVector2D, QVector3D, QVector4D
from PyQt6.QtOpenGL import (QOpenGLFramebufferObject, QOpenGLShader,
                            QOpenGLShaderProgram, QOpenGLTexture,
                            QOpenGLVertexArrayObject)

from .. import config
from . import shaders

GL_TRIANGLES = 0x0004
GL_DEPTH_TEST = 0x0B71
GL_CULL_FACE = 0x0B44
GL_BLEND = 0x0BE2
GL_SCISSOR_TEST = 0x0C11
GL_TEXTURE_2D = 0x0DE1
GL_COLOR_BUFFER_BIT = 0x4000
GL_TEXTURE0 = 0x84C0
GL_TEXTURE1 = 0x84C1
GL_FRAMEBUFFER = 0x8D40
GL_TEXTURE_MIN_FILTER = 0x2801
GL_TEXTURE_MAG_FILTER = 0x2800
GL_TEXTURE_WRAP_S = 0x2802
GL_TEXTURE_WRAP_T = 0x2803
GL_CLAMP_TO_EDGE = 0x812F

_CRT_BLUR_HALF_PX = 1.5
_CRT_BLUR_ASPECT = 0.7


class GLFuncs:
    """Die wenigen rohen GL-Einstiegspunkte, die wir selbst aufrufen."""

    def __init__(self, ctx):
        self._ctx = ctx
        c = ctypes
        self.BindFramebuffer = self._load("glBindFramebuffer", None, c.c_uint, c.c_uint)
        self.Viewport = self._load("glViewport", None, c.c_int, c.c_int, c.c_int, c.c_int)
        self.ClearColor = self._load("glClearColor", None, c.c_float, c.c_float, c.c_float, c.c_float)
        self.Clear = self._load("glClear", None, c.c_uint)
        self.Disable = self._load("glDisable", None, c.c_uint)
        self.DrawArrays = self._load("glDrawArrays", None, c.c_uint, c.c_int, c.c_int)
        self.ActiveTexture = self._load("glActiveTexture", None, c.c_uint)
        self.BindTexture = self._load("glBindTexture", None, c.c_uint, c.c_uint)
        self.TexParameteri = self._load("glTexParameteri", None, c.c_uint, c.c_uint, c.c_int)

    def proc_address(self, name):
        try:
            return int(self._ctx.getProcAddress(bytes(name)))
        except Exception:
            return 0

    def _load(self, name, restype, *argtypes):
        addr = self.proc_address(name.encode())
        if not addr:
            raise RuntimeError(f"OpenGL entry point {name} not available")
        return ctypes.CFUNCTYPE(restype, *argtypes)(addr)


class CRTRenderer:
    """Baut die Programme/FBOs und rendert ein Szenen-Bytearray auf ein Ziel-FBO."""

    def __init__(self, gl):
        self.gl = gl
        self._textures = {}
        self.force_dt = None      # Tools: feste Frame-Zeit statt Wanduhr (Nachleuchten)
        self.scan_on = True       # Scanlines + Schattenmaske (Einstellung)
        self._size = None
        self._vao = None
        self._last_t = None
        self._crt_t0 = time.monotonic()
        self._seed = 0
        self._build()

    # ------------------------------------------------------------------ Setup
    def _header(self):
        return "#version 130\n"   # texelFetch / gl_VertexID brauchen GL 3.0

    def _compile(self, frag, uniforms, samplers=()):
        header = self._header()
        prog = QOpenGLShaderProgram()
        if not prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Vertex, header + shaders.ASCII_VERT):
            raise RuntimeError("vertex shader: " + prog.log())
        if not prog.addShaderFromSourceCode(QOpenGLShader.ShaderTypeBit.Fragment, header + frag):
            raise RuntimeError("fragment shader: " + prog.log())
        if not prog.link():
            raise RuntimeError("link: " + prog.log())
        u = {name: prog.uniformLocation(name) for name in uniforms}
        if samplers:
            prog.bind()
            for name, unit in samplers:
                prog.setUniformValue(prog.uniformLocation(name), unit)
            prog.release()
        return prog, u

    def _build(self):
        common = shaders.GLSL_COMMON
        self._progs = {
            "bayer": self._compile(common + shaders.BAYER_FRAG, (
                "u_origin", "u_cell", "u_grid", "u_fbh", "u_gamma", "u_mode", "u_phosphor",
                "u_order", "u_spread", "u_pal_off", "u_pal_n", "u_hud_scale", "u_has_hud",
                "u_contrast", "u_sat", "u_lift"),
                (("u_frame", 0), ("u_hud", 1))),
            "persist": self._compile(shaders.CRT_PERSIST_FRAG, (
                "u_res", "u_decay", "u_floor", "u_dtn", "u_tint", "u_tint_mix"),
                (("u_cur", 0), ("u_prev", 1))),
            "focus": self._compile(shaders.CRT_FOCUS_FRAG, ("u_res", "u_dir", "u_sigma"), (("u_src", 0),)),
            "blur": self._compile(shaders.CRT_BLUR_FRAG, ("u_res", "u_dir", "u_prep"), (("u_src", 0),)),
            "crt": self._compile(shaders.CRT_FRAG, (
                "u_res", "u_rect", "u_curve", "u_corner", "u_mask", "u_mask_px", "u_scan",
                "u_scan_period", "u_bloom_amt", "u_grain", "u_hum", "u_vignette", "u_aberr",
                "u_time", "u_seed"), (("u_scene", 0), ("u_bloom", 1))),
        }
        vao = QOpenGLVertexArrayObject()
        self._vao = vao if vao.create() else None

    def _make_fbo(self, gl, w, h):
        f = QOpenGLFramebufferObject(w, h)
        gl.ActiveTexture(GL_TEXTURE0)
        gl.BindTexture(GL_TEXTURE_2D, f.texture())
        for pname, val in ((GL_TEXTURE_MIN_FILTER, 0x2601),   # GL_LINEAR
                           (GL_TEXTURE_MAG_FILTER, 0x2601),
                           (GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE),
                           (GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)):
            gl.TexParameteri(GL_TEXTURE_2D, pname, val)
        gl.BindTexture(GL_TEXTURE_2D, 0)
        gl.BindFramebuffer(GL_FRAMEBUFFER, f.handle())
        gl.Viewport(0, 0, w, h)
        gl.ClearColor(0.0, 0.0, 0.0, 1.0)
        gl.Clear(GL_COLOR_BUFFER_BIT)
        return f

    def _ensure(self, fw, fh):
        if self._size == (fw, fh) and self._scene_fbo is not None:
            return
        gl = self.gl
        self._scene_fbo = self._make_fbo(gl, fw, fh)
        self._persist = [self._make_fbo(gl, fw, fh), self._make_fbo(gl, fw, fh)]
        self._focus = [self._make_fbo(gl, fw, fh), self._make_fbo(gl, fw, fh)]
        bw, bh = max(1, (fw + 1) // 2), max(1, (fh + 1) // 2)
        self._focus_half = [self._make_fbo(gl, bw, bh), self._make_fbo(gl, bw, bh)]
        self._bloom = [self._make_fbo(gl, bw, bh), self._make_fbo(gl, bw, bh)]
        self._size = (fw, fh)
        self._persist_ix = 0
        self._persist_stale = True
        self._last_t = None

    def _tri(self):
        if self._vao is not None:
            self._vao.bind()
        self.gl.DrawArrays(GL_TRIANGLES, 0, 3)
        if self._vao is not None:
            self._vao.release()

    def _run_pass(self, target, w, h, textures):
        gl = self.gl
        gl.BindFramebuffer(GL_FRAMEBUFFER, target)
        gl.Viewport(0, 0, w, h)
        for unit, tex in enumerate(textures):
            gl.ActiveTexture(GL_TEXTURE0 + unit)
            gl.BindTexture(GL_TEXTURE_2D, tex)
        self._tri()

    def _upload(self, slot, img):
        """QImage (RGB32/ARGB32_Premultiplied) als BGRA-Textur hochladen, Speicher wiederverwenden."""
        if img.format() not in (QImage.Format.Format_RGB32, QImage.Format.Format_ARGB32_Premultiplied):
            img = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        size = (img.width(), img.height())
        tex, tsize = self._textures.get(slot, (None, None))
        if tex is None or tsize != size:
            if tex is not None:
                tex.destroy()
            tex = QOpenGLTexture(QOpenGLTexture.Target.Target2D)
            tex.setFormat(QOpenGLTexture.TextureFormat.RGBA8_UNorm)
            tex.setSize(size[0], size[1])
            tex.setMinificationFilter(QOpenGLTexture.Filter.Nearest)
            tex.setMagnificationFilter(QOpenGLTexture.Filter.Nearest)
            tex.setWrapMode(QOpenGLTexture.WrapMode.ClampToEdge)
            tex.allocateStorage(QOpenGLTexture.PixelFormat.BGRA, QOpenGLTexture.PixelType.UInt8)
            self._textures[slot] = (tex, size)
        tex.setData(QOpenGLTexture.PixelFormat.BGRA, QOpenGLTexture.PixelType.UInt8, img.constBits())
        return tex.textureId()

    def _scene_texture(self, scene, vc, vr):
        if not isinstance(scene, QImage):   # Altpfad: RGB-Bytearray
            scene = QImage(bytes(scene), vc, vr, vc * 3, QImage.Format.Format_RGB888)
        return self._upload("scene", scene)

    # ------------------------------------------------------------------ Render
    def render(self, target, fw, fh, scene_buf, vc, vr, gamma=0.9, dt=0.016, dpr=1.0, level=None, hud=None):
        gl = self.gl
        level = level or shaders.CRT_LEVEL
        self._ensure(fw, fh)
        tex = self._scene_texture(scene_buf, vc, vr)
        hud_tex = self._upload("hud", hud) if hud is not None else 0

        cell = min(fw / vc, fh / vr)
        pw, ph = vc * cell, vr * cell
        ox, oy = (fw - pw) / 2.0, (fh - ph) / 2.0

        # 1. Bayer-Dither: Szene -> self._scene_fbo (bildschirmfüllend)
        gl.BindFramebuffer(GL_FRAMEBUFFER, self._scene_fbo.handle())
        gl.Viewport(0, 0, fw, fh)
        gl.ClearColor(0.0, 0.0, 0.0, 1.0)
        gl.Clear(GL_COLOR_BUFFER_BIT)
        for cap in (GL_BLEND, GL_SCISSOR_TEST, GL_DEPTH_TEST, GL_CULL_FACE):
            gl.Disable(cap)
        prog, u = self._progs["bayer"]
        prog.bind()
        prog.setUniformValue(u["u_origin"], QVector2D(float(ox), float(oy)))
        prog.setUniformValue(u["u_cell"], QVector2D(float(cell), float(cell)))
        prog.setUniformValue(u["u_grid"], QVector2D(float(vc), float(vr)))
        prog.setUniformValue(u["u_fbh"], float(fh))
        prog.setUniformValue(u["u_gamma"], float(gamma))
        prog.setUniformValue(u["u_mode"], 3)
        prog.setUniformValue(u["u_order"], 3)
        prog.setUniformValue(u["u_spread"], float(config.DITHER_SPREAD))
        pal = config.ACTIVE["palette"]
        prog.setUniformValue(u["u_pal_off"], shaders.PAL_OFFSETS[pal])
        prog.setUniformValue(u["u_pal_n"], len(config.PALETTES[pal]))
        prog.setUniformValue(u["u_phosphor"], QVector3D(0.0, 0.0, 0.0))
        prog.setUniformValue(u["u_has_hud"], 1 if hud is not None else 0)
        prog.setUniformValue(u["u_contrast"], float(config.GRADE_CONTRAST))
        prog.setUniformValue(u["u_sat"], float(config.GRADE_SATURATION))
        prog.setUniformValue(u["u_lift"], float(config.GRADE_LIFT))
        prog.setUniformValue(u["u_hud_scale"], float(hud.width() / vc) if hud is not None else 1.0)
        gl.ActiveTexture(GL_TEXTURE1)
        gl.BindTexture(GL_TEXTURE_2D, hud_tex)
        gl.ActiveTexture(GL_TEXTURE0)
        gl.BindTexture(GL_TEXTURE_2D, tex)
        self._tri()
        prog.release()

        rect = (ox, fh - oy - ph, pw, ph)
        self._crt(gl, target, fw, fh, rect, cell, dt, dpr, level)
        gl.ActiveTexture(GL_TEXTURE1)
        gl.BindTexture(GL_TEXTURE_2D, 0)
        gl.ActiveTexture(GL_TEXTURE0)
        gl.BindTexture(GL_TEXTURE_2D, 0)

    def _crt(self, gl, fbo, fw, fh, rect, cell_y, dt, dpr, lvl):
        now = time.monotonic()
        dt = 0.0 if self._last_t is None else min(0.1, max(0.0, now - self._last_t))
        if self.force_dt is not None:
            dt = self.force_dt
        self._last_t = now
        self._seed = (self._seed + 1) & 0xFFFF

        # 1. Phosphor-Nachleuchten (ping-pong)
        tau_scale = 1.0
        prev, cur = self._persist[self._persist_ix], self._persist[1 - self._persist_ix]
        self._persist_ix = 1 - self._persist_ix
        if self._persist_stale:
            gl.BindFramebuffer(GL_FRAMEBUFFER, prev.handle())
            gl.Viewport(0, 0, fw, fh)
            gl.ClearColor(0.0, 0.0, 0.0, 1.0)
            gl.Clear(GL_COLOR_BUFFER_BIT)
        prog, u = self._progs["persist"]
        prog.bind()
        prog.setUniformValue(u["u_res"], QVector2D(float(fw), float(fh)))
        prog.setUniformValue(u["u_decay"], QVector3D(*(math.exp(-dt / (t * tau_scale)) for t in lvl["tau"])))
        prog.setUniformValue(u["u_floor"], float(dt * 0.5))
        prog.setUniformValue(u["u_dtn"], float(dt * 60.0))
        prog.setUniformValue(u["u_tint"], QVector3D(0.0, 0.0, 0.0))
        prog.setUniformValue(u["u_tint_mix"], 0.0)
        self._run_pass(cur.handle(), fw, fh, (self._scene_fbo.texture(), prev.texture()))
        prog.release()
        self._persist_stale = False
        lit = cur.texture()

        # 2. Fokus-Blur (H, dann V)
        # An die Dither-Zellgröße koppeln statt an dpr: dann wirkt CRT gleich stark,
        # egal ob 720p oder 4K (cell = Framebuffer-Pixel pro Dither-Pixel). Referenz 720p -> cell 2.
        s = max(0.5, cell_y * 0.5)
        sigma = lvl["blur"] * s
        if sigma > 0.02:
            half = sigma > _CRT_BLUR_HALF_PX * dpr
            buf = self._focus_half if half else self._focus
            tw, th = buf[0].width(), buf[0].height()
            s_px = sigma * 0.5 if half else sigma
            prog, u = self._progs["focus"]
            prog.bind()
            prog.setUniformValue(u["u_res"], QVector2D(float(tw), float(th)))
            prog.setUniformValue(u["u_dir"], QVector2D(1.0 / tw, 0.0))
            prog.setUniformValue(u["u_sigma"], float(s_px))
            self._run_pass(buf[0].handle(), tw, th, (lit,))
            prog.setUniformValue(u["u_dir"], QVector2D(0.0, 1.0 / th))
            prog.setUniformValue(u["u_sigma"], float(s_px * _CRT_BLUR_ASPECT))
            self._run_pass(buf[1].handle(), tw, th, (buf[0].texture(),))
            prog.release()
            lit = buf[1].texture()

        # 3. Bloom (halb, H + V)
        bw, bh = self._bloom[0].width(), self._bloom[0].height()
        prog, u = self._progs["blur"]
        prog.bind()
        prog.setUniformValue(u["u_res"], QVector2D(float(bw), float(bh)))
        prog.setUniformValue(u["u_dir"], QVector2D(2.0 * dpr / fw, 0.0))
        prog.setUniformValue(u["u_prep"], 1)
        self._run_pass(self._bloom[0].handle(), bw, bh, (lit,))
        prog.setUniformValue(u["u_dir"], QVector2D(0.0, dpr / bh))
        prog.setUniformValue(u["u_prep"], 0)
        self._run_pass(self._bloom[1].handle(), bw, bh, (self._bloom[0].texture(),))
        prog.release()

        # 4. Röhre
        scan_period = cell_y * max(1, int(round(3.0 * dpr / cell_y)))
        prog, u = self._progs["crt"]
        prog.bind()
        prog.setUniformValue(u["u_res"], QVector2D(float(fw), float(fh)))
        prog.setUniformValue(u["u_rect"], QVector4D(*(float(v) for v in rect)))
        prog.setUniformValue(u["u_curve"], float(lvl["curve"]))
        prog.setUniformValue(u["u_corner"], float(0.035 * min(rect[2], rect[3])))
        so = 1.0 if self.scan_on else 0.0
        prog.setUniformValue(u["u_mask"], float(lvl["mask"] * so))
        prog.setUniformValue(u["u_mask_px"], float(max(1, round(dpr))))
        prog.setUniformValue(u["u_scan"], float(lvl["scan"] * so))
        prog.setUniformValue(u["u_scan_period"], float(scan_period))
        prog.setUniformValue(u["u_bloom_amt"], float(lvl["bloom"]))
        prog.setUniformValue(u["u_grain"], float(lvl["grain"]))
        prog.setUniformValue(u["u_hum"], float(lvl["hum"]))
        prog.setUniformValue(u["u_vignette"], float(lvl["vignette"]))
        prog.setUniformValue(u["u_aberr"], float(lvl["aberr"] * s))
        prog.setUniformValue(u["u_time"], float((now - self._crt_t0) % 3600.0))
        prog.setUniformValue(u["u_seed"], int(self._seed))
        self._run_pass(fbo, fw, fh, (lit, self._bloom[1].texture()))
        prog.release()
