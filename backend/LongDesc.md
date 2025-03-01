# SAM 2: Segment Anything in Images and Videos

**Segment Anything Model 2 (SAM 2)** is a model designed for visual segmentation in images and videos, extending SAM to video processing with a simple transformer architecture and streaming memory for real-time tasks. SAM 2 uses a model-in-the-loop data engine to improve both the model and the dataset through user interaction, resulting in the **SA-V dataset**, the largest video segmentation dataset to date. SAM 2 provides strong performance across a wide range of tasks and visual domains.

## Installation

SAM 2 requires `python>=3.10`, as well as `torch>=2.3.1` and `torchvision>=0.18.1`. Install SAM 2 on a GPU machine using:

```bash
git clone https://github.com/facebookresearch/sam2.git && cd sam2
pip install -e .
```

For Windows, it's recommended to use [Windows Subsystem for Linux (WSL)](https://learn.microsoft.com/en-us/windows/wsl/install) with Ubuntu.

To use SAM 2 with example notebooks:

```bash
pip install -e ".[notebooks]"
```

See [`INSTALL.md`](./INSTALL.md) for FAQs and troubleshooting.

## Getting Started

### Download Checkpoints

Download model checkpoints:

```bash
cd checkpoints && ./download_ckpts.sh && cd ..
```

Then SAM 2 can be used for image and video prediction.

### Image Prediction

Use the `SAM2ImagePredictor` class for image segmentation:

```python
import torch
from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor

checkpoint = "./checkpoints/sam2.1_hiera_large.pt"
model_cfg = "configs/sam2.1/sam2.1_hiera_l.yaml"
predictor = SAM2ImagePredictor(build_sam2(model_cfg, checkpoint))

with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
    predictor.set_image(<your_image>)
    masks, _, _ = predictor.predict(<input_prompts>)
```

### Video Prediction

For video segmentation, use the video predictor:

```python
import torch
from sam2.build_sam import build_sam2_video_predictor

checkpoint = "./checkpoints/sam2.1_hiera_large.pt"
model_cfg = "configs/sam2.1/sam2.1_hiera_l.yaml"
predictor = build_sam2_video_predictor(model_cfg, checkpoint)

with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
    state = predictor.init_state(<your_video>)
    frame_idx, object_ids, masks = predictor.add_new_points_or_box(state, <your_prompts>)
    for frame_idx, object_ids, masks in predictor.propagate_in_video(state):
        ...
```

Refer to the examples in [video_predictor_example.ipynb](./notebooks/video_predictor_example.ipynb) for more details.

## Training SAM 2

You can train or fine-tune SAM 2 on custom datasets of images, videos, or both. Check the training [README](training/README.md) for instructions.

## License

SAM 2 is licensed under [Apache 2.0](./LICENSE).

