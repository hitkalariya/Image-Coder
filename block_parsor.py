import os
import cv2
import json
import argparse
from utils import Doubao, encode_image, image_mask

DEFAULT_IMAGE_PATH = "data/input/test1.png"
DEFAULT_API_PATH = "doubao_api.txt"
PROMPT_LIST = [
    ("header", "Please output the minimum bounding box of the header. Please output the bounding box in the format of <bbox>x1 y1 x2 y2</bbox>. Avoid the blank space in the header."),
    ("sidebar", "Please output the minimum bounding box of the sidebar. Please output the bounding box in the format of <bbox>x1 y1 x2 y2</bbox>. Avoid meaningless blank space in the sidebar."),
    ("navigation", "Please output the minimum bounding box of the navigation. Please output the bounding box in the format of <bbox>x1 y1 x2 y2</bbox>. Avoid the blank space in the navigation."),
    ("main content", "Please output the minimum bounding box of the main content. Please output the bounding box in the format of <bbox>x1 y1 x2 y2</bbox>. Avoid the blank space in the main content."),
]
PROMPT_MERGE = "Return the bounding boxes of the sidebar, main content, header, and navigation in this webpage screenshot. Please only return the corresponding bounding boxes. Note: 1. The areas should not overlap; 2. All text information and other content should be framed inside; 3. Try to keep it compact without leaving a lot of blank space; 4. Output a label and the corresponding bounding box for each line."
BBOX_TAG_START = "<bbox>"
BBOX_TAG_END = "</bbox>"

def get_args():
    parser = argparse.ArgumentParser(description="Parses bounding boxes from an image using a vision model.")
    parser.add_argument('--run_id', type=str, required=True, help='A unique identifier for the processing run.')
    return parser.parse_args()

def parse_bboxes(bbox_input: str) -> dict[str, tuple[int, int, int, int]]:
    """Parse bounding box string to a dictionary of normalized (0-1000) coordinate tuples."""
    bboxes = {}
    try:
        components = bbox_input.strip().split('\n')
        for component in components:
            component = component.strip()
            if not component:
                continue
            
            if ':' in component:
                name, bbox_str = component.split(':', 1)
            else:
                bbox_str = component
                if 'sidebar' in component.lower(): name = 'sidebar'
                elif 'header' in component.lower(): name = 'header'
                elif 'navigation' in component.lower(): name = 'navigation'
                elif 'main content' in component.lower(): name = 'main content'
                else: name = 'unknown'
            
            name = name.strip().lower()
            bbox_str = bbox_str.strip()
            
            if BBOX_TAG_START in bbox_str and BBOX_TAG_END in bbox_str:
                start_idx = bbox_str.find(BBOX_TAG_START) + len(BBOX_TAG_START)
                end_idx = bbox_str.find(BBOX_TAG_END)
                coords_str = bbox_str[start_idx:end_idx].strip()
                
                try:
                    norm_coords = list(map(int, coords_str.split()))
                    if len(norm_coords) == 4:
                        bboxes[name] = tuple(norm_coords) # Directly store normalized coordinates
                        print(f"Successfully parsed {name}: {bboxes[name]}")
                except ValueError as e:
                    print(f"Failed to parse coordinates for {name}: {e}")
    except Exception as e:
        print(f"Coordinate parsing failed: {str(e)}")
    
    print("Final parsed bboxes:", bboxes)
    return bboxes

