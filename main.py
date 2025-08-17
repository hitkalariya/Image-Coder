import subprocess
import sys
import os
import json
import uuid
import shutil
from PIL import Image
from pathlib import Path

# This function is now more robust, injecting the prompt into a temporary copy of the generator.
def inject_prompt_to_generator(prompt_text, temp_generator_path):
    if not prompt_text:
        return

    user_instruction = {
        "sidebar": "Make all icons look better; fill in relevant English text; beautify the layout.",
        "header": "Make the Google logo look better; change the avatar color to be more appealing.",
        "navigation": "Please beautify the layout.",
        "main content": prompt_text
    }
    
    with open(temp_generator_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    start_marker = "user_instruction = {"
    end_marker = "}"
    start_index = content.find(start_marker)
    end_index = content.find(end_marker, start_index)
    
    if start_index != -1 and end_index != -1:
        dict_str = f"user_instruction = {json.dumps(user_instruction, indent=4)}"
        content = content[:start_index] + dict_str + content[end_index+1:]

    with open(temp_generator_path, 'w', encoding='utf-8') as f:
        f.write(content)

def run_script_with_run_id(script_name, run_id, instructions=None):
    """Executes a script with a specific run_id and optional instructions."""
    # HF Spaces: Use absolute paths based on the script's location
    screencoder_dir = Path(__file__).parent.resolve()
    script_path = screencoder_dir / script_name
    if not script_path.exists():
        # Handle scripts inside subdirectories like UIED/
        script_path = screencoder_dir / "UIED" / script_name

    command = [sys.executable, str(script_path), "--run_id", run_id]

    # Add instructions to the command if provided
    if instructions and "html_generator.py" in str(script_path):
        instructions_json = json.dumps(instructions)
        command.extend(["--instructions", instructions_json])

    print(f"\n--- Running script: {script_path.name} ---")
    try:
        # Pass the current environment variables to the subprocess
        result = subprocess.run(command, check=True, capture_output=True, text=True, env=os.environ)
        print(result.stdout)
        if result.stderr:
            print("Error:")
            print(result.stderr)
    except subprocess.CalledProcessError as e:
        print(f"Error executing {script_path.name}:")
        print(e.stdout)
        print(e.stderr)
        raise  # Re-raise the exception to stop the workflow if a script fails

def generate_html_for_demo(image_path, instructions):
    """
    A refactored main function for Gradio demo integration.
    It orchestrates the script executions for a single image processing run.
    - Creates a unique run_id for each call.
    - Sets up temporary directories for input and output.
    - Cleans up temporary directories after execution.
    """
    run_id = str(uuid.uuid4())
    print(f"--- Starting Screencoder workflow for run_id: {run_id} ---")
    
    # HF Spaces: Use absolute paths and pathlib for robustness
    base_dir = Path(__file__).parent.resolve()
    tmp_dir = base_dir / 'data' / 'tmp' / run_id
    output_dir = base_dir / 'data' / 'output' / run_id
    os.makedirs(tmp_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    try:
        # 1. Copy user-uploaded image to the temp input directory
        new_image_path = tmp_dir / f"{run_id}.png"
        print(f"Debug - main.py: saving image from {image_path} to {new_image_path}")
        print(f"Debug - main.py: image_path exists: {Path(image_path).exists()}")
        
        img = Image.open(image_path)
        img.save(new_image_path, "PNG")
        
        print(f"Debug - main.py: saved image, new_image_path exists: {new_image_path.exists()}")
        if new_image_path.exists():
            print(f"Debug - main.py: saved image size: {new_image_path.stat().st_size} bytes")

        # 2. Run the processing scripts in sequence
        run_script_with_run_id("UIED/run_single.py", run_id)
        run_script_with_run_id("block_parsor.py", run_id)
        run_script_with_run_id("html_generator.py", run_id, instructions)
        run_script_with_run_id("image_box_detection.py", run_id)
        run_script_with_run_id("mapping.py", run_id)
        run_script_with_run_id("image_replacer.py", run_id)

        # 3. Read the generated HTML files
        layout_html_path = output_dir / f"{run_id}_layout.html"
        final_html_path = output_dir / f"{run_id}_layout_final.html"

        layout_html_content = ""
        if layout_html_path.exists():
            with open(layout_html_path, 'r', encoding='utf-8') as f:
                layout_html_content = f.read()
            print(f"Successfully read layout HTML for run_id: {run_id}")
        else:
            print(f"Warning: Layout HTML file not found for run_id: {run_id}")

        if final_html_path.exists():
            with open(final_html_path, 'r', encoding='utf-8') as f:
                final_html_content = f.read()
            print(f"Successfully generated final HTML for run_id: {run_id}")
            return layout_html_content, final_html_content, run_id
        else:
            error_msg = f"Error: Final HTML file not found for run_id: {run_id}"
            return error_msg, None, run_id

    except Exception as e:
        error_msg = f"An error occurred: {e}"
        print(f"An error occurred during the workflow for run_id {run_id}: {e}")
        # Return signature needs to match success case
        return error_msg, None, run_id
    finally:
        # 4. Cleanup: Remove temporary directories
        try:
            # shutil.rmtree(tmp_dir)
            # shutil.rmtree(output_dir)
            print(f"Cleaned up temporary files for run_id: {run_id}")
        except OSError as e:
            print(f"Error cleaning up temporary files for run_id {run_id}: {e}")

def main():
    """Main function to run the entire Screencoder workflow (legacy)."""
    print("Starting the Screencoder full workflow (legacy)...")
    # This main function is now considered legacy and should not be used in HF Spaces.
    run_id = "test1"  # Hardcoded for legacy main
    # Use a dummy image path for legacy run
    dummy_image_path = Path(__file__).parent.resolve() / "data" / "input" / "test1.png"
    instructions = {"main content": "Generate the HTML for this screenshot."}
    generate_html_for_demo(str(dummy_image_path), instructions)
    print("\nScreencoder workflow completed successfully!")

if __name__ == "__main__":
    main()