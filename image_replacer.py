import argparse
import json
from pathlib import Path
from bs4 import BeautifulSoup
import cv2
import re
import sys

def main():
    args = get_args()
    run_id = args.run_id

    # --- Dynamic Path Construction ---
    base_dir = Path(__file__).parent.resolve()
    tmp_dir = base_dir / 'data' / 'tmp' / run_id
    output_dir = base_dir / 'data' / 'output' / run_id

    mapping_path = tmp_dir / f"mapping_full_{run_id}.json"
    uied_path = tmp_dir / "ip" / f"{run_id}.json"
    original_image_path = tmp_dir / f"{run_id}.png"
    # This is the input HTML with placeholders
    gray_html_path = output_dir / f"{run_id}_layout.html"
    # This will be the final output of the entire pipeline
    final_html_path = output_dir / f"{run_id}_layout_final.html"

    # --- Input Validation ---
    if not all([p.exists() for p in [mapping_path, uied_path, original_image_path, gray_html_path]]):
        print("Error: One or more required input files are missing.", file=sys.stderr)
        if not mapping_path.exists(): print(f"- Missing: {mapping_path}", file=sys.stderr)
        if not uied_path.exists(): print(f"- Missing: {uied_path}", file=sys.stderr)
        if not original_image_path.exists(): print(f"- Missing: {original_image_path}", file=sys.stderr)
        if not gray_html_path.exists(): print(f"- Missing: {gray_html_path}", file=sys.stderr)
        sys.exit(1)

    print(f"--- Starting Image Replacement for run_id: {run_id} ---")

    # --- Phase 1: Crop and Save All Images First ---
    
    # 1. Load data
    mapping_data = json.loads(mapping_path.read_text())
    uied_data = json.loads(uied_path.read_text())
    original_image = cv2.imread(str(original_image_path))
    
    if original_image is None:
        raise ValueError(f"Could not load the original image from {original_image_path}")

    # Get image shapes to calculate a simple, global scaling factor
    H_proc, W_proc, _ = uied_data['img_shape']
    H_orig, W_orig, _ = original_image.shape
    scale_x = W_orig / W_proc
    scale_y = H_orig / H_proc
    print(f"Using global scaling for cropping: scale_x={scale_x:.3f}, scale_y={scale_y:.3f}")

    uied_boxes = {
        comp['id']: (comp['column_min'], comp['row_min'], comp['width'], comp['height'])
        for comp in uied_data['compos']
    }

    # 2. Create a directory for cropped images
    crop_dir = final_html_path.parent / f"cropped_images_{run_id}"
    crop_dir.mkdir(exist_ok=True)
    print(f"Saving cropped images to: {crop_dir.resolve()}")

    # 3. Iterate through mappings and save cropped images to files
    for region_id, region_data in mapping_data.items():
        for placeholder_id, uied_id in region_data['mapping'].items():
            if uied_id not in uied_boxes:
                print(f"Warning: UIED ID {uied_id} from mapping not found. Skipping placeholder {placeholder_id}.")
                continue

            uied_bbox = uied_boxes[uied_id]
            
            x_proc, y_proc, w_proc, h_proc = uied_bbox
            x_tf = x_proc * scale_x
            y_tf = y_proc * scale_y
            w_tf = w_proc * scale_x
            h_tf = h_proc * scale_y

            x1, y1 = int(x_tf), int(y_tf)
            x2, y2 = int(x_tf + w_tf), int(y_tf + h_tf)
            
            h_img, w_img, _ = original_image.shape
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w_img, x2), min(h_img, y2)
            
            cropped_img = original_image[y1:y2, x1:x2]
            
            if cropped_img.size == 0:
                print(f"Warning: Cropped image for {placeholder_id} is empty. Skipping.")
                continue
            
            output_path = crop_dir / f"{placeholder_id}.png"
            cv2.imwrite(str(output_path), cropped_img)

    # --- Phase 2: Use BeautifulSoup to Replace Placeholders by Order ---
    
    print("\nStarting offline HTML processing with BeautifulSoup...")
    html_content = gray_html_path.read_text()
    soup = BeautifulSoup(html_content, 'html.parser')

    # 1. Find all placeholder elements by their class, in document order.
    placeholder_elements = soup.find_all(class_='bg-gray-400')

    # 2. Get the placeholder IDs from the mapping file in the correct, sorted order.
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

    ordered_placeholder_ids = []
    # Sort region IDs numerically to process them in order
    for region_id in sorted(mapping_data.keys(), key=int):
        region_mapping = mapping_data[region_id]['mapping']
        # Sort the placeholder IDs within each region naturally (e.g., ph1, ph2, ph10)
        sorted_ph_ids = sorted(region_mapping.keys(), key=natural_sort_key)
        ordered_placeholder_ids.extend(sorted_ph_ids)
    
    # 3. Check for count mismatches
    if len(placeholder_elements) != len(ordered_placeholder_ids):
        print(f"Warning: Mismatch in counts! Found {len(placeholder_elements)} placeholder images in HTML, but {len(ordered_placeholder_ids)} mappings.")
    else:
        print(f"Found {len(placeholder_elements)} placeholder images to replace.")

    # 4. Iterate through both lists, create a proper <img> tag, and replace the placeholder.
    for i, ph_element in enumerate(placeholder_elements):
        if i >= len(ordered_placeholder_ids):
            print(f"Warning: More placeholder images in HTML than mappings. Stopping at image {i+1}.")
            break
        
        ph_id = ordered_placeholder_ids[i]
        # Fix: Use the correct relative path from HTML file to image directory
        relative_img_path = f"{crop_dir.name}/{ph_id}.png"
        
        # Debug: Print the path being used
        print(f"Setting image path for {ph_id}: {relative_img_path}")
        
        # --- Convert div with bg-gray-400 class to img tag ---
        # Create a new img element
        new_img = soup.new_tag('img')
        new_img['src'] = relative_img_path
        new_img['class'] = ph_element.get('class', [])
        # Remove bg-gray-400 class and add appropriate image classes
        if 'bg-gray-400' in new_img['class']:
            new_img['class'].remove('bg-gray-400')
        new_img['class'].extend(['h-full', 'object-cover'])
        
        # Replace the div element with the new img element
        ph_element.replace_with(new_img)

    # Save the modified HTML
    final_html_path.write_text(str(soup))
    
    print(f"\nSuccessfully replaced {min(len(placeholder_elements), len(ordered_placeholder_ids))} placeholders.")
    print(f"Final HTML generated at {final_html_path.resolve()}")
    print(f"--- Image Replacement Complete for run_id: {run_id} ---")

def get_args():
    parser = argparse.ArgumentParser(description="Replace placeholder divs in an HTML file with cropped images based on UIED mappings.")
    parser.add_argument("--run_id", type=str, required=True, help="A unique identifier for the processing run.")
    return parser.parse_args()

if __name__ == "__main__":
    main()
