import cv2
import os
import numpy as np
import multiprocessing
import argparse
from os.path import join as pjoin

def get_args():
    parser = argparse.ArgumentParser(description="Processes a single image for UI element detection.")
    parser.add_argument('--run_id', type=str, required=True, help='A unique identifier for the processing run.')
    return parser.parse_args()

def resize_height_by_longest_edge(img_path, resize_length=800):
    org = cv2.imread(img_path)
    height, width = org.shape[:2]
    if height > width:
        return resize_length
    else:
        return int(resize_length * (height / width))


def color_tips():
    color_map = {'Text': (0, 0, 255), 'Compo': (0, 255, 0), 'Block': (0, 255, 255), 'Text Content': (255, 0, 255)}
    board = np.zeros((200, 200, 3), dtype=np.uint8)

    board[:50, :, :] = (0, 0, 255)
    board[50:100, :, :] = (0, 255, 0)
    board[100:150, :, :] = (255, 0, 255)
    board[150:200, :, :] = (0, 255, 255)
    cv2.putText(board, 'Text', (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
    cv2.putText(board, 'Non-text Compo', (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
    cv2.putText(board, "Compo's Text Content", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
    cv2.putText(board, "Block", (10, 170), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
    cv2.imshow('colors', board)


if __name__ == '__main__':
    args = get_args()
    
    # --- Dynamic Path Construction ---
    # Construct paths based on the provided run_id
    base_dir = os.path.dirname(os.path.abspath(__file__))
    run_id = args.run_id
    
    # The temporary directory for this specific run
    tmp_dir = os.path.join(base_dir, '..', 'data', 'tmp', run_id)
    
    # Input image path
    input_path_img = os.path.join(tmp_dir, f"{run_id}.png")
    
    # Output directory for this script's results
    output_root = tmp_dir # All results (ip, ocr, etc.) will go into the run's tmp subdir.
    
    if not os.path.exists(input_path_img):
        print(f"Error: Input image not found at {input_path_img}")
        exit(1)

    print(f"--- Starting UIED processing for run_id: {run_id} ---")
    print(f"Input image: {input_path_img}")
    print(f"Output root: {output_root}")
    # Set multiprocessing start method to 'spawn' for macOS compatibility.
    # This must be done at the very beginning of the main block.
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass  # It's OK if it's already set.
    
    # Disable multiprocessing for PaddleOCR to avoid segmentation fault on macOS
    import os
    os.environ['PADDLE_USE_MULTIPROCESSING'] = '0'

    '''
        ele:min-grad: gradient threshold to produce binary map         
        ele:ffl-block: fill-flood threshold
        ele:min-ele-area: minimum area for selected elements 
        ele:merge-contained-ele: if True, merge elements contained in others
        text:max-word-inline-gap: words with smaller distance than the gap are counted as a line
        text:max-line-gap: lines with smaller distance than the gap are counted as a paragraph

        Tips:
        1. Larger *min-grad* produces fine-grained binary-map while prone to over-segment element to small pieces
        2. Smaller *min-ele-area* leaves tiny elements while prone to produce noises
        3. If not *merge-contained-ele*, the elements inside others will be recognized, while prone to produce noises
        4. The *max-word-inline-gap* and *max-line-gap* should be dependent on the input image size and resolution

        mobile: {'min-grad':4, 'ffl-block':5, 'min-ele-area':50, 'max-word-inline-gap':6, 'max-line-gap':1}
        web   : {'min-grad':3, 'ffl-block':5, 'min-ele-area':25, 'max-word-inline-gap':4, 'max-line-gap':4}
    '''
    key_params = {'min-grad':10, 'ffl-block':5, 'min-ele-area':50,
                  'merge-contained-ele':True, 'merge-line-to-paragraph':False, 'remove-bar':True}

    # set input image path
    # input_path_img = 'data/test1.png'
    # output_root = 'data'

    resized_height = resize_height_by_longest_edge(input_path_img, resize_length=800)
    # color_tips() # This shows a window, which is not suitable for a script.

    is_ip = True
    is_clf = False
    is_ocr = False
    is_merge = False

    if is_ocr:
        import detect_text.text_detection as text
        os.makedirs(pjoin(output_root, 'ocr'), exist_ok=True)
        text.text_detection(input_path_img, output_root, show=True, method='paddle')

    if is_ip:
        import detect_compo.ip_region_proposal as ip
        os.makedirs(pjoin(output_root, 'ip'), exist_ok=True)
        # switch of the classification func
        classifier = None
        if is_clf:
            classifier = {}
            from cnn.CNN import CNN
            # classifier['Image'] = CNN('Image')
            classifier['Elements'] = CNN('Elements')
            # classifier['Noise'] = CNN('Noise')
        ip.compo_detection(input_path_img, output_root, key_params,
                           classifier=classifier, resize_by_height=resized_height, show=False)

    if is_merge:
        import detect_merge.merge as merge
        os.makedirs(pjoin(output_root, 'merge'), exist_ok=True)
        name = input_path_img.split('/')[-1][:-4]
        compo_path = pjoin(output_root, 'ip', str(name) + '.json')
        ocr_path = pjoin(output_root, 'ocr', str(name) + '.json')
        merge.merge(input_path_img, compo_path, ocr_path, pjoin(output_root, 'merge'),
                    is_remove_bar=key_params['remove-bar'], is_paragraph=key_params['merge-line-to-paragraph'], show=False)
    
    print(f"--- UIED processing complete for run_id: {run_id} ---")
