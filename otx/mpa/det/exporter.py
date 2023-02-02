# Copyright (C) 2022 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#

import numpy as np
from mmcv import ConfigDict
from mmcv.runner import wrap_fp16_model

from otx.mpa.exporter_mixin import ExporterMixin
from otx.mpa.registry import STAGES
from otx.mpa.utils.logger import get_logger

from .stage import DetectionStage

logger = get_logger()


@STAGES.register_module()
class DetectionExporter(ExporterMixin, DetectionStage):
    def run(self, model_cfg, model_ckpt, data_cfg, **kwargs):  # noqa: C901
        """Run exporter stage"""

        precision = kwargs.get("precision", "FP32")
        model_builder = kwargs.get("model_builder", self.MODEL_BUILDER)

        def model_builder_helper(*args, **kwargs):
            model = model_builder(*args, **kwargs)

            if precision == "FP16":
                wrap_fp16_model(model)
            elif precision == "INT8":
                from nncf.torch.nncf_network import NNCFNetwork

                assert isinstance(model, NNCFNetwork)

            return model

        # patch test_pipeline in case of missing LoadImageFromOTXDataset
        if self.cfg.data.test.pipeline[0].type != "LoadImageFromOTXDataset":
            self.cfg.data.test.pipeline.insert(0, ConfigDict(dict(type="LoadImageFromOTXDataset")))

        kwargs["model_builder"] = model_builder_helper

        return super().run(model_cfg, model_ckpt, data_cfg, **kwargs)

    @staticmethod
    def naive_export(output_dir, model_builder, precision, cfg, model_name="model"):
        from mmdet.apis.inference import LoadImage
        from mmdet.datasets.pipelines import Compose

        from ..deploy.apis import NaiveExporter
        from ..deploy.utils.mmdet_symbolic import (
            register_extra_symbolics_for_openvino,
            unregister_extra_symbolics_for_openvino,
        )

        def get_fake_data(cfg, orig_img_shape=(128, 128, 3)):
            pipeline = [LoadImage()] + cfg.data.test.pipeline[1:]
            pipeline = Compose(pipeline)
            data = dict(img=np.zeros(orig_img_shape, dtype=np.uint8))
            data = pipeline(data)
            return data

        fake_data = get_fake_data(cfg)
        opset_version = 11
        register_extra_symbolics_for_openvino(opset_version)

        NaiveExporter.export2openvino(
            output_dir,
            model_builder,
            cfg,
            fake_data,
            precision=precision,
            model_name=model_name,
            input_names=["image"],
            output_names=["boxes", "labels"],
            opset_version=opset_version,
        )

        unregister_extra_symbolics_for_openvino(opset_version)