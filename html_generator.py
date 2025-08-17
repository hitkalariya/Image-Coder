from utils import encode_image, Doubao, Qwen_2_5_VL
from PIL import Image
import bs4
from threading import Thread
import time
import argparse
import json
import os

# This dictionary holds the user's instructions for the current run.
user_instruction = {"sidebar": "", "header": "", "navigation": "", "main content": ""}

def get_args():
    parser = argparse.ArgumentParser(description="Generates an HTML layout from bounding box data.")
    parser.add_argument('--run_id', type=str, required=True, help='A unique identifier for the processing run.')
    parser.add_argument('--instructions', type=str, help='A JSON string of instructions for different components.')
    return parser.parse_args()

def get_prompt_dict(instructions):
    """Dynamically creates the prompt dictionary with the user's instructions."""
    # return {
    #     "sidebar": f"""This is a screenshot of a container. Please fill in a complete HTML and tail-wind CSS code to accurately reproduce the given container. Please note that the layout, icon style, size, and text information of all blocks need to be basically consistent with the original screenshot based on the user's additional conditions. User instruction: {instructions["sidebar"]}. The following is the code for filling in:
    # <div>
    # your code here
    # </div>,
    # only return the code within the <div> and </div> tags""",
    #     "header": f"""This is a screenshot of a container. Please fill in a complete HTML and tail-wind CSS code to accurately reproduce the given container. Please note that the relative position, layout, text information, and color of all blocks in the boundary box need to be basically consistent with the original screenshot based on the user's additional conditions. User instruction: {instructions["header"]}. The following is the code for filling in:
    # <div>
    # your code here
    # </div>,
    # only return the code within the <div> and </div> tags""",
    #     "navigation": f"""This is a screenshot of a container. Please fill in a complete HTML and tail-wind CSS code to accurately reproduce the given container. Please note that the relative position, layout, text information, and color of all blocks in the boundary box need to be basically consistent with the original screenshot based on the user's additional conditions. Please use the same icons as in the original screenshot. User instruction: {instructions["navigation"]}. The following is the code for filling in:
    # <div>
    # your code here
    # </div>,
    # only return the code within the <div> and </div> tags""",
    #     "main content": f"""This is a screenshot of a container. Please fill in a complete HTML and tail-wind CSS code to accurately reproduce the given container. Please note that all images displayed in the screenshot must be replaced with pure gray-400 image blocks of the same size as the corresponding images in the original screenshot, and the text information in the images does not need to be recognized. The relative position, layout, text information, and color of all blocks in the boundary box need to be basically consistent with the original screenshot based on the user's additional conditions. User instruction: {instructions["main content"]}. The following is the code for filling in:
    # <div>
    # your code here
    # </div>,
    # only return the code within the <div> and </div> tags""",
    # }
    return {
        "sidebar": f"""这是一个container的截图。这是用户给的额外要求：{instructions["sidebar"]}请填写一段完整的HTML和tail-wind CSS代码以准确再现给定的容器。请注意所有组块的排版、图标样式、大小、文字信息需要在用户额外条件的基础上与原始截图基本保持一致。对于小图标，请保持生成的svg图标和原图一致。请使用相同大小、位置的纯灰色图像块并标记为"bg-gray-400"代替大的图片，注意代码中的大小和位置信息。以下是供填写的代码：

        <div>
        your code here
        </div>

        只需返回<div>和</div>标签内的代码""",

        "header": f"""这是一个container的截图。这是用户给的额外要求：{instructions["header"]}请填写一段完整的HTML和tail-wind CSS代码以准确再现给定的容器。请注意所有组块在boundary box中的相对位置、排版、文字信息、颜色需要在用户额外条件的基础上与原始截图基本保持一致。请保持生成的svg图标和原图一致。请使用相同大小、位置的纯灰色图像块并标记为"bg-gray-400"代替图片，注意代码中的大小和位置信息。以下是供填写的代码：

        <div>
        your code here
        </div>

        只需返回<div>和</div>标签内的代码""",

        "navigation": f"""这是一个container的截图。这是用户给的额外要求：{instructions["navigation"]}请填写一段完整的HTML和tail-wind CSS代码以准确再现给定的容器。请注意所有组块的在boundary box中的相对位置、文字排版、颜色需要在用户额外条件的基础上与原始截图基本保持一致。图像请你直接使用原始截图中一致的图标。请使用相同大小、位置的纯灰色图像块并标记为"bg-gray-400"代替图片，注意代码中的大小和位置信息。以下是供填写的代码：

        <div>
        your code here
        </div>

        只需返回<div>和</div>标签内的代码""",

        "main content": f"""这是一个container的截图。这是用户给的额外要求：{instructions["main content"]}请填写一段完整的HTML和tail-wind CSS代码以准确再现给定的容器。截图中显示的图像请使用相同大小、位置的纯灰色图像块并标记为"bg-gray-400"代替图片，注意代码中其大小和位置信息，不需要识别其中的文字信息。请注意所有组块在boundary box中的相对位置、排版、文字信息、颜色需要在用户额外条件的基础上与原始截图基本保持一致。以下是供填写的代码：

        <div>
        your code here
        </div>

        只需返回<div>和</div>标签内的代码"""
    }

