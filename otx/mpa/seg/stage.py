# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

from mmcv import ConfigDict
from mmseg.utils import get_root_logger

from otx.mpa.stage import Stage
from otx.mpa.utils.config_utils import recursively_update_cfg
from otx.mpa.utils.logger import get_logger

logger = get_logger()


class SegStage(Stage):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def configure(self, model_cfg, model_ckpt, data_cfg, training=True, **kwargs):
        """Create MMCV-consumable config from given inputs"""
        logger.info(f"configure!: training={training}")

        cfg = self.cfg
        self.configure_model(cfg, model_cfg, training, **kwargs)
        self.configure_ckpt(cfg, model_ckpt, kwargs.get("pretrained", None))
        self.configure_data(cfg, data_cfg, training)
        self.configure_task(cfg, training, **kwargs)

        return cfg

    def configure_model(self, cfg, model_cfg, training, **kwargs):

        ir_model_path = kwargs.get("ir_model_path")
        if ir_model_path:

            def is_mmov_model(k, v):
                if k == "type" and v.startswith("MMOV"):
                    return True
                return False

            ir_weight_path = kwargs.get("ir_weight_path", None)
            ir_weight_init = kwargs.get("ir_weight_init", False)
            recursively_update_cfg(
                cfg,
                is_mmov_model,
                {"model_path": ir_model_path, "weight_path": ir_weight_path, "init_weight": ir_weight_init},
            )

        if model_cfg:
            if hasattr(model_cfg, "model"):
                cfg.merge_from_dict(model_cfg._cfg_dict)
            else:
                raise ValueError(
                    "Unexpected config was passed through 'model_cfg'. "
                    "it should have 'model' attribute in the config"
                )
            cfg.model_task = cfg.model.pop("task", "segmentation")
            if cfg.model_task != "segmentation":
                raise ValueError(f"Given model_cfg ({model_cfg.filename}) is not supported by segmentation recipe")

    def configure_ckpt(self, cfg, model_ckpt, pretrained=None):
        if model_ckpt:
            cfg.load_from = self.get_model_ckpt(model_ckpt)
        if pretrained and isinstance(pretrained, str):
            logger.info(f"Overriding cfg.load_from -> {pretrained}")
            cfg.load_from = pretrained  # Overriding by stage input

        if cfg.get("resume", False):
            cfg.resume_from = cfg.load_from

    def configure_data(self, cfg, data_cfg, training):
        # Data
        if data_cfg:
            cfg.merge_from_dict(data_cfg)

        if training:
            if cfg.data.get("val", False):
                self.validate = True
        # Dataset
        src_data_cfg = Stage.get_data_cfg(cfg, "train")
        for mode in ["train", "val", "test"]:
            if src_data_cfg.type == "MPASegDataset" and cfg.data.get(mode, False):
                if cfg.data[mode]["type"] != "MPASegDataset":
                    # Wrap original dataset config
                    org_type = cfg.data[mode]["type"]
                    cfg.data[mode]["type"] = "MPASegDataset"
                    cfg.data[mode]["org_type"] = org_type

    def configure_task(self, cfg, training, **kwargs):
        """Adjust settings for task adaptation"""
        self.logger = get_root_logger()
        if cfg.get("task_adapt", None):
            self.logger.info(f"task config!!!!: training={training}")
            task_adapt_op = cfg["task_adapt"].get("op", "REPLACE")

            # Task classes
            self.configure_classes(cfg, task_adapt_op)
            # Ignored mode
            self.configure_ignore(cfg)

    def configure_classes(self, cfg, task_adapt_op):
        # Task classes
        org_model_classes = self.get_model_classes(cfg)
        data_classes = self.get_data_classes(cfg)
        if "background" not in org_model_classes:
            org_model_classes = ["background"] + org_model_classes
        if "background" not in data_classes:
            data_classes = ["background"] + data_classes

        # Model classes
        if task_adapt_op == "REPLACE":
            if len(data_classes) == 1:  # 'background'
                model_classes = org_model_classes.copy()
            else:
                model_classes = data_classes.copy()
        elif task_adapt_op == "MERGE":
            model_classes = org_model_classes + [cls for cls in data_classes if cls not in org_model_classes]
        else:
            raise KeyError(f"{task_adapt_op} is not supported for task_adapt options!")

        cfg.task_adapt.final = model_classes
        cfg.model.task_adapt = ConfigDict(
            src_classes=org_model_classes,
            dst_classes=model_classes,
        )

        # Model architecture
        if "decode_head" in cfg.model:
            decode_head = cfg.model.decode_head
            if isinstance(decode_head, dict):
                decode_head.num_classes = len(model_classes)
            elif isinstance(decode_head, list):
                for head in decode_head:
                    head.num_classes = len(model_classes)

        # Task classes
        self.org_model_classes = org_model_classes
        self.model_classes = model_classes

    def configure_ignore(self, cfg):
        # Change to incremental loss (ignore mode)
        if cfg.get("ignore", False):
            cfg_loss_decode = ConfigDict(
                type="CrossEntropyLossWithIgnore",
                reduction="mean",
                sampler=dict(type="MaxPoolingPixelSampler", ratio=0.25, p=1.7),
                loss_weight=1.0,
            )

            if "decode_head" in cfg.model:
                decode_head = cfg.model.decode_head
                if decode_head.type == "FCNHead":
                    decode_head.type = "CustomFCNHead"
                    decode_head.loss_decode = cfg_loss_decode