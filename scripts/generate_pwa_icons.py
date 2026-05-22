#!/usr/bin/env python3
"""Generate PWA icons for WealthEagle."""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

# WealthEagle brand colors
BG_COLOR = "#1a1a2e"  # Dark background
ACCENT_COLOR = "#4f46e5"  # Indigo accent
TEXT_COLOR = "#ffffff"  # White text

def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def create_icon(size, output_path):
    """Create a simple WealthEagle icon."""
    # Create image with dark background
    img = Image.new('RGB', (size, size), hex_to_rgb(BG_COLOR))
    draw = ImageDraw.Draw(img)

    # Draw eagle symbol (stylized W + E in a circle)
    margin = size // 8
    circle_bbox = [margin, margin, size - margin, size - margin]

    # Draw circle background
    draw.ellipse(circle_bbox, fill=hex_to_rgb(ACCENT_COLOR))

    # Draw "WE" monogram
    try:
        # Try to use a nice font if available
        font_size = size // 3
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except:
        # Fallback to default font
        font = ImageFont.load_default()

    text = "WE"
    # Get text bounding box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Center the text
    x = (size - text_width) // 2
    y = (size - text_height) // 2 - bbox[1]

    draw.text((x, y), text, fill=hex_to_rgb(TEXT_COLOR), font=font)

    # Save
    img.save(output_path, 'PNG')
    print(f"Created {output_path} ({size}x{size})")

def main():
    icons_dir = Path(__file__).parent.parent / "src" / "templates" / "assets" / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)

    # Generate required icon sizes
    create_icon(192, icons_dir / "icon-192.png")
    create_icon(512, icons_dir / "icon-512.png")
    create_icon(180, icons_dir / "apple-touch-icon.png")  # Apple requires 180x180
    create_icon(32, icons_dir / "favicon-32.png")
    create_icon(16, icons_dir / "favicon-16.png")

    print("\n✓ All PWA icons generated successfully!")

if __name__ == "__main__":
    main()