def generate_code(bbox_tree, img_path, bot, instructions):
    """Generates code for each leaf node in the bounding box tree."""
    img = Image.open(img_path)
    code_dict = {}
    prompt_dict = get_prompt_dict(instructions)

    def _generate_code(node):
        if not node.get("children"): # It's a leaf node
            bbox = node["bbox"]
            cropped_img = img.crop(bbox)
            
            node_type = node.get("type")
            if node_type and node_type in prompt_dict:
                prompt = prompt_dict[node_type]
                try:
                    code = bot.ask(prompt, encode_image(cropped_img))
                    code_dict[node["id"]] = code
                except Exception as e:
                    print(f"Error generating code for {node_type}: {e}")
            else:
                print(f"Node type '{node_type}' not found or invalid.")
        else:
            for child in node["children"]:
                _generate_code(child)

    _generate_code(bbox_tree)
    return code_dict

def generate_html(bbox_tree, output_file):
    """Generates an HTML file with nested containers based on the bounding box tree."""
    html_template_start = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Bounding Boxes Layout</title>
        <style>
            body, html {
                margin: 0;
                padding: 0;
                width: 100%;
                height: 100%;
            }
            .container { 
                position: relative;
                width: 100%;
                height: 100%;
                box-sizing: border-box;
            }
            .box {
                position: absolute;
                box-sizing: border-box;
                overflow: hidden;
            }
            .box > .container {
                display: grid;
                width: 100%;
                height: 100%;
            }
        </style>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    </head>
    <body>
        <div class="container">
    """

    html_template_end = """
        </div>
    </body>
    </html>
    """

    def process_bbox(node, parent_width, parent_height, parent_left, parent_top):
        bbox = node['bbox']
        children = node.get('children', [])
        node_id = node['id']
        
        left = (bbox[0] - parent_left) / parent_width * 100
        top = (bbox[1] - parent_top) / parent_height * 100
        width = (bbox[2] - bbox[0]) / parent_width * 100
        height = (bbox[3] - bbox[1]) / parent_height * 100

        html = f'<div id="{node_id}" class="box" style="left: {left}%; top: {top}%; width: {width}%; height: {height}%;">'
        if children:
            html += '<div class="container">'
            current_width = bbox[2] - bbox[0]
            current_height = bbox[3] - bbox[1]
            for child in children:
                html += process_bbox(child, current_width, current_height, bbox[0], bbox[1])
            html += '</div>'
        html += '</div>'
        return html

    root_bbox = bbox_tree['bbox']
    root_children = bbox_tree.get('children', [])
    root_width = root_bbox[2] - root_bbox[0]
    root_height = root_bbox[3] - root_bbox[1]

    html_content = html_template_start
    for child in root_children:
        html_content += process_bbox(child, root_width, root_height, root_bbox[0], root_bbox[1])
    html_content += html_template_end

    with open(output_file, 'w') as f:
        f.write(bs4.BeautifulSoup(html_content, 'html.parser').prettify())
def generate_code_parallel(bbox_tree, img_path, bot, instructions):
    """generate code for all the leaf nodes in the bounding box tree, return a dictionary: {'id': 'code'}"""
    code_dict = {}
    t_list = []
    prompt_dict = get_prompt_dict(instructions)
    def _generate_code_with_retry(node, max_retries=3, retry_delay=2):
        """Generate code with retry mechanism for rate limit errors"""
        try:
            # Create a new image instance for each thread
            with Image.open(img_path) as img:
                bbox = node["bbox"]
                cropped_img = img.crop(bbox)

                # Select prompt based on node type
                if "type" in node:
                    if node["type"] in prompt_dict:
                        prompt = prompt_dict[node["type"]]
                    else:
                        print(f"Unknown component type: {node['type']}")
                        code_dict[node["id"]] = f"<!-- Unknown component type: {node['type']} -->"
                        return
                else:
                    print("Node type not found")
                    code_dict[node["id"]] = f"<!-- Node type not found -->"
                    return
                
                for attempt in range(max_retries):
                    try:
                        code = bot.ask(prompt, encode_image(cropped_img))
                        code_dict[node["id"]] = code
                        return
                    except Exception as e:
                        if "rate_limit" in str(e).lower() and attempt < max_retries - 1:
                            print(f"Rate limit hit, retrying in {retry_delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                            time.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                        else:
                            print(f"Error generating code for node {node['id']}: {str(e)}")
                            code_dict[node["id"]] = f"<!-- Error: {str(e)} -->"
                            return
        except Exception as e:
            print(f"Error processing image for node {node['id']}: {str(e)}")
            code_dict[node["id"]] = f"<!-- Error: {str(e)} -->"

    def _generate_code(node):
        if not node.get("children"):
            t = Thread(target=_generate_code_with_retry, args=(node,))
            t.start()
            t_list.append(t)
        else:
            for child in node["children"]:
                _generate_code(child)

    _generate_code(bbox_tree)
    
    # Wait for all threads to complete
    for t in t_list:
        t.join()
        
    return code_dict

def code_substitution(html_file, code_dict):
    """Substitutes the generated code into the HTML file."""
    with open(html_file, "r") as f:
        soup = bs4.BeautifulSoup(f.read(), 'html.parser')
    for node_id, code in code_dict.items():
        div = soup.find(id=node_id)
        if div:
            div.append(bs4.BeautifulSoup(code.replace("```html", "").replace("```", ""), 'html.parser'))
    with open(html_file, "w") as f:
        f.write(soup.prettify())

def main():
    args = get_args()
    if args.instructions:
        try:
            user_instruction.update(json.loads(args.instructions))
        except json.JSONDecodeError:
            print("Error: Could not decode instructions JSON.")

    # --- Dynamic Path Construction ---
    base_dir = os.path.dirname(os.path.abspath(__file__))
    tmp_dir = os.path.join(base_dir, 'data', 'tmp', args.run_id)
    output_dir = os.path.join(base_dir, 'data', 'output', args.run_id)
    os.makedirs(output_dir, exist_ok=True)

    input_json_path = os.path.join(tmp_dir, f"{args.run_id}_bboxes.json")
    img_path = os.path.join(tmp_dir, f"{args.run_id}.png")
    output_html_path = os.path.join(output_dir, f"{args.run_id}_layout.html")

    if not os.path.exists(input_json_path) or not os.path.exists(img_path):
        print("Error: Input bbox JSON or image file not found.")
        exit(1)

    print(f"--- Starting HTML Generation for run_id: {args.run_id} ---")
    
    with open(input_json_path, 'r') as f:
        boxes_data = json.load(f)

    with Image.open(img_path) as img:
        width, height = img.size
    
    root = {"bbox": [0, 0, width, height], "children": [], "id": 0}
    
    # Convert normalized bboxes to pixel coordinates
    for name, norm_bbox in boxes_data.items():
        x1 = int(norm_bbox[0] * width / 1000)
        y1 = int(norm_bbox[1] * height / 1000)
        x2 = int(norm_bbox[2] * width / 1000)
        y2 = int(norm_bbox[3] * height / 1000)
        root["children"].append({"bbox": [x1, y1, x2, y2], "type": name, "children": []})
    
    # Assign unique IDs to all nodes for code substitution
    next_id = 1
    for child in root["children"]:
        child["id"] = next_id
        next_id += 1
    
    generate_html(root, output_html_path)

    # Check for API key - first try environment variable, then file
    api_key = os.environ.get('API_key')
    # api_path = os.path.join(base_dir, "doubao_api.txt")
    if not api_key:
        print(f"Error: API key not found in environment variable 'API_key'")
        exit(1)
    
    # Use environment variable if available, otherwise use file path
    bot = Doubao(api_key, model="doubao-1.5-thinking-vision-pro-250428")
    code_dict = generate_code_parallel(root, img_path, bot, user_instruction)
    code_substitution(output_html_path, code_dict)

    print(f"HTML layout with generated content saved to {os.path.basename(output_html_path)}")
    print(f"--- HTML Generation Complete for run_id: {args.run_id} ---")

if __name__ == "__main__":
    main()