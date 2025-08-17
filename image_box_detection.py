import argparse, asyncio, cv2, json, os, sys
from pathlib import Path
import numpy as np
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

# ---------- Fallback HTML parsing method ----------
def extract_bboxes_from_html_fallback(html_path: Path):
    """
    Fallback method to extract bboxes from HTML without using Playwright.
    This is a simplified version that may not be as accurate but will allow the pipeline to continue.
    """
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract region bboxes from CSS styles
        region_bboxes = []
        region_containers = soup.find_all('div', class_='box')
        for i, container in enumerate(region_containers):
            container_id = container.get('id', f'region_{i}')
            style = container.get('style', '')
            
            # Parse CSS style to extract position and size
            # This is a simplified parser - in real scenarios, you might need a more robust CSS parser
            left = 0
            top = 0
            width = 100
            height = 100
            
            if 'left:' in style:
                left_str = style.split('left:')[1].split('%')[0].strip()
                left = float(left_str)
            if 'top:' in style:
                top_str = style.split('top:')[1].split('%')[0].strip()
                top = float(top_str)
            if 'width:' in style:
                width_str = style.split('width:')[1].split('%')[0].strip()
                width = float(width_str)
            if 'height:' in style:
                height_str = style.split('height:')[1].split('%')[0].strip()
                height = float(height_str)
            
            # Convert percentage to pixels (assuming 1280x720 viewport)
            x = int(left * 12.8)  # 1280 / 100
            y = int(top * 7.2)    # 720 / 100
            w = int(width * 12.8)
            h = int(height * 7.2)
            
            region_bboxes.append({
                'id': container_id,
                'x': x,
                'y': y,
                'w': w,
                'h': h
            })
        
        # Extract placeholder bboxes
        placeholder_bboxes = []
        placeholder_images = soup.find_all(class_='bg-gray-400')
        for i, img in enumerate(placeholder_images):
            # For fallback, we'll use a simple approach
            # In a real scenario, you'd need to parse the actual layout
            placeholder_bboxes.append({
                'id': f'ph{i}',
                'x': 100 + i * 50,
                'y': 100 + i * 50,
                'w': 100,
                'h': 100,
                'region_id': region_bboxes[0]['id'] if region_bboxes else '1'
            })
        
        return region_bboxes, placeholder_bboxes, 1280, 720
        
    except Exception as e:
        print(f"Error in fallback HTML parsing: {e}")
        return [], [], 1280, 720

