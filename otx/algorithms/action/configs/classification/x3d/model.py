"""Model configuration of X3D model for Action Classification Task."""

# Copyright (C) 2022 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions
# and limitations under the License.

# pylint: disable=invalid-name

num_classes = 400
num_samples = 12
model = dict(
    type="Recognizer3D",
    backbone=dict(type="X3D", gamma_w=1, gamma_b=2.25, gamma_d=2.2),
    cls_head=dict(
        type="X3DHead", in_channels=432, num_classes=num_classes, spatial_type="avg", dropout_ratio=0.5, fc1_bias=False
    ),
    # model training and testing settings
    train_cfg=None,
    test_cfg=dict(average_clips="prob"),
)


# dataset settings
seed = 2
dataset_type = "RawframeDataset"

img_norm_cfg = dict(mean=[0.0, 0.0, 0.0], std=[255.0, 255.0, 255.0], to_bgr=False)

clip_len = 8
frame_interval = 4
train_pipeline = [
    dict(type="SampleFrames", clip_len=clip_len, frame_interval=frame_interval, num_clips=1),
    dict(type="RawFrameDecode"),
    dict(type="Resize", scale=(-1, 256)),
    dict(type="RandomResizedCrop"),
    dict(type="Resize", scale=(224, 224), keep_ratio=False),
    dict(type="Flip", flip_ratio=0.5),
    dict(type="Normalize", **img_norm_cfg),
    dict(type="FormatShape", input_format="NCTHW"),
    dict(type="Collect", keys=["imgs", "label"], meta_keys=[]),
    dict(type="ToTensor", keys=["imgs", "label"]),
]

val_pipeline = [
    dict(type="SampleFrames", clip_len=clip_len, frame_interval=frame_interval, num_clips=1, test_mode=True),
    dict(type="RawFrameDecode"),
    dict(type="Resize", scale=(-1, 256)),
    dict(type="CenterCrop", crop_size=224),
    dict(type="Normalize", **img_norm_cfg),
    dict(type="FormatShape", input_format="NCTHW"),
    dict(type="Collect", keys=["imgs", "label"], meta_keys=[]),
    dict(type="ToTensor", keys=["imgs"]),
]
# TODO Delete label in meta key in test pipeline
test_pipeline = [
    dict(type="SampleFrames", clip_len=clip_len, frame_interval=frame_interval, num_clips=1, test_mode=True),
    dict(type="RawFrameDecode"),
    dict(type="Resize", scale=(-1, 256)),
    dict(type="CenterCrop", crop_size=224),
    dict(type="Normalize", **img_norm_cfg),
    dict(type="FormatShape", input_format="NCTHW"),
    dict(type="Collect", keys=["imgs"], meta_keys=[]),
    dict(type="ToTensor", keys=["imgs"]),
]

data = dict(
    videos_per_gpu=10,
    workers_per_gpu=0,
    test_dataloader=dict(videos_per_gpu=1),
    train=dict(
        type=dataset_type,
        filename_tmpl="{:05}.jpg",
        pipeline=train_pipeline,
    ),
    val=dict(
        type=dataset_type,
        filename_tmpl="{:05}.jpg",
        pipeline=val_pipeline,
    ),
    test=dict(
        type=dataset_type,
        filename_tmpl="{:05}.jpg",
        pipeline=test_pipeline,
    ),
)
evaluation = dict(interval=1, metrics=["top_k_accuracy", "mean_class_accuracy"], final_metric="mean_class_accuracy")

optimizer = dict(
    type="AdamW",
    lr=0.001,
    weight_decay=0.0001,
)

optimizer_config = dict(grad_clip=dict(max_norm=40.0, norm_type=2))
lr_config = dict(policy="step", step=5)
total_epochs = 5

# runtime settings
checkpoint_config = dict(interval=1)
log_config = dict(
    interval=10,
    hooks=[
        dict(type="TextLoggerHook", ignore_last=False),
    ],
)
# runtime settings
log_level = "INFO"
workflow = [("train", 1)]

find_unused_parameters = False
gpu_ids = range(0, 1)

dist_params = dict(backend="nccl")
resume_from = None
load_from = (
    "https://download.openmmlab.com/mmaction/recognition/x3d/facebook/"
    "x3d_m_facebook_16x5x1_kinetics400_rgb_20201027-3f42382a.pth"
)