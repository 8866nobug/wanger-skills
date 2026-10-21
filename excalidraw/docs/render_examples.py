"""生成 README 用的示例 .excalidraw.md / .excalidraw / SVG / PNG。

用法：
    python docs/render_examples.py            # 生成 SVG，并尝试生成 PNG
    python docs/render_examples.py --no-png   # 只生成 SVG

样例 spec 位于 examples/*.json；PNG 由本机 Chrome/Edge 无头模式把 SVG 截图得到。
没有浏览器时会跳过 PNG，已提交的 PNG 仍可直接用于 README。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from excalidraw import builder, cli, models, styles, validator, writer  # noqa: E402
import preview_render  # noqa: E402

EXAMPLES = ROOT / "examples"
IMAGES = ROOT / "docs" / "images"

# spec 文件 -> 输出名
SAMPLES = [
    ("flow.json", "flow"),
    ("uml-classes.json", "uml-classes"),
    ("er-shop.json", "er-shop"),
    ("er-domains.json", "er-domains"),
    ("chen-orders.json", "chen-orders"),
]

STYLE_PANELS = [
    ("clean", "clean · 默认印刷体"),
    ("hand", "hand · 手绘白板"),
    ("mono", "mono · 灰度打印"),
    ("night", "night · 深色演示"),
]


def build_obj(spec: dict, style: str | None = None):
    diagram = cli.diagram_from_spec(spec)
    obj = builder.build_diagram(diagram, style=style)
    doc = models.Document(elements=obj["elements"], app_state=obj["appState"],
                          files=obj["files"], source=obj["source"])
    issues = validator.validate_document(doc)
    if validator.has_errors(issues):
        raise SystemExit(f"校验失败：\n{validator.format_issues(issues)}")
    for issue in issues:
        print(f"  [{issue['level']}] {issue['code']}: {issue['message']}")
    return obj, doc


def write_md(path: Path, obj: dict) -> None:
    writer.write_document(
        str(path), obj["elements"], obj["appState"], files=obj["files"],
        source=obj["source"], backup_file=False)
    print(f"  wrote {path.relative_to(ROOT)}")


def write_plain(path: Path, obj: dict) -> None:
    writer.write_excalidraw(
        str(path), obj["elements"], obj["appState"], files=obj["files"],
        source=styles.STANDALONE_SOURCE, backup_file=False)
    print(f"  wrote {path.relative_to(ROOT)}")


def find_browser():
    candidates = [
        shutil.which("msedge"),
        shutil.which("chrome"),
        shutil.which("google-chrome"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return path
    return None


def svg_to_png(browser: str | None, svg: Path, png: Path,
               width: float, height: float, scale: int = 2) -> None:
    if not browser:
        return
    w, h = max(1, int(round(width))), max(1, int(round(height)))
    cmd = [
        browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        f"--force-device-scale-factor={scale}",
        f"--window-size={w},{h}", f"--screenshot={png}", svg.as_uri(),
    ]
    subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=120)
    if png.exists():
        print(f"  wrote {png.relative_to(ROOT)}")


def render_gallery(browser: str | None, scale: int = 2) -> None:
    spec = json.loads((EXAMPLES / "style-gallery.json").read_text(encoding="utf-8"))
    panels = []
    for style, caption in STYLE_PANELS:
        _obj, doc = build_obj(spec, style=style)
        inner, w, h, bg = preview_render.render_content(doc)
        panels.append((style, caption, inner, w, h, bg))

    panel_w = 320.0
    gap, margin, caption_h = 24.0, 36.0, 46.0
    panel_h = max(panel_w * h / w for _s, _c, _i, w, h, _b in panels)
    gw = margin * 2 + panel_w * len(panels) + gap * (len(panels) - 1)
    gh = margin * 2 + panel_h + caption_h
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{gw:.0f}" '
        f'height="{gh:.0f}" viewBox="0 0 {gw:.0f} {gh:.0f}">',
        f'<rect width="{gw:.0f}" height="{gh:.0f}" fill="#f5f7fa"/>',
    ]
    for i, (_style, caption, inner, w, h, bg) in enumerate(panels):
        x = margin + i * (panel_w + gap)
        y = margin
        ph = panel_w * h / w
        out.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{panel_w:.1f}" '
            f'height="{ph:.1f}" rx="14" fill="{bg}" stroke="#ced4da" '
            f'stroke-width="1"/>')
        out.append(
            f'<svg x="{x:.1f}" y="{y:.1f}" width="{panel_w:.1f}" '
            f'height="{ph:.1f}" viewBox="0 0 {w:.0f} {h:.0f}">')
        out.extend(inner)
        out.append("</svg>")
        out.append(
            f'<text x="{x + panel_w / 2:.1f}" y="{y + ph + 28:.1f}" '
            f'text-anchor="middle" fill="#343a40" '
            f'font-family="Arial, \'Microsoft YaHei\', sans-serif" '
            f'font-size="18" font-weight="600">{caption}</text>')
    out.append("</svg>")
    svg = IMAGES / "styles.svg"
    svg.write_text("\n".join(out), encoding="utf-8")
    print(f"  wrote {svg.relative_to(ROOT)}")
    svg_to_png(browser, svg, IMAGES / "styles.png", gw, gh, scale=scale)


def main() -> int:
    EXAMPLES.mkdir(exist_ok=True)
    IMAGES.mkdir(parents=True, exist_ok=True)
    browser = None if "--no-png" in sys.argv else find_browser()
    if not browser and "--no-png" not in sys.argv:
        print("未找到 Chrome/Edge，跳过 PNG（SVG 已生成）")

    for spec_name, out_name in SAMPLES:
        print(f"[{out_name}]")
        spec = json.loads((EXAMPLES / spec_name).read_text(encoding="utf-8"))
        obj, doc = build_obj(spec)
        write_md(EXAMPLES / f"{out_name}.excalidraw.md", obj)
        write_plain(EXAMPLES / f"{out_name}.excalidraw", obj)
        svg_text, w, h = preview_render.render_svg(doc)
        svg = IMAGES / f"{out_name}.svg"
        svg.write_text(svg_text, encoding="utf-8")
        print(f"  wrote {svg.relative_to(ROOT)} ({w:.0f}x{h:.0f})")
        svg_to_png(browser, svg, IMAGES / f"{out_name}.png", w, h, scale=2)

    print("[styles]")
    render_gallery(browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