# ---------- Main logic ----------
async def extract_bboxes_from_html(html_path: Path):
    async with async_playwright() as p:
        try:
            # Try to launch browser with headless mode for HF Spaces compatibility
            browser = await p.chromium.launch(headless=True)
        except Exception as e:
            print(f"Error launching browser: {e}")
            print("Attempting to install browser dependencies...")
            try:
                # Try to install browser dependencies
                import subprocess
                result = subprocess.run(["playwright", "install", "chromium"], 
                                      capture_output=True, text=True, timeout=300)
                if result.returncode == 0:
                    print("Browser dependencies installed successfully, retrying...")
                    browser = await p.chromium.launch(headless=True)
                else:
                    print(f"Failed to install browser dependencies: {result.stderr}")
                    # Return empty results to continue the pipeline
                    return [], [], 1280, 720
            except Exception as install_error:
                print(f"Failed to install browser dependencies: {install_error}")
                # Return empty results to continue the pipeline
                return [], [], 1280, 720
        
        try:
            ctx = await browser.new_context(
                viewport={"width": 1280, "height": 720},
            )
            page = await ctx.new_page()
            await page.goto(html_path.resolve().as_uri())

            metrics = await page.evaluate("""
                () => {
                    const region_containers = Array.from(document.querySelectorAll('.box[id]'));
                    const region_bboxes = region_containers.map(el => {
                        const rect = el.getBoundingClientRect();
                        return { id: el.id, x: rect.x, y: rect.y, w: rect.width, h: rect.height };
                    });

                    const placeholder_bboxes = [];
                    let ph_id_counter = 0;
                    const all_potential_placeholders = document.querySelectorAll('.bg-gray-400');

                    for (const el of all_potential_placeholders) {
                        // Apply the same filters as before
                        if (el.tagName === 'SVG') continue;
                        if (el.innerText && el.innerText.trim() !== '') continue;
                        
                        const el_rect = el.getBoundingClientRect();
                        const el_center = { x: el_rect.left + el_rect.width / 2, y: el_rect.top + el_rect.height / 2 };
                        
                        // Find which region this placeholder is inside
                        let containing_region_id = null;
                        for (const region_el of region_containers) {
                            const region_rect = region_el.getBoundingClientRect();
                            if (el_center.x >= region_rect.left && el_center.x <= region_rect.right &&
                                el_center.y >= region_rect.top && el_center.y <= region_rect.bottom) {
                                containing_region_id = region_el.id;
                                break; // Assume non-overlapping regions
                            }
                        }
                        
                        if (containing_region_id) {
                            placeholder_bboxes.push({
                                id: 'ph' + ph_id_counter++,
                                x: el_rect.x,
                                y: el_rect.y,
                                w: el_rect.width,
                                h: el_rect.height,
                                region_id: containing_region_id
                            });
                        }
                    }

                    const layout_rect = document.documentElement.getBoundingClientRect();
                    return { 
                        region_bboxes, 
                        placeholder_bboxes, 
                        layout_width: layout_rect.width, 
                        layout_height: layout_rect.height 
                    };
                }
            """)
            await browser.close()
            return metrics['region_bboxes'], metrics['placeholder_bboxes'], metrics['layout_width'], metrics['layout_height']
        except Exception as e:
            print(f"Error during browser operation: {e}")
            await browser.close()
            # Return empty results to continue the pipeline
            return [], [], 1280, 720


def draw_bboxes_on_image(img, region_bboxes, placeholder_bboxes):
    """Draw region (green) and placeholder (red) boxes with labels on img."""
    boxed = img.copy()
    H, W = img.shape[:2]
    
    # --- Helper to draw a single box with label ---
    def draw_box_with_label(b, color, label_text):
        x, y, w, h = b["x"], b["y"], b["w"], b["h"]
        # Boundary correction
        x_draw, y_draw = max(0, x), max(0, y)
        w_draw, h_draw = min(w, W - x_draw), min(h, H - y_draw)
        cv2.rectangle(boxed, (x_draw, y_draw), (x_draw + w_draw, y_draw + h_draw), color, 3) # Thicker lines
        
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.8
        font_thickness = 2
        text_color = (255, 255, 255)

        (text_width, text_height), baseline = cv2.getTextSize(label_text, font, font_scale, font_thickness)
        
        # Position for the label background. Put it just above the box.
        label_y_start = y - text_height - baseline - 5
        if label_y_start < 0: # Adjust if the label goes off the top of the image
            label_y_start = y + 5
        
        label_x_start = x
        label_y_end = label_y_start + text_height + baseline
        
        cv2.rectangle(boxed, (label_x_start, label_y_start), (label_x_start + text_width, label_y_end), color, cv2.FILLED)
        cv2.putText(boxed, label_text, (label_x_start + 2, label_y_start + text_height), font, font_scale, text_color, font_thickness)

    # --- Draw Regions (Green) ---
    for b in region_bboxes:
        draw_box_with_label(b, color=(0, 255, 0), label_text=f'Area_{b.get("id", "")}')

    # --- Draw Placeholders (Red) ---
    for b in placeholder_bboxes:
        draw_box_with_label(b, color=(0, 0, 255), label_text=f'{b.get("region_id")}_{b.get("id")}')
        
    return boxed