def draw_bboxes(image_path: str, bboxes: dict[str, tuple[int, int, int, int]], output_path: str) -> str:
    """Draws normalized (0-1000) bboxes on an image for visualization."""
    image = cv2.imread(image_path)
    if image is None: return ""
    
    h, w = image.shape[:2]
    colors = {'sidebar': (0, 0, 255), 'header': (0, 255, 0), 'navigation': (255, 0, 0), 'main content': (255, 255, 0), 'unknown': (0, 0, 0)}
    
    output_image = image.copy()
    for component, norm_bbox in bboxes.items():
        x_min = int(norm_bbox[0] * w / 1000)
        y_min = int(norm_bbox[1] * h / 1000)
        x_max = int(norm_bbox[2] * w / 1000)
        y_max = int(norm_bbox[3] * h / 1000)
        
        color = colors.get(component.lower(), (0, 0, 255))
        cv2.rectangle(output_image, (x_min, y_min), (x_max, y_max), color, 3)
        cv2.putText(output_image, component, (x_min, y_min - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)
    
    if cv2.imwrite(output_path, output_image):
        print(f"Successfully saved annotated image: {output_path}")
        return output_path
    return ""

def save_bboxes_to_json(bboxes: dict[str, tuple[int, int, int, int]], json_path: str) -> str:
    """Saves the normalized bboxes to a JSON file."""
    # This is the unified format: a dictionary of lists.
    bboxes_dict = {k: list(v) for k, v in bboxes.items()}
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(bboxes_dict, f, indent=4, ensure_ascii=False)
        print(f"Successfully saved bbox information to: {json_path}")
        return json_path
    except Exception as e:
        print(f"Error saving JSON file: {str(e)}")
        return ""

def resolve_containment(bboxes: dict[str, tuple[int, int, int, int]]) -> dict[str, tuple[int, int, int, int]]:
    """
    Resolves containment issues among bounding boxes.
    If a box is found to be fully contained within another, it is removed.
    This is based on the assumption that major layout components should not contain each other.
    """
    
    def contains(box_a, box_b):
        """Checks if box_a completely contains box_b."""
        xa1, ya1, xa2, ya2 = box_a
        xb1, yb1, xb2, yb2 = box_b
        return xa1 <= xb1 and ya1 <= yb1 and xa2 >= xb2 and ya2 >= yb2

    names = list(bboxes.keys())
    removed = set()

    for i in range(len(names)):
        for j in range(len(names)):
            if i == j or names[i] in removed or names[j] in removed:
                continue
            
            name1, box1 = names[i], bboxes[names[i]]
            name2, box2 = names[j], bboxes[names[j]]

            if contains(box1, box2) or contains(box2, box1):
                print(f"Containment found: '{name1}' contains '{name2}'. Removing '{name2}'.")
                removed.add(name2)

    return {name: bbox for name, bbox in bboxes.items() if name not in removed}

# sequential version of bbox parsing: Using recursive detection with mask
def sequential_component_detection(image_path: str, temp_dir: str) -> dict[str, tuple[int, int, int, int]]:
    """
    Sequential processing flow: detect each component in turn, mask the image after each detection
    """
    bboxes = {}
    current_image_path = image_path
    
    # Check for API key - first try environment variable, then use provided path
    api_key = os.environ.get('API_key')
    if not api_key:
        print(f"Error: API key not found in environment variable 'API_key'")
        exit(1)
    ark_client = Doubao(api_key)
    
    image = cv2.imread(image_path)
    if image is None:
        print(f"Error: Failed to read image {image_path}")
        return bboxes
    h, w = image.shape[:2]
    
    for i, (component_name, prompt) in enumerate(PROMPT_LIST):
        print(f"\n=== Processing {component_name} (Step {i+1}/{len(PROMPT_LIST)}) ===")

        base64_image = encode_image(current_image_path)
        if not base64_image:
            print(f"Error: Failed to encode image for {component_name}")
            continue

        print(f"Sending prompt for {component_name}...")
        bbox_content = ark_client.ask(prompt, base64_image)
        print(f"Model response for {component_name}:")
        print(bbox_content)
        
        norm_bbox = parse_single_bbox(bbox_content, component_name)
        if norm_bbox:
            bboxes[component_name] = norm_bbox
            print(f"Successfully detected {component_name}: {norm_bbox}")
            
            masked_image = image_mask(current_image_path, norm_bbox)
            
            temp_image_path = os.path.join(temp_dir, f"temp_{component_name}_masked.png")
            masked_image.save(temp_image_path)
            current_image_path = temp_image_path
            
            print(f"Created masked image for next step: {temp_image_path}")
        else:
            print(f"Failed to detect {component_name}")
    
    return bboxes

def parse_single_bbox(bbox_input: str, component_name: str) -> tuple[int, int, int, int]:
    """
    Parses a single component's bbox string and returns normalized coordinates.
    """
    print(f"Parsing bbox for {component_name}: {bbox_input}")
    
    try:
        if BBOX_TAG_START in bbox_input and BBOX_TAG_END in bbox_input:
            start_idx = bbox_input.find(BBOX_TAG_START) + len(BBOX_TAG_START)
            end_idx = bbox_input.find(BBOX_TAG_END)
            coords_str = bbox_input[start_idx:end_idx].strip()
            
            norm_coords = list(map(int, coords_str.split()))
            if len(norm_coords) == 4:
                return tuple(norm_coords)
            else:
                print(f"Invalid number of coordinates for {component_name}: {norm_coords}")
        else:
            print(f"No bbox tags found in response for {component_name}")
    except Exception as e:
        print(f"Failed to parse bbox for {component_name}: {e}")
    
    return None

def main_content_processing(bboxes: dict[str, tuple[int, int, int, int]], image_path: str) -> dict[str, tuple[int, int, int, int]]:
    """devide the main content into several parts"""
    image = cv2.imread(image_path)
    if image is None:
        print(f"Error: Failed to read image {image_path}")
        return
    h, w = image.shape[:2]
    for component, bbox in bboxes.items():
        bboxes[component] = (
            int(bbox[0] * w / 1000),
            int(bbox[1] * h / 1000),
            int(bbox[2] * w / 1000),
            int(bbox[3] * h / 1000))
    
    
def main():
    args = get_args()
    run_id = args.run_id

    # --- Dynamic Path Construction ---
    base_dir = os.path.dirname(os.path.abspath(__file__))
    tmp_dir = os.path.join(base_dir, 'data', 'tmp', run_id)
    
    image_path = os.path.join(tmp_dir, f"{run_id}.png")
    # api_path = os.path.join(base_dir, "doubao_api.txt")
    json_output_path = os.path.join(tmp_dir, f"{run_id}_bboxes.json")
    annotated_image_output_path = os.path.join(tmp_dir, f"{run_id}_with_bboxes.png")

    # Debug: Print all paths and check if files exist
    print(f"Debug - base_dir: {base_dir}")
    print(f"Debug - tmp_dir: {tmp_dir}")
    print(f"Debug - image_path: {image_path}")
    # print(f"Debug - api_path: {api_path}")
    print(f"Debug - image_path exists: {os.path.exists(image_path)}")
    # print(f"Debug - api_path exists: {os.path.exists(api_path)}")
    
    # List contents of tmp_dir if it exists
    if os.path.exists(tmp_dir):
        print(f"Debug - tmp_dir contents: {os.listdir(tmp_dir)}")
    else:
        print(f"Debug - tmp_dir does not exist: {tmp_dir}")

    if not os.path.exists(image_path):
        print(f"Error: Input image not found at {image_path}")
        # Create empty json file so the pipeline doesn't break
        save_bboxes_to_json({}, json_output_path)
        exit(1)
    
    api_key = os.environ.get('API_key')
    if not api_key:
        print(f"Error: API key not found in environment variable 'API_key'")
        # Create empty json file so the pipeline doesn't break
        save_bboxes_to_json({}, json_output_path)
        exit(1)

    print(f"--- Starting BBox Parsing for run_id: {run_id} ---")
    
    # Use environment variable if available, otherwise use file path
    client = Doubao(api_key)
    base64_image = encode_image(image_path)
    if not base64_image:
        print(f"Error: Failed to encode image {image_path}")
        # Create empty json file so the pipeline doesn't break
        save_bboxes_to_json({}, json_output_path)
        exit(1)
    
    bbox_content = client.ask(PROMPT_MERGE, base64_image)
    bboxes = parse_bboxes(bbox_content)
    
    if bboxes:
        print("\n--- Resolving containment issues ---")
        bboxes = resolve_containment(bboxes)
        print("--- Containment resolved ---")
        
        print(f"\n--- Detection Complete for run_id: {run_id} ---")
        save_bboxes_to_json(bboxes, json_output_path)
        draw_bboxes(image_path, bboxes, annotated_image_output_path)
    else:
        print(f"\nNo valid bounding box coordinates found for run_id: {run_id}")
        # Still create an empty json file so the pipeline doesn't break
        save_bboxes_to_json({}, json_output_path)

if __name__ == "__main__":
    main()