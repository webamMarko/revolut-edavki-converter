#!/usr/bin/env python3
"""Apply the WealthEagle logo to all PWA icons and favicons."""

from PIL import Image
from pathlib import Path
import sys

def create_icon_from_logo(logo_path, size, output_path, padding_ratio=0.1):
    """
    Create an icon from the logo by resizing and adding padding.

    Args:
        logo_path: Path to the source logo image
        size: Target size for the output icon
        output_path: Where to save the generated icon
        padding_ratio: Ratio of padding to add around the logo (0.1 = 10%)
    """
    # Load the logo
    logo = Image.open(logo_path)

    # Convert to RGBA if not already
    if logo.mode != 'RGBA':
        logo = logo.convert('RGBA')

    # Calculate the size with padding
    padding = int(size * padding_ratio)
    logo_size = size - (2 * padding)

    # Resize logo to fit within the target size (maintaining aspect ratio)
    logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)

    # Create a new image with transparent or white background
    icon = Image.new('RGBA', (size, size), (255, 255, 255, 0))

    # Calculate position to center the logo
    x = (size - logo.width) // 2
    y = (size - logo.height) // 2

    # Paste the logo onto the icon
    icon.paste(logo, (x, y), logo if logo.mode == 'RGBA' else None)

    # Save as PNG
    icon.save(output_path, 'PNG')
    print(f"✓ Created {output_path.name} ({size}x{size})")

def create_favicon_ico(logo_path, output_path):
    """Create a multi-resolution .ico favicon."""
    logo = Image.open(logo_path)
    if logo.mode != 'RGBA':
        logo = logo.convert('RGBA')

    # Create multiple sizes for the .ico
    sizes = [(16, 16), (32, 32), (48, 48)]
    icons = []

    for size in sizes:
        icon = Image.new('RGBA', size, (255, 255, 255, 0))
        temp_logo = logo.copy()
        temp_logo.thumbnail(size, Image.Resampling.LANCZOS)
        x = (size[0] - temp_logo.width) // 2
        y = (size[1] - temp_logo.height) // 2
        icon.paste(temp_logo, (x, y), temp_logo)
        icons.append(icon)

    # Save as .ico
    icons[0].save(output_path, format='ICO', sizes=[s for s in sizes])
    print(f"✓ Created {output_path.name} (multi-resolution .ico)")

def main():
    # Paths
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    logo_path = project_root / "logo-original.jpeg"
    icons_dir = project_root / "src" / "templates" / "assets" / "icons"

    # Verify logo exists
    if not logo_path.exists():
        print(f"❌ Logo not found at {logo_path}")
        print("Please ensure logo-original.jpeg is in the project root.")
        sys.exit(1)

    # Create icons directory if it doesn't exist
    icons_dir.mkdir(parents=True, exist_ok=True)

    print("Generating PWA icons from WealthEagle logo...\n")

    # Generate required icon sizes
    create_icon_from_logo(logo_path, 16, icons_dir / "favicon-16.png", padding_ratio=0.05)
    create_icon_from_logo(logo_path, 32, icons_dir / "favicon-32.png", padding_ratio=0.05)
    create_icon_from_logo(logo_path, 180, icons_dir / "apple-touch-icon.png", padding_ratio=0.1)
    create_icon_from_logo(logo_path, 192, icons_dir / "icon-192.png", padding_ratio=0.1)
    create_icon_from_logo(logo_path, 512, icons_dir / "icon-512.png", padding_ratio=0.1)

    # Create favicon.ico
    create_favicon_ico(logo_path, icons_dir / "favicon.ico")

    # Also save a copy of the original logo as PNG for use in templates
    logo_png_path = project_root / "src" / "templates" / "assets" / "logo.png"
    logo = Image.open(logo_path)
    if logo.mode != 'RGBA':
        logo = logo.convert('RGBA')
    logo.save(logo_png_path, 'PNG')
    print(f"✓ Created {logo_png_path.name} (full logo for templates)")

    print("\n✅ All icons generated successfully!")
    print("\nGenerated files:")
    print("  - favicon-16.png (16x16)")
    print("  - favicon-32.png (32x32)")
    print("  - favicon.ico (multi-resolution)")
    print("  - apple-touch-icon.png (180x180)")
    print("  - icon-192.png (192x192)")
    print("  - icon-512.png (512x512)")
    print("  - logo.png (full resolution)")

if __name__ == "__main__":
    main()