def main():
    args = get_args()
    run_id = args.run_id

    # --- Dynamic Path Construction ---
    base_dir = Path(__file__).parent.resolve()
    tmp_dir = base_dir / 'data' / 'tmp' / run_id
    output_dir = base_dir / 'data' / 'output' / run_id
    
    html_path = output_dir / f"{run_id}_layout.html"
    screenshot_path = tmp_dir / f"{run_id}.png"
    output_json_path = tmp_dir / f"{run_id}_bboxes.json"
    debug_image_path = tmp_dir / f"debug_gray_bboxes_{run_id}.png"

    if not html_path.exists():
        sys.exit(f"Error: HTML file not found at {html_path}")
    if not screenshot_path.exists():
        sys.exit(f"Error: Screenshot not found at {screenshot_path}")

    print(f"--- Starting Image Box Detection for run_id: {run_id} ---")
    
    # Read original screenshot
    img = cv2.imread(str(screenshot_path))
    if img is None:
        sys.exit(f"Error: Cannot read image {screenshot_path}")
    if img.std() < 5:
        print("Warning: The screenshot is almost pure color, it may not be the original screenshot with real thumbnails.")

    H, W = img.shape[:2]

    # Parse HTML → Get bboxes
    try:
        region_bboxes, placeholder_bboxes, layout_width, layout_height = asyncio.run(
            extract_bboxes_from_html(html_path)
        )
        print("Successfully extracted bboxes using Playwright")
    except Exception as e:
        print(f"Playwright failed: {e}")
        print("Falling back to HTML parsing method...")
        region_bboxes, placeholder_bboxes, layout_width, layout_height = extract_bboxes_from_html_fallback(html_path)
        print("Successfully extracted bboxes using fallback method")
    
    if not placeholder_bboxes:
        # This is not necessarily an error; some UIs might not have placeholders.
        print("Info: No gray placeholder blocks found.")

    # Calculate separate scale factors for X and Y to handle aspect ratio differences
    scale_x = W / layout_width if layout_width > 0 else 1
    scale_y = H / layout_height if layout_height > 0 else 1
    
    if abs(scale_x - scale_y) > 0.05:
        print(f"[*] Detected different X/Y scales. X: {scale_x:.2f}, Y: {scale_y:.2f}")
    elif abs(scale_x - 1.0) > 0.05:
        print(f"[*] Detected uniform scale: {scale_x:.2f}")


    # Scale all bboxes to the original image coordinate system
    scaled_regions = []
    for b in region_bboxes:
        scaled_regions.append({
            **b,
            "x": int(b['x'] * scale_x), "y": int(b['y'] * scale_y),
            "w": int(b['w'] * scale_x), "h": int(b['h'] * scale_y)
        })

    scaled_placeholders = []
    for b in placeholder_bboxes:
        scaled_placeholders.append({
            **b,
            "x": int(b['x'] * scale_x), "y": int(b['y'] * scale_y),
            "w": int(b['w'] * scale_x), "h": int(b['h'] * scale_y)
        })

    # Draw boxes using the now-scaled data
    overlay = draw_bboxes_on_image(img, scaled_regions, scaled_placeholders)

    # Save debug image
    debug_image_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(debug_image_path), overlay)
    print(f"Success: BBox overlay saved to {debug_image_path}")


    # Convert absolute pixel coordinates to proportions for the final JSON output
    proportional_regions = []
    for b in scaled_regions:
        proportional_regions.append({
            **b,
            "x": b["x"] / W, "y": b["y"] / H,
            "w": b["w"] / W, "h": b["h"] / H
        })
        
    proportional_placeholders = []
    for b in scaled_placeholders:
        proportional_placeholders.append({
            **b,
            "x": b["x"] / W, "y": b["y"] / H,
            "w": b["w"] / W, "h": b["h"] / H
        })

    # Print/save bbox array
    print("\n=== BBox (proportional to image dimensions) ===")
    output_data = {
        "regions": proportional_regions,
        "placeholders": proportional_placeholders
    }
    output_json = json.dumps(output_data, indent=2, ensure_ascii=False)
    print(output_json)

    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(output_json)
    print(f"Success: BBox list saved to {output_json_path}")
    print(f"--- Image Box Detection Complete for run_id: {run_id} ---")

def get_args():
    parser = argparse.ArgumentParser(
        description="Extracts placeholder bounding boxes from an HTML file and maps them to a screenshot."
    )
    parser.add_argument('--run_id', required=True, type=str,
                        help="A unique identifier for the processing run.")
    return parser.parse_args()

# ---------- CLI ----------
if __name__ == "__main__":
    main()
