
# UIED - UI Element Detection

**Maintained by: Hit Kalariya**  
[GitHub](https://github.com/hitkalariya) | [LinkedIn](https://www.linkedin.com/in/hitkalariya/)

---

UIED is a professional tool for detecting UI elements from screenshots or design drawings. This repository is maintained and enhanced by Hit Kalariya, providing advanced features and integration for modern UI analysis workflows.

---


## Key Features
- Detects and classifies UI elements (text, buttons, images, etc.) from screenshots or design files
- Integrates Google OCR for robust text detection
- Modular and customizable detection pipeline
- Outputs results as JSON for downstream applications


## What is UIED?
UIED (UI Element Detection) is a computer vision-based tool for detecting and classifying UI elements in screenshots, mockups, or hand-drawn designs. It supports:
- Mobile app and web page screenshots
- Photoshop/Sketch/hand-drawn UI designs
- Exporting detection results as JSON for further processing


<!-- UIED Approach diagram can be added here if desired -->


## Getting Started

### Dependencies
- Python 3.5+
- OpenCV 3.4.2
- Pandas
<!-- Optional: Tensorflow, Keras, Sklearn for advanced features -->

### Installation
Install dependencies and set up your environment as described in the main project README.


### Usage
- To test a single image, set `input_path_img` in `run_single.py` and run the script. Results are saved to `output_root`.
- For batch processing, set `input_img_root` in `run_batch.py`.
- Use `run_testing.py` to tune parameters for your data type (mobile, web, PC, etc.).

---

## Folder Structure
- `cnn/`: Train classifier for graphic UI elements
- `config/`: Data paths and detection parameters
- `data/`: Input images and output detection results
- `detect_compo/`: Non-text GUI component detection
- `detect_text/`: GUI text detection (Google OCR)
- `detect_merge/`: Merge non-text and text detection results

---

## Example
```python
# Example: Run UIED on a sample image
python run_single.py --input ../data/input/test1.png --output ../data/output/
```

---

## License
This module is maintained and enhanced by Hit Kalariya. See LICENSE for details.
